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
AFMX Integrations
==================
First-party integrations with the Agentdyne9 platform ecosystem and
external observability / governance systems.

Available integrations
----------------------
agentability  —  Observability platform. Captures every node execution as an
                 Agentability Decision with confidence, cost, and reasoning chain.

hyperstate    —  Cognitive memory layer. RETRIEVE-layer nodes query HyperState
                 for persistent, temporal, policy-aware memory. REASON/PLAN/EVALUATE
                 outputs are stored back for future runs.

map_plugin    —  Memory Augmentation Platform. Provides deterministic, SHA-256
                 verified, provenanced context to RETRIEVE-layer nodes.

rhfl          —  Responsible Human Feedback Loop. Gates ACT-layer nodes through
                 the RHFL governance and human-in-the-loop control plane.
                 AUTO / REVIEW / BLOCK / ESCALATE classification per action.

Quick start::

    # Agentability — attach at AFMX startup
    from afmx.integrations.agentability_hook import attach_to_afmx
    attach_to_afmx(afmx_app.hook_registry, afmx_app.event_bus, db_path="obs.db")

    # HyperState — cognitive memory for RETRIEVE nodes
    from afmx.integrations.hyperstate import attach_hyperstate
    attach_hyperstate(
        api_url="http://localhost:8000",
        api_key="hs_...",
        hook_registry=afmx_app.hook_registry,
        inject_into_memory=True,
        persist_agent_outputs=True,
    )

    # MAP — verified, deterministic context
    from map.service import MAPService
    from afmx.integrations.map_plugin import attach_map
    map_svc = await MAPService.create()
    await attach_map(service=map_svc, hook_registry=afmx_app.hook_registry)

    # RHFL — human governance gate for ACT-layer nodes
    from afmx.integrations.rhfl import attach_rhfl
    attach_rhfl(
        api_url="http://rhfl.internal:4000/api/v1",
        token=os.getenv("RHFL_TOKEN"),
        hook_registry=afmx_app.hook_registry,
        gate_act_nodes=True,
    )
"""
