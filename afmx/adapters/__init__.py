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
AFMX Adapters Package
=====================
Framework-agnostic translation layer between external agent frameworks
and the AFMX execution engine.

All adapters are lazily loaded — importing this package does NOT import
any framework. If a framework is not installed, the adapter is skipped
silently. Calling ``to_afmx_node()`` on an uninstalled adapter raises
a clear ``ImportError`` with the install command.

Built-in adapters
-----------------
langchain         —  LangChain tools, chains, and runnables
langgraph         —  LangGraph node functions and full graph translation
crewai            —  CrewAI tasks, agents, and full Crew translation
openai            —  OpenAI function-calling tools and Assistants API
mcp               —  Any MCP server (SSE or stdio transport)  — v1.2.1
semantic_kernel   —  Microsoft Semantic Kernel functions and plugins
google_adk        —  Google Agent Development Kit agents and tools
bedrock           —  Amazon Bedrock Agents and model invocations

Quick start::

    from afmx.adapters import LangChainAdapter, MCPAdapter, SemanticKernelAdapter

    # LangChain tool
    lc   = LangChainAdapter()
    node = lc.to_afmx_node(my_tool)

    # MCP server — auto-discovers tools and infers CognitiveLayer
    mcp   = MCPAdapter()
    nodes = await mcp.from_server("http://localhost:3000")

    # Microsoft Semantic Kernel
    sk   = SemanticKernelAdapter(kernel=my_kernel)
    node = sk.function_node(my_sk_function, cognitive_layer="REASON")

    # Google ADK
    from afmx.adapters import GoogleADKAdapter
    adk  = GoogleADKAdapter()
    node = adk.agent_node(my_llm_agent, cognitive_layer="REASON")

    # Amazon Bedrock
    from afmx.adapters import BedrockAdapter
    br   = BedrockAdapter(region_name="us-east-1")
    node = br.model_node("anthropic.claude-3-5-sonnet-20241022-v2:0")
"""
from __future__ import annotations

from afmx.adapters.base import AdapterNodeConfig, AdapterResult, AFMXAdapter
from afmx.adapters.bedrock import BedrockAdapter
from afmx.adapters.crewai import CrewAIAdapter
from afmx.adapters.google_adk import GoogleADKAdapter
from afmx.adapters.langchain import LangChainAdapter
from afmx.adapters.langgraph import LangGraphAdapter
from afmx.adapters.mcp import MCPAdapter, MCPServerConfig, infer_cognitive_layer
from afmx.adapters.openai import OpenAIAdapter
from afmx.adapters.registry import AdapterRegistry, adapter_registry
from afmx.adapters.semantic_kernel import SemanticKernelAdapter

__all__ = [
    # Base contract
    "AFMXAdapter",
    "AdapterResult",
    "AdapterNodeConfig",
    # Registry
    "AdapterRegistry",
    "adapter_registry",
    # Core framework adapters
    "LangChainAdapter",
    "LangGraphAdapter",
    "CrewAIAdapter",
    "OpenAIAdapter",
    # MCP (v1.2.1)
    "MCPAdapter",
    "MCPServerConfig",
    "infer_cognitive_layer",
    # Enterprise adapters (v1.3.0)
    "SemanticKernelAdapter",
    "GoogleADKAdapter",
    "BedrockAdapter",
]
