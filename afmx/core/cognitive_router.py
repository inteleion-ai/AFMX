"""
AFMX Cognitive Model Router

Routes LLM model selection based on the CognitiveLayer of a Node.

Rationale
---------
Different cognitive layers have very different latency and accuracy requirements:

  PERCEIVE / RETRIEVE / ACT / REPORT
      → High-frequency, latency-sensitive operations.
        A cheap, fast model (e.g. Haiku, gpt-4o-mini) is appropriate.
        These layers ingest, fetch, execute, or report — they rarely need
        deep reasoning. Using a premium model here burns tokens for no gain.

  REASON / PLAN / EVALUATE
      → Low-frequency, accuracy-critical operations.
        A premium model (e.g. Claude Opus, o3, gpt-4o) is appropriate.
        These layers synthesise, strategise, and validate — this is where
        model capability directly affects output quality and correctness.

Cost impact: routing correctly reduces LLM spend by 60–90% on typical
enterprise multi-agent workflows, because PERCEIVE/RETRIEVE/ACT nodes
are the majority of invocations.

Configuration
-------------
Override the default models via AFMXSettings (afmx/config.py):
    AFMX_COGNITIVE_CHEAP_MODEL   = "claude-haiku-4-5-20251001"
    AFMX_COGNITIVE_PREMIUM_MODEL = "claude-opus-4-6"

These are passed into CognitiveModelRouter at startup in AFMXApplication.

Usage in handlers
-----------------
The router injects the model hint into ExecutionContext.metadata before
each node executes:

    context.metadata["__model_hint__"]      → "claude-haiku-4-5-20251001"
    context.metadata["__cognitive_layer__"] → "PERCEIVE"
    context.metadata["__agent_role__"]      → "OPS"

Handlers read these to select the correct model:

    async def my_handler(node_input, context, node):
        model = node_input["metadata"].get("__model_hint__", "default")
        response = await llm_client.call(model=model, prompt=...)
        return {"result": response, "model_used": model}
"""
from __future__ import annotations

import logging
from typing import Optional

from afmx.models.node import CognitiveLayer

logger = logging.getLogger(__name__)

# ─── Layer-to-tier mapping ────────────────────────────────────────────────────

_CHEAP_LAYERS: frozenset[CognitiveLayer] = frozenset({
    CognitiveLayer.PERCEIVE,
    CognitiveLayer.RETRIEVE,
    CognitiveLayer.ACT,
    CognitiveLayer.REPORT,
})

_PREMIUM_LAYERS: frozenset[CognitiveLayer] = frozenset({
    CognitiveLayer.REASON,
    CognitiveLayer.PLAN,
    CognitiveLayer.EVALUATE,
})


# ─── Router ───────────────────────────────────────────────────────────────────

class CognitiveModelRouter:
    """
    Maps a CognitiveLayer to the appropriate LLM model string.

    This class is stateless once constructed — safe to call from multiple
    async tasks concurrently with no locking needed.
    """

    def __init__(
        self,
        cheap_model:   str = "claude-haiku-4-5-20251001",
        premium_model: str = "claude-opus-4-6",
    ) -> None:
        self.cheap_model   = cheap_model
        self.premium_model = premium_model
        logger.info(
            f"[CognitiveModelRouter] cheap={cheap_model!r} "
            f"premium={premium_model!r}"
        )

    def resolve(self, layer: Optional[CognitiveLayer | str]) -> str:
        """
        Return the model string for a given CognitiveLayer.

        Args:
            layer: CognitiveLayer enum value, its string representation,
                   or None (→ returns cheap_model as safe default).

        Returns:
            Model identifier string (e.g. "claude-haiku-4-5-20251001").
        """
        if layer is None:
            return self.cheap_model

        # Accept both enum and raw string (e.g. from pydantic use_enum_values=True)
        if isinstance(layer, str):
            try:
                layer = CognitiveLayer(layer)
            except ValueError:
                logger.warning(
                    f"[CognitiveModelRouter] Unknown layer '{layer}' — using cheap model"
                )
                return self.cheap_model

        return self.premium_model if layer in _PREMIUM_LAYERS else self.cheap_model

    def resolve_tier(self, layer: Optional[CognitiveLayer | str]) -> str:
        """Return 'premium' or 'cheap' for a given layer (for observability)."""
        model = self.resolve(layer)
        return "premium" if model == self.premium_model else "cheap"

    def inject_hint(self, node, context) -> None:
        """
        Inject model routing metadata into ExecutionContext.metadata
        BEFORE the node's handler is called.

        Sets:
          __model_hint__      — full model string
          __model_tier__      — "cheap" | "premium"
          __cognitive_layer__ — layer string (or None)
          __agent_role__      — role string (or None)
        """
        layer = node.cognitive_layer  # may be str (use_enum_values=True) or None
        model = self.resolve(layer)
        tier  = self.resolve_tier(layer)

        context.metadata["__model_hint__"]      = model
        context.metadata["__model_tier__"]      = tier
        context.metadata["__cognitive_layer__"] = layer
        context.metadata["__agent_role__"]      = node.agent_role

        logger.debug(
            f"[CognitiveModelRouter] node='{node.name}' "
            f"layer={layer} role={node.agent_role} "
            f"→ model={model!r} ({tier})"
        )

    def list_layer_assignments(self) -> dict:
        """
        Returns a mapping of every CognitiveLayer to its assigned model.
        Useful for /health endpoints and observability.
        """
        result = {}
        for layer in CognitiveLayer:
            model = self.resolve(layer)
            tier  = self.resolve_tier(layer)
            result[layer.value] = {"model": model, "tier": tier}
        return result
