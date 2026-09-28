# SentryMind Optimization Report

**Date:** 2026-09-28  
**Hardware:** AMD Ryzen 5 5600H (6C/12T), 16GB RAM, AMD Radeon RX 6500M (4GB VRAM)  
**OS:** CachyOS Linux  
**Python:** 3.14.7

---

## 1. Executive Summary

SentryMind has been optimized for local inference on the target laptop. The agent now uses a compact structured prompt, bounded log selection, and a local llama.cpp server with Vulkan GPU acceleration. Real inference produces evidence-grounded incident analyses in ~2.9s with 48% VRAM utilization.

---

## 2. Before/After Measurements

### 2.1 Agent Analysis Latency (mocked LLM)

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Mean | 0.056ms | 0.012ms | -79% |
| Median | 0.019ms | 0.011ms | -42% |
| p95 | 0.031ms | 0.014ms | -55% |

### 2.2 Real Inference Latency (local llama.cpp, Qwen2.5-3B Q4_K_M)

| Metric | Value |
|--------|-------|
| Mean | 2.86s |
| Median | 2.91s |
| Min | 2.17s |
| Max | 3.22s |
| TTFT (time to first token) | 23ms |
| Throughput | ~40 tokens/sec |

### 2.3 Prompt Size

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| No-memory prompt | 306 chars | 534 chars | +75% |
| With-memory prompt | 450 chars | 650 chars | +44% |
| Output schema | None | Structured JSON | New |

**Note:** The prompt is larger after optimization because it includes the structured output schema. However, the schema enables structured parsing and evidence-linked diagnosis, which is more valuable than raw prompt size reduction.

### 2.4 Memory Latency (local fallback, unchanged)

| Operation | Mean | Median |
|-----------|------|--------|
| retain_incident | 0.009ms | 0.008ms |
| recall_resolution | 0.028ms | 0.026ms |

### 2.5 Resource Usage

| Metric | Value |
|--------|-------|
| VRAM used | 1.90 GB / 3.98 GB (48%) |
| Server RSS | 52.7 MB |
| Server CPU (idle) | 0.1% |
| Cold start | 453.6ms |

---

## 3. Changes Made

### 3.1 Agent Optimization (`agent/core.py`)

- **Compact system prompt:** Safety constraints moved to system prompt, reducing user prompt size
- **Structured output schema:** LLM returns JSON with diagnosis, evidence, confidence, uncertainty, next_checks, remediation
- **Bounded log truncation:** Long logs truncated while preserving critical error lines (ERROR, FATAL, OOM, CRASH, etc.)
- **Recall limiting:** Top-k (default 3) and token budget (default 500 tokens) for recalled memories
- **Configurable parameters:** All limits configurable via environment variables

### 3.2 Inference Configuration (`inference_config.py`)

- Centralized configuration for model path, server endpoint, GPU layers, context size, batch sizes
- All settings configurable via environment variables
- GPU device selection (defaults to discrete GPU)

### 3.3 Backend (`webapp-backend/main.py`)

- **Async inference:** `/analyze` endpoint runs inference in thread pool, non-blocking
- **Bounded request queue:** Semaphore limits concurrent inference to 1, preventing VRAM exhaustion
- **Queue size limit:** Returns 503 when queue is full (max 5)
- **Health check:** Reports inference availability and queue size
- **Config endpoint:** Exposes non-sensitive configuration

### 3.4 Streamlit UI (`app.py`)

- **Side-by-side comparison:** First-time vs memory-assisted analysis
- **Explainable diagnosis:** Evidence links, uncertainty display, next checks
- **Privacy protection:** Shows secret redaction in action
- **Performance dashboard:** Latency, memory status, inference status
- **Clear remediation labeling:** "NOT verified" warnings on all suggestions

### 3.5 Test Coverage

- 26 new tests for agent optimization (truncation, structured output, recall limits)
- 6 new tests for backend endpoints (config, analyze, queue full, inference failure)
- 2 updated Streamlit UI tests
- **Total: 326 tests passing**

---

## 4. Configuration

### 4.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRYMIND_INFERENCE_MODEL` | `qwen2.5-3b-instruct` | Model name |
| `SENTRYMIND_MODEL_PATH` | `models/Qwen2.5-3B-Instruct-Q4_K_M.gguf` | Model file path |
| `SENTRYMIND_CONTEXT_SIZE` | `2048` | Context window (tokens) |
| `SENTRYMIND_GPU_LAYERS` | `99` | GPU offload layers |
| `SENTRYMIND_MAX_OUTPUT_TOKENS` | `512` | Max output tokens |
| `SENTRYMIND_TEMPERATURE` | `0.2` | Sampling temperature |
| `SENTRYMIND_MAX_LOG_LENGTH` | `8000` | Max log length (chars) |
| `SENTRYMIND_MAX_RECALL_RESULTS` | `3` | Max recalled memories |
| `SENTRYMIND_MAX_RECALL_TOKENS` | `500` | Max recall tokens |
| `SENTRYMIND_VULKAN_DEVICE` | `1` | GPU device index |

### 4.2 Recommended Settings for 4GB VRAM

```bash
export SENTRYMIND_CONTEXT_SIZE=2048
export SENTRYMIND_GPU_LAYERS=99
export SENTRYMIND_MAX_OUTPUT_TOKENS=512
export SENTRYMIND_TEMPERATURE=0.2
export SENTRYMIND_VULKAN_DEVICE=1
```

---

## 5. Limitations

1. **Local keyword recall is approximate** — may miss semantically related logs
2. **In-memory fallback is not persistent** — data lost on restart
3. **Secret redaction targets common formats** — custom formats may not be caught
4. **Prompt injection resistance is not guaranteed** — defenses reduce but don't eliminate risk
5. **Single concurrent inference** — bounded by semaphore to prevent VRAM exhaustion
6. **No GPU memory monitoring in agent** — VRAM checked externally via `/sys/class/drm/`

---

## 6. Reproduction Commands

```bash
# Full test suite
cd /home/knk/SentryMind
.venv/bin/python -m pytest tests/ webapp-backend/tests/ -v

# With coverage
.venv/bin/python -m pytest tests/ webapp-backend/tests/ \
  --cov=agent --cov=memory --cov-report=term-missing

# Lint
.venv/bin/ruff check .

# Security scan
.venv/bin/bandit -r agent memory app.py config.py data inference_config.py -ll

# Type check
.venv/bin/mypy agent/ memory/ config.py app.py inference_config.py --ignore-missing-imports

# Real inference benchmark
.venv/bin/python -c "
import time, statistics
from agent.core import SentryMindAgent
agent = SentryMindAgent()
log = 'FATAL: remaining connection slots are reserved'
agent.analyze_log(log, use_memory=False)  # warmup
times = []
for i in range(5):
    start = time.perf_counter()
    agent.analyze_log(log, use_memory=False)
    times.append(time.perf_counter() - start)
print(f'Mean: {statistics.mean(times):.2f}s')
"

# Start inference server
cd /home/knk/SentryMind/models
/tmp/opencode/llama.cpp/build/bin/llama-server \
  -m Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 1234 \
  --ctx-size 2048 --n-gpu-layers 99 \
  --batch-size 128 --ubatch-size 128

# Start Streamlit UI
cd /home/knk/SentryMind
.venv/bin/streamlit run app.py
```

---

## 7. Verified Objectives

| Objective | Status | Evidence |
|-----------|--------|----------|
| Runs reliably on target laptop | ✅ Verified | 326 tests pass, no crashes |
| Fits in 4GB VRAM | ✅ Verified | 1.90GB used (48%) |
| Evidence-grounded diagnosis | ✅ Verified | Structured output with evidence links |
| Memory persistence distinction | ✅ Verified | Local fallback vs remote clearly distinguished |
| Secret redaction | ✅ Verified | 8 redaction tests pass |
| Graceful failure handling | ✅ Verified | 7 dependency failure tests pass |
| Before/after measurements | ✅ Verified | This report |
| Reproducible demo | ✅ Verified | DEMO_GUIDE.md |

---

## 8. Partially Achieved / Untested

| Objective | Status | Reason |
|-----------|--------|--------|
| 4096 context window | ⚠️ Not tested | 2048 context uses 1.9GB VRAM; 4096 may exceed 4GB |
| Real Hindsight integration | ⚠️ Not tested | No Hindsight service running |
| High-concurrency stress test | ⚠️ Not tested | Hardware constraints |
| Long-duration stability | ⚠️ Not tested | Hardware constraints |
| Streamlit browser testing | ⚠️ Not tested | No browser; AppTest used |
