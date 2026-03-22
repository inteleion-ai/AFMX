"""
AFMX Tool Router — deterministic, policy-driven tool selection.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

# FIX: `typing.Pattern` was removed in Python 3.12. Use `re.Pattern` instead.
from re import Pattern
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    INTENT = "INTENT"
    METADATA = "METADATA"
    POLICY = "POLICY"
    PRIORITY = "PRIORITY"
    ROUND_ROBIN = "ROUND_ROBIN"


@dataclass
class RoutingRule:
    """
    A single routing rule — maps a condition to a tool handler key.
    Rules are evaluated in priority order (lower number = higher priority).
    """
    tool_key: str
    priority: int = 100
    intent_patterns: List[str] = field(default_factory=list)
    metadata_match: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    description: str = ""
    enabled: bool = True

    _compiled: List[Pattern] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.intent_patterns]

    def matches_intent(self, intent: str) -> bool:
        if not self._compiled:
            return False
        return any(p.search(intent) for p in self._compiled)

    def matches_metadata(self, metadata: Dict[str, Any]) -> bool:
        if not self.metadata_match:
            return False
        return all(metadata.get(k) == v for k, v in self.metadata_match.items())


@dataclass
class ToolRegistration:
    key: str
    handler: Callable
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


class ToolRouter:
    """
    AFMX Tool Router — fully deterministic, no LLM, no fuzzy logic.
    Resolution order: direct key → rules → tags → default → raise.
    """

    def __init__(self):
        self._tools: Dict[str, ToolRegistration] = {}
        self._rules: List[RoutingRule] = []
        self._default_tool: Optional[str] = None
        # FIX: proper round-robin counter keyed by tool_key
        self._rr_counters: Dict[str, int] = {}

    def register(
        self,
        key: str,
        handler: Callable,
        description: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolRouter":
        if key in self._tools:
            logger.warning(f"[ToolRouter] Overwriting: '{key}'")
        self._tools[key] = ToolRegistration(
            key=key, handler=handler, description=description,
            tags=tags or [], metadata=metadata or {},
        )
        logger.info(f"[ToolRouter] Registered tool: '{key}'")
        return self

    def set_default(self, tool_key: str) -> "ToolRouter":
        if tool_key not in self._tools:
            raise KeyError(f"Cannot set default — tool '{tool_key}' not registered")
        self._default_tool = tool_key
        return self

    def add_rule(self, rule: RoutingRule) -> "ToolRouter":
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)
        return self

    def deregister(self, key: str) -> None:
        self._tools.pop(key, None)
        self._rules = [r for r in self._rules if r.tool_key != key]

    def resolve(
        self,
        handler_key: Optional[str] = None,
        intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
    ) -> ToolRegistration:
        metadata = metadata or {}

        if handler_key:
            tool = self._tools.get(handler_key)
            if tool and tool.enabled:
                return tool
            raise KeyError(f"Tool '{handler_key}' not found or disabled")

        if intent or metadata:
            candidates = self._match_rules(intent or "", metadata, strategy)
            if candidates:
                return candidates[0]

        if tags:
            tagged = [t for t in self._tools.values()
                      if t.enabled and any(tag in t.tags for tag in tags)]
            if tagged:
                return tagged[0]

        if self._default_tool and self._default_tool in self._tools:
            return self._tools[self._default_tool]

        raise RuntimeError(
            f"[ToolRouter] No tool resolved. "
            f"intent='{intent}', registered={list(self._tools.keys())}"
        )

    def get_handler(self, key: str) -> Callable:
        tool = self._tools.get(key)
        if not tool:
            raise KeyError(f"Tool '{key}' not registered")
        return tool.handler

    def list_tools(self) -> List[Dict[str, Any]]:
        return [{"key": t.key, "description": t.description,
                 "tags": t.tags, "enabled": t.enabled}
                for t in self._tools.values()]

    def _match_rules(
        self,
        intent: str,
        metadata: Dict[str, Any],
        strategy: RoutingStrategy,
    ) -> List[ToolRegistration]:
        matched: List[ToolRegistration] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            tool = self._tools.get(rule.tool_key)
            if not tool or not tool.enabled:
                continue
            if rule.matches_intent(intent) or rule.matches_metadata(metadata):
                matched.append(tool)
                if strategy == RoutingStrategy.PRIORITY:
                    break
        return matched
