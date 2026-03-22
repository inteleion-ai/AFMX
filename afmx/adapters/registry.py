"""
AFMX Adapter Registry
Central registry for all external framework adapters.
Auto-registers built-in adapters and exposes a decorator API.

Usage:
    from afmx.adapters.registry import adapter_registry

    # Get a registered adapter
    lc = adapter_registry.get("langchain")
    node = lc.to_afmx_node(my_tool)

    # Register a custom adapter
    @adapter_registry.register_adapter
    class MyAdapter(AFMXAdapter):
        @property
        def name(self): return "my_framework"
        ...
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from afmx.adapters.base import AFMXAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Central registry for AFMX adapters.

    Built-in adapters (langchain, langgraph, crewai, openai) are lazily
    registered on first access — no ImportError if the framework isn't installed.

    Thread-safe for reads. Writes should happen at startup only.
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, AFMXAdapter] = {}
        self._initialized: bool = False

    # ─── Registration ─────────────────────────────────────────────────────────

    def register(self, adapter: AFMXAdapter) -> "AdapterRegistry":
        """Register an adapter instance by its name."""
        if adapter.name in self._adapters:
            logger.warning(
                f"[AdapterRegistry] Overwriting adapter: '{adapter.name}'"
            )
        self._adapters[adapter.name] = adapter
        logger.info(f"[AdapterRegistry] Registered adapter: '{adapter.name}'")
        return self

    def register_adapter(self, cls: Type[AFMXAdapter]) -> Type[AFMXAdapter]:
        """
        Class decorator — instantiates and registers the adapter.

        Usage:
            @adapter_registry.register_adapter
            class MyAdapter(AFMXAdapter):
                ...
        """
        self.register(cls())
        return cls

    def deregister(self, name: str) -> None:
        """Remove an adapter from the registry."""
        self._adapters.pop(name, None)

    # ─── Lookup ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> AFMXAdapter:
        """
        Get an adapter by name.

        Raises KeyError if not registered.
        Triggers lazy loading of built-in adapters on first call.
        """
        self._ensure_builtins()
        adapter = self._adapters.get(name)
        if adapter is None:
            available = list(self._adapters.keys())
            raise KeyError(
                f"Adapter '{name}' not registered. "
                f"Available: {available}. "
                f"Install the framework and ensure its adapter is loaded."
            )
        return adapter

    def get_optional(self, name: str) -> Optional[AFMXAdapter]:
        """Get adapter or None if not registered (no exception)."""
        self._ensure_builtins()
        return self._adapters.get(name)

    def has(self, name: str) -> bool:
        """Check if an adapter is registered."""
        self._ensure_builtins()
        return name in self._adapters

    def list_adapters(self) -> List[Dict]:
        """List all registered adapters with metadata."""
        self._ensure_builtins()
        return [
            {
                "name": a.name,
                "class": type(a).__name__,
                "available": True,
            }
            for a in self._adapters.values()
        ]

    # ─── Built-in lazy loading ────────────────────────────────────────────────

    def _ensure_builtins(self) -> None:
        """
        Register built-in adapters on first access.

        Each adapter is imported lazily so that AFMX starts without error
        even if the underlying framework is not installed.
        Adapters whose frameworks are missing are simply not registered.
        """
        if self._initialized:
            return
        self._initialized = True

        builtin_specs = [
            ("langchain", "afmx.adapters.langchain", "LangChainAdapter"),
            ("langgraph", "afmx.adapters.langgraph", "LangGraphAdapter"),
            ("crewai",    "afmx.adapters.crewai",    "CrewAIAdapter"),
            ("openai",    "afmx.adapters.openai",    "OpenAIAdapter"),
        ]

        import importlib
        for adapter_name, module_path, class_name in builtin_specs:
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                instance = cls()
                self.register(instance)
            except Exception as exc:
                logger.debug(
                    f"[AdapterRegistry] Skipped '{adapter_name}': {exc}"
                )


# ─── Global singleton ─────────────────────────────────────────────────────────
adapter_registry = AdapterRegistry()
