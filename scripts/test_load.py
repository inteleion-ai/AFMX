#!/usr/bin/env python3.10
"""
AFMX Load Test
Fires concurrent matrix executions and reports throughput.

Usage:
    python3.10 scripts/test_load.py
    python3.10 scripts/test_load.py --concurrency 20 --total 100
"""
from __future__ import annotations
import argparse
import asyncio
import time
from collections import Counter

import httpx

DEFAULT_URL = "http://localhost:8100"

MATRIX = {
    "name": "load-test",
    "mode": "SEQUENTIAL",
    "nodes": [
        {"id": "n1", "name": "echo",    "type": "FUNCTION", "handler": "echo"},
        {"id": "n2", "name": "upper",   "type": "FUNCTION", "handler": "upper"},
        {"id": "n3", "name": "analyst", "type": "FUNCTION", "handler": "analyst_agent"},
    ],
    "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
}


async def run_one(client: httpx.AsyncClient, req_id: int) -> dict:
    start = time.perf_counter()
    try:
        r = await client.post("/afmx/execute", json={
            "matrix": MATRIX,
            "input": {"query": f"load-test-{req_id}", "id": req_id},
            "triggered_by": "load-test",
            "tags": ["load"],
        })
        elapsed = (time.perf_counter() - start) * 1000
        data = r.json()
        return {
            "id": req_id,
            "status": data.get("status", "UNKNOWN"),
            "http": r.status_code,
            "duration_ms": elapsed,
            "nodes_done": data.get("completed_nodes", 0),
        }
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "id": req_id,
            "status": "ERROR",
            "http": 0,
            "duration_ms": elapsed,
            "error": str(exc),
        }


async def run_load_test(base_url: str, concurrency: int, total: int) -> None:
    print(f"\n\033[1mAFMX Load Test\033[0m")
    print(f"Server      : {base_url}")
    print(f"Concurrency : {concurrency} simultaneous requests")
    print(f"Total       : {total} executions")
    print(f"Matrix      : echo → upper → analyst_agent (3 nodes)\n")

    sem = asyncio.Semaphore(concurrency)
    results = []

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        start = time.perf_counter()

        async def bounded(i: int):
            async with sem:
                result = await run_one(client, i)
                results.append(result)
                status_color = "\033[32m" if result["status"] == "COMPLETED" else "\033[31m"
                print(
                    f"  [{i:4d}]  {status_color}{result['status']:<12}\033[0m"
                    f"  {result['duration_ms']:7.1f}ms"
                    f"  nodes={result.get('nodes_done', 0)}"
                )

        await asyncio.gather(*[bounded(i) for i in range(1, total + 1)])
        wall_time = time.perf_counter() - start

    # ─── Summary ──────────────────────────────────────────────────────────────
    status_counts = Counter(r["status"] for r in results)
    durations = [r["duration_ms"] for r in results]
    durations.sort()

    print(f"\n\033[1m{'═'*50}\033[0m")
    print(f"\033[1m  Results\033[0m")
    print(f"{'═'*50}")
    print(f"  Wall time     : {wall_time:.2f}s")
    print(f"  Throughput    : {total / wall_time:.1f} req/s")
    print(f"  Total         : {total}")
    for s, c in status_counts.items():
        color = "\033[32m" if s == "COMPLETED" else "\033[31m"
        print(f"  {color}{s:<14}: {c}{chr(27)}[0m")
    print(f"\n  Latency (ms)")
    print(f"    min    : {durations[0]:.1f}")
    print(f"    p50    : {durations[len(durations)//2]:.1f}")
    print(f"    p95    : {durations[int(len(durations)*0.95)]:.1f}")
    print(f"    p99    : {durations[int(len(durations)*0.99)]:.1f}")
    print(f"    max    : {durations[-1]:.1f}")
    print(f"\033[1m{'═'*50}\033[0m\n")


def main():
    parser = argparse.ArgumentParser(description="AFMX load test")
    parser.add_argument("--url",         default=DEFAULT_URL)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total",       type=int, default=50)
    args = parser.parse_args()

    asyncio.run(run_load_test(args.url, args.concurrency, args.total))


if __name__ == "__main__":
    main()
