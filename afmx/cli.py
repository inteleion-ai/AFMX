"""
AFMX CLI
Command-line tool for interacting with a running AFMX server.

Usage:
    python -m afmx.cli --help
    python -m afmx.cli run --matrix examples/matrix.json --input '{"query":"test"}'
    python -m afmx.cli status <execution_id>
    python -m afmx.cli validate --matrix examples/matrix.json
    python -m afmx.cli list
    python -m afmx.cli plugins
    python -m afmx.cli serve
    python -m afmx.cli health
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ─── HTTP Client ──────────────────────────────────────────────────────────────

def _base_url() -> str:
    host = os.getenv("AFMX_HOST", "localhost")
    port = os.getenv("AFMX_PORT", "8100")
    return f"http://{host}:{port}"


async def _request(method: str, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
    try:
        import httpx
    except ImportError:
        print("❌  httpx not installed. Run: pip install httpx")
        sys.exit(1)

    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            resp = await client.post(url, json=body or {})
        elif method == "DELETE":
            resp = await client.delete(url)
        else:
            raise ValueError(f"Unsupported method: {method}")
    resp.raise_for_status()
    return resp.json()


# ─── Formatters ───────────────────────────────────────────────────────────────

def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _print_table(rows: list[dict], columns: list[str]) -> None:
    if not rows:
        print("  (no results)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  " + "  ".join(c.upper().ljust(widths[c]) for c in columns)
    print(header)
    print("  " + "─" * (sum(widths.values()) + 2 * len(columns)))
    for row in rows:
        line = "  " + "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns)
        print(line)


def _status_icon(status: str) -> str:
    return {
        "COMPLETED": "✅", "FAILED": "❌", "RUNNING": "⏳",
        "QUEUED": "🕐", "ABORTED": "🚫", "TIMEOUT": "⏱",
        "PARTIAL": "⚠️",
    }.get(status, "❓")


# ─── Commands ─────────────────────────────────────────────────────────────────

async def cmd_run(args) -> None:
    """Execute a matrix from a JSON file or inline."""
    matrix_def = None

    if args.matrix:
        path = Path(args.matrix)
        if not path.exists():
            print(f"❌  Matrix file not found: {args.matrix}")
            sys.exit(1)
        matrix_def = json.loads(path.read_text())
    elif args.inline:
        matrix_def = json.loads(args.inline)
    else:
        print("❌  Provide --matrix <file> or --inline '<json>'")
        sys.exit(1)

    input_data = json.loads(args.input) if args.input else None
    variables  = json.loads(args.variables) if args.variables else None
    metadata   = json.loads(args.metadata) if args.metadata else None

    payload = {
        "matrix": matrix_def,
        "input": input_data,
        "variables": variables,
        "metadata": metadata,
        "triggered_by": args.triggered_by or "cli",
    }

    endpoint = "/afmx/execute/async" if args.async_ else "/afmx/execute"
    print(f"▶  Executing '{matrix_def.get('name', 'matrix')}' "
          f"({'async' if args.async_ else 'sync'})...")

    t0 = time.perf_counter()
    result = await _request("POST", endpoint, payload)
    elapsed = (time.perf_counter() - t0) * 1000

    if args.async_:
        print(f"\n  Execution ID : {result['execution_id']}")
        print(f"  Poll URL     : {_base_url()}{result['poll_url']}")
        print(f"  Status       : {result['status']}")

        if args.watch:
            await _watch_execution(result["execution_id"])
    else:
        status = result.get("status", "?")
        icon   = _status_icon(status)
        print(f"\n  {icon} Status       : {status}")
        print(f"  Execution ID : {result.get('execution_id')}")
        print(f"  Duration     : {result.get('duration_ms', elapsed):.1f}ms")
        print(f"  Nodes        : {result.get('completed_nodes')}/{result.get('total_nodes')} completed")

        if result.get("error"):
            print(f"  Error        : {result['error']}")

        if args.verbose:
            print("\n  Node Results:")
            for nid, nr in result.get("node_results", {}).items():
                icon_n = "✅" if nr.get("status") == "SUCCESS" else "❌"
                print(f"    {icon_n} {nr.get('node_name', nid):25s} "
                      f"{nr.get('status', '?'):10s} "
                      f"{nr.get('duration_ms', 0):.1f}ms")


async def _watch_execution(execution_id: str) -> None:
    """Poll status until terminal."""
    print(f"\n  Watching '{execution_id}'...")
    terminal = {"COMPLETED", "FAILED", "ABORTED", "TIMEOUT", "PARTIAL"}
    while True:
        await asyncio.sleep(1.0)
        try:
            status_data = await _request("GET", f"/afmx/status/{execution_id}")
            status = status_data.get("status", "?")
            completed = status_data.get("completed_nodes", 0)
            total = status_data.get("total_nodes", 0)
            print(f"  ⏳ {status:12s} | {completed}/{total} nodes", end="\r")
            if status in terminal:
                icon = _status_icon(status)
                print(f"\n  {icon} Final: {status} | "
                      f"{status_data.get('duration_ms', 0):.1f}ms")
                break
        except Exception as exc:
            print(f"\n  ⚠️  Poll error: {exc}")
            break


async def cmd_status(args) -> None:
    """Get status of an execution."""
    data = await _request("GET", f"/afmx/status/{args.execution_id}")
    status = data.get("status", "?")
    icon   = _status_icon(status)
    print(f"\n  {icon} {data.get('matrix_name', '?')} — {status}")
    print(f"  Execution ID : {data.get('execution_id')}")
    print(f"  Nodes        : {data.get('completed_nodes')}/{data.get('total_nodes')} "
          f"(failed={data.get('failed_nodes')}, skipped={data.get('skipped_nodes')})")
    if data.get("duration_ms"):
        print(f"  Duration     : {data['duration_ms']:.1f}ms")
    if data.get("error"):
        print(f"  Error        : {data['error']}")


async def cmd_result(args) -> None:
    """Get full execution result including node outputs."""
    data = await _request("GET", f"/afmx/result/{args.execution_id}")
    _print_json(data)


async def cmd_list(args) -> None:
    """List recent executions."""
    params = f"?limit={args.limit}"
    if args.status:
        params += f"&status_filter={args.status}"
    data = await _request("GET", f"/afmx/executions{params}")
    execs = data.get("executions", [])
    print(f"\n  {data.get('count', 0)} execution(s)\n")
    _print_table(execs, ["matrix_name", "status", "completed_nodes", "duration_ms"])


async def cmd_validate(args) -> None:
    """Validate a matrix file."""
    path = Path(args.matrix)
    if not path.exists():
        print(f"❌  File not found: {args.matrix}")
        sys.exit(1)
    matrix_def = json.loads(path.read_text())
    result = await _request("POST", "/afmx/validate", {"matrix": matrix_def})

    if result.get("valid"):
        print("✅  Valid matrix")
        print(f"   Nodes : {result.get('node_count')}")
        print(f"   Edges : {result.get('edge_count')}")
        print(f"   Order : {' → '.join(result.get('execution_order', []))}")
    else:
        print("❌  Invalid matrix:")
        for err in result.get("errors", []):
            print(f"   • {err}")
        sys.exit(1)


async def cmd_plugins(args) -> None:
    """List all registered plugins."""
    data = await _request("GET", "/afmx/plugins")
    for ptype in ["tools", "agents", "functions"]:
        items = data.get(ptype, [])
        if items:
            print(f"\n  {ptype.upper()} ({len(items)})")
            _print_table(items, ["key", "description", "enabled"])


async def cmd_health(args) -> None:
    """Check server health."""
    data = await _request("GET", "/health")
    status = "healthy" if data.get("status") == "healthy" else "unhealthy"
    icon = "✅" if status == "healthy" else "❌"
    print(f"\n  {icon} AFMX {data.get('version', '?')} — {status}")
    print(f"   Environment : {data.get('environment')}")
    print(f"   Store       : {data.get('store_backend')}")
    print(f"   Uptime      : {data.get('uptime_seconds', 0):.1f}s")
    conc = data.get("concurrency", {})
    if conc:
        print(f"   Concurrency : {conc.get('active')}/{conc.get('max_concurrent')} "
              f"({conc.get('utilization_pct')}% utilization)")


async def cmd_cancel(args) -> None:
    """Cancel a running execution."""
    result = await _request("POST", f"/afmx/cancel/{args.execution_id}")
    print(f"  {result.get('message')} — status: {result.get('status')}")


def cmd_serve(args) -> None:
    """Start the AFMX server."""
    try:
        import uvicorn
    except ImportError:
        print("❌  uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    host    = args.host or os.getenv("AFMX_HOST", "0.0.0.0")
    port    = int(args.port or os.getenv("AFMX_PORT", "8100"))
    reload  = args.reload
    workers = 1 if reload else (args.workers or 1)

    print(f"🚀  Starting AFMX server on {host}:{port} "
          f"(workers={workers}, reload={reload})")
    uvicorn.run(
        "afmx.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level="info",
    )


# ─── Parser ───────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="afmx",
        description="AFMX CLI — Agent Flow Matrix Execution Engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── run ──────────────────────────────────────────────────────────────────
    run_p = sub.add_parser("run", help="Execute a matrix")
    run_p.add_argument("--matrix",      "-m", help="Path to matrix JSON file")
    run_p.add_argument("--inline",      "-M", help="Matrix definition as inline JSON string")
    run_p.add_argument("--input",       "-i", help="Input JSON string")
    run_p.add_argument("--variables",   "-V", help="Variables JSON string")
    run_p.add_argument("--metadata",         help="Metadata JSON string")
    run_p.add_argument("--triggered-by",     dest="triggered_by", default="cli")
    run_p.add_argument("--async",            dest="async_", action="store_true", help="Fire-and-forget")
    run_p.add_argument("--watch",            action="store_true", help="Poll until terminal (with --async)")
    run_p.add_argument("--verbose",    "-v", action="store_true")

    # ── status ────────────────────────────────────────────────────────────────
    st_p = sub.add_parser("status", help="Get execution status")
    st_p.add_argument("execution_id")

    # ── result ────────────────────────────────────────────────────────────────
    res_p = sub.add_parser("result", help="Get full execution result")
    res_p.add_argument("execution_id")

    # ── list ──────────────────────────────────────────────────────────────────
    list_p = sub.add_parser("list", help="List recent executions")
    list_p.add_argument("--limit",  "-n", type=int, default=20)
    list_p.add_argument("--status", "-s", help="Filter by status")

    # ── validate ──────────────────────────────────────────────────────────────
    val_p = sub.add_parser("validate", help="Validate a matrix file")
    val_p.add_argument("--matrix", "-m", required=True)

    # ── plugins ───────────────────────────────────────────────────────────────
    sub.add_parser("plugins", help="List registered plugins")

    # ── health ────────────────────────────────────────────────────────────────
    sub.add_parser("health", help="Check server health")

    # ── cancel ────────────────────────────────────────────────────────────────
    can_p = sub.add_parser("cancel", help="Cancel a running execution")
    can_p.add_argument("execution_id")

    # ── serve ─────────────────────────────────────────────────────────────────
    srv_p = sub.add_parser("serve", help="Start the AFMX server")
    srv_p.add_argument("--host",    default=None)
    srv_p.add_argument("--port",    default=None, type=int)
    srv_p.add_argument("--workers", default=1,    type=int)
    srv_p.add_argument("--reload",  action="store_true")

    return parser


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    # Non-async commands
    if args.command == "serve":
        cmd_serve(args)
        return

    # Async commands
    async_commands = {
        "run":      cmd_run,
        "status":   cmd_status,
        "result":   cmd_result,
        "list":     cmd_list,
        "validate": cmd_validate,
        "plugins":  cmd_plugins,
        "health":   cmd_health,
        "cancel":   cmd_cancel,
    }

    fn = async_commands.get(args.command)
    if fn:
        try:
            asyncio.run(fn(args))
        except KeyboardInterrupt:
            print("\n  Interrupted.")
        except Exception as exc:
            print(f"\n❌  Error: {exc}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
