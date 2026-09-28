"""Lightweight performance baseline for SentryMind.

Measures: API response latency, incident-analysis latency,
memory retention/recall latency, and CPU/RAM usage.
Run: python tests/performance_benchmark.py
"""

import os
import resource
import statistics
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests

from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager


def measure_latency(func, iterations=100, warmup=10):
    """Measure latency statistics for a callable."""
    # Warmup
    for _ in range(warmup):
        func()

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)  # Convert to ms

    return {
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "p95_ms": sorted(times)[int(len(times) * 0.95)],
        "min_ms": min(times),
        "max_ms": max(times),
        "total_ms": sum(times),
    }


def get_memory_usage_mb():
    """Get current memory usage in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss / 1024  # Convert KB to MB on Linux


def benchmark_api_latency():
    """Benchmark API endpoint latency using in-process ASGI transport."""
    import asyncio
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webapp-backend"))
    import httpx
    from main import app

    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/")

    def do_request():
        asyncio.run(request())

    return measure_latency(do_request, iterations=200, warmup=20)


def benchmark_health_latency():
    """Benchmark /health endpoint latency."""
    import asyncio
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webapp-backend"))
    import httpx
    from main import app

    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health")

    def do_request():
        asyncio.run(request())

    return measure_latency(do_request, iterations=200, warmup=20)


def benchmark_analysis_latency():
    """Benchmark incident analysis latency (mocked LLM)."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")
    agent = SentryMindAgent(manager)

    with (
        patch.object(agent, "query_local_qwen", return_value="mocked"),
        patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ),
    ):
        log = "FATAL: remaining connection slots are reserved for non-replication superuser connections"
        return measure_latency(
            lambda: agent.analyze_log(log, use_memory=False),
            iterations=100,
            warmup=10,
        )


def benchmark_analysis_with_memory_latency():
    """Benchmark incident analysis with memory (mocked LLM)."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")
    agent = SentryMindAgent(manager)

    with (
        patch.object(agent, "query_local_qwen", return_value="mocked"),
        patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ),
    ):
        manager.retain_incident("PostgreSQL connection pool exhausted by idle sessions")
        log = "FATAL: remaining connection slots are reserved for non-replication superuser connections"
        return measure_latency(
            lambda: agent.analyze_log(log, use_memory=True),
            iterations=100,
            warmup=10,
        )


def benchmark_memory_retain_latency():
    """Benchmark memory retention latency."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")

    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        return measure_latency(
            lambda: manager.retain_incident("database connection pool timeout"),
            iterations=200,
            warmup=20,
        )


def benchmark_memory_recall_latency():
    """Benchmark memory recall latency."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")

    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        # Pre-populate with some incidents
        for i in range(10):
            manager.retain_incident(f"database connection pool timeout incident {i}")

        return measure_latency(
            lambda: manager.recall_resolution("database connection pool"),
            iterations=200,
            warmup=20,
        )


def benchmark_retain_recall_roundtrip():
    """Benchmark full retain → recall roundtrip."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")

    def roundtrip():
        manager.retain_incident("database connection pool timeout")
        manager.recall_resolution("database connection pool")

    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        return measure_latency(roundtrip, iterations=100, warmup=10)


def benchmark_bulk_retain_recall():
    """Benchmark retaining 100 incidents then recalling."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")

    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        # Retain 100 incidents
        start = time.perf_counter()
        for i in range(100):
            manager.retain_incident(f"database connection pool timeout incident {i}")
        retain_time = (time.perf_counter() - start) * 1000

        # Recall 100 times
        start = time.perf_counter()
        for _ in range(100):
            manager.recall_resolution("database connection pool")
        recall_time = (time.perf_counter() - start) * 1000

    return {
        "retain_100_ms": retain_time,
        "recall_100_ms": recall_time,
        "retain_per_incident_ms": retain_time / 100,
        "recall_per_call_ms": recall_time / 100,
    }


def main():
    print("=" * 70)
    print("SentryMind Performance Baseline")
    print("=" * 70)
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print()

    mem_before = get_memory_usage_mb()

    print("--- API Latency (in-process ASGI) ---")
    api_stats = benchmark_api_latency()
    print(f"GET /           mean={api_stats['mean_ms']:.3f}ms  "
          f"median={api_stats['median_ms']:.3f}ms  "
          f"p95={api_stats['p95_ms']:.3f}ms")

    health_stats = benchmark_health_latency()
    print(f"GET /health     mean={health_stats['mean_ms']:.3f}ms  "
          f"median={health_stats['median_ms']:.3f}ms  "
          f"p95={health_stats['p95_ms']:.3f}ms")
    print()

    print("--- Incident Analysis Latency (mocked LLM) ---")
    analysis_stats = benchmark_analysis_latency()
    print(f"analyze (no mem) mean={analysis_stats['mean_ms']:.3f}ms  "
          f"median={analysis_stats['median_ms']:.3f}ms  "
          f"p95={analysis_stats['p95_ms']:.3f}ms")

    analysis_mem_stats = benchmark_analysis_with_memory_latency()
    print(f"analyze (w/ mem) mean={analysis_mem_stats['mean_ms']:.3f}ms  "
          f"median={analysis_mem_stats['median_ms']:.3f}ms  "
          f"p95={analysis_mem_stats['p95_ms']:.3f}ms")
    print()

    print("--- Memory Latency (local fallback) ---")
    retain_stats = benchmark_memory_retain_latency()
    print(f"retain_incident  mean={retain_stats['mean_ms']:.3f}ms  "
          f"median={retain_stats['median_ms']:.3f}ms  "
          f"p95={retain_stats['p95_ms']:.3f}ms")

    recall_stats = benchmark_memory_recall_latency()
    print(f"recall_resolution mean={recall_stats['mean_ms']:.3f}ms  "
          f"median={recall_stats['median_ms']:.3f}ms  "
          f"p95={recall_stats['p95_ms']:.3f}ms")

    roundtrip_stats = benchmark_retain_recall_roundtrip()
    print(f"retain+recall    mean={roundtrip_stats['mean_ms']:.3f}ms  "
          f"median={roundtrip_stats['median_ms']:.3f}ms  "
          f"p95={roundtrip_stats['p95_ms']:.3f}ms")
    print()

    print("--- Bulk Operations ---")
    bulk_stats = benchmark_bulk_retain_recall()
    print(f"Retain 100 incidents: {bulk_stats['retain_100_ms']:.2f}ms total "
          f"({bulk_stats['retain_per_incident_ms']:.3f}ms each)")
    print(f"Recall 100 times:    {bulk_stats['recall_100_ms']:.2f}ms total "
          f"({bulk_stats['recall_per_call_ms']:.3f}ms each)")
    print()

    mem_after = get_memory_usage_mb()
    print("--- Memory Usage ---")
    print(f"Peak RSS: {mem_after:.1f} MB")
    print(f"Delta:    {mem_after - mem_before:.1f} MB")
    print()
    print("=" * 70)
    print("Note: These are microbenchmarks on local hardware.")
    print("      Not representative of production service latency.")
    print("=" * 70)


if __name__ == "__main__":
    main()
