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
AFMX Adapter Registry
======================
Central registry for all AFMX adapters.  Adapters are loaded lazily on first
access so that AFMX starts without error even if framework packages are absent.

Usage::

    from afmx.adapters.registry import adapter_registry

    # Get a registered adapter by name
    lc   = adapter_registry.get("langchain")
    node = lc.to_afmx_node(my_tool)

    # Check availability without raising
    if adapter_registry.has("bedrock"):
        br = adapter_registry.get("bedrock")

    # Register a custom adapter via decorator
    @adapter_registry.register_adapter
    class MyAdapter(AFMXAdapter):
        @property
        def name(self) -> str:
            return "my_framework"
        ...

    # List everything that loaded successfully
    for info in adapter_registry.list_adapters():
        print(info["name"], info["class"])
"""
from __future__ import annotations

import importlib
import logging
from typing import Dict, List, Optional, Type

from afmx.adapters.base import AFMXAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Central registry for AFMX framework adapters.

    Built-in adapters are registered lazily on first ``get()`` / ``has()``
    call.  Each adapter module imports its framework lazily, so a missing
    ``langchain``, ``semantic-kernel``, ``boto3``, etc. is simply skipped
    rather than raising an ``ImportError`` at AFMX startup.
    """

    #: Ordered list of (registry_name, module_path, class_name) for
    #: every built-in adapter.  New adapters go here — nothing else changes.
    _BUILTIN_SPECS: List[tuple[str, str, str]] = [
        # Core frameworks
        ("langchain",       "afmx.adapters.langchain",       "LangChainAdapter"),
        ("langgraph",       "afmx.adapters.langgraph",       "LangGraphAdapter"),
        ("crewai",          "afmx.adapters.crewai",          "CrewAIAdapter"),
        ("openai",          "afmx.adapters.openai",          "OpenAIAdapter"),
        # Protocol adapters
        ("mcp",             "afmx.adapters.mcp",             "MCPAdapter"),
        # Enterprise adapters
        ("semantic_kernel", "afmx.adapters.semantic_kernel", "SemanticKernelAdapter"),
        ("google_adk",      "afmx.adapters.google_adk",      "GoogleADKAdapter"),
        ("bedrock",         "afmx.adapters.bedrock",         "BedrockAdapter"),
    ]

    def __init__(self) -> None:
        self._adapters:   Dict[str, AFMXAdapter] = {}
        self._initialized: bool = False

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, adapter: AFMXAdapter) -> "AdapterRegistry":
        """Register an adapter instance.  Overwrites an existing entry."""
        if adapter.name in self._adapters:
            logger.warning("[AdapterRegistry] Overwriting adapter: '%s'", adapter.name)
        self._adapters[adapter.name] = adapter
        logger.debug("[AdapterRegistry] Registered adapter: '%s'", adapter.name)
        return self

    def register_adapter(self, cls: Type[AFMXAdapter]) -> Type[AFMXAdapter]:
        """
        Class decorator — instantiate and register the adapter.

        Example::

            @adapter_registry.register_adapter
            class MyAdapter(AFMXAdapter):
                @property
                def name(self) -> str:
                    return "my_framework"
        """
        self.register(cls())
        return cls

    def deregister(self, name: str) -> None:
        """Remove an adapter from the registry by name."""
        self._adapters.pop(name, None)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> AFMXAdapter:
        """
        Return the adapter for *name*.

        Triggers lazy loading of built-ins on the first call.

        Raises:
            KeyError: if the adapter is not registered (e.g. framework not installed).
        """
        self._ensure_builtins()
        adapter = self._adapters.get(name)
        if adapter is None:
            available = sorted(self._adapters.keys())
            raise KeyError(
                f"Adapter '{name}' is not registered. "
                f"Available adapters: {available}. "
                f"If the adapter requires a third-party package, install it first "
                f"(e.g. 'pip install semantic-kernel>=1.0.0')."
            )
        return adapter

    def get_optional(self, name: str) -> Optional[AFMXAdapter]:
        """Return the adapter or ``None`` — never raises."""
        self._ensure_builtins()
        return self._adapters.get(name)

    def has(self, name: str) -> bool:
        """Return ``True`` if an adapter is registered under *name*."""
        self._ensure_builtins()
        return name in self._adapters

    def list_adapters(self) -> List[Dict]:
        """
        Return metadata for every registered adapter.

        Each entry contains ``name``, ``class``, and ``available=True``.
        Adapters that failed to load are absent from the list.
        """
        self._ensure_builtins()
        return [
            {"name": a.name, "class": type(a).__name__, "available": True}
            for a in self._adapters.values()
        ]

    # ── Lazy loading ──────────────────────────────────────────────────────────

    def _ensure_builtins(self) -> None:
        """
        Load built-in adapters on first access.

        Each adapter is imported via ``importlib`` inside a try/except so
        that a missing optional dependency (e.g. ``boto3``) does not raise
        and does not prevent other adapters from loading.
        """
        if self._initialized:
            return
        self._initialized = True

        for adapter_name, module_path, class_name in self._BUILTIN_SPECS:
            try:
                module  = importlib.import_module(module_path)
                cls     = getattr(module, class_name)
                # Adapters with required __init__ args (SK, Bedrock) cannot be
                # instantiated without arguments — skip them here; users call
                # the constructor directly with the required config.
                if _requires_init_args(cls):
                    logger.debug(
                        "[AdapterRegistry] Skipped auto-instantiation of '%s' "
                        "(requires constructor args).",
                        adapter_name,
                    )
                    continue
                instance = cls()
                self.register(instance)
            except Exception as exc:
                logger.debug(
                    "[AdapterRegistry] Skipped '%s': %s", adapter_name, exc
                )


def _requires_init_args(cls: type) -> bool:
    """
    Return True if the class ``__init__`` has required (no-default) parameters
    beyond ``self``.

    Used to decide whether we can auto-instantiate an adapter at registry
    load time.  Adapters like ``SemanticKernelAdapter(kernel=...)`` and
    ``BedrockAdapter(region_name=...)`` have required args and must be
    instantiated by the user.
    """
    import inspect
    try:
        sig    = inspect.signature(cls.__init__)
        params = list(sig.parameters.values())[1:]  # skip 'self'
        return any(
            p.default is inspect.Parameter.empty
            and p.kind not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
            for p in params
        )
    except (ValueError, TypeError):
        return False


# ─── Global singleton ─────────────────────────────────────────────────────────

#: The global default adapter registry. Import this in application code.
adapter_registry = AdapterRegistry()
