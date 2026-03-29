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
AFMX MCP (Model Context Protocol) Adapter
==========================================
Connects any MCP server to the AFMX execution engine as a first-class
``NodeType.MCP`` node.

Model Context Protocol (MCP) is the open standard for connecting AI systems
to tools and data sources.  Thousands of MCP servers exist for web search,
file systems, databases, GitHub, Slack, Notion, and more.  This adapter
turns each MCP tool into an AFMX node that participates in the Cognitive
Matrix — with automatic ``CognitiveLayer`` inference, retry, circuit breaker,
and audit trail — without any per-tool boilerplate.

Transports
----------
HTTP + SSE (remote servers):
    The MCP server runs as an HTTP service.  Connection uses the official
    MCP Python SDK's SSE transport.

    .. code-block:: python

        adapter = MCPAdapter()
        nodes = await adapter.from_server("http://localhost:3000/sse")

stdio (local process):
    The MCP server is a subprocess communicating over stdin/stdout.  This
    matches the Claude Desktop ``mcpServers`` config format.

    .. code-block:: python

        nodes = await adapter.from_config({
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-server-filesystem", "/tmp"],
        })

Claude Desktop config file:
    Load all servers from a Claude Desktop / Cursor config dict at once:

    .. code-block:: python

        nodes = await adapter.from_desktop_config({
            "mcpServers": {
                "filesystem": {"command": "npx", "args": ["..."]},
                "github":     {"command": "npx", "args": ["..."]},
            }
        })

CognitiveLayer inference
------------------------
The adapter infers ``CognitiveLayer`` automatically from tool names and
descriptions so tools land in the correct matrix cell without any manual
annotation:

+------------------+-----------------------------------------+
| Inferred layer   | Trigger keywords (name or description)  |
+==================+=========================================+
| RETRIEVE         | search, fetch, read, get, list, query,  |
|                  | find, lookup, load, retrieve, browse    |
+------------------+-----------------------------------------+
| ACT              | write, create, update, delete, send,    |
|                  | post, execute, run, deploy, set, insert |
+------------------+-----------------------------------------+
| EVALUATE         | check, validate, test, verify, audit,   |
|                  | review, inspect, compare, analyse       |
+------------------+-----------------------------------------+
| PERCEIVE         | monitor, watch, listen, observe,        |
|                  | subscribe, detect, capture, receive     |
+------------------+-----------------------------------------+
| REPORT           | report, summarise, export, format,      |
|                  | render, generate, produce               |
+------------------+-----------------------------------------+
| REASON           | (default for tools not matching above)  |
+------------------+-----------------------------------------+

Installation
------------
The MCP Python SDK is required::

    pip install mcp>=1.0.0
    # or
    pip install afmx[mcp]

The ``mcp`` package is NOT imported at module load time.  Installing AFMX
without ``mcp`` succeeds; calling adapter methods raises a clear
``ImportError`` with the install command.

Usage
-----
.. code-block:: python

    import asyncio
    from afmx.adapters.mcp import MCPAdapter
    from afmx import ExecutionMatrix, ExecutionMode

    async def main():
        adapter = MCPAdapter()

        # Discover all tools from a filesystem MCP server
        nodes = await adapter.from_server("http://localhost:3000/sse")

        # Build a matrix from the discovered nodes
        matrix = ExecutionMatrix(
            name="mcp-filesystem",
            mode=ExecutionMode.DIAGONAL,
            nodes=nodes,
        )
        print(f"Discovered {len(nodes)} tools across layers:")
        for node in nodes:
            print(f"  {node.name} → {node.cognitive_layer}")

    asyncio.run(main())

See ``examples/mcp_quickstart.py`` for a full working example.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from afmx.adapters.base import AdapterResult, AFMXAdapter
from afmx.core.executor import HandlerRegistry
from afmx.models.node import (
    CognitiveLayer,
    Node,
    NodeConfig,
    NodeType,
    RetryPolicy,
    TimeoutPolicy,
)

logger = logging.getLogger(__name__)

# ─── Handler key prefix ───────────────────────────────────────────────────────

_HANDLER_PREFIX = "mcp:"

# ─── CognitiveLayer inference keyword sets ───────────────────────────────────
# Each entry: (CognitiveLayer, frozenset of trigger keywords)
# Keywords are matched against the lowercased tool name + description.
# Evaluated in order; first match wins.

_LAYER_KEYWORDS: List[Tuple[CognitiveLayer, frozenset]] = [
    (CognitiveLayer.RETRIEVE, frozenset({
        "search", "fetch", "read", "get", "list", "query",
        "find", "lookup", "load", "retrieve", "browse", "select",
    })),
    (CognitiveLayer.ACT, frozenset({
        "write", "create", "update", "delete", "send", "post",
        "execute", "run", "deploy", "set", "insert", "push",
        "commit", "apply", "submit", "remove", "move", "copy",
    })),
    (CognitiveLayer.EVALUATE, frozenset({
        "check", "validate", "test", "verify", "audit",
        "review", "inspect", "compare", "analyse", "analyze",
        "lint", "scan", "assert",
    })),
    (CognitiveLayer.PERCEIVE, frozenset({
        "monitor", "watch", "listen", "observe", "subscribe",
        "detect", "capture", "receive", "stream", "poll",
    })),
    (CognitiveLayer.REPORT, frozenset({
        "report", "summarise", "summarize", "export", "format",
        "render", "generate", "produce", "display", "show",
        "describe", "explain",
    })),
]

_LAYER_FALLBACK = CognitiveLayer.REASON


# ─── MCP import helpers ───────────────────────────────────────────────────────

def _require_mcp() -> None:
    """Raise a helpful ImportError when the ``mcp`` package is not installed."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        raise ImportError(
            "The 'mcp' package is required for MCPAdapter.\n"
            "Install it with:\n"
            "    pip install mcp>=1.0.0\n"
            "or:\n"
            "    pip install afmx[mcp]"
        ) from None


# ─── Server config dataclass ─────────────────────────────────────────────────

@dataclass
class MCPServerConfig:
    """
    Configuration for a single MCP server.

    Attributes
    ----------
    server_url:
        HTTP base URL for SSE transport, e.g. ``"http://localhost:3000"``.
        Mutually exclusive with ``command``.
    command:
        Executable to launch for stdio transport, e.g. ``"npx"``.
        Mutually exclusive with ``server_url``.
    args:
        Arguments passed to ``command``.
    env:
        Extra environment variables for the subprocess (stdio only).
    name:
        Human-readable label used in node names and handler keys.
    default_role:
        Optional ``agent_role`` string applied to all nodes from this server.
        If ``None``, nodes have no role coordinate.
    timeout_seconds:
        Per-tool-call timeout.  Defaults to 30 s.
    """

    server_url:       Optional[str]       = None
    command:          Optional[str]       = None
    args:             List[str]           = field(default_factory=list)
    env:              Dict[str, str]      = field(default_factory=dict)
    name:             str                 = "mcp"
    default_role:     Optional[str]       = None
    timeout_seconds:  float               = 30.0

    def __post_init__(self) -> None:
        if self.server_url is None and self.command is None:
            raise ValueError(
                "MCPServerConfig requires either 'server_url' (SSE transport) "
                "or 'command' (stdio transport)."
            )
        if self.server_url is not None and self.command is not None:
            raise ValueError(
                "MCPServerConfig: specify either 'server_url' or 'command', not both."
            )


# ─── Main adapter ─────────────────────────────────────────────────────────────

class MCPAdapter(AFMXAdapter):
    """
    AFMX adapter for Model Context Protocol (MCP) servers.

    Discovers all tools exposed by one or more MCP servers and translates
    them into AFMX ``NodeType.MCP`` nodes.  Each node is registered in
    ``HandlerRegistry`` so the AFMX engine can invoke it directly.

    The adapter is **stateless per call** — it opens a connection for each
    ``from_server`` / ``from_config`` call, collects tool definitions, then
    closes the connection.  Tool invocations during matrix execution open
    a fresh short-lived connection per call (keeps the adapter simple and
    avoids stale connection issues in long-running servers).

    Example::

        adapter = MCPAdapter()

        # SSE transport — remote server
        nodes = await adapter.from_server("http://localhost:3000")

        # stdio transport — local process
        nodes = await adapter.from_config({
            "command": "python",
            "args": ["-m", "my_mcp_server"],
        })

        # Claude Desktop config format
        nodes = await adapter.from_desktop_config({
            "mcpServers": {
                "fs": {"command": "npx", "args": ["-y", "@anthropic/mcp-server-filesystem", "/"]},
            }
        })
    """

    def __init__(
        self,
        default_retry_policy: Optional[RetryPolicy] = None,
        default_timeout_seconds: float = 30.0,
    ) -> None:
        """
        Parameters
        ----------
        default_retry_policy:
            ``RetryPolicy`` applied to all MCP nodes unless overridden.
            Defaults to 2 retries with 0.5 s backoff.
        default_timeout_seconds:
            Per-tool-call timeout in seconds.
        """
        self._default_retry = default_retry_policy or RetryPolicy(
            retries=2,
            backoff_seconds=0.5,
            backoff_multiplier=2.0,
            jitter=True,
        )
        self._default_timeout = default_timeout_seconds

    # ── AFMXAdapter contract ──────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "mcp"

    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: NodeType = NodeType.MCP,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Convert a raw MCP tool dict to an AFMX node.

        *external_obj* must be a dict with at least ``"name"`` and
        ``"description"`` keys, as returned by ``tools/list``.

        Note: does NOT require the ``mcp`` package.  The ``mcp`` package is
        only required when actually connecting to a server (``from_server``,
        ``from_config``) or when the registered handler is invoked at
        execution time.
        """
        if not isinstance(external_obj, dict):
            raise TypeError(
                "MCPAdapter.to_afmx_node expects a tool dict from 'tools/list'. "
                f"Got {type(external_obj).__name__}. "
                "Use from_server() or from_config() for automatic discovery."
            )
        tool_name   = external_obj.get("name", "mcp-tool")
        description = external_obj.get("description", "")
        server_url  = (extra_config or {}).get("server_url")
        server_cfg  = (extra_config or {}).get("server_config")
        handler_key = _build_handler_key(tool_name, server_url)

        # Register a handler that will call this tool at execution time
        self._register_tool_handler(
            handler_key=handler_key,
            tool_name=tool_name,
            tool_schema=external_obj.get("inputSchema", {}),
            server_config=server_cfg,
        )

        return _build_node(
            handler_key=handler_key,
            tool_name=tool_name,
            description=description,
            tool_schema=external_obj.get("inputSchema", {}),
            node_id=node_id,
            node_name=node_name,
            agent_role=(extra_config or {}).get("agent_role"),
            retry_policy=retry_policy or self._default_retry,
            timeout_policy=timeout_policy or TimeoutPolicy(
                timeout_seconds=self._default_timeout
            ),
        )

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        """
        Execute an MCP tool call directly.

        ``external_ref`` must be an ``MCPServerConfig`` instance.
        Use the registered handler (via ``to_afmx_node`` / ``from_server``)
        rather than calling this method directly from application code.
        """
        _require_mcp()
        if not isinstance(external_ref, MCPServerConfig):
            return AdapterResult.fail(
                "MCPAdapter.execute expects an MCPServerConfig as external_ref.",
                "TypeError",
            )
        tool_name = node_input.get("params", {}).get("__mcp_tool_name__", "")
        arguments  = _extract_arguments(node_input)
        return await _call_tool(external_ref, tool_name, arguments)

    def normalize(self, raw_output: Any) -> AdapterResult:
        if isinstance(raw_output, dict):
            return AdapterResult.ok(output=raw_output)
        return AdapterResult.ok(output={"result": raw_output})

    # ── High-level discovery API ──────────────────────────────────────────────

    async def from_server(
        self,
        server_url: str,
        *,
        server_name: str = "mcp",
        default_role: Optional[str] = None,
        timeout_seconds: float = 30.0,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> List[Node]:
        """
        Discover all tools from an HTTP+SSE MCP server and return AFMX nodes.

        Parameters
        ----------
        server_url:
            Base URL of the MCP server, e.g. ``"http://localhost:3000"``.
            The adapter appends ``"/sse"`` if not already present.
        server_name:
            Label used in node names and handler keys.
        default_role:
            Optional ``agent_role`` string for all nodes from this server.
        timeout_seconds:
            Per-tool-call timeout.
        extra_headers:
            Additional HTTP headers (for auth tokens, API keys, etc.).

        Returns
        -------
        List[Node]
            One AFMX ``NodeType.MCP`` node per tool exposed by the server.

        Raises
        ------
        ImportError
            If ``mcp`` is not installed.
        ConnectionError
            If the server cannot be reached.
        """
        _require_mcp()

        # Normalise URL: ensure /sse endpoint
        sse_url = _normalise_sse_url(server_url)

        cfg = MCPServerConfig(
            server_url=sse_url,
            name=server_name,
            default_role=default_role,
            timeout_seconds=timeout_seconds,
        )

        tools = await _discover_tools_sse(sse_url, extra_headers=extra_headers)
        logger.info(
            "[MCPAdapter] Discovered %d tool(s) from SSE server '%s'",
            len(tools),
            sse_url,
        )

        return self._tools_to_nodes(tools, cfg)

    async def from_config(
        self,
        config: Dict[str, Any],
        *,
        server_name: str = "mcp",
        default_role: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> List[Node]:
        """
        Discover tools from a stdio MCP server defined by a config dict.

        The ``config`` dict matches the Claude Desktop / Cursor
        ``mcpServers`` entry format::

            {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server-filesystem", "/"],
                "env": {"HOME": "/home/user"},   # optional
            }

        Parameters
        ----------
        config:
            Server config dict with ``"command"`` and optional ``"args"`` /
            ``"env"`` keys.
        server_name:
            Label used in node names and handler keys.
        default_role:
            Optional ``agent_role`` string for all nodes from this server.
        timeout_seconds:
            Per-tool-call timeout.

        Returns
        -------
        List[Node]
            One AFMX ``NodeType.MCP`` node per tool.
        """
        _require_mcp()

        command = config.get("command")
        if not command:
            raise ValueError(
                "MCPAdapter.from_config: 'command' is required in the config dict."
            )

        cfg = MCPServerConfig(
            command=command,
            args=config.get("args", []),
            env=config.get("env", {}),
            name=server_name,
            default_role=default_role,
            timeout_seconds=timeout_seconds,
        )

        tools = await _discover_tools_stdio(cfg)
        logger.info(
            "[MCPAdapter] Discovered %d tool(s) from stdio server '%s' (%s)",
            len(tools),
            server_name,
            command,
        )

        return self._tools_to_nodes(tools, cfg)

    async def from_desktop_config(
        self,
        desktop_config: Dict[str, Any],
        *,
        default_role: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> List[Node]:
        """
        Discover tools from all servers in a Claude Desktop config dict.

        Accepts the full ``{"mcpServers": {...}}`` structure or just the
        inner ``{server_name: config, ...}`` dict.

        Example::

            nodes = await adapter.from_desktop_config({
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@anthropic/mcp-server-filesystem", "/"]
                    },
                    "github": {
                        "command": "npx",
                        "args": ["-y", "@anthropic/mcp-server-github"]
                    }
                }
            })

        Returns
        -------
        List[Node]
            All tools from all servers, deduplicated by handler key.
        """
        _require_mcp()

        # Support both the full Claude Desktop JSON and just the inner dict
        servers = desktop_config.get("mcpServers", desktop_config)
        if not isinstance(servers, dict):
            raise ValueError(
                "MCPAdapter.from_desktop_config: expected a dict with 'mcpServers' "
                "or a flat server-name → config dict."
            )

        all_nodes: List[Node] = []
        seen_keys: set = set()

        for server_name, server_cfg in servers.items():
            try:
                nodes = await self.from_config(
                    server_cfg,
                    server_name=server_name,
                    default_role=default_role,
                    timeout_seconds=timeout_seconds,
                )
                for node in nodes:
                    if node.handler not in seen_keys:
                        seen_keys.add(node.handler)
                        all_nodes.append(node)
            except Exception as exc:
                logger.warning(
                    "[MCPAdapter] Skipped server '%s': %s",
                    server_name,
                    exc,
                )

        logger.info(
            "[MCPAdapter] Loaded %d unique tool(s) from %d server(s)",
            len(all_nodes),
            len(servers),
        )
        return all_nodes

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _tools_to_nodes(
        self,
        tools: List[Dict[str, Any]],
        cfg: MCPServerConfig,
    ) -> List[Node]:
        """Convert a list of MCP tool dicts into AFMX Node instances."""
        nodes: List[Node] = []
        for tool in tools:
            tool_name   = tool.get("name", f"tool-{uuid.uuid4().hex[:6]}")
            description = tool.get("description", "")
            handler_key = _build_handler_key(tool_name, cfg.server_url or cfg.command)

            self._register_tool_handler(
                handler_key=handler_key,
                tool_name=tool_name,
                tool_schema=tool.get("inputSchema", {}),
                server_config=cfg,
            )

            node = _build_node(
                handler_key=handler_key,
                tool_name=tool_name,
                description=description,
                tool_schema=tool.get("inputSchema", {}),
                node_id=None,
                node_name=f"{cfg.name}:{tool_name}",
                agent_role=cfg.default_role,
                retry_policy=self._default_retry,
                timeout_policy=TimeoutPolicy(timeout_seconds=cfg.timeout_seconds),
            )
            nodes.append(node)

        return nodes

    def _register_tool_handler(
        self,
        handler_key: str,
        tool_name: str,
        tool_schema: Dict[str, Any],
        server_config: Optional[MCPServerConfig],
    ) -> None:
        """
        Register a closure in HandlerRegistry that invokes the MCP tool at
        execution time.

        The closure captures ``tool_name`` and ``server_config`` at
        registration time so the handler is self-contained.
        """
        _tool_name  = tool_name
        _server_cfg = server_config

        async def _mcp_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            if _server_cfg is None:
                raise RuntimeError(
                    f"[MCPAdapter] No server config for tool '{_tool_name}'. "
                    "Re-create the node via from_server() or from_config()."
                )
            args = _extract_arguments(node_input)
            result = await _call_tool(_server_cfg, _tool_name, args)
            if not result.success:
                raise RuntimeError(
                    f"[MCPAdapter:{_tool_name}] {result.error}"
                )
            return result.output

        _mcp_handler.__name__ = f"mcp_{tool_name}"
        HandlerRegistry.register(handler_key, _mcp_handler)
        logger.debug("[MCPAdapter] Registered handler '%s'", handler_key)


# ─── Pure functions ───────────────────────────────────────────────────────────


def infer_cognitive_layer(name: str, description: str) -> CognitiveLayer:
    """
    Infer the ``CognitiveLayer`` for an MCP tool from its name and description.

    Uses keyword matching against the combined lowercased ``name`` and
    ``description`` strings.  The first matching layer wins; ties are broken
    by the order in ``_LAYER_KEYWORDS``.  Returns ``REASON`` as a safe default
    when no keywords match.

    Parameters
    ----------
    name:
        Tool name, e.g. ``"read_file"``, ``"search_web"``.
    description:
        Tool description from the MCP ``tools/list`` response.

    Returns
    -------
    CognitiveLayer
    """
    text_tokens = set(
        re.split(r"[\s_\-/.,;:!?()\[\]{}]+", (name + " " + description).lower())
    )
    text_tokens.discard("")

    for layer, keywords in _LAYER_KEYWORDS:
        if text_tokens & keywords:
            return layer

    return _LAYER_FALLBACK


def _normalise_sse_url(url: str) -> str:
    """
    Ensure the URL ends with ``/sse``.

    The MCP SSE transport expects the endpoint at ``<base>/sse``.
    If the caller passes the base URL without the path, this function
    appends it.
    """
    url = url.rstrip("/")
    if not url.endswith("/sse"):
        url = f"{url}/sse"
    return url


def _build_handler_key(tool_name: str, server_identifier: Optional[str]) -> str:
    """
    Build a stable, unique HandlerRegistry key for an MCP tool.

    Format: ``"mcp:<safe_tool_name>"`` — the server identifier is not
    included in the key because tool names must be unique per matrix.
    """
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)
    return f"{_HANDLER_PREFIX}{safe}"


def _extract_arguments(node_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract MCP tool call arguments from AFMX node input.

    Merges ``params`` into ``input`` when both are dicts, letting
    the matrix author pass arguments via either field.  ``params``
    takes precedence over ``input`` for overlapping keys.
    """
    raw_input = node_input.get("input", {})
    params    = node_input.get("params", {})

    if isinstance(raw_input, dict) and isinstance(params, dict):
        # params override input; remove internal AFMX keys
        merged = {**raw_input, **params}
        merged.pop("__mcp_tool_name__", None)
        return merged

    if isinstance(params, dict) and params:
        params.pop("__mcp_tool_name__", None)
        return params

    if isinstance(raw_input, dict):
        return raw_input

    # Scalar input — wrap in a "value" key as a fallback
    return {"value": raw_input} if raw_input is not None else {}


def _build_node(
    handler_key:  str,
    tool_name:    str,
    description:  str,
    tool_schema:  Dict[str, Any],
    node_id:      Optional[str],
    node_name:    Optional[str],
    agent_role:   Optional[str],
    retry_policy: RetryPolicy,
    timeout_policy: TimeoutPolicy,
) -> Node:
    """Construct an AFMX Node from MCP tool metadata."""
    layer = infer_cognitive_layer(tool_name, description)

    # Extract required params from the JSON Schema for documentation
    required_params: List[str] = (
        tool_schema.get("required", [])
        if isinstance(tool_schema, dict) else []
    )
    properties: Dict[str, Any] = (
        tool_schema.get("properties", {})
        if isinstance(tool_schema, dict) else {}
    )

    return Node(
        id=node_id or str(uuid.uuid4()),
        name=node_name or tool_name,
        type=NodeType.MCP,
        handler=handler_key,
        cognitive_layer=layer,
        agent_role=agent_role,
        config=NodeConfig(
            params={
                "__mcp_tool_name__": tool_name,
                "__mcp_schema__":    tool_schema,
                "__required__":      required_params,
            },
            tags=["mcp"],
        ),
        retry_policy=retry_policy,
        timeout_policy=timeout_policy,
        metadata={
            "adapter":     "mcp",
            "tool_name":   tool_name,
            "description": description,
            "schema":      tool_schema,
            "properties":  list(properties.keys()),
        },
    )


# ─── MCP protocol helpers ────────────────────────────────────────────────────


async def _discover_tools_sse(
    sse_url: str,
    extra_headers: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Connect to an SSE MCP server and return its ``tools/list`` response.

    Parameters
    ----------
    sse_url:
        Full SSE endpoint URL (must end with ``/sse``).
    extra_headers:
        Additional HTTP headers (auth tokens, etc.).

    Returns
    -------
    List[Dict[str, Any]]
        Raw tool dicts from ``tools/list``.
    """
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    headers = extra_headers or {}
    try:
        async with sse_client(sse_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_tool_to_dict(t) for t in result.tools]
    except Exception as exc:
        raise ConnectionError(
            f"MCPAdapter: could not connect to SSE server at '{sse_url}': {exc}"
        ) from exc


async def _discover_tools_stdio(
    cfg: MCPServerConfig,
) -> List[Dict[str, Any]]:
    """
    Launch a stdio MCP server subprocess and return its ``tools/list`` response.

    Parameters
    ----------
    cfg:
        Server configuration with ``command`` and optional ``args`` / ``env``.

    Returns
    -------
    List[Dict[str, Any]]
        Raw tool dicts from ``tools/list``.
    """
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args or [],
        env=cfg.env or None,
    )
    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_tool_to_dict(t) for t in result.tools]
    except Exception as exc:
        raise ConnectionError(
            f"MCPAdapter: could not start stdio server '{cfg.command}': {exc}"
        ) from exc


async def _call_tool(
    cfg: MCPServerConfig,
    tool_name: str,
    arguments: Dict[str, Any],
) -> AdapterResult:
    """
    Open a short-lived MCP connection and call a single tool.

    A new connection is opened for each invocation so that:
    1. The adapter remains stateless — no dangling connections.
    2. Long-running AFMX executions don't hold server resources idle.
    3. Connection errors on one node don't affect other nodes.

    Parameters
    ----------
    cfg:
        Server configuration (SSE or stdio).
    tool_name:
        MCP tool name to call.
    arguments:
        Tool arguments matching the tool's ``inputSchema``.

    Returns
    -------
    AdapterResult
        ``AdapterResult.ok()`` on success; ``AdapterResult.fail()`` on any error.
    """
    try:
        if cfg.server_url:
            raw = await _call_tool_sse(cfg, tool_name, arguments)
        else:
            raw = await _call_tool_stdio(cfg, tool_name, arguments)
        return AdapterResult.ok(output=raw)
    except Exception as exc:
        logger.error(
            "[MCPAdapter] Tool call failed: tool=%s server=%s error=%s",
            tool_name,
            cfg.server_url or cfg.command,
            exc,
        )
        return AdapterResult.fail(str(exc), type(exc).__name__)


async def _call_tool_sse(
    cfg: MCPServerConfig,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(cfg.server_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _normalise_tool_result(result)


async def _call_tool_stdio(
    cfg: MCPServerConfig,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args or [],
        env=cfg.env or None,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _normalise_tool_result(result)


def _normalise_tool_result(result: Any) -> Any:
    """
    Normalise an MCP ``CallToolResult`` into a plain Python value.

    MCP results are a list of ``Content`` objects (TextContent,
    ImageContent, EmbeddedResource, etc.).  This function extracts the
    text from TextContent items and combines them; non-text content is
    represented as a metadata dict.
    """
    if not hasattr(result, "content"):
        return {"raw": str(result)}

    text_parts: List[str] = []
    other_parts: List[Dict[str, Any]] = []

    for item in result.content:
        item_type = getattr(item, "type", "unknown")
        if item_type == "text":
            text_parts.append(getattr(item, "text", ""))
        else:
            other_parts.append({
                "type": item_type,
                "data": getattr(item, "data", None),
            })

    if text_parts and not other_parts:
        # Pure text response — return combined string for easy downstream use
        combined = "\n".join(text_parts)
        return {"text": combined, "is_error": getattr(result, "isError", False)}

    # Mixed or non-text content — return structured dict
    return {
        "text":     "\n".join(text_parts) if text_parts else None,
        "content":  other_parts,
        "is_error": getattr(result, "isError", False),
    }


def _tool_to_dict(tool: Any) -> Dict[str, Any]:
    """
    Convert an MCP ``Tool`` object to a plain Python dict.

    Handles both Pydantic model objects (MCP SDK v1+) and raw dicts.
    """
    if isinstance(tool, dict):
        return tool

    return {
        "name":        getattr(tool, "name", ""),
        "description": getattr(tool, "description", ""),
        "inputSchema": (
            tool.inputSchema.model_dump()
            if hasattr(tool, "inputSchema") and hasattr(tool.inputSchema, "model_dump")
            else getattr(tool, "inputSchema", {}) or {}
        ),
    }
