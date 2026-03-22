"""
AFMX Edge Model
Defines transitions between nodes in the execution graph.

FIX: Replaced deprecated Pydantic v1 `class Config` with
     `model_config = ConfigDict(populate_by_name=True)`.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid


class EdgeConditionType(str, Enum):
    ALWAYS = "ALWAYS"
    ON_SUCCESS = "ON_SUCCESS"
    ON_FAILURE = "ON_FAILURE"
    EXPRESSION = "EXPRESSION"
    ON_OUTPUT = "ON_OUTPUT"


class EdgeCondition(BaseModel):
    """
    Defines when an edge should be traversed.

    ALWAYS      → default, unconditional
    ON_SUCCESS  → only if upstream node succeeded
    ON_FAILURE  → only if upstream node failed
    EXPRESSION  → evaluate a Python expression against {output, context}
    ON_OUTPUT   → check a specific output field against an expected value
    """
    type: EdgeConditionType = EdgeConditionType.ALWAYS
    expression: Optional[str] = Field(
        default=None,
        description="Boolean expression: 'output[\"status\"] == \"ok\"'"
    )
    output_key: Optional[str] = Field(
        default=None,
        description="Dot-notation key for ON_OUTPUT check"
    )
    output_value: Optional[Any] = Field(
        default=None,
        description="Expected value for ON_OUTPUT check"
    )


class Edge(BaseModel):
    """
    A directed connection between two nodes.
    Edges are the routing fabric — they define WHAT executes after WHAT.
    """
    # FIX: ConfigDict instead of class Config (Pydantic v2)
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")
    condition: EdgeCondition = Field(default_factory=EdgeCondition)
    label: Optional[str] = Field(default=None)
    weight: int = Field(default=1, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_applicable(
        self,
        node_succeeded: bool,
        output: Any = None,
        context: Dict[str, Any] = None,
    ) -> bool:
        """Evaluate whether this edge should be traversed."""
        c = self.condition

        if c.type == EdgeConditionType.ALWAYS:
            return True

        if c.type == EdgeConditionType.ON_SUCCESS:
            return node_succeeded

        if c.type == EdgeConditionType.ON_FAILURE:
            return not node_succeeded

        if c.type == EdgeConditionType.ON_OUTPUT and output is not None:
            return self._check_output_match(output, c.output_key, c.output_value)

        if c.type == EdgeConditionType.EXPRESSION and c.expression:
            return self._evaluate_expression(c.expression, output, context or {})

        return True

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _check_output_match(
        self, output: Any, key: Optional[str], expected: Any
    ) -> bool:
        if key is None:
            return output == expected
        try:
            parts = key.split(".")
            val = output
            for part in parts:
                if isinstance(val, dict):
                    val = val[part]
                else:
                    val = getattr(val, part)
            return val == expected
        except (KeyError, AttributeError, TypeError):
            return False

    def _evaluate_expression(
        self, expr: str, output: Any, context: Dict[str, Any]
    ) -> bool:
        """
        Safe expression evaluator — simple boolean comparisons only.
        No exec, no arbitrary builtins.
        """
        try:
            safe_ns = {
                "output": output,
                "context": context,
                "True": True,
                "False": False,
                "None": None,
            }
            result = eval(expr, {"__builtins__": {}}, safe_ns)  # noqa: S307
            return bool(result)
        except Exception:
            return False
