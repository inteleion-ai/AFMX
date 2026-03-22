"""
AFMX Realistic Agent Handlers
==============================
Drop-in replacement for the stub handlers in startup_handlers.py.
These produce rich outputs that make BOTH dashboards interesting:
  - Real confidence scores (0.0–1.0) that drift under load
  - Reasoning chains (shown in Agentability → Decisions)
  - Token usage + cost estimates (shown in Agentability → Cost)
  - Constraint checking (shown as violations in Agentability)
  - Realistic latency variation

Install:
    Copy this file to your project root, then in startup_handlers.py
    add at the bottom:
        from realistic_handlers import register_realistic
        register_realistic()

OR run it standalone to verify:
    python realistic_handlers.py
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from afmx.core.executor import HandlerRegistry
from afmx.plugins.registry import default_registry

# ─── Simulated LLM call ───────────────────────────────────────────────────────

async def _llm_call(
    prompt: str,
    model: str = "gpt-4o",
    temperature: float = 0.3,
) -> dict:
    """
    Simulates a real LLM call with realistic token counts and latency.
    In production, replace this with your actual LLM SDK call.
    """
    # Realistic latency: 150–600ms for GPT-4o
    await asyncio.sleep(random.uniform(0.15, 0.60))

    prompt_tokens     = len(prompt.split()) * 1.3  # rough token estimate
    completion_tokens = random.randint(80, 320)
    total_tokens      = int(prompt_tokens + completion_tokens)

    # GPT-4o pricing (as of March 2026): $5/$15 per 1M tokens
    cost_usd = (prompt_tokens * 5 + completion_tokens * 15) / 1_000_000

    return {
        "model":             model,
        "prompt_tokens":     int(prompt_tokens),
        "completion_tokens": completion_tokens,
        "total_tokens":      total_tokens,
        "cost_usd":          round(cost_usd, 8),
    }


# ─── Realistic Analyst Agent ──────────────────────────────────────────────────

async def realistic_analyst(node_input: dict, context, node) -> dict:
    """
    Realistic analyst agent with confidence scoring, reasoning chain,
    and simulated LLM token usage captured for Agentability.
    """
    inp      = node_input.get("input", {})
    query    = inp.get("topic") or inp.get("query") or inp.get("task") or str(inp)
    depth    = node_input.get("variables", {}).get("review_depth", "standard")

    prompt   = f"Analyse the following and provide insights:\n\n{query}\n\nDepth: {depth}"
    llm_meta = await _llm_call(prompt, model="gpt-4o", temperature=0.2)

    # Confidence varies with topic complexity (simple heuristic)
    base_conf = 0.88
    word_count = len(query.split())
    if word_count > 20: base_conf -= 0.06
    if "risk" in query.lower() or "uncertain" in query.lower(): base_conf -= 0.08
    confidence = max(0.52, min(0.97, base_conf + random.gauss(0, 0.04)))

    result = {
        "analysis":         f"Comprehensive analysis of: {query[:60]}{'…' if len(query)>60 else ''}",
        "confidence":       round(confidence, 3),
        "key_findings":     [
            f"Finding 1: Primary factor identified in '{query[:30]}…'",
            "Finding 2: Risk level classified as medium-high",
            "Finding 3: Recommend iterative validation approach",
        ],
        "recommendations":  ["immediate_action", "monitor_kpis", "schedule_review"],
        "entities_detected": random.randint(3, 12),
        "sentiment":        random.choice(["positive", "neutral", "cautious"]),
        "agent":            "analyst",
        # Agentability hook picks these up from node metadata / context
        "_llm_meta":        llm_meta,
        "_reasoning":       [
            f"Step 1: Parsed input — detected {len(query.split())} tokens",
            f"Step 2: Applied {depth} analysis depth",
            f"Step 3: Cross-referenced knowledge base",
            f"Step 4: Confidence calibrated to {confidence:.2f} based on topic clarity",
        ],
        "_constraints_checked": ["input_not_empty", "depth_valid", "model_available"],
    }

    # Simulate a constraint violation for high-risk topics
    if "autonomous" in query.lower() and "oversight" not in query.lower():
        result["_constraints_violated"] = ["human_oversight_required"]

    context.set_memory(f"analyst_confidence_{node.id}", confidence)
    return result


# ─── Realistic Writer Agent ───────────────────────────────────────────────────

async def realistic_writer(node_input: dict, context, node) -> dict:
    """
    Realistic writer agent — reads upstream analyst output,
    produces structured content with word count and quality score.
    """
    upstream = node_input.get("node_outputs", {})
    analysis = next(
        (v for v in upstream.values() if isinstance(v, dict) and "analysis" in v),
        None,
    ) or {}

    topic    = analysis.get("analysis", str(node_input.get("input", "")))
    findings = analysis.get("key_findings", [])
    prompt   = f"Write a professional report based on:\n{topic}\nFindings: {findings}"
    llm_meta = await _llm_call(prompt, model="gpt-4o", temperature=0.7)

    # Writer confidence typically lower than analyst — more subjective
    confidence = max(0.60, min(0.92, 0.80 + random.gauss(0, 0.05)))

    sections = ["Executive Summary", "Key Findings", "Risk Assessment", "Recommendations"]
    if analysis.get("sentiment") == "cautious":
        sections.append("Risk Mitigation Plan")

    return {
        "content":   f"## Report: {topic[:50]}{'…' if len(topic)>50 else ''}\n\n"
                     f"Based on {len(findings)} key findings from the analyst review.",
        "sections":  sections,
        "word_count":  random.randint(320, 1200),
        "quality_score": confidence,
        "confidence": round(confidence, 3),
        "agent":     "writer",
        "_llm_meta": llm_meta,
        "_reasoning": [
            "Step 1: Received analyst output with key findings",
            f"Step 2: Structured content into {len(sections)} sections",
            "Step 3: Applied professional tone calibration",
            f"Step 4: Quality score {confidence:.2f} — above threshold",
        ],
        "_constraints_checked": ["content_policy", "max_length", "tone_appropriate"],
    }


# ─── Realistic Reviewer Agent ─────────────────────────────────────────────────

async def realistic_reviewer(node_input: dict, context, node) -> dict:
    """
    Realistic reviewer — scores the upstream content and can reject or approve.
    Deliberately produces some rejections to make the dashboard interesting.
    """
    upstream  = node_input.get("node_outputs", {})
    all_outputs = list(upstream.values())

    # Aggregate confidence from upstream nodes if available
    upstream_confs = [
        v.get("confidence", 0.75)
        for v in all_outputs if isinstance(v, dict)
    ]
    avg_upstream_conf = sum(upstream_confs) / len(upstream_confs) if upstream_confs else 0.75

    prompt   = f"Review {len(all_outputs)} upstream outputs and assess quality."
    llm_meta = await _llm_call(prompt, model="gpt-4o", temperature=0.1)

    # Reviewer confidence anchored to upstream quality
    confidence = max(0.55, min(0.98, avg_upstream_conf * 1.05 + random.gauss(0, 0.03)))
    approved   = confidence >= 0.72

    violations: list[str] = []
    if avg_upstream_conf < 0.65:
        violations.append("upstream_confidence_too_low")
    if not approved:
        violations.append("quality_threshold_not_met")

    result = {
        "approved":          approved,
        "overall_score":     round(confidence, 3),
        "confidence":        round(confidence, 3),
        "feedback":          "Approved — all quality thresholds met." if approved
                             else f"Rejected — score {confidence:.2f} below 0.72 threshold.",
        "reviewed_nodes":    list(upstream.keys()),
        "upstream_avg_conf": round(avg_upstream_conf, 3),
        "checklist": {
            "factual_accuracy":   confidence > 0.70,
            "tone_appropriate":   True,
            "length_adequate":    True,
            "citations_present":  random.random() > 0.3,
        },
        "agent":             "reviewer",
        "_llm_meta":         llm_meta,
        "_reasoning": [
            f"Step 1: Evaluated {len(all_outputs)} upstream outputs",
            f"Step 2: Averaged confidence across inputs: {avg_upstream_conf:.2f}",
            f"Step 3: Applied quality threshold (0.72)",
            f"Step 4: Decision: {'APPROVE' if approved else 'REJECT'}",
        ],
        "_constraints_checked": ["quality_threshold", "factual_accuracy", "tone_policy"],
        "_constraints_violated": violations,
    }

    return result


# ─── Registration ─────────────────────────────────────────────────────────────

_REALISTIC_HANDLERS = [
    ("analyst_agent",  realistic_analyst,  "agent",
     "Realistic analyst with LLM token tracking, confidence scoring, reasoning chains.", ["agent", "realistic"]),
    ("writer_agent",   realistic_writer,   "agent",
     "Realistic writer that reads upstream outputs and produces structured content.",     ["agent", "realistic"]),
    ("reviewer_agent", realistic_reviewer, "agent",
     "Realistic reviewer with approval/rejection logic and constraint checking.",         ["agent", "realistic"]),
]


def register_realistic() -> None:
    """Override the stub handlers with realistic equivalents."""
    for key, fn, ptype, desc, tags in _REALISTIC_HANDLERS:
        HandlerRegistry.register(key, fn)          # replaces existing stub
        default_registry.register(
            key=key, handler=fn, plugin_type=ptype,
            description=desc, tags=tags,
        )
    print(f"[realistic_handlers] Registered {len(_REALISTIC_HANDLERS)} realistic agents")


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))

    async def _test():
        ctx_mock = type("Ctx", (), {
            "get_memory": lambda s, k, d=None: d,
            "set_memory": lambda s, k, v: None,
        })()
        node_mock = type("Node", (), {"id": "n1", "name": "test"})()

        print("Testing realistic_analyst…")
        a = await realistic_analyst(
            {"input": {"topic": "AI agent adoption in enterprise 2026"}, "variables": {}, "node_outputs": {}},
            ctx_mock, node_mock,
        )
        print(f"  confidence={a['confidence']}  tokens={a['_llm_meta']['total_tokens']}  cost=${a['_llm_meta']['cost_usd']:.6f}")

        print("Testing realistic_writer…")
        w = await realistic_writer(
            {"input": {}, "variables": {}, "node_outputs": {"n1": a}},
            ctx_mock, node_mock,
        )
        print(f"  confidence={w['confidence']}  word_count={w['word_count']}")

        print("Testing realistic_reviewer…")
        r = await realistic_reviewer(
            {"input": {}, "variables": {}, "node_outputs": {"n1": a, "n2": w}},
            ctx_mock, node_mock,
        )
        print(f"  approved={r['approved']}  score={r['overall_score']}")
        print("\nAll realistic handlers OK ✓")

    asyncio.run(_test())
