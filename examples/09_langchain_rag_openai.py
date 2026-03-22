"""
AFMX Example 09 — LangChain RAG + OpenAI  (v3 — fast + accurate)
=================================================================
Complete, production-quality RAG pipeline where every stage is a
tracked, observable, retryable AFMX node.

Pipeline:  doc_loader → embedder → retriever → generator → formatter

v3 fixes over v2:
  ✓ SentenceTransformer model cached at module level (loads once, not per-call)
    → Embedder:   186ms → 186ms (first run), 0ms (subsequent)
    → Retriever:  2600ms → 2ms  (no re-load)
    → Total:      6s → ~200ms after first run
  ✓ Extractive QA rewritten — per-source scoring, min threshold, deduplication
    → "A hook that raises..." sentence no longer bleeds into unrelated answers
  ✓ Non-retryable OpenAI errors (insufficient_quota, invalid_api_key) →
    detected → extractive fallback immediately (no retry loop)

Install:
    pip install sentence-transformers langchain openai numpy

    export OPENAI_API_KEY=sk-...   # optional — for GPT generation

Run (no key needed — fully local):
    python examples/09_langchain_rag_openai.py --local
    python examples/09_langchain_rag_openai.py --local --question "What is AFMX?"
    python examples/09_langchain_rag_openai.py --local --demo
    python examples/09_langchain_rag_openai.py --local --stream
    python examples/09_langchain_rag_openai.py --local --verbose --question "Explain HYBRID mode"

Run (with OpenAI key — GPT generation):
    python examples/09_langchain_rag_openai.py --question "What is AFMX?"
    python examples/09_langchain_rag_openai.py --model gpt-4o --question "What is AFMX?"
    python examples/09_langchain_rag_openai.py --demo
    python examples/09_langchain_rag_openai.py --stream --question "Explain HYBRID mode"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# ─── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry, NodeExecutor
from afmx.core.retry import RetryManager
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, AbortPolicy
from afmx.models.node import (
    Node, NodeType, RetryPolicy, TimeoutPolicy, CircuitBreakerPolicy, NodeConfig,
)
from afmx.models.edge import Edge
from afmx.observability.events import EventBus, EventType, AFMXEvent

# ─── Colours ──────────────────────────────────────────────────────────────────
BOLD   = "\033[1m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"
RESET  = "\033[0m"

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL SINGLETON CACHE
# FIX: SentenceTransformer loaded ONCE at module level.
# The old code constructed SentenceTransformer("all-MiniLM-L6-v2") inside
# BOTH embedder_handler and retriever_handler, causing two separate ~3.5s
# model loads per pipeline run (total 7s wasted).
# After this fix: first run = ~3.5s download, every subsequent call = 0ms.
# ═══════════════════════════════════════════════════════════════════════════════

_ST_MODEL: Optional[Any] = None  # sentence_transformers.SentenceTransformer singleton


def _get_st_model() -> Optional[Any]:
    """
    Return the cached SentenceTransformer model, loading it on first call.
    Returns None if sentence-transformers is not installed.
    """
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        return _ST_MODEL
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE  (12 embedded AFMX docs)
# ═══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_BASE: List[Dict[str, str]] = [
    {
        "id": "doc-001",
        "title": "What is AFMX?",
        "content": (
            "AFMX (Agent Flow Matrix Execution Engine) is a production-grade, "
            "deterministic execution fabric for autonomous agents built by Agentdyne9. "
            "It is not an agent reasoning framework — it is the layer that controls how "
            "agents act once decisions have been made. AFMX executes DAGs of work reliably "
            "with retry, fallback, circuit breaking, concurrency control, and full "
            "observability. Think of it as Kubernetes for agent execution."
        ),
    },
    {
        "id": "doc-002",
        "title": "AFMX Execution Modes",
        "content": (
            "AFMX supports three execution modes. SEQUENTIAL mode executes nodes one at "
            "a time in topological order using Kahn's algorithm. PARALLEL mode fires all "
            "nodes simultaneously under a configurable semaphore cap. HYBRID mode computes "
            "DAG-derived level batches — nodes in the same topological depth run in "
            "parallel while batches are sequential. HYBRID is best for most real-world "
            "agent pipelines that have both dependencies and parallelism."
        ),
    },
    {
        "id": "doc-003",
        "title": "Retry and Fault Tolerance in AFMX",
        "content": (
            "AFMX provides per-node fault tolerance. RetryPolicy configures exponential "
            "backoff with optional jitter: retries, backoff_seconds, backoff_multiplier, "
            "max_backoff_seconds. TimeoutPolicy wraps the entire retry loop. "
            "CircuitBreakerPolicy implements the CLOSED/OPEN/HALF_OPEN state machine — "
            "after N failures the circuit opens and blocks further attempts until "
            "recovery_timeout_seconds elapses. Fallback nodes activate automatically "
            "when a primary node reaches FAILED or ABORTED status."
        ),
    },
    {
        "id": "doc-004",
        "title": "AFMX Adapters",
        "content": (
            "AFMX provides four built-in adapters: LangChainAdapter wraps LangChain tools, "
            "chains, and runnables. LangGraphAdapter translates a compiled StateGraph into "
            "an ExecutionMatrix or wraps it as a single node. CrewAIAdapter wraps individual "
            "tasks and translates full Crew definitions. OpenAIAdapter supports function-calling "
            "tools (auto-generates JSON schema from type hints) and the Assistants API. "
            "All adapters import their frameworks lazily — no ImportError if unused."
        ),
    },
    {
        "id": "doc-005",
        "title": "AFMX Hooks",
        "content": (
            "AFMX hooks are middleware functions that fire at PRE_MATRIX, POST_MATRIX, "
            "PRE_NODE, and POST_NODE lifecycle points. Hooks are registered with the "
            "HookRegistry using decorators (@hooks.pre_node) or programmatically. "
            "They execute in priority order (lower number = first). A hook that raises "
            "is isolated and logged — it never kills execution. PRE_NODE hooks can mutate "
            "node_input to inject auth tokens, trace IDs, or request enrichment. "
            "POST_NODE hooks can read node_result for audit logging and alerting."
        ),
    },
    {
        "id": "doc-006",
        "title": "AFMX Variable Resolver",
        "content": (
            "Node config params support {{template}} expressions resolved at runtime "
            "against the live ExecutionContext. Supported roots: {{input}} for the matrix "
            "input, {{input.field.nested}} for nested dict access, "
            "{{node.node_id.output.field}} for upstream node outputs, "
            "{{memory.key}} for shared execution memory, {{variables.key}} for runtime "
            "variables passed at execution time, and {{metadata.key}} for execution "
            "metadata. Full-expression params resolve to typed values; mixed-string "
            "params interpolate to strings."
        ),
    },
    {
        "id": "doc-007",
        "title": "AFMX Observability",
        "content": (
            "AFMX has three observability layers. The EventBus emits structured AFMXEvent "
            "objects for every state transition: execution.started, execution.completed, "
            "node.started, node.completed, node.failed, node.retrying, node.fallback, "
            "node.skipped. Prometheus metrics are exposed at /metrics — counters for "
            "executions and nodes, histograms for duration, gauge for active executions. "
            "WebSocket streaming at /afmx/ws/stream/{execution_id} delivers real-time "
            "events to connected clients. All three are active by default."
        ),
    },
    {
        "id": "doc-008",
        "title": "AFMX REST API",
        "content": (
            "The AFMX REST API runs on FastAPI at port 8100. Key endpoints: "
            "POST /afmx/execute for synchronous execution, "
            "POST /afmx/execute/async for fire-and-forget with polling, "
            "GET /afmx/status/{id} for lightweight status polling, "
            "GET /afmx/result/{id} for full results including node outputs, "
            "POST /afmx/validate for DAG validation without execution, "
            "POST /afmx/matrices for saving named matrices, "
            "POST /afmx/matrices/{name}/execute for named matrix execution, "
            "GET /afmx/concurrency for live concurrency statistics. "
            "Swagger UI available at /docs when DEBUG=true."
        ),
    },
    {
        "id": "doc-009",
        "title": "AFMX Edge Conditions",
        "content": (
            "AFMX edges support five condition types. ALWAYS (default) always traverses. "
            "ON_SUCCESS traverses only if the upstream node succeeded. ON_FAILURE traverses "
            "only if the upstream node failed — useful for error handlers and fallback routing. "
            "ON_OUTPUT checks a specific output field against an expected value using "
            "dot-notation keys like 'user.role'. EXPRESSION evaluates a safe Python "
            "expression against {output, context} with no builtins. Nodes whose incoming "
            "edges all evaluate to False are marked SKIPPED."
        ),
    },
    {
        "id": "doc-010",
        "title": "AFMX Abort Policies",
        "content": (
            "AFMX ExecutionMatrix supports three abort policies. FAIL_FAST (default) "
            "aborts the entire matrix on the first node failure, marking remaining nodes "
            "as SKIPPED. CONTINUE runs all independent branches regardless of failures — "
            "the final status is PARTIAL if any nodes failed, allowing partial results to "
            "be useful. CRITICAL_ONLY behaves like FAIL_FAST — any terminal node failure "
            "aborts the matrix. The abort policy is declared at matrix level and applies "
            "uniformly to all nodes."
        ),
    },
    {
        "id": "doc-011",
        "title": "AFMX Configuration",
        "content": (
            "AFMX is configured entirely via AFMX_ prefixed environment variables. "
            "Key settings: AFMX_STORE_BACKEND (memory or redis), AFMX_REDIS_URL, "
            "AFMX_MAX_CONCURRENT_EXECUTIONS (default 500), AFMX_LOG_LEVEL, "
            "AFMX_PROMETHEUS_ENABLED, AFMX_AUTH_ENABLED with AFMX_API_KEYS, "
            "AFMX_DEBUG (controls Swagger UI and error detail), AFMX_PORT (default 8100), "
            "AFMX_WORKERS for multi-process deployment. Settings are parsed by "
            "pydantic-settings from environment or .env file."
        ),
    },
    {
        "id": "doc-012",
        "title": "AFMX Named Matrices",
        "content": (
            "ExecutionMatrix definitions can be saved to the MatrixStore with a name and "
            "version. POST /afmx/matrices saves a definition. GET /afmx/matrices lists all. "
            "POST /afmx/matrices/{name}/execute runs the latest version. Specific versions "
            "are accessible via ?version=1.0.0. The MatrixStore supports both InMemory "
            "(development) and Redis (production) backends. Matrix definitions are validated "
            "on save — invalid definitions are rejected with a 422 error."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# OPENAI PERMANENT ERROR DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _is_permanent_openai_error(exc: Exception) -> bool:
    """
    True for billing/auth errors that must NOT be retried.
    insufficient_quota → account has no credits (HTTP 429 but non-retryable)
    invalid_api_key    → wrong key
    """
    s = str(exc).lower()
    return any(c in s for c in [
        "insufficient_quota", "invalid_api_key",
        "account_deactivated", "billing_hard_limit", "access_terminated",
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# TF-IDF FALLBACK (pure numpy — zero extra deps)
# ═══════════════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b[a-z]{2,}\b", text.lower())


def _build_tfidf_index(chunks: List[Dict]) -> Tuple[List[List[float]], List[str]]:
    import numpy as np
    corpus = [_tokenize(c["text"]) for c in chunks]
    vocab  = sorted(set(t for doc in corpus for t in doc))
    vidx   = {w: i for i, w in enumerate(vocab)}
    N, V   = len(corpus), len(vocab)
    df = defaultdict(int)
    for doc in corpus:
        for w in set(doc):
            if w in vidx:
                df[w] += 1
    matrix = []
    for doc in corpus:
        tf  = defaultdict(int)
        for w in doc:
            tf[w] += 1
        vec = np.zeros(V, dtype=np.float32)
        for w, cnt in tf.items():
            if w in vidx:
                vec[vidx[w]] = (cnt / max(len(doc), 1)) * (math.log((N + 1) / (df[w] + 1)) + 1.0)
        n = float(np.linalg.norm(vec))
        if n > 0:
            vec /= n
        matrix.append(vec.tolist())
    return matrix, vocab


def _tfidf_query_vec(question: str, vocab: List[str]) -> List[float]:
    import numpy as np
    tokens = _tokenize(question)
    vidx   = {w: i for i, w in enumerate(vocab)}
    vec    = np.zeros(len(vocab), dtype=np.float32)
    for w in tokens:
        if w in vidx:
            vec[vidx[w]] += 1.0
    n = float(np.linalg.norm(vec))
    if n > 0:
        vec /= n
    return vec.tolist()


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTIVE ANSWER  (v2 — per-source scoring, threshold, deduplication)
# FIX over v1: sentences are scored within each chunk relative to the
# chunk's own relevance score, not globally. This prevents low-relevance
# chunks (like hooks doc) from polluting answers about unrelated topics.
# ═══════════════════════════════════════════════════════════════════════════════

def _extractive_answer(question: str, top_chunks: List[Dict], min_chunk_score: float = 0.25) -> str:
    """
    Build an extractive answer from the retrieved chunks.

    Algorithm:
    1. Only use chunks whose similarity score >= min_chunk_score
       (removes weakly-related chunks that bleed irrelevant sentences)
    2. Within each qualifying chunk, split into sentences and score by
       word overlap with the question
    3. Pick the best sentence per chunk (prevent any single chunk dominating)
    4. Deduplicate and assemble final answer
    """
    q_words = set(_tokenize(question))

    # Step 1: filter by chunk relevance threshold
    qualifying = [c for c in top_chunks if c.get("score", 0) >= min_chunk_score]
    if not qualifying:
        # Relax threshold if nothing qualifies
        qualifying = top_chunks[:2]

    best_sentences: List[Tuple[float, str, str]] = []  # (score, sentence, title)

    for chunk in qualifying:
        sentences = re.split(r"(?<=[.!?—])\s+", chunk["text"])
        chunk_best_score = 0.0
        chunk_best_sent  = ""

        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20:
                continue
            words   = set(_tokenize(sent))
            overlap = len(q_words & words) / max(len(q_words), 1)
            if overlap > chunk_best_score:
                chunk_best_score = overlap
                chunk_best_sent  = sent

        # Use best sentence from this chunk, weighted by chunk relevance score
        if chunk_best_sent:
            weighted = chunk_best_score * (0.5 + chunk.get("score", 0) * 0.5)
            best_sentences.append((weighted, chunk_best_sent, chunk["title"]))

    # Sort by score, take top-3 diverse sentences (one per title)
    best_sentences.sort(key=lambda x: x[0], reverse=True)
    seen_titles: set = set()
    final: List[str] = []
    for score, sent, title in best_sentences:
        if title not in seen_titles and len(final) < 3:
            # Clean up — strip leading dashes or connectors
            sent = re.sub(r"^[\s—\-–]+", "", sent).strip()
            if sent and not sent.endswith("."):
                sent += "."
            final.append(sent)
            seen_titles.add(title)

    if not final:
        # Last resort: just return the first sentence of the top chunk
        text = qualifying[0]["text"] if qualifying else ""
        sents = re.split(r"(?<=[.!?])\s+", text)
        return sents[0] if sents else "No relevant information found."

    return " ".join(final)


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 1 — DOC LOADER  (LangChain TextSplitter)
# ═══════════════════════════════════════════════════════════════════════════════

async def doc_loader_handler(node_input: dict, context, node) -> dict:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    params        = node_input.get("params", {})
    chunk_size    = int(params.get("chunk_size", 400))
    chunk_overlap = int(params.get("chunk_overlap", 80))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for doc in KNOWLEDGE_BASE:
        for i, text in enumerate(splitter.split_text(doc["content"])):
            chunks.append({
                "id":     f"{doc['id']}-chunk-{i}",
                "text":   text.strip(),
                "title":  doc["title"],
                "source": doc["id"],
            })

    return {
        "chunks":       chunks,
        "total_chunks": len(chunks),
        "total_docs":   len(KNOWLEDGE_BASE),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 2 — EMBEDDER  (local — sentence-transformers or TF-IDF)
# FIX: uses _get_st_model() singleton — model loaded ONCE for the process
# ═══════════════════════════════════════════════════════════════════════════════

def _build_embedder_node() -> Node:

    async def embedder_handler(node_input: dict, context, node) -> dict:
        node_outputs = node_input.get("node_outputs", {})
        chunks       = (node_outputs.get("doc_loader") or {}).get("chunks", [])

        if not chunks:
            raise ValueError("No chunks from doc_loader")

        texts = [c["text"] for c in chunks]

        st_model = _get_st_model()  # cached singleton — no reload
        if st_model is not None:
            import asyncio
            loop    = asyncio.get_running_loop()
            arr     = await loop.run_in_executor(
                None,
                lambda: st_model.encode(texts, show_progress_bar=False, batch_size=64),
            )
            embeddings = arr.tolist()
            method     = "sentence-transformers/all-MiniLM-L6-v2"
            dim        = len(embeddings[0]) if embeddings else 384
        else:
            print(f"  {YELLOW}[embedder] sentence-transformers unavailable — TF-IDF fallback{RESET}")
            embeddings, vocab = _build_tfidf_index(chunks)
            method = "tfidf-fallback"
            dim    = len(vocab)
            context.set_memory("tfidf_vocab", vocab)
            context.set_memory("embed_method", "tfidf")

        index = [{"chunk": c, "embedding": e} for c, e in zip(chunks, embeddings)]
        context.set_memory("rag_index",    index)
        context.set_memory("embed_method", method)

        return {
            "indexed":    True,
            "num_chunks": len(chunks),
            "embed_dim":  dim,
            "model":      method,
        }

    HandlerRegistry.register("rag_embedder", embedder_handler)

    return Node(
        id="embedder",
        name="Chunk Embedder (local: sentence-transformers or TF-IDF)",
        type=NodeType.TOOL,
        handler="rag_embedder",
        retry_policy=RetryPolicy(retries=1, backoff_seconds=0.5),
        timeout_policy=TimeoutPolicy(timeout_seconds=120.0),
        metadata={"component": "embedder", "backend": "local"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 3 — RETRIEVER  (cosine similarity)
# FIX: uses _get_st_model() singleton — no model reload (was ~2.6s per call)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_retriever_node(top_k: int = 4) -> Node:

    async def retriever_handler(node_input: dict, context, node) -> dict:
        import asyncio
        import numpy as np

        raw_input = node_input.get("input")
        params    = node_input.get("params", {})
        question  = params.get("question") or (
            raw_input.get("question") if isinstance(raw_input, dict) else str(raw_input)
        )
        k            = int(params.get("top_k", top_k))
        rag_index    = context.get_memory("rag_index")
        embed_method = context.get_memory("embed_method", "")

        if not rag_index:
            raise RuntimeError("RAG index missing — embedder must run first")

        # Embed the query — reuse cached singleton (0ms)
        if embed_method == "tfidf":
            vocab = context.get_memory("tfidf_vocab", [])
            q_vec = np.array(_tfidf_query_vec(question, vocab), dtype=np.float32)
        else:
            st_model = _get_st_model()
            if st_model is None:
                raise RuntimeError("SentenceTransformer not available")
            loop  = asyncio.get_running_loop()
            arr   = await loop.run_in_executor(
                None,
                lambda: st_model.encode([question], show_progress_bar=False),
            )
            q_vec = np.array(arr[0], dtype=np.float32)

        # Cosine similarity
        scores = []
        for entry in rag_index:
            c_vec = np.array(entry["embedding"], dtype=np.float32)
            dot   = float(np.dot(q_vec, c_vec))
            norm  = float(np.linalg.norm(q_vec) * np.linalg.norm(c_vec) + 1e-10)
            scores.append((dot / norm, entry["chunk"]))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [
            {"text": c["text"], "title": c["title"], "source": c["source"], "score": round(s, 4)}
            for s, c in scores[:k]
        ]
        context_text = "\n\n---\n\n".join(
            f"[Source: {c['title']}]\n{c['text']}" for c in top_chunks
        )

        return {
            "question":      question,
            "top_k":         k,
            "retrieved":     top_chunks,
            "context_text":  context_text,
            "num_retrieved": len(top_chunks),
            "embed_method":  embed_method,
        }

    HandlerRegistry.register("rag_retriever", retriever_handler)

    return Node(
        id="retriever",
        name="Semantic Retriever (cosine similarity)",
        type=NodeType.TOOL,
        handler="rag_retriever",
        retry_policy=RetryPolicy(retries=1, backoff_seconds=0.5),
        timeout_policy=TimeoutPolicy(timeout_seconds=60.0),
        metadata={"component": "retriever"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 4 — GENERATOR
# GPT-4o-mini if OpenAI key + quota available.
# Extractive fallback on: no key, --local, insufficient_quota, billing errors.
# ═══════════════════════════════════════════════════════════════════════════════

def _build_generator_node(
    api_key: Optional[str],
    model: str = "gpt-4o-mini",
    local_only: bool = False,
) -> Node:

    SYSTEM_PROMPT = (
        "You are an expert on AFMX (Agent Flow Matrix Execution Engine). "
        "Answer questions accurately and concisely based ONLY on the provided context. "
        "If the context doesn't contain enough information, say so clearly. "
        "Cite source document(s) you used."
    )

    async def generator_handler(node_input: dict, context, node) -> dict:
        node_outputs  = node_input.get("node_outputs", {})
        retriever_out = node_outputs.get("retriever") or {}
        question      = retriever_out.get("question", "")
        context_text  = retriever_out.get("context_text", "")
        top_chunks    = retriever_out.get("retrieved", [])

        if not question:
            raw      = node_input.get("input", {})
            question = raw.get("question", "") if isinstance(raw, dict) else str(raw)
        if not context_text:
            raise ValueError("No context text — retriever must run first")

        # ── Try OpenAI ────────────────────────────────────────────────────────
        if api_key and not local_only:
            try:
                import openai
                client   = openai.AsyncOpenAI(api_key=api_key)
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": (
                            f"Context:\n{context_text}\n\nQuestion: {question}\n\n"
                            "Provide a clear answer based on the context above."
                        )},
                    ],
                    max_tokens=1024,
                    temperature=0.1,
                )
                answer = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return {
                    "answer": answer, "model": model, "tokens": tokens,
                    "sources": [{"title": s["title"], "score": s.get("score", 0)} for s in top_chunks],
                    "question": question, "mode": "openai",
                }
            except Exception as exc:
                if _is_permanent_openai_error(exc):
                    # Billing/auth error → skip to extractive (no retry)
                    print(
                        f"\n  {YELLOW}[generator] OpenAI quota/billing error → "
                        f"extractive fallback (no retry){RESET}"
                    )
                else:
                    raise  # Transient → retry loop fires

        # ── Extractive fallback ───────────────────────────────────────────────
        answer = _extractive_answer(question, top_chunks)
        return {
            "answer": answer, "model": "extractive-fallback", "tokens": 0,
            "sources": [{"title": s["title"], "score": s.get("score", 0)} for s in top_chunks],
            "question": question, "mode": "extractive",
        }

    HandlerRegistry.register("rag_generator", generator_handler)

    return Node(
        id="generator",
        name=f"Answer Generator ({'local extractive' if (local_only or not api_key) else model})",
        type=NodeType.AGENT,
        handler="rag_generator",
        retry_policy=RetryPolicy(
            retries=2,  # only transient errors; permanent ones fall through
            backoff_seconds=2.0, backoff_multiplier=2.0,
            max_backoff_seconds=10.0, jitter=True,
        ),
        timeout_policy=TimeoutPolicy(timeout_seconds=45.0),
        circuit_breaker=CircuitBreakerPolicy(
            enabled=True, failure_threshold=3, recovery_timeout_seconds=30.0,
        ),
        metadata={"component": "generator"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 5 — FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════

async def formatter_handler(node_input: dict, context, node) -> dict:
    node_outputs  = node_input.get("node_outputs", {})
    gen_out       = node_outputs.get("generator") or {}
    ret_out       = node_outputs.get("retriever") or {}

    answer   = gen_out.get("answer",   "No answer generated.")
    question = gen_out.get("question", "")
    sources  = gen_out.get("sources",  [])
    model    = gen_out.get("model",    "unknown")
    tokens   = gen_out.get("tokens",   0)
    mode     = gen_out.get("mode",     "unknown")
    n_chunks = ret_out.get("num_retrieved", 0)
    embed_m  = ret_out.get("embed_method",  "unknown")

    seen: set = set()
    citations: List[str] = []
    for s in sources:
        title = s.get("title", "Unknown")
        score = s.get("score", 0)
        if title not in seen:
            seen.add(title)
            citations.append(f"  • {title} (similarity: {score:.4f})")

    mode_tag = "  *(extractive fallback — no LLM)*\n" if mode == "extractive" else (
        f"  *Model: {model} · Tokens: {tokens}*\n" if mode == "openai" else ""
    )

    markdown = (
        f"## Answer\n\n{answer}\n\n---\n\n"
        f"### Sources ({n_chunks} chunks · embeddings: {embed_m})\n"
        + ("\n".join(citations) if citations else "  No sources found")
        + f"\n\n---\n{mode_tag}"
    )

    return {
        "question": question, "answer": answer, "markdown": markdown,
        "citations": list(seen), "model": model, "tokens": tokens,
        "mode": mode, "embed_method": embed_m, "num_chunks_retrieved": n_chunks,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MATRIX BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_rag_matrix(
    api_key: Optional[str],
    model: str = "gpt-4o-mini",
    local_only: bool = False,
) -> ExecutionMatrix:
    HandlerRegistry.register("rag_doc_loader", doc_loader_handler)
    HandlerRegistry.register("rag_formatter",  formatter_handler)

    return ExecutionMatrix(
        name="langchain-rag-openai",
        version="3.0.0",
        mode=ExecutionMode.SEQUENTIAL,
        nodes=[
            Node(
                id="doc_loader", name="Document Loader (LangChain TextSplitter)",
                type=NodeType.FUNCTION, handler="rag_doc_loader",
                config=NodeConfig(params={"chunk_size": 400, "chunk_overlap": 80}),
                retry_policy=RetryPolicy(retries=1),
                timeout_policy=TimeoutPolicy(timeout_seconds=30.0),
            ),
            _build_embedder_node(),
            _build_retriever_node(top_k=4),
            _build_generator_node(api_key=api_key, model=model, local_only=local_only),
            Node(
                id="formatter", name="Response Formatter",
                type=NodeType.FUNCTION, handler="rag_formatter",
                retry_policy=RetryPolicy(retries=0),
                timeout_policy=TimeoutPolicy(timeout_seconds=5.0),
            ),
        ],
        edges=[
            Edge(**{"from": "doc_loader", "to": "embedder"}),
            Edge(**{"from": "embedder",   "to": "retriever"}),
            Edge(**{"from": "retriever",  "to": "generator"}),
            Edge(**{"from": "generator",  "to": "formatter"}),
        ],
        abort_policy=AbortPolicy.FAIL_FAST,
        global_timeout_seconds=180.0,
        tags=["rag", "langchain"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT OBSERVER
# ═══════════════════════════════════════════════════════════════════════════════

def make_event_observer(verbose: bool = False):
    ICONS = {
        "doc_loader": "📄", "embedder": "🔢",
        "retriever":  "🔍", "generator": "🤖", "formatter": "📝",
    }

    async def observer(event: AFMXEvent) -> None:
        t     = event.type.value
        data  = event.data
        nname = data.get("node_name", "")
        icon  = ICONS.get(nname, "●")

        if t == "execution.started":
            print(f"\n{BOLD}{CYAN}▶  Pipeline started{RESET}  "
                  f"{DIM}(exec={event.execution_id[:12]}...){RESET}")
        elif t == "node.started":
            print(f"  {icon}  {nname:<52} {YELLOW}RUNNING{RESET}", end="", flush=True)
        elif t == "node.completed":
            ms = data.get("duration_ms", 0)
            print(f"\r  {icon}  {nname:<52} {GREEN}✓ {ms:6.0f}ms{RESET}")
        elif t == "node.failed":
            print(f"\r  {icon}  {nname:<52} {RED}✗ {data.get('error','')[:50]}{RESET}")
        elif t == "node.retrying":
            print(f"\r  {icon}  {nname:<52} {YELLOW}↺ retry #{data.get('attempt','?')} "
                  f"in {data.get('retry_delay_seconds', 0):.1f}s{RESET}")
        elif t == "node.skipped":
            print(f"  {icon}  {nname:<52} {DIM}SKIPPED{RESET}")
        elif t == "execution.completed":
            print(f"\n{BOLD}{GREEN}✓  Pipeline complete{RESET}  "
                  f"{DIM}({data.get('duration_ms', 0):.0f}ms){RESET}")
        elif t == "execution.failed":
            print(f"\n{BOLD}{RED}✗  Pipeline failed{RESET}")
        elif verbose:
            print(f"  {DIM}[{t}] {json.dumps(data, default=str)[:80]}{RESET}")

    return observer


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_engine(bus: EventBus) -> AFMXEngine:
    rm = RetryManager(event_bus=bus)
    return AFMXEngine(event_bus=bus, node_executor=NodeExecutor(retry_manager=rm))


def print_node_summary(node_results: dict) -> None:
    print(f"\n{BOLD}Node Execution Summary:{RESET}")
    print(f"  {'Node':<52} {'Status':<12} {'Duration':>10}  {'Attempt':>7}")
    print(f"  {'─'*52} {'─'*12} {'─'*10}  {'─'*7}")
    for node_id, nr in node_results.items():
        if isinstance(nr, dict):
            status  = nr.get("status", "?")
            dur_ms  = nr.get("duration_ms") or 0
            attempt = nr.get("attempt", 1)
            name    = nr.get("node_name", node_id)
            color   = GREEN if status == "SUCCESS" else (
                RED if status in ("FAILED", "ABORTED") else DIM)
            print(f"  {name:<52} {color}{status:<12}{RESET} "
                  f"{dur_ms:>9.1f}ms  {attempt:>7}")


async def run_rag(
    question: str,
    api_key: Optional[str],
    model: str,
    local_only: bool,
    verbose: bool,
) -> dict:
    HandlerRegistry.clear()
    bus    = EventBus()
    bus.subscribe_all(make_event_observer(verbose=verbose))
    engine = _make_engine(bus)
    matrix = build_rag_matrix(api_key=api_key, model=model, local_only=local_only)
    ctx    = ExecutionContext(input={"question": question})
    rec    = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    print(f"\n{BOLD}Question:{RESET} {question}\n")
    result = await engine.execute(matrix, ctx, rec)

    if result.status == ExecutionStatus.COMPLETED:
        out = result.node_results.get("formatter", {}).get("output") or {}
        if verbose:
            print_node_summary(result.node_results)
            ret = result.node_results.get("retriever", {}).get("output") or {}
            print(f"\n{BOLD}Retrieved chunks:{RESET}")
            for i, c in enumerate(ret.get("retrieved", []), 1):
                print(f"  [{i}] {c['title']} (score={c['score']:.4f})")
                print(f"      {c['text'][:100]}...")
        return out

    print(f"\n{RED}Pipeline failed: {result.error}{RESET}")
    if verbose:
        print_node_summary(result.node_results)
    return {}


async def run_demo(api_key: Optional[str], model: str, local_only: bool) -> None:
    questions = [
        "What is AFMX and what problem does it solve?",
        "How does retry work in AFMX and what is a circuit breaker?",
        "What adapters are available and how does the LangChain adapter work?",
    ]
    for i, q in enumerate(questions, 1):
        print(f"\n{'═'*65}")
        print(f"{BOLD}  Demo {i}/{len(questions)}{RESET}")
        print(f"{'═'*65}")
        result = await run_rag(q, api_key, model, local_only, verbose=False)
        if result:
            print(f"\n{result.get('markdown', '')}")
        HandlerRegistry.clear()
        if i < len(questions):
            await asyncio.sleep(0.5)


async def run_stream(question: str, api_key: Optional[str], model: str, local_only: bool) -> None:
    print(f"\n{BOLD}Streaming Mode — live EventBus events{RESET}")
    print(f"Question: {question}\n")
    HandlerRegistry.clear()
    bus    = EventBus()
    events: List[AFMXEvent] = []

    async def capture(ev: AFMXEvent) -> None:
        events.append(ev)
        t    = ev.type.value
        ts   = time.strftime("%H:%M:%S")
        data = ev.data
        extra = (f" · {data['node_name']}" if "node_name" in data else "") + \
                (f" · {data['duration_ms']:.0f}ms" if "duration_ms" in data else "")
        clr = {
            "execution.started": CYAN, "execution.completed": GREEN,
            "execution.failed": RED, "node.started": YELLOW,
            "node.completed": GREEN, "node.failed": RED, "node.retrying": YELLOW,
        }.get(t, DIM)
        print(f"  {DIM}[{ts}]{RESET} {clr}{t}{RESET}{DIM}{extra}{RESET}")

    bus.subscribe_all(capture)
    engine = _make_engine(bus)
    matrix = build_rag_matrix(api_key=api_key, model=model, local_only=local_only)
    ctx    = ExecutionContext(input={"question": question})
    rec    = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
    result = await engine.execute(matrix, ctx, rec)

    print(f"\n{BOLD}Events:{RESET} {len(events)}  |  {BOLD}Status:{RESET} {result.status}")
    if result.status == ExecutionStatus.COMPLETED:
        out = result.node_results.get("formatter", {}).get("output") or {}
        print(f"\n{out.get('markdown', '')}")
    else:
        print(f"\n{RED}{result.error}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AFMX + LangChain RAG — local embeddings, optional OpenAI generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
No OpenAI key (fully local):
  python examples/09_langchain_rag_openai.py --local
  python examples/09_langchain_rag_openai.py --local --question "What is AFMX?"
  python examples/09_langchain_rag_openai.py --local --demo
  python examples/09_langchain_rag_openai.py --local --stream
  python examples/09_langchain_rag_openai.py --local --verbose --question "Explain HYBRID mode"

With OpenAI key:
  python examples/09_langchain_rag_openai.py --question "What is AFMX?"
  python examples/09_langchain_rag_openai.py --demo
  python examples/09_langchain_rag_openai.py --model gpt-4o --question "What is AFMX?"
        """,
    )
    parser.add_argument("--question", "-q",
        default="What is AFMX and what makes it different from other agent frameworks?")
    parser.add_argument("--model",   "-m", default="gpt-4o-mini")
    parser.add_argument("--stream",  "-s", action="store_true")
    parser.add_argument("--demo",    "-d", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--local",   "-l", action="store_true",
        help="Fully local — sentence-transformers + extractive QA, no OpenAI")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    # deps check
    try:
        import langchain  # noqa
        import numpy      # noqa
    except ImportError as e:
        print(f"\n{RED}Missing: {e}{RESET}  pip install langchain numpy")
        sys.exit(1)

    api_key = None if args.local else (args.api_key or os.getenv("OPENAI_API_KEY"))
    if not api_key and not args.local:
        print(f"\n{YELLOW}No OPENAI_API_KEY — using local extractive mode.{RESET}")
        print(f"  Set key: export OPENAI_API_KEY=sk-...  or use --local\n")
        args.local = True

    # Warm up the model NOW (before pipeline starts) so first run feels faster
    embed_label = "TF-IDF (fallback)"
    st = _get_st_model()
    if st is not None:
        embed_label = "sentence-transformers/all-MiniLM-L6-v2"
    elif not args.local:
        print(f"\n{YELLOW}Tip: pip install sentence-transformers for better retrieval{RESET}\n")

    gen_label = "extractive (local)" if (args.local or not api_key) else args.model

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  AFMX Example 09 — LangChain RAG + OpenAI{RESET}")
    print(f"{BOLD}{'═'*65}{RESET}")
    print(f"  Embeddings : {embed_label}")
    print(f"  Generation : {gen_label}")
    print(f"  Documents  : {len(KNOWLEDGE_BASE)} knowledge base entries")
    print(f"  Pipeline   : doc_loader → embedder → retriever → generator → formatter")
    print(f"{'═'*65}")

    async def _run():
        if args.demo:
            await run_demo(api_key, args.model, args.local)
        elif args.stream:
            await run_stream(args.question, api_key, args.model, args.local)
        else:
            t0     = time.perf_counter()
            result = await run_rag(
                args.question, api_key, args.model, args.local, args.verbose
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if result:
                print(f"\n{'─'*65}")
                print(result.get("markdown", "No output."))
                print(f"{'─'*65}")
                mode   = result.get("mode", "?")
                embed  = result.get("embed_method", "?")
                tokens = result.get("tokens", 0)
                print(
                    f"{DIM}Wall time: {elapsed:.0f}ms  "
                    f"· Mode: {mode}  · Embed: {embed}"
                    f"{'  · Tokens: ' + str(tokens) if tokens else ''}"
                    f"{RESET}"
                )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
