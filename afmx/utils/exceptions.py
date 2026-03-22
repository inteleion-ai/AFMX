"""
AFMX Custom Exceptions
Structured exception hierarchy for clean error propagation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class AFMXException(Exception):
    """Base exception for all AFMX errors."""
    status_code: int = 500
    error_code: str = "AFMX_ERROR"

    def __init__(
        self,
        message: str,
        details: Optional[Any] = None,
        error_code: Optional[str] = None,
    ):
        self.message = message
        self.details = details
        if error_code:
            self.error_code = error_code
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class MatrixValidationError(AFMXException):
    """Raised when an ExecutionMatrix fails validation."""
    status_code = 422
    error_code = "MATRIX_VALIDATION_ERROR"


class MatrixCycleError(AFMXException):
    """Raised when a cycle is detected in the execution DAG."""
    status_code = 422
    error_code = "MATRIX_CYCLE_ERROR"


class NodeNotFoundError(AFMXException):
    """Raised when a referenced node cannot be found."""
    status_code = 404
    error_code = "NODE_NOT_FOUND"


class HandlerNotFoundError(AFMXException):
    """Raised when a handler cannot be resolved from the registry."""
    status_code = 404
    error_code = "HANDLER_NOT_FOUND"


class ExecutionNotFoundError(AFMXException):
    """Raised when an execution record cannot be found."""
    status_code = 404
    error_code = "EXECUTION_NOT_FOUND"


class ExecutionTimeoutError(AFMXException):
    """Raised when global or node-level timeout is exceeded."""
    status_code = 408
    error_code = "EXECUTION_TIMEOUT"


class ExecutionAbortedError(AFMXException):
    """Raised when an execution is aborted mid-flight."""
    status_code = 409
    error_code = "EXECUTION_ABORTED"


class CircuitBreakerOpenError(AFMXException):
    """Raised when a circuit breaker is OPEN and blocks execution."""
    status_code = 503
    error_code = "CIRCUIT_BREAKER_OPEN"


class ToolRoutingError(AFMXException):
    """Raised when the tool router cannot resolve a handler."""
    status_code = 400
    error_code = "TOOL_ROUTING_ERROR"


class AgentDispatchError(AFMXException):
    """Raised when the agent dispatcher cannot route a task."""
    status_code = 400
    error_code = "AGENT_DISPATCH_ERROR"


class PluginNotFoundError(AFMXException):
    """Raised when a plugin key is not found in the registry."""
    status_code = 404
    error_code = "PLUGIN_NOT_FOUND"


class StoreError(AFMXException):
    """Raised on state store read/write failures."""
    status_code = 500
    error_code = "STORE_ERROR"


class ConfigurationError(AFMXException):
    """Raised on invalid or missing configuration."""
    status_code = 500
    error_code = "CONFIGURATION_ERROR"
