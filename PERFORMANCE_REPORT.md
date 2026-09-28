# SentryMind Performance Report

**Date:** 2026-09-28  
**Hardware:** AMD Ryzen 5 5600H (6C/12T), 16GB RAM, AMD Radeon RX 6500M (4GB VRAM)  
**OS:** CachyOS Linux  
**Python:** 3.14.7

---

## 1. Executive Summary

Lightweight performance baseline established for the SentryMind API backend and agent. All measurements are microbenchmarks on local hardware and are not representative of production service latency. The system is lightweight, with sub-millisecond in-process latency and minimal resource consumption.

---

## 2. API Latency

### 2.1 In-Process (ASGI Transport, No Network)

| Endpoint | Mean | Median | p95 | Min | Max |
|----------|------|--------|-----|-----|-----|
| GET `/` | 0.385ms | 0.378ms | 0.405ms | 0.350ms | 0.520ms |
| GET `/health` | 0.381ms | 0.375ms | 0.401ms | 0.340ms | 0.510ms |

**Iterations:** 200 (20 warmup)

### 2.2 Live HTTP (Uvicorn on 127.0.0.1:8001)

| Endpoint | Mean | Median | p95 |
|----------|------|--------|-----|
| GET `/` | 0.57ms | 0.41ms | 0.48ms |
| GET `/health` | 0.41ms | 0.40ms | 0.48ms |

**Iterations:** 50

### 2.3 Analysis

- In-process latency is sub-millisecond, indicating minimal overhead from the ASGI stack
- Live HTTP adds ~0.2ms overhead from TCP/socket handling
- Both endpoints perform identically (trivial handlers)
- No performance degradation under repeated requests

---

## 3. Incident Analysis Latency

### 3.1 Without Memory (mocked LLM)

| Metric | Value |
|--------|-------|
| Mean | 0.012ms |
| Median | 0.011ms |
| p95 | 0.014ms |

### 3.2 With Memory (mocked LLM, local fallback)

| Metric | Value |
|--------|-------|
| Mean | 0.054ms |
| Median | 0.035ms |
| p95 | 0.045ms |

### 3.3 Analysis

- Analysis without memory is extremely fast (prompt construction only)
- Memory-enabled analysis adds ~0.04ms for recall lookup
- The local keyword fallback is efficient for small memory banks
- LLM inference time is excluded (mocked) — real inference would dominate

---

## 4. Memory Latency

### 4.1 Single Operations (local fallback)

| Operation | Mean | Median | p95 |
|-----------|------|--------|-----|
| `retain_incident` | 0.009ms | 0.008ms | 0.012ms |
| `recall_resolution` | 0.028ms | 0.026ms | 0.031ms |
| Retain + Recall roundtrip | 0.023ms | 0.021ms | 0.027ms |

**Iterations:** 200 (20 warmup)

### 4.2 Bulk Operations

| Operation | Total Time | Per Operation |
|-----------|-----------|---------------|
| Retain 100 incidents | 1.09ms | 0.011ms |
| Recall 100 times | 15.54ms | 0.155ms |

### 4.3 Analysis

- Retention is O(n) where n is the number of stored incidents (duplicate check scans the store)
- Recall is O(n*m) where n is stored incidents and m is query words
- For small memory banks (< 1000 incidents), performance is excellent
- For large memory banks, consider using remote Hindsight with semantic search

---

## 5. Resource Usage

### 5.1 API Server (Uvicorn)

| Metric | Value |
|--------|-------|
| RSS (Resident Set Size) | 52.7 MB |
| VSZ (Virtual Memory Size) | 164.3 MB |
| CPU (idle) | 0.1% |
| Cold start time | 453.6ms |
| First request latency | 22.6ms |

### 5.2 Agent (in-process)

| Metric | Value |
|--------|-------|
| Peak RSS (full test suite) | 423.8 MB |
| Memory delta during benchmarks | ~0 MB |

### 5.3 Analysis

- The API server is lightweight at ~53MB RSS
- Cold start is under 0.5s, suitable for development
- The agent adds minimal memory overhead when services are unavailable
- No GPU memory usage (no model loaded)

---

## 6. Cold Start Performance

| Component | Cold Start Time |
|-----------|----------------|
| Uvicorn server | 453.6ms |
| First request after start | 22.6ms |
| Agent instantiation | < 1ms |
| Memory manager instantiation | < 1ms |

---

## 7. Concurrent Performance

### 7.1 API Concurrent Requests

- 10 concurrent GET `/` + 10 concurrent GET `/health` → all succeed
- No connection errors or timeouts

### 7.2 Memory Concurrent Access

- 12 threads retaining 100 duplicate incidents → stored once (deduplicated)
- 12 threads retaining 50 distinct incidents → all 50 stored
- 4 threads (2 retain + 2 recall) concurrently → no errors
- 20 threads recalling concurrently → consistent results

---

## 8. Performance Under Load

### 8.1 Repeated Requests

- 20 consecutive GET `/` → consistent 200 responses
- 20 consecutive GET `/health` → consistent 200 responses
- 10 alternating requests → consistent responses

### 8.2 Large Inputs

- 10,000-char query string → 200 (handled)
- 5,000-char path → 404 (handled)
- 500KB incident log → valid response (no crash)

---

## 9. Performance Bottlenecks

| Bottleneck | Impact | Mitigation |
|------------|--------|------------|
| LLM inference (30s timeout) | Dominates real-world latency | Use smaller model (3B) for local inference |
| Hindsight remote calls (5s timeout) | Adds latency when remote is slow | Falls back to local after timeout |
| Local keyword recall O(n*m) | Degrades with large memory banks | Use remote Hindsight for large banks |
| Duplicate check O(n) | Degrades with large memory banks | Use remote Hindsight with deduplication |

---

## 10. Recommendations

### 10.1 For Local Development

1. **Use Qwen 2.5 3B Instruct Q4_K_M** with llama.cpp Vulkan for real local inference
   - The default `qwen2.5-35b-instruct` is infeasible on 16GB RAM / 4GB VRAM
   - 3B model provides acceptable quality for incident triage
2. **Keep Hindsight local** for development — remote calls add latency
3. **Monitor memory bank size** — local keyword recall degrades with > 1000 incidents

### 10.2 For Production

1. **Use remote Hindsight** for persistent, scalable memory
2. **Add caching** for frequent queries
3. **Add rate limiting** to prevent abuse
4. **Monitor p95 latency** — alert if > 100ms for API endpoints

---

## 11. Measurement Methodology

- **Latency:** `time.perf_counter()` around function calls
- **Iterations:** 100-200 per benchmark (10-20 warmup)
- **Memory:** `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`
- **CPU:** `ps aux` sampling
- **Cold start:** TCP connection acceptance time
- **All measurements:** Single run, no averaging across runs

---

## 12. Reproduction

```bash
# Performance benchmark
cd /home/knk/SentryMind
.venv/bin/python tests/performance_benchmark.py

# Live API latency
.venv/bin/python -c "
import time, statistics, urllib.request
times = []
for _ in range(50):
    start = time.perf_counter()
    with urllib.request.urlopen('http://127.0.0.1:8001/', timeout=5) as r:
        r.read()
    times.append((time.perf_counter() - start) * 1000)
print(f'Mean: {statistics.mean(times):.2f}ms')
"

# Server resource usage
ps aux | grep "uvicorn.*8001" | grep -v grep | awk '{print "CPU:", $3"%", "MEM:", $4"%", "RSS:", $6/1024"MB"}'
```
