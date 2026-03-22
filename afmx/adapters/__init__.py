"""
AFMX Adapters Package
=====================
Framework-agnostic translation layer between external agent frameworks
and the AFMX execution engine.

Built-in adapters (lazily loaded — framework install not required):
    langchain  —  LangChain tools, chains, runnables
    langgraph  —  LangGraph node functions + full graph translation
    crewai     —  CrewAI tasks, agents, and full Crew translation
    openai     —  OpenAI function-calling tools + Assistants API

Quick start:

    from afmx.adapters import (
        LangChainAdapter,
        LangGraphAdapter,
        LangGraphTranslator,     # full graph → AFMX matrix
        CrewAIAdapter,
        OpenAIAdapter,
        adapter_registry,        # global singleton
    )

    # Get any built-in adapter
    lc = adapter_registry.get("langchain")
    node = lc.to_afmx_node(my_tool)

    # Register a custom adapter
    from afmx.adapters import AFMXAdapter, AdapterRegistry

    @adapter_registry.register_adapter
    class MyAdapter(AFMXAdapter):
        @property
        def name(self): return "my_framework"
        ...
"""
from afmx.adapters.base import AFMXAdapter, AdapterResult, AdapterNodeConfig
from afmx.adapters.registry import AdapterRegistry, adapter_registry
from afmx.adapters.langchain import LangChainAdapter
from afmx.adapters.langgraph import LangGraphAdapter
from afmx.adapters.crewai import CrewAIAdapter
from afmx.adapters.openai import OpenAIAdapter

__all__ = [
    # Base contract
    "AFMXAdapter",
    "AdapterResult",
    "AdapterNodeConfig",
    # Registry
    "AdapterRegistry",
    "adapter_registry",
    # Built-in adapters
    "LangChainAdapter",
    "LangGraphAdapter",
    "CrewAIAdapter",
    "OpenAIAdapter",
]
