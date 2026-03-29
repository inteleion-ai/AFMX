# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
AFMX ↔ RHFL (Responsible Human Feedback Loop) Integration
===========================================================
Gates AFMX ACT-layer nodes through RHFL — the deterministic governance and
human-in-the-loop control plane.

RHFL classifies every proposed action as:
- ``AUTO``      → execute immediately (AFMX proceeds normally)
- ``REVIEW``    → queue for human approval (AFMX pauses, waits)
- ``BLOCK``     → hard stop (AFMX marks node as ABORTED)
- ``ESCALATE``  → escalate to senior reviewer (AFMX waits with escalation context)

Architecture
------------
::

    AFMX ACT-layer node about to execute
            ↓
    [RHFL PRE_NODE hook]
            ↓
    POST /api/v1/decisions  (RHFL REST API)
            ↓
    classification = AUTO | REVIEW | BLOCK | ESCALATE
            ↓
    AUTO     → proceed normally, record decision_id in context
    REVIEW   → poll for approval (max timeout, configurable)
    BLOCK    → raise RHFLBlockedError → AFMX marks node ABORTED
    ESCALATE → poll with escalation context → wait for escalation resolution

RHFL is a Node.js/TypeScript service with a PostgreSQL backend.
This integration communicates with it purely over its REST API.

Environment variables
---------------------
    AFMX_RHFL_ENABLED=true
    AFMX_RHFL_URL=http://localhost:4000/api/v1
    AFMX_RHFL_TOKEN=<JWT from POST /auth/login or /auth/dev-token>
    AFMX_RHFL_POLL_INTERVAL=2.0     # seconds between status polls
    AFMX_RHFL_MAX_WAIT=300          # max seconds to wait for approval

Usage::

    from afmx.integrations.rhfl import attach_rhfl

    attach_rhfl(
        api_url="http://localhost:4000/api/v1",
        token="<jwt>",
        hook_registry=afmx_app.hook_registry,
    )

Install::

    pip install afmx[rhfl]
    # or: pip install httpx>=0.27.0 (already a dep)

No additional packages needed — RHFL REST API is called via httpx.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Handler key used in HandlerRegistry for direct ACT-gate calls
_GATE_HANDLER_KEY = "rhfl:gate"

# RHFL decision statuses that mean "approved"
_APPROVED_STATUSES = frozenset({"APPROVED", "EXECUTING", "COMPLETED"})
# RHFL decision statuses that mean "rejected/blocked"
_REJECTED_STATUSES = frozenset({"REJECTED", "BLOCKED"})
# Pending statuses — keep polling
_PENDING_STATUSES  = frozenset({"PENDING", "ESCALATED", "DEFERRED"})


class RHFLBlockedError(RuntimeError):
    """Raised when RHFL blocks or rejects an AFMX action."""

    def __init__(self, decision_id: str, reason: str, classification: str) -> None:
        super().__init__(
            f"RHFL {classification} decision '{decision_id}': {reason}"
        )
        self.decision_id    = decision_id
        self.reason         = reason
        self.classification = classification


class RHFLTimeoutError(RuntimeError):
    """Raised when a REVIEW or ESCALATE decision is not resolved within max_wait."""

    def __init__(self, decision_id: str, waited_seconds: float) -> None:
        super().__init__(
            f"RHFL decision '{decision_id}' not resolved after {waited_seconds:.0f}s"
        )
        self.decision_id    = decision_id
        self.waited_seconds = waited_seconds


# ─── Low-level RHFL REST client ───────────────────────────────────────────────


class _RHFLClient:
    """
    Minimal async REST client for the RHFL API.
    Uses httpx (already an AFMX dependency).
    """

    def __init__(self, api_url: str, token: str, timeout: float = 30.0) -> None:
        self._base    = api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "User-Agent":    "afmx-rhfl-integration/1.2.1",
        }
        self._timeout = timeout

    async def submit_decision(
        self,
        *,
        source: str,
        intent: str,
        payload: Dict[str, Any],
        risk_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Submit a proposed action to RHFL for classification.

        Returns the full RHFL Decision object including ``classification``
        (``AUTO`` | ``REVIEW`` | ``BLOCK`` | ``ESCALATE``).
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required: pip install httpx>=0.27.0")

        body = {
            "source":     source,
            "intent":     intent,
            "payload":    payload,
            "risk_score": risk_score,
            "metadata":   metadata or {},
        }
        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as http:
            resp = await http.post(f"{self._base}/decisions", json=body)
            resp.raise_for_status()
            return resp.json()

    async def get_decision_status(self, decision_id: str) -> Dict[str, Any]:
        """Poll a RHFL decision for its current status."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required: pip install httpx>=0.27.0")

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as http:
            resp = await http.get(f"{self._base}/decisions/{decision_id}")
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> Dict[str, Any]:
        """Check RHFL service health."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required: pip install httpx>=0.27.0")

        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{self._base}/health")
            resp.raise_for_status()
            return resp.json()


# ─── Core gate logic ──────────────────────────────────────────────────────────


async def _gate_through_rhfl(
    client: _RHFLClient,
    *,
    source: str,
    intent: str,
    payload: Dict[str, Any],
    risk_score: float,
    poll_interval: float,
    max_wait: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Submit an action to RHFL and wait for resolution.

    Returns the resolved RHFL Decision dict.
    Raises:
        RHFLBlockedError   — decision was BLOCK or REJECTED
        RHFLTimeoutError   — decision not resolved within max_wait
    """
    decision = await client.submit_decision(
        source=source,
        intent=intent,
        payload=payload,
        risk_score=risk_score,
        metadata=metadata,
    )
    decision_id    = decision.get("id", "unknown")
    classification = decision.get("classification", "REVIEW")
    status         = decision.get("status", "PENDING")

    logger.info(
        "[AFMX→RHFL] Decision submitted: id=%s classification=%s status=%s",
        decision_id, classification, status,
    )

    # AUTO — proceed immediately
    if classification == "AUTO" and status in _APPROVED_STATUSES:
        return decision

    # BLOCK — fail immediately
    if classification == "BLOCK" or status in _REJECTED_STATUSES:
        raise RHFLBlockedError(
            decision_id=decision_id,
            reason=decision.get("rejection_reason") or "Blocked by RHFL policy",
            classification=classification,
        )

    # REVIEW / ESCALATE — poll until resolved or timeout
    waited = 0.0
    while waited < max_wait:
        await asyncio.sleep(poll_interval)
        waited += poll_interval

        current = await client.get_decision_status(decision_id)
        current_status = current.get("status", "PENDING")

        logger.debug(
            "[AFMX→RHFL] Polling decision %s: status=%s waited=%.0fs",
            decision_id, current_status, waited,
        )

        if current_status in _APPROVED_STATUSES:
            logger.info(
                "[AFMX→RHFL] Decision %s approved after %.0fs", decision_id, waited
            )
            return current

        if current_status in _REJECTED_STATUSES:
            raise RHFLBlockedError(
                decision_id=decision_id,
                reason=current.get("rejection_reason") or "Rejected by human reviewer",
                classification=current.get("classification", classification),
            )

    raise RHFLTimeoutError(decision_id=decision_id, waited_seconds=waited)


# ─── Handler factory ──────────────────────────────────────────────────────────


def _make_gate_handler(
    client: _RHFLClient,
    poll_interval: float,
    max_wait: float,
) -> Any:
    """
    Return an AFMX handler that gates execution through RHFL.

    Use as the handler for ACT-layer guard nodes::

        Node(
            name="rhfl-gate",
            handler="rhfl:gate",
            cognitive_layer=CognitiveLayer.ACT,
        )

    Input::

        node_input["params"]["intent"]      → action description (required)
        node_input["params"]["risk_score"]  → 0.0–1.0 (optional, default: 0.0)
        node_input["params"]["payload"]     → action payload dict (optional)
    """
    _client   = client
    _interval = poll_interval
    _max      = max_wait

    async def rhfl_gate(
        node_input: Dict[str, Any],
        context: Any,
        node: Any,
    ) -> Dict[str, Any]:
        params  = node_input.get("params", {})
        intent  = params.get("intent") or str(node_input.get("input", node.name))
        payload = params.get("payload") or {}
        risk    = float(params.get("risk_score", 0.0))
        source  = getattr(node, "name", "afmx-node")

        decision = await _gate_through_rhfl(
            _client,
            source=source,
            intent=intent,
            payload=payload,
            risk_score=risk,
            poll_interval=_interval,
            max_wait=_max,
            metadata={
                "afmx_node":      source,
                "cognitive_layer": getattr(node, "cognitive_layer", None),
                "agent_role":      getattr(node, "agent_role", None),
            },
        )
        return {
            "rhfl_decision_id":    decision.get("id"),
            "rhfl_classification": decision.get("classification"),
            "rhfl_status":         decision.get("status"),
            "approved":            True,
        }

    rhfl_gate.__name__ = "rhfl_gate"
    return rhfl_gate


# ─── PRE_NODE hook factory ────────────────────────────────────────────────────


def _make_pre_node_hook(
    client: _RHFLClient,
    poll_interval: float,
    max_wait: float,
    risk_threshold: float,
) -> Any:
    """
    PRE_NODE hook that gates all ACT-layer nodes through RHFL.

    Only fires when ``node.cognitive_layer == "ACT"``.
    If RHFL blocks or times out, raises an exception that AFMX's
    fault-tolerance layer treats as a node failure.

    Parameters
    ----------
    risk_threshold:
        Nodes with ``metadata.get("risk_score", 0)`` below this threshold
        are submitted with ``risk_score=0`` (lower risk → more likely AUTO).
    """
    _client    = client
    _interval  = poll_interval
    _max       = max_wait
    _threshold = risk_threshold

    async def rhfl_pre_node(payload: Any) -> Any:
        node    = getattr(payload, "node", None)
        context = getattr(payload, "context", None)
        if node is None:
            return payload

        layer = str(getattr(node, "cognitive_layer", "")).upper()
        if layer != "ACT":
            return payload

        node_input = getattr(payload, "node_input", {}) or {}
        params     = node_input.get("params", {})
        intent     = (
            params.get("intent")
            or params.get("action")
            or str(node_input.get("input", node.name))
        )
        risk = float(
            params.get("risk_score")
            or (node.metadata or {}).get("risk_score", 0.0)
        )
        payload_data = params.get("payload") or {}

        try:
            decision = await _gate_through_rhfl(
                _client,
                source=node.name,
                intent=intent,
                payload=payload_data,
                risk_score=risk,
                poll_interval=_interval,
                max_wait=_max,
                metadata={
                    "afmx_execution_id": getattr(context, "execution_id", None)
                        if context else None,
                    "cognitive_layer": layer,
                    "agent_role": getattr(node, "agent_role", None),
                },
            )
            # Stamp approval into context metadata for audit trail
            if context is not None:
                context.set_memory(
                    f"rhfl:{node.id}:decision_id",
                    decision.get("id"),
                )
                context.set_memory(
                    f"rhfl:{node.id}:classification",
                    decision.get("classification"),
                )
            logger.info(
                "[AFMX→RHFL] ACT node '%s' approved by RHFL (decision=%s)",
                node.name, decision.get("id"),
            )
        except (RHFLBlockedError, RHFLTimeoutError) as exc:
            logger.warning("[AFMX→RHFL] ACT node '%s' blocked: %s", node.name, exc)
            raise  # Let AFMX fault-tolerance handle it as a node failure

        return payload

    rhfl_pre_node.__name__ = "rhfl_pre_node"
    return rhfl_pre_node


# ─── Public entry point ───────────────────────────────────────────────────────


def attach_rhfl(
    *,
    api_url: str = "http://localhost:4000/api/v1",
    token: str,
    hook_registry: Any = None,
    gate_act_nodes: bool = True,
    poll_interval: float = 2.0,
    max_wait: float = 300.0,
    risk_threshold: float = 0.5,
    timeout: float = 30.0,
) -> bool:
    """
    Attach RHFL governance to AFMX.

    Registers a ``"rhfl:gate"`` handler in ``HandlerRegistry``.
    Optionally registers a PRE_NODE hook that gates all ACT-layer nodes.

    Parameters
    ----------
    api_url:
        RHFL API base URL (e.g. ``"http://localhost:4000/api/v1"``).
    token:
        RHFL JWT token. Obtain from ``POST /auth/login`` or
        ``POST /auth/dev-token?role=admin`` (non-production).
    hook_registry:
        AFMX ``HookRegistry`` (required for automatic ACT-layer gating).
    gate_act_nodes:
        If ``True`` and ``hook_registry`` provided, gate all ACT-layer
        nodes through RHFL via PRE_NODE hook.
    poll_interval:
        Seconds between status polls for REVIEW/ESCALATE decisions.
    max_wait:
        Maximum seconds to wait for human approval.
    risk_threshold:
        Nodes whose metadata ``risk_score`` exceeds this are flagged to RHFL.
    timeout:
        HTTP request timeout for RHFL API calls.

    Returns
    -------
    bool
        ``True`` on success; ``False`` if setup fails.

    Example::

        from afmx.integrations.rhfl import attach_rhfl

        attach_rhfl(
            api_url="http://rhfl.internal:4000/api/v1",
            token=os.getenv("RHFL_TOKEN"),
            hook_registry=afmx_app.hook_registry,
            gate_act_nodes=True,
            max_wait=120.0,
        )
    """
    if not token:
        logger.error(
            "[AFMX→RHFL] No token provided — integration disabled. "
            "Get a token from RHFL: POST /api/v1/auth/login"
        )
        return False

    try:
        client = _RHFLClient(api_url=api_url, token=token, timeout=timeout)
    except Exception as exc:
        logger.error("[AFMX→RHFL] Client creation failed: %s", exc)
        return False

    from afmx.core.executor import HandlerRegistry

    HandlerRegistry.register(
        _GATE_HANDLER_KEY,
        _make_gate_handler(client, poll_interval, max_wait),
    )
    logger.info("[AFMX→RHFL] Handler registered: '%s'", _GATE_HANDLER_KEY)

    if hook_registry is not None and gate_act_nodes:
        try:
            from afmx.core.hooks import HookType

            hook_registry.register(
                name="rhfl_pre_node",
                fn=_make_pre_node_hook(client, poll_interval, max_wait, risk_threshold),
                hook_type=HookType.PRE_NODE,
                priority=5,   # runs before everything else — governance first
            )
            logger.info("[AFMX→RHFL] PRE_NODE ACT-layer gate hook registered")
        except Exception as exc:
            logger.error("[AFMX→RHFL] Hook registration failed: %s", exc)

    logger.info(
        "[AFMX→RHFL] ✅ Integration active — url=%s poll=%.1fs max_wait=%.0fs",
        api_url, poll_interval, max_wait,
    )
    return True
