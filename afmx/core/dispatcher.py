"""
AFMX Agent Dispatcher
Routes tasks to the correct agent based on complexity, capability, and policy.

FIX: Round-robin policy now uses a proper per-group counter,
     not always-first-available.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentTier(str, Enum):
    DEFAULT = "DEFAULT"
    SPECIALIST = "SPECIALIST"
    EXPERT = "EXPERT"
    COORDINATOR = "COORDINATOR"


class DispatchPolicy(str, Enum):
    COMPLEXITY = "COMPLEXITY"
    CAPABILITY = "CAPABILITY"
    ROUND_ROBIN = "ROUND_ROBIN"
    STICKY = "STICKY"
    EXPLICIT = "EXPLICIT"


@dataclass
class AgentRegistration:
    key: str
    handler: Callable
    tier: AgentTier = AgentTier.DEFAULT
    capabilities: List[str] = field(default_factory=list)
    complexity_min: float = 0.0
    complexity_max: float = 1.0
    max_concurrent: int = 100
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    _active_count: int = field(default=0, init=False, repr=False)

    def can_accept(self) -> bool:
        return self.enabled and self._active_count < self.max_concurrent

    def acquire(self) -> None:
        self._active_count += 1

    def release(self) -> None:
        self._active_count = max(0, self._active_count - 1)


@dataclass
class DispatchRequest:
    task_id: str
    handler_key: Optional[str] = None
    complexity: float = 0.5
    required_capabilities: List[str] = field(default_factory=list)
    policy: DispatchPolicy = DispatchPolicy.COMPLEXITY
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentDispatcher:
    """
    AFMX Agent Dispatcher — deterministic task-to-agent routing.

    Resolution order:
    1. Explicit handler_key
    2. Capability matching
    3. Complexity-based
    4. Round-robin (proper counter, not always-first)
    5. Sticky session
    6. Default fallback
    7. Raise
    """

    def __init__(self):
        self._agents: Dict[str, AgentRegistration] = {}
        self._default_agent: Optional[str] = None
        self._sticky_map: Dict[str, str] = {}
        # FIX: proper round-robin counter — persists across calls
        self._rr_counter: int = 0

    def register(
        self,
        key: str,
        handler: Callable,
        tier: AgentTier = AgentTier.DEFAULT,
        capabilities: Optional[List[str]] = None,
        complexity_min: float = 0.0,
        complexity_max: float = 1.0,
        max_concurrent: int = 100,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "AgentDispatcher":
        if key in self._agents:
            logger.warning(f"[AgentDispatcher] Overwriting agent: '{key}'")
        self._agents[key] = AgentRegistration(
            key=key, handler=handler, tier=tier,
            capabilities=capabilities or [],
            complexity_min=complexity_min, complexity_max=complexity_max,
            max_concurrent=max_concurrent, description=description,
            metadata=metadata or {},
        )
        logger.info(f"[AgentDispatcher] Registered agent: '{key}' tier={tier}")
        return self

    def set_default(self, agent_key: str) -> "AgentDispatcher":
        if agent_key not in self._agents:
            raise KeyError(f"Cannot set default — agent '{agent_key}' not registered")
        self._default_agent = agent_key
        return self

    def deregister(self, key: str) -> None:
        self._agents.pop(key, None)

    def dispatch(self, request: DispatchRequest) -> AgentRegistration:
        # Path 1: Explicit
        if request.handler_key:
            agent = self._agents.get(request.handler_key)
            if agent and agent.can_accept():
                return agent
            raise RuntimeError(
                f"Agent '{request.handler_key}' not found, disabled, or at capacity"
            )

        # Path 2: Sticky
        if request.policy == DispatchPolicy.STICKY and request.session_id:
            sticky_key = self._sticky_map.get(request.session_id)
            if sticky_key:
                agent = self._agents.get(sticky_key)
                if agent and agent.can_accept():
                    return agent

        # Path 3: Capability
        if request.required_capabilities:
            capable = [
                a for a in self._agents.values()
                if a.can_accept()
                and all(cap in a.capabilities for cap in request.required_capabilities)
            ]
            if capable:
                selected = self._select_by_complexity(capable, request.complexity)
                self._maybe_pin_sticky(request, selected.key)
                return selected

        # Path 4: Complexity
        if request.policy == DispatchPolicy.COMPLEXITY:
            complexity_match = [
                a for a in self._agents.values()
                if a.can_accept()
                and a.complexity_min <= request.complexity <= a.complexity_max
            ]
            if complexity_match:
                return sorted(complexity_match, key=lambda a: a.complexity_max)[0]

        # Path 5: Round-robin — FIX: uses persistent counter for true distribution
        if request.policy == DispatchPolicy.ROUND_ROBIN:
            available = [a for a in self._agents.values() if a.can_accept()]
            if available:
                # Sort by key for deterministic ordering before round-robin index
                available.sort(key=lambda a: a.key)
                selected = available[self._rr_counter % len(available)]
                self._rr_counter += 1
                return selected

        # Path 6: Default
        if self._default_agent:
            agent = self._agents.get(self._default_agent)
            if agent and agent.can_accept():
                return agent

        raise RuntimeError(
            f"[AgentDispatcher] No agent available for task '{request.task_id}' "
            f"complexity={request.complexity} capabilities={request.required_capabilities}"
        )

    def get_handler(self, key: str) -> Callable:
        agent = self._agents.get(key)
        if not agent:
            raise KeyError(f"Agent '{key}' not registered")
        return agent.handler

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": a.key, "tier": a.tier,
                "capabilities": a.capabilities,
                "complexity_range": [a.complexity_min, a.complexity_max],
                "active": a._active_count,
                "max_concurrent": a.max_concurrent,
                "enabled": a.enabled,
            }
            for a in self._agents.values()
        ]

    def _select_by_complexity(
        self, candidates: List[AgentRegistration], complexity: float,
    ) -> AgentRegistration:
        exact = [a for a in candidates
                 if a.complexity_min <= complexity <= a.complexity_max]
        if exact:
            return sorted(exact, key=lambda a: a.complexity_max - complexity)[0]
        tier_order = {
            AgentTier.DEFAULT: 0, AgentTier.SPECIALIST: 1,
            AgentTier.EXPERT: 2, AgentTier.COORDINATOR: 3,
        }
        return sorted(candidates, key=lambda a: tier_order.get(a.tier, 0))[0]

    def _maybe_pin_sticky(self, request: DispatchRequest, agent_key: str) -> None:
        if request.policy == DispatchPolicy.STICKY and request.session_id:
            self._sticky_map[request.session_id] = agent_key
