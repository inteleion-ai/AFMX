"""
AFMX Plugin Registry
Central registry for all handlers (tools, agents, functions).
Supports decorator-based registration and runtime discovery.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PluginMeta:
    key: str
    handler: Callable
    plugin_type: str  # "tool" | "agent" | "function"
    description: str = ""
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    schema_in: Optional[Dict[str, Any]] = None
    schema_out: Optional[Dict[str, Any]] = None
    enabled: bool = True


class PluginRegistry:
    """
    Central registry for all AFMX plugins.

    Usage (decorator style):
        registry = PluginRegistry()

        @registry.tool("search_tool")
        async def my_search(input, context, node):
            ...

        @registry.agent("default_agent")
        async def my_agent(input, context, node):
            ...

    Usage (programmatic):
        registry.register("my_tool", my_handler, plugin_type="tool")
    """

    def __init__(self):
        self._plugins: Dict[str, PluginMeta] = {}

    # ─── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        key: str,
        handler: Callable,
        plugin_type: str = "function",
        description: str = "",
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        schema_in: Optional[Dict[str, Any]] = None,
        schema_out: Optional[Dict[str, Any]] = None,
    ) -> "PluginRegistry":
        if key in self._plugins:
            logger.warning(f"[PluginRegistry] Overwriting plugin: '{key}'")

        self._plugins[key] = PluginMeta(
            key=key,
            handler=handler,
            plugin_type=plugin_type,
            description=description,
            version=version,
            tags=tags or [],
            schema_in=schema_in,
            schema_out=schema_out,
        )
        logger.info(f"[PluginRegistry] Registered [{plugin_type}] '{key}'")
        return self

    def tool(
        self,
        key: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ):
        """Decorator for registering tool handlers."""
        def decorator(fn: Callable) -> Callable:
            self.register(key, fn, plugin_type="tool", description=description, tags=tags, **kwargs)
            return fn
        return decorator

    def agent(
        self,
        key: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ):
        """Decorator for registering agent handlers."""
        def decorator(fn: Callable) -> Callable:
            self.register(key, fn, plugin_type="agent", description=description, tags=tags, **kwargs)
            return fn
        return decorator

    def function(
        self,
        key: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ):
        """Decorator for registering function handlers."""
        def decorator(fn: Callable) -> Callable:
            self.register(key, fn, plugin_type="function", description=description, tags=tags, **kwargs)
            return fn
        return decorator

    # ─── Lookup ───────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[PluginMeta]:
        return self._plugins.get(key)

    def get_handler(self, key: str) -> Callable:
        meta = self._plugins.get(key)
        if not meta:
            raise KeyError(f"Plugin '{key}' not registered")
        if not meta.enabled:
            raise RuntimeError(f"Plugin '{key}' is disabled")
        return meta.handler

    def list_all(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": p.key,
                "type": p.plugin_type,
                "description": p.description,
                "version": p.version,
                "tags": p.tags,
                "enabled": p.enabled,
            }
            for p in self._plugins.values()
        ]

    def list_by_type(self, plugin_type: str) -> List[PluginMeta]:
        return [p for p in self._plugins.values() if p.plugin_type == plugin_type]

    def disable(self, key: str) -> None:
        if key in self._plugins:
            self._plugins[key].enabled = False

    def enable(self, key: str) -> None:
        if key in self._plugins:
            self._plugins[key].enabled = True

    def sync_to_handler_registry(self) -> None:
        """Push all registered plugins into HandlerRegistry for executor lookup."""
        from afmx.core.executor import HandlerRegistry
        for key, meta in self._plugins.items():
            if meta.enabled:
                HandlerRegistry.register(key, meta.handler)
        logger.info(f"[PluginRegistry] Synced {len(self._plugins)} plugins to HandlerRegistry")


# Global default registry
default_registry = PluginRegistry()
