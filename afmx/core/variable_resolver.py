"""
AFMX Variable Resolver — bug-fixed version
Fixes:
  - _evaluate: removed unreachable `return self._dig(target, rest)` after branch exhaustion
  - input path: digs correctly into rest when root == "input" and rest is non-empty
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from afmx.models.execution import ExecutionContext

logger = logging.getLogger(__name__)

# Matches {{some.dot.path}} — non-greedy match inside double braces
_TEMPLATE_RE = re.compile(r"\{\{([^}]+?)\}\}")


class VariableResolver:
    """
    Resolves {{template}} expressions in node config params against
    the live ExecutionContext at the moment a node is about to run.

    Supported roots:
        {{input}}                       root input value (any type)
        {{input.field.nested}}          nested field on input object/dict
        {{node.<id>.output}}            entire output dict of a previous node
        {{node.<id>.output.<field>}}    specific field from previous node output
        {{memory.<key>}}                value from shared execution memory
        {{variables.<key>}}             runtime variable
        {{metadata.<key>}}              execution metadata field

    Resolution rules:
        - Full-expression param  (e.g. "{{input.x}}")  → typed value (int, dict, etc.)
        - Mixed-string param     (e.g. "prefix {{x}}") → string interpolation
        - Dict/list params       → resolved recursively
        - Unresolvable           → None for full-expr; original token for mixed-string
    """

    def resolve_params(
        self,
        params: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """
        Walk all param values and resolve any template expressions.
        Returns a new dict — never mutates the original.
        """
        return {k: self._resolve_value(v, context) for k, v in params.items()}

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _resolve_value(self, value: Any, context: ExecutionContext) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value, context)
        if isinstance(value, dict):
            return {k: self._resolve_value(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, context) for item in value]
        return value

    def _resolve_string(self, value: str, context: ExecutionContext) -> Any:
        matches = _TEMPLATE_RE.findall(value)
        if not matches:
            return value

        stripped = value.strip()
        # Single full-expression → return typed value (not stringified)
        if stripped == f"{{{{{matches[0]}}}}}" and len(matches) == 1:
            return self._evaluate(matches[0].strip(), context)

        # Mixed/multiple expressions → string interpolation
        def replacer(m: re.Match) -> str:
            expr = m.group(1).strip()
            result = self._evaluate(expr, context)
            return str(result) if result is not None else m.group(0)

        return _TEMPLATE_RE.sub(replacer, value)

    def _evaluate(self, expr: str, context: ExecutionContext) -> Any:
        """
        Evaluate a single dot-path expression against the context.
        Returns None if path cannot be resolved.
        """
        parts = expr.split(".")
        root = parts[0]
        rest = parts[1:]

        try:
            if root == "input":
                # {{input}} or {{input.field.nested}}
                return self._dig(context.input, rest)

            if root == "memory":
                # {{memory}} or {{memory.key}}
                if not rest:
                    return context.memory
                return context.get_memory(rest[0])

            if root == "variables":
                # {{variables}} or {{variables.key}}
                if not rest:
                    return context.variables
                return context.variables.get(rest[0])

            if root == "metadata":
                # {{metadata}} or {{metadata.key}}
                if not rest:
                    return context.metadata
                return context.metadata.get(rest[0])

            if root == "node":
                # {{node.<id>}} or {{node.<id>.output}} or {{node.<id>.output.<field>...}}
                if not rest:
                    return None
                node_id = rest[0]
                node_output = context.get_node_output(node_id)
                remainder = rest[1:]  # e.g. ["output", "field"] or []
                if not remainder:
                    return node_output
                # Skip the literal "output" keyword if present
                field_path = remainder[1:] if remainder[0] == "output" else remainder
                return self._dig(node_output, field_path)

            logger.debug(f"[VariableResolver] Unknown root '{root}' in '{expr}'")
            return None

        except Exception as exc:
            logger.debug(f"[VariableResolver] Could not resolve '{{{{{expr}}}}}': {exc}")
            return None

    @staticmethod
    def _dig(target: Any, path: List[str]) -> Any:
        """
        Navigate into a nested dict / object using a path list.
        Returns None if any step fails — never raises.
        """
        current = target
        for part in path:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
        return current


# Module-level singleton
resolver = VariableResolver()
