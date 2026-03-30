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
AFMX Amazon Bedrock Agents Adapter
=====================================
Wraps Amazon Bedrock Agents and Bedrock InvokeModel calls as AFMX nodes.

Amazon Bedrock is the dominant enterprise AI platform on AWS.  This adapter
integrates two Bedrock entry points:

1. **Bedrock Agents** (``agents-runtime``) — fully managed agent execution
   with action groups and knowledge bases. Maps to AFMX AGENT nodes.

2. **Bedrock InvokeModel** — direct model invocation (Claude, Llama, Titan,
   Mistral, etc.). Maps to AFMX FUNCTION nodes at any cognitive layer.

Install::

    pip install afmx[bedrock]
    # or: pip install boto3>=1.34.0

Usage::

    from afmx.adapters.bedrock import BedrockAdapter

    adapter = BedrockAdapter(region_name="us-east-1")

    # Invoke a Bedrock Agent
    node = adapter.agent_node(
        agent_id="AGENT_ID_HERE",
        agent_alias_id="TSTALIASID",
        node_name="risk-agent",
        cognitive_layer="REASON",
    )

    # Invoke a model directly (Claude on Bedrock)
    node = adapter.model_node(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        node_name="analyst",
        cognitive_layer="REASON",
    )

    matrix = ExecutionMatrix(nodes=[node], mode=ExecutionMode.DIAGONAL)

Authentication::

    AWS credentials are read from the standard boto3 chain:
    environment variables → ~/.aws/credentials → IAM role.

    # Required IAM permissions:
    # bedrock:InvokeAgent, bedrock-runtime:InvokeModel
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from afmx.adapters.base import AdapterResult, AFMXAdapter
from afmx.core.executor import HandlerRegistry
from afmx.models.node import CognitiveLayer, Node, NodeConfig, NodeType, RetryPolicy, TimeoutPolicy

logger = logging.getLogger(__name__)

_HANDLER_PREFIX = "bedrock:"


def _require_boto3() -> None:
    try:
        import boto3  # noqa: F401
    except ImportError:
        raise ImportError(
            "boto3 is required for BedrockAdapter.\n"
            "Install: pip install afmx[bedrock]  or  pip install boto3>=1.34.0"
        ) from None


class BedrockAdapter(AFMXAdapter):
    """
    AFMX adapter for Amazon Bedrock Agents and model invocations.

    Args:
        region_name: AWS region (e.g. ``"us-east-1"``).
        profile_name: Optional AWS profile name.
        session: Optional pre-configured ``boto3.Session``.
    """

    def __init__(
        self,
        *,
        region_name: str = "us-east-1",
        profile_name: Optional[str] = None,
        session: Any = None,
    ) -> None:
        _require_boto3()
        import boto3

        self._session = session or boto3.Session(
            region_name=region_name,
            profile_name=profile_name,
        )
        self._region = region_name

    @property
    def name(self) -> str:
        return "bedrock"

    # ── AFMXAdapter contract ──────────────────────────────────────────────────

    def to_afmx_node(
        self,
        external_obj: Any,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: NodeType = NodeType.AGENT,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Node:
        """
        Convert a Bedrock configuration dict to an AFMX node.

        ``external_obj`` should be a dict with ``"agent_id"`` (for Bedrock Agents)
        or ``"model_id"`` (for direct model invocation).
        """
        if not isinstance(external_obj, dict):
            raise TypeError(
                "BedrockAdapter.to_afmx_node expects a dict with "
                "'agent_id' or 'model_id'. "
                "Use agent_node() or model_node() for a better API."
            )
        if "agent_id" in external_obj:
            return self.agent_node(
                agent_id=external_obj["agent_id"],
                agent_alias_id=external_obj.get("agent_alias_id", "TSTALIASID"),
                node_id=node_id,
                node_name=node_name,
                retry_policy=retry_policy,
                timeout_policy=timeout_policy,
            )
        return self.model_node(
            model_id=external_obj.get("model_id", "anthropic.claude-3-haiku-20240307-v1:0"),
            node_id=node_id,
            node_name=node_name,
            retry_policy=retry_policy,
            timeout_policy=timeout_policy,
        )

    async def execute(
        self,
        node_input: Dict[str, Any],
        external_ref: Any,
    ) -> AdapterResult:
        if isinstance(external_ref, dict) and "agent_id" in external_ref:
            return await self._invoke_agent(
                agent_id=external_ref["agent_id"],
                agent_alias_id=external_ref.get("agent_alias_id", "TSTALIASID"),
                node_input=node_input,
            )
        model_id = external_ref if isinstance(external_ref, str) else external_ref.get("model_id", "")
        return await self._invoke_model(model_id=model_id, node_input=node_input)

    def normalize(self, raw_output: Any) -> AdapterResult:
        if isinstance(raw_output, dict):
            return AdapterResult.ok(output=raw_output)
        return AdapterResult.ok(output={"result": str(raw_output)})

    # ── Public node factories ─────────────────────────────────────────────────

    def agent_node(
        self,
        agent_id: str,
        agent_alias_id: str = "TSTALIASID",
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        cognitive_layer: Optional[CognitiveLayer] = None,
        agent_role: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
    ) -> Node:
        """
        Wrap a Bedrock Agent as an AFMX AGENT node.

        Args:
            agent_id: Bedrock Agent ID (e.g. ``"ABCDEF1234"``).
            agent_alias_id: Alias ID (use ``"TSTALIASID"`` for dev).

        Returns:
            AFMX node that invokes the Bedrock Agent via
            ``bedrock-agent-runtime:invoke_agent``.
        """
        # _require_boto3() is intentionally NOT called here — it was already
        # enforced in __init__.  Calling it here would break unit tests that
        # bypass __init__ via BedrockAdapter.__new__.
        handler_key = f"{_HANDLER_PREFIX}agent.{agent_id}"
        layer       = cognitive_layer or CognitiveLayer.REASON

        _adapter        = self
        _agent_id       = agent_id
        _agent_alias_id = agent_alias_id

        async def _bedrock_agent_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await _adapter._invoke_agent(
                agent_id=_agent_id,
                agent_alias_id=_agent_alias_id,
                node_input=node_input,
            )
            if not result.success:
                raise RuntimeError(f"[Bedrock:agent:{_agent_id}] {result.error}")
            return result.output

        _bedrock_agent_handler.__name__ = f"bedrock_agent_{agent_id}"
        HandlerRegistry.register(handler_key, _bedrock_agent_handler)

        return Node(
            id=node_id or str(uuid.uuid4()),
            name=node_name or f"bedrock-agent-{agent_id[:8]}",
            type=NodeType.AGENT,
            handler=handler_key,
            cognitive_layer=layer,
            agent_role=agent_role,
            config=NodeConfig(
                params={
                    "agent_id":       agent_id,
                    "agent_alias_id": agent_alias_id,
                    "region":         self._region,
                },
                tags=["bedrock", "bedrock-agent"],
            ),
            retry_policy=retry_policy or RetryPolicy(retries=1, backoff_seconds=2.0),
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=120.0),
            metadata={
                "adapter":         "bedrock",
                "agent_id":        agent_id,
                "agent_alias_id":  agent_alias_id,
                "region":          self._region,
            },
        )

    def model_node(
        self,
        model_id: str,
        *,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        cognitive_layer: Optional[CognitiveLayer] = None,
        agent_role: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
    ) -> Node:
        """
        Wrap a Bedrock model invocation as an AFMX FUNCTION node.

        Supports Anthropic Claude (messages API), Meta Llama, Amazon Titan,
        Mistral, and Cohere via the unified ``bedrock-runtime:invoke_model``.

        Args:
            model_id: Full Bedrock model ID
                (e.g. ``"anthropic.claude-3-5-sonnet-20241022-v2:0"``).
            system_prompt: Optional system prompt for the model.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.
        """
        # _require_boto3() not called here — enforced in __init__ (see agent_node comment).
        from afmx.adapters.mcp import infer_cognitive_layer

        handler_key = f"{_HANDLER_PREFIX}model.{model_id.replace(':', '_').replace('.', '_')}"
        layer = cognitive_layer or _model_id_to_layer(model_id)

        _adapter       = self
        _model_id      = model_id
        _system_prompt = system_prompt
        _max_tokens    = max_tokens
        _temperature   = temperature

        async def _bedrock_model_handler(
            node_input: Dict[str, Any],
            context: Any,
            node: Any,
        ) -> Any:
            result = await _adapter._invoke_model(
                model_id=_model_id,
                node_input=node_input,
                system_prompt=_system_prompt,
                max_tokens=_max_tokens,
                temperature=_temperature,
            )
            if not result.success:
                raise RuntimeError(f"[Bedrock:model:{_model_id}] {result.error}")
            return result.output

        _bedrock_model_handler.__name__ = f"bedrock_model_{model_id[:32].replace(':', '_')}"
        HandlerRegistry.register(handler_key, _bedrock_model_handler)

        # Infer short name from model ID
        short_name = model_id.split(".")[-1].split(":")[0]

        return Node(
            id=node_id or str(uuid.uuid4()),
            name=node_name or short_name,
            type=NodeType.FUNCTION,
            handler=handler_key,
            cognitive_layer=layer,
            agent_role=agent_role,
            config=NodeConfig(
                params={
                    "model_id":    model_id,
                    "max_tokens":  max_tokens,
                    "temperature": temperature,
                    "region":      self._region,
                },
                tags=["bedrock", "bedrock-model"],
            ),
            retry_policy=retry_policy or RetryPolicy(retries=2, backoff_seconds=1.0),
            timeout_policy=timeout_policy or TimeoutPolicy(timeout_seconds=60.0),
            metadata={
                "adapter":    "bedrock",
                "model_id":   model_id,
                "region":     self._region,
                "max_tokens": max_tokens,
            },
        )

    # ── Internal execution ────────────────────────────────────────────────────

    async def _invoke_agent(
        self,
        agent_id: str,
        agent_alias_id: str,
        node_input: Dict[str, Any],
    ) -> AdapterResult:
        """Invoke a Bedrock Agent via bedrock-agent-runtime."""
        _require_boto3()
        params     = node_input.get("params", {})
        raw_input  = node_input.get("input", "")
        input_text = (
            params.get("input_text")
            or (raw_input if isinstance(raw_input, str) else str(raw_input))
            or "Continue."
        )
        session_id = params.get("session_id") or str(uuid.uuid4())

        try:
            client = self._session.client("bedrock-agent-runtime")
            loop   = asyncio.get_running_loop()

            def _invoke():
                resp = client.invoke_agent(
                    agentId=agent_id,
                    agentAliasId=agent_alias_id,
                    sessionId=session_id,
                    inputText=input_text,
                )
                # Collect streaming response
                output_text = ""
                for event in resp["completion"]:
                    if "chunk" in event:
                        chunk = event["chunk"]
                        if "bytes" in chunk:
                            output_text += chunk["bytes"].decode("utf-8", errors="replace")
                return output_text

            output = await loop.run_in_executor(None, _invoke)
            return AdapterResult.ok(output={
                "text":       output,
                "agent_id":   agent_id,
                "session_id": session_id,
            })
        except Exception as exc:
            logger.error("[Bedrock:agent] Error: %s", exc, exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)

    async def _invoke_model(
        self,
        model_id: str,
        node_input: Dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> AdapterResult:
        """Invoke a Bedrock model directly via bedrock-runtime:invoke_model."""
        _require_boto3()
        params    = node_input.get("params", {})
        raw_input = node_input.get("input", "")
        prompt    = (
            params.get("prompt")
            or params.get("message")
            or (raw_input if isinstance(raw_input, str) else json.dumps(raw_input))
            or "Hello"
        )
        max_tokens = int(params.get("max_tokens", max_tokens))
        temperature = float(params.get("temperature", temperature))

        try:
            client = self._session.client("bedrock-runtime")
            loop   = asyncio.get_running_loop()

            # Build provider-specific request body
            request_body = _build_invoke_body(
                model_id=model_id,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            def _invoke():
                resp = client.invoke_model(
                    modelId=model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(request_body),
                )
                return json.loads(resp["body"].read())

            raw   = await loop.run_in_executor(None, _invoke)
            text  = _extract_response_text(model_id, raw)
            return AdapterResult.ok(output={"text": text, "model_id": model_id, "raw": raw})
        except Exception as exc:
            logger.error("[Bedrock:model] Error: %s", exc, exc_info=True)
            return AdapterResult.fail(str(exc), type(exc).__name__)


# ─── Helper functions ─────────────────────────────────────────────────────────


def _model_id_to_layer(model_id: str) -> CognitiveLayer:
    """
    Infer CognitiveLayer from a Bedrock model ID.

    Frontier models (Claude 3.5, Claude 3 Opus, Llama 3 70B) → REASON.
    Smaller/faster models (Haiku, Titan Lite) → RETRIEVE.
    """
    mid = model_id.lower()
    premium_signals = ("opus", "sonnet", "3-5", "70b", "llama-3-3", "mistral-large")
    cheap_signals   = ("haiku", "lite", "micro", "instant", "titan-text-lite")

    if any(s in mid for s in cheap_signals):
        return CognitiveLayer.RETRIEVE
    if any(s in mid for s in premium_signals):
        return CognitiveLayer.REASON
    return CognitiveLayer.REASON  # safe default


def _build_invoke_body(
    model_id: str,
    prompt: str,
    system_prompt: Optional[str],
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    """Build provider-specific invoke_model request body."""
    mid = model_id.lower()

    # Anthropic Claude (Messages API)
    if "anthropic" in mid:
        body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt
        return body

    # Meta Llama
    if "meta" in mid or "llama" in mid:
        full_prompt = f"<s>[INST] {system_prompt + chr(10) if system_prompt else ''}{prompt} [/INST]"
        return {
            "prompt":           full_prompt,
            "max_gen_len":      max_tokens,
            "temperature":      temperature,
        }

    # Amazon Titan
    if "amazon" in mid or "titan" in mid:
        config: Dict[str, Any] = {
            "maxTokenCount": max_tokens,
            "temperature":   temperature,
        }
        text = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        return {"inputText": text, "textGenerationConfig": config}

    # Mistral
    if "mistral" in mid:
        text = f"<s>[INST] {prompt} [/INST]"
        return {"prompt": text, "max_tokens": max_tokens, "temperature": temperature}

    # Cohere
    if "cohere" in mid:
        return {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}

    # Generic fallback
    return {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}


def _extract_response_text(model_id: str, raw: Dict[str, Any]) -> str:
    """Extract the text content from a Bedrock invoke_model response."""
    mid = model_id.lower()

    if "anthropic" in mid:
        content = raw.get("content", [])
        return content[0].get("text", "") if content else ""
    if "meta" in mid or "llama" in mid:
        return raw.get("generation", "")
    if "amazon" in mid or "titan" in mid:
        results = raw.get("results", [])
        return results[0].get("outputText", "") if results else ""
    if "mistral" in mid:
        outputs = raw.get("outputs", [])
        return outputs[0].get("text", "") if outputs else ""
    if "cohere" in mid:
        gens = raw.get("generations", [])
        return gens[0].get("text", "") if gens else ""

    # Last resort: stringify the whole response
    return json.dumps(raw)
