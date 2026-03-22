# Adapters

AFMX adapters are thin, stateless translation layers between external agent frameworks and the AFMX execution runtime. All four built-in adapters load lazily — their framework packages are only required if you use them.

---

## Architecture

```
External Framework Object  (LangChain tool / LangGraph graph / CrewAI task / OpenAI function)
        ↓  adapter.to_afmx_node()
AFMX Node  (handler registered in HandlerRegistry)
        ↓  AFMXEngine executes node
adapter.execute() called via registered handler
        ↓
AdapterResult → NodeResult
```

**Design rules:**
- Adapters never hold state
- Adapters never call the engine directly
- Framework packages are imported lazily (inside methods), not at module level
- All framework objects are wrapped — AFMX remains the execution authority

---

## Adapter Registry

The `AdapterRegistry` lazy-loads all four built-in adapters on first access:

```python
from afmx.adapters.registry import adapter_registry

# Get an adapter
adapter = adapter_registry.get("langchain")

# Check availability
if adapter_registry.has("openai"):
    oai = adapter_registry.get("openai")

# List all registered adapters
for entry in adapter_registry.list_adapters():
    print(entry["name"], entry["class"])

# Register a custom adapter
@adapter_registry.register_adapter
class MyFrameworkAdapter(AFMXAdapter):
    @property
    def name(self): return "my_framework"
    ...
```

**REST:** `GET /afmx/adapters` returns the registry state.

---

## LangChain Adapter

Wraps LangChain tools (`BaseTool`), chains, and runnables (`Runnable`).

### Install

```bash
pip install "afmx[langchain]"   # or: pip install langchain
```

### Basic Usage

```python
from afmx.adapters.langchain import LangChainAdapter
from langchain.tools import DuckDuckGoSearchRun

adapter = LangChainAdapter()
tool = DuckDuckGoSearchRun()

# Convert to AFMX node (auto-registers the handler)
node = adapter.to_afmx_node(
    tool,
    node_id="web-search",
    node_name="DuckDuckGo Search",
    retry_policy=RetryPolicy(retries=2, backoff_seconds=1.0),
)

# Use in a matrix
matrix = ExecutionMatrix(nodes=[node], edges=[])
```

### Register Handler Directly

```python
# Register without creating a node (useful when you build the node manually)
handler_key = adapter.register_handler(tool)
# handler_key = "langchain:DuckDuckGoSearchRun"

# Or build a handler callable for HandlerRegistry
HandlerRegistry.register("my_search", adapter.make_handler(tool))
```

### Type Detection

| LangChain Class | AFMX NodeType |
|---|---|
| `BaseTool` | `TOOL` |
| `AgentExecutor` | `AGENT` |
| `BaseChain`, `Runnable` | `FUNCTION` |

### Invocation Chain

The adapter tries these methods in order (prefers async):
1. `ainvoke(input)`
2. `invoke(input)` — run in thread executor
3. `_arun(input_str)` — legacy BaseTool
4. `run(input_str)` — legacy BaseTool, thread executor
5. Direct callable — sync or async

### Output Normalization

If the raw output is `{"output": value}`, the adapter unwraps it to just `value`. Otherwise, the raw output is returned as-is.

---

## LangGraph Adapter

Two modes: **full graph translation** (AFMX controls execution) and **single-node wrapping** (LangGraph controls routing, AFMX provides fault tolerance).

### Install

```bash
pip install "afmx[langgraph]"   # or: pip install langgraph
```

### Mode 1: Full Graph Translation

Every LangGraph node becomes an AFMX node. Every LangGraph edge becomes an AFMX edge. AFMX controls execution order, retry, and fallback.

```python
from afmx.adapters.langgraph import LangGraphAdapter
from langgraph.graph import StateGraph

# Build your LangGraph as normal
graph = StateGraph(MyState)
graph.add_node("classify", classify_fn)
graph.add_node("respond", respond_fn)
graph.add_edge("classify", "respond")
compiled = graph.compile()

# Translate to AFMX matrix
adapter = LangGraphAdapter()
matrix = adapter.translate_graph(
    compiled,
    matrix_name="classify-respond",
    default_timeout=30.0,
    default_retries=2,
)

# Execute through AFMX engine
engine = AFMXEngine()
ctx = ExecutionContext(input={"messages": [...]})
rec = ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)
result = await engine.execute(matrix, ctx, rec)
```

The `__start__` and `__end__` virtual nodes are excluded. Only real graph nodes are translated.

### Mode 2: Single-Node Wrapping

The entire compiled graph runs as one AFMX node. LangGraph handles its own routing; AFMX wraps it with retry + timeout.

```python
node = adapter.to_afmx_node(
    compiled_graph,
    node_name="reasoning_graph",
    timeout_policy=TimeoutPolicy(timeout_seconds=120.0),
    retry_policy=RetryPolicy(retries=2),
)
```

### State Management

In Mode 1, each LangGraph node's handler:
1. Receives current state via `node_input["input"]` + `node_input["memory"]`
2. Calls the LangGraph node function
3. Returns the state update

In Mode 2, the full graph receives `{input: ..., ...params}` and returns the final state dict.

---

## CrewAI Adapter

Wraps individual CrewAI agents and tasks, or translates an entire `Crew` into a matrix.

### Install

```bash
pip install "afmx[crewai]"   # or: pip install crewai
```

### Wrap a Single Task

```python
from afmx.adapters.crewai import CrewAIAdapter
from crewai import Agent, Task

researcher = Agent(role="Researcher", goal="Find facts", backstory="Expert researcher")
task = Task(description="Research AI agent frameworks", agent=researcher)

adapter = CrewAIAdapter()
node = adapter.to_afmx_node(task, node_name="research_task")
```

### Translate a Full Crew

```python
from crewai import Crew

crew = Crew(
    agents=[researcher, writer, reviewer],
    tasks=[research_task, writing_task, review_task],
)

matrix = adapter.translate_crew(
    crew,
    matrix_name="research-crew",
    default_timeout=120.0,
    default_retries=1,
)
```

Each task becomes a SEQUENTIAL AFMX node. Hierarchical process maps to HYBRID mode.

### Execution

The adapter tries these invocation methods in order:
1. `execute_sync(input)` / `execute(input)` — Task
2. `kickoff(inputs={...})` — Crew or Agent
3. Direct callable

---

## OpenAI Adapter

Two modes: **Function Tool** (Chat Completions + auto-generated JSON schema) and **Assistants API** (thread → run → poll → message).

### Install

```bash
pip install "afmx[openai]"   # or: pip install openai>=1.0.0
export OPENAI_API_KEY="sk-..."
```

### Mode 1: Function Tool

Wraps a Python function. The adapter auto-generates the OpenAI JSON schema from type hints, calls GPT-4, parses the tool call, and executes the Python function.

```python
from afmx.adapters.openai import OpenAIAdapter

adapter = OpenAIAdapter(model="gpt-4o", temperature=0.0)

def get_weather(city: str, units: str = "celsius") -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 22, "units": units}

node = adapter.tool_node(
    fn=get_weather,
    description="Get current weather conditions for any city",
    node_id="weather-tool",
    system_prompt="You are a helpful weather assistant.",
)
```

**Schema auto-generation:**
- Type hints → JSON types (`str→string`, `int→integer`, `float→number`, `bool→boolean`, `dict→object`, `list→array`)
- Parameters with no default → `required`
- Function docstring first line → description (if not provided)

**Output shape:**
```python
{
    "function_called": "get_weather",    # or None if model responded with text
    "arguments": {"city": "Hyderabad"},  # args the model chose
    "result": {"city": "Hyderabad", "temp": 22, "units": "celsius"},  # fn return value
    "model": "gpt-4o",
    "tokens": 142
}
```

### Mode 2: Assistants API

Creates a thread, adds the input as a user message, runs the assistant, polls until complete, returns the final message.

```python
node = adapter.assistant_node(
    assistant_id="asst_abc123",
    node_id="ai-assistant",
    node_name="Research Assistant",
    additional_instructions="Focus on recent developments only.",
    timeout_policy=TimeoutPolicy(timeout_seconds=120.0),
)
```

Poll interval: 1 second. Max polls: 120 (2 minutes total before timeout).

**Output shape:**
```python
{
    "response": "Here is the analysis...",
    "thread_id": "thread_abc",
    "run_id": "run_xyz",
    "assistant_id": "asst_abc123",
    "polls": 4
}
```

### Generic to_afmx_node

Pass a callable → routes to `tool_node`. Pass an `asst_*` string → routes to `assistant_node`.

```python
adapter.to_afmx_node(my_function)      # → tool_node
adapter.to_afmx_node("asst_abc123")    # → assistant_node
```

---

## Writing a Custom Adapter

```python
from afmx.adapters.base import AFMXAdapter, AdapterResult
from afmx.adapters.registry import adapter_registry
from afmx.models.node import Node, NodeType

@adapter_registry.register_adapter
class MyFrameworkAdapter(AFMXAdapter):

    @property
    def name(self) -> str:
        return "my_framework"

    def to_afmx_node(
        self,
        external_obj,
        *,
        node_id=None,
        node_name=None,
        node_type=NodeType.FUNCTION,
        retry_policy=None,
        timeout_policy=None,
        extra_config=None,
    ) -> Node:
        handler_key = f"my_framework:{id(external_obj)}"

        # Register handler so the engine can call it
        from afmx.core.executor import HandlerRegistry
        HandlerRegistry.register(handler_key, self.make_handler(external_obj))

        return self._make_node(
            handler_key=handler_key,
            external_ref=external_obj,
            node_id=node_id,
            node_name=node_name or "my_node",
            node_type=node_type,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
            extra_config=extra_config,
        )

    async def execute(self, node_input: dict, external_ref) -> AdapterResult:
        try:
            result = await external_ref.run(node_input["input"])
            return self.normalize(result)
        except Exception as exc:
            return AdapterResult.fail(str(exc), type(exc).__name__)

    def normalize(self, raw_output) -> AdapterResult:
        if isinstance(raw_output, str):
            return AdapterResult.ok(output={"result": raw_output})
        return AdapterResult.ok(output=raw_output)
```

The `_make_node()` helper (from `AFMXAdapter` base) handles Node construction with all default policies.

---

## AdapterResult

Every adapter's `execute()` method returns an `AdapterResult`:

```python
# Success
AdapterResult.ok(output={"key": "value"}, latency_ms=45)

# Failure
AdapterResult.fail("Network timeout", error_type="TimeoutError", node_id="n1")

# Fields
result.success    # bool
result.output     # Any — the node's output
result.error      # str — error message
result.error_type # str — exception class name
result.metadata   # dict — extra metadata (kwargs passed to ok/fail)
```

When `success=False`, the registered handler raises `RuntimeError(error)` which AFMX catches and records as `NodeStatus.FAILED`.
