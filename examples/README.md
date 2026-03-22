# AFMX Examples

Runnable examples demonstrating every major AFMX feature.

## Prerequisites

```bash
cd /home/opc/afmx
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run any example directly

```bash
python examples/01_sequential_flow.py
python examples/02_parallel_fanout.py
python examples/03_conditional_routing.py
python examples/04_retry_fallback.py
python examples/05_variable_resolver.py
python examples/06_hooks_and_plugins.py
python examples/07_multi_agent.py
python examples/08_adapters.py

# RAG example requires OpenAI API key
export OPENAI_API_KEY=sk-...
pip install langchain langchain-openai numpy tiktoken
python examples/09_langchain_rag_openai.py
python examples/09_langchain_rag_openai.py --question "What is AFMX?"
python examples/09_langchain_rag_openai.py --demo
python examples/09_langchain_rag_openai.py --stream
```

## Examples Overview

| File | Demonstrates |
|------|-------------|
| `01_sequential_flow.py` | Basic 3-node pipeline, context passing between nodes |
| `02_parallel_fanout.py` | Fan-out to 3 parallel sources, fan-in aggregator (HYBRID mode) |
| `03_conditional_routing.py` | Classifier node + ON_OUTPUT / EXPRESSION edge conditions |
| `04_retry_fallback.py` | Flaky node with exponential backoff; terminal failure → fallback |
| `05_variable_resolver.py` | `{{input.field}}` `{{node.id.output.x}}` `{{variables.k}}` |
| `06_hooks_and_plugins.py` | `@registry.tool` decorators + PRE_NODE / POST_NODE hooks |
| `07_multi_agent.py` | Coordinator → specialist agents, complexity-based dispatch |
| `08_adapters.py` | LangChain, LangGraph, CrewAI adapters (mock objects — no install needed) |
| `09_langchain_rag_openai.py` | **Full RAG pipeline: LangChain + OpenAI + AFMX** (see below) |
| `09b_rag_via_api.py` | Same RAG pipeline executed via the AFMX REST API + WebSocket stream |

---

## Example 09 — LangChain RAG + OpenAI (Featured)

A complete, production-quality Retrieval-Augmented Generation pipeline where
every stage is a tracked, observable, retryable AFMX node.

### Pipeline

```
[user question]
      │
      ▼
[1. doc_loader]     — Split 12 AFMX knowledge docs into chunks
      │               (LangChain RecursiveCharacterTextSplitter)
      ▼
[2. embedder]       — Embed all chunks via OpenAI text-embedding-3-small
      │               (custom handler using langchain-openai)
      ▼
[3. retriever]      — Cosine similarity search → top-4 most relevant chunks
      │               (numpy, reads from context.memory["rag_index"])
      ▼
[4. generator]      — GPT-4o-mini answers the question with context
      │               (direct openai call, 3 retries + circuit breaker)
      ▼
[5. formatter]      — Markdown response with citations and source titles
```

### Install

```bash
pip install langchain langchain-openai openai numpy tiktoken
export OPENAI_API_KEY=sk-...
```

### Run

```bash
# Default question
python examples/09_langchain_rag_openai.py

# Custom question
python examples/09_langchain_rag_openai.py --question "What is AFMX?"
python examples/09_langchain_rag_openai.py --question "How does retry work in AFMX?"
python examples/09_langchain_rag_openai.py --question "What adapters are available?"
python examples/09_langchain_rag_openai.py --question "Explain HYBRID execution mode"

# With verbose node output
python examples/09_langchain_rag_openai.py --question "What is AFMX?" --verbose

# With live EventBus streaming
python examples/09_langchain_rag_openai.py --question "What is AFMX?" --stream

# Run 3 demo questions automatically
python examples/09_langchain_rag_openai.py --demo

# Use GPT-4o for higher quality answers
python examples/09_langchain_rag_openai.py --question "..." --model gpt-4o
```

### AFMX Features Demonstrated

| Feature | Where |
|---|---|
| `SEQUENTIAL` mode | Matrix with 5 chained nodes |
| Data flow via `context.node_outputs` | Each node reads upstream output via `node_input["node_outputs"]` |
| `context.memory` for vector index | Embedder stores index, retriever reads it |
| `RetryPolicy` (3 retries + backoff) | embedder, retriever, generator nodes |
| `CircuitBreakerPolicy` | generator node (trips after 5 failures) |
| `TimeoutPolicy` | Per-node: 60s embedder, 45s generator |
| `LangChainAdapter` pattern | Embedder uses `langchain_openai.OpenAIEmbeddings` |
| `OpenAI` direct API | Generator uses `openai.AsyncOpenAI` |
| `EventBus` live events | All events printed with icons and timing |
| `HandlerRegistry.register` | All 5 handlers registered at runtime |
| `AbortPolicy.FAIL_FAST` | Any stage failure stops the pipeline |

### Sample Output

```
════════════════════════════════════════════════════════════════
  AFMX Example 09 — LangChain RAG + OpenAI
════════════════════════════════════════════════════════════════
  Model      : gpt-4o-mini
  Documents  : 12 knowledge base entries
  Pipeline   : doc_loader → embedder → retriever → generator → formatter

Question: What is AFMX and what makes it different?

▶  Pipeline started  (exec=7f3a1b2c9d4e...)
  📄  Document Loader (LangChain TextSplitter)       ✓      4ms
  🔢  Chunk Embedder (OpenAI text-embedding-3-small) ✓   1243ms
  🔍  Cosine Retriever                               ✓    412ms
  🤖  GPT-4o-mini Answer Generator                  ✓   2103ms
  📝  Response Formatter                             ✓      1ms

✓  Pipeline complete  (3763ms)

─────────────────────────────────────────────────────────────────
## Answer

AFMX (Agent Flow Matrix Execution Engine) is a production-grade,
deterministic execution fabric for autonomous agents...

### Sources (4 chunks retrieved)
  • What is AFMX? (similarity: 0.8912)
  • AFMX Adapters (similarity: 0.7234)
  • AFMX Execution Modes (similarity: 0.6891)

*Model: gpt-4o-mini · Tokens used: 412*
─────────────────────────────────────────────────────────────────
```

### Via REST API (Example 09b)

`09b_rag_via_api.py` executes the same pipeline through the running AFMX server:

```bash
# Start the server
python3.10 -m afmx serve --reload

# Execute via REST API
python examples/09b_rag_via_api.py --question "What is AFMX?"

# Execute via REST API + WebSocket streaming
python examples/09b_rag_via_api.py --question "How does retry work?" --stream
```

---

## Handler Signature (all examples)

```python
async def my_handler(node_input: dict, context: ExecutionContext, node: Node) -> Any:
    raw_input    = node_input["input"]           # matrix-level input payload
    params       = node_input["params"]          # resolved node config params
    node_outputs = node_input["node_outputs"]    # upstream outputs by node_id
    memory       = node_input["memory"]          # shared execution memory snapshot
    variables    = node_input["variables"]       # runtime variables
    metadata     = node_input["metadata"]        # merged execution + node metadata
    return {"result": "..."}                     # any JSON-serializable value
```

## matrix.json Reference

```json
{
  "name": "my-flow",
  "mode": "SEQUENTIAL",
  "nodes": [
    {
      "id": "n1",
      "name": "step_one",
      "type": "FUNCTION",
      "handler": "my_module.my_handler",
      "config": {"params": {"key": "{{input.value}}"}},
      "retry_policy": {"retries": 3, "backoff_seconds": 1.0, "jitter": true},
      "timeout_policy": {"timeout_seconds": 30.0},
      "circuit_breaker": {"enabled": true, "failure_threshold": 5},
      "fallback_node_id": "n1_fallback"
    }
  ],
  "edges": [
    {"from": "n1", "to": "n2"},
    {"from": "n1", "to": "n1_fallback", "condition": {"type": "ON_FAILURE"}}
  ],
  "abort_policy": "FAIL_FAST",
  "global_timeout_seconds": 120.0
}
```
