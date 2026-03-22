"""
AFMX Adapter Routes
===================
REST API endpoints for the adapter layer.

Endpoints:
    GET  /afmx/adapters          — list all registered adapters
    POST /afmx/adapters/register — register an adapter by class name (dev/debug)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)

adapter_router = APIRouter()


def get_adapter_registry():
    from afmx.main import afmx_app
    return afmx_app.adapter_registry


@adapter_router.get(
    "/adapters",
    summary="List all registered framework adapters",
    tags=["Adapters"],
)
async def list_adapters(registry=Depends(get_adapter_registry)):
    """
    Returns all framework adapters registered with AFMX.
    Adapters translate external frameworks (LangChain, LangGraph, CrewAI)
    into AFMX-executable nodes.
    """
    return {
        "adapters": registry.list_adapters(),
        "count": len(registry.list_adapters()),
    }
