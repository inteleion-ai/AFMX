"""
Unit tests for AgentDispatcher
"""
import pytest
from afmx.core.dispatcher import (
    AgentDispatcher, DispatchRequest, AgentTier, DispatchPolicy,
)


async def default_agent(inp, ctx, node):
    return "default"


async def expert_agent(inp, ctx, node):
    return "expert"


async def specialist_agent(inp, ctx, node):
    return "specialist"


class TestAgentDispatcher:
    def test_explicit_dispatch(self):
        d = AgentDispatcher()
        d.register("expert", expert_agent, tier=AgentTier.EXPERT)
        req = DispatchRequest(task_id="t1", handler_key="expert")
        agent = d.dispatch(req)
        assert agent.key == "expert"

    def test_unknown_explicit_raises(self):
        d = AgentDispatcher()
        req = DispatchRequest(task_id="t1", handler_key="ghost")
        with pytest.raises(RuntimeError):
            d.dispatch(req)

    def test_complexity_routing_low(self):
        d = AgentDispatcher()
        d.register("default", default_agent, complexity_min=0.0, complexity_max=0.4)
        d.register("expert", expert_agent, complexity_min=0.7, complexity_max=1.0)
        req = DispatchRequest(task_id="t1", complexity=0.2, policy=DispatchPolicy.COMPLEXITY)
        agent = d.dispatch(req)
        assert agent.key == "default"

    def test_complexity_routing_high(self):
        d = AgentDispatcher()
        d.register("default", default_agent, complexity_min=0.0, complexity_max=0.4)
        d.register("expert", expert_agent, complexity_min=0.7, complexity_max=1.0)
        req = DispatchRequest(task_id="t1", complexity=0.9, policy=DispatchPolicy.COMPLEXITY)
        agent = d.dispatch(req)
        assert agent.key == "expert"

    def test_capability_routing(self):
        d = AgentDispatcher()
        d.register("nlp_agent", specialist_agent, capabilities=["nlp", "summarize"])
        d.register("code_agent", expert_agent, capabilities=["code", "debug"])
        req = DispatchRequest(
            task_id="t1",
            required_capabilities=["nlp"],
            policy=DispatchPolicy.CAPABILITY,
        )
        agent = d.dispatch(req)
        assert agent.key == "nlp_agent"

    def test_capability_missing_falls_through(self):
        d = AgentDispatcher()
        d.register("default", default_agent)
        d.set_default("default")
        req = DispatchRequest(
            task_id="t1",
            required_capabilities=["quantum"],
            policy=DispatchPolicy.CAPABILITY,
        )
        # Falls through to default
        agent = d.dispatch(req)
        assert agent.key == "default"

    def test_default_fallback(self):
        d = AgentDispatcher()
        d.register("fallback", default_agent)
        d.set_default("fallback")
        req = DispatchRequest(task_id="t1", complexity=0.5)
        agent = d.dispatch(req)
        assert agent.key == "fallback"

    def test_no_match_raises(self):
        d = AgentDispatcher()
        req = DispatchRequest(task_id="t1", complexity=0.5)
        with pytest.raises(RuntimeError):
            d.dispatch(req)

    def test_concurrency_limit(self):
        d = AgentDispatcher()
        d.register("limited", default_agent, max_concurrent=1)
        agent = d.dispatch(DispatchRequest(task_id="t1", handler_key="limited"))
        agent.acquire()
        # Now at capacity
        with pytest.raises(RuntimeError):
            d.dispatch(DispatchRequest(task_id="t2", handler_key="limited"))
        agent.release()
        # Should work again
        a2 = d.dispatch(DispatchRequest(task_id="t3", handler_key="limited"))
        assert a2.key == "limited"

    def test_sticky_routing(self):
        d = AgentDispatcher()
        d.register("agent_a", default_agent, capabilities=["x"])
        d.register("agent_b", expert_agent, capabilities=["x"])
        req1 = DispatchRequest(
            task_id="t1",
            required_capabilities=["x"],
            policy=DispatchPolicy.STICKY,
            session_id="sess-001",
        )
        first = d.dispatch(req1)
        first_key = first.key
        # Same session — should get same agent
        req2 = DispatchRequest(
            task_id="t2",
            required_capabilities=["x"],
            policy=DispatchPolicy.STICKY,
            session_id="sess-001",
        )
        second = d.dispatch(req2)
        assert second.key == first_key

    def test_list_agents(self):
        d = AgentDispatcher()
        d.register("a1", default_agent, tier=AgentTier.DEFAULT)
        d.register("a2", expert_agent, tier=AgentTier.EXPERT)
        agents = d.list_agents()
        assert len(agents) == 2
