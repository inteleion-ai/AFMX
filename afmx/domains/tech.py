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
AFMX Domain Pack -- Technology / SRE / DevOps
==============================================

The DEFAULT domain pack. These are the roles used in software engineering,
site reliability engineering, platform engineering, and DevOps teams.

``AgentRole`` is a plain namespace class (not an Enum) for backward
compatibility with v1.1 code. Each constant equals its string value --
``AgentRole.OPS == "OPS"``.

For new code, prefer passing role strings directly::

    node = Node(agent_role="OPS", ...)

Apache-2.0 License. See LICENSE for details.
"""
from __future__ import annotations

from afmx.domains import DomainPack, domain_registry


class AgentRole:
    """Tech/SRE domain role string constants (backward-compatible namespace)."""

    RESEARCHER = "RESEARCHER"
    CODER = "CODER"
    ANALYST = "ANALYST"
    OPS = "OPS"
    COMPLIANCE = "COMPLIANCE"
    VERIFIER = "VERIFIER"
    PLANNER = "PLANNER"

    ALL: frozenset = frozenset({
        "RESEARCHER", "CODER", "ANALYST", "OPS",
        "COMPLIANCE", "VERIFIER", "PLANNER",
    })

    def __class_getitem__(cls, item: str) -> str:
        """Support AgentRole["OPS"] as an alternative access pattern."""
        return getattr(cls, item)


TechDomain = DomainPack(
    name="tech",
    description=(
        "Technology, software engineering, and site reliability engineering. "
        "Default domain for AFMX -- SRE incident response, CI/CD automation, "
        "platform engineering, DevOps workflows."
    ),
    roles={
        "RESEARCHER": "Research, investigation, document retrieval and synthesis",
        "CODER": "Code generation, implementation, debugging, refactoring",
        "ANALYST": "Data analysis, metrics interpretation, root-cause correlation",
        "OPS": "Operations, incident response, deployment, infrastructure",
        "COMPLIANCE": "Policy enforcement, security checks, regulatory alignment",
        "VERIFIER": "Testing, QA, validation, code review, acceptance criteria",
        "PLANNER": "Architecture decisions, sprint planning, roadmap strategy",
    },
    tags=["tech", "sre", "devops", "software", "platform", "incident-response"],
)

domain_registry.register(TechDomain)
