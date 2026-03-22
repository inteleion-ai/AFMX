"""
Pytest configuration for AFMX test suite.

asyncio_mode = "auto" is set in pyproject.toml.
The session-scoped event_loop fixture is removed — it was deprecated
in pytest-asyncio >= 0.21. With asyncio_mode="auto", each test function
gets its own event loop by default which is the correct behavior.
"""
import pytest


# No custom event_loop fixture needed — asyncio_mode="auto" handles it.
# Shared fixtures for all tests go here.
