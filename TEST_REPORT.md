# SentryMind Test Report

**Date:** 2026-09-28  
**Tester:** Senior QA, AI Reliability and Security Engineer  
**Repository:** SentryMind (commit f281deb + optimization changes)

---

## 1. Executive Summary

Comprehensive testing and optimization of the SentryMind repository. **326 automated tests pass** with **100% statement and branch coverage** on `agent/core.py` and `memory/hindsight_client.py`. Real local inference verified with Qwen2.5-3B-Instruct Q4_K_M on AMD RX 6500M (Vulkan). Two defects were fixed during initial hardening. No critical security vulnerabilities remain.

---

## 2. Test Environment

| Component | Version/Details |
|-----------|----------------|
| OS | CachyOS Linux |
| Python | 3.14.7 |
| FastAPI | 0.141.1 |
| llama.cpp | 0.5.0-dev (Vulkan) |
| Model | Qwen2.5-3B-Instruct Q4_K_M (2.1 GB) |
| GPU | AMD Radeon RX 6500M (4GB VRAM, RADV NAVI24) |
| CPU | AMD Ryzen 5 5600H (6 cores / 12 threads) |
| RAM | 16 GB |

---

## 3. Final Test Counts

| Test File | Tests | Description |
|-----------|-------|-------------|
| `tests/test_agent_unit.py` | 10 | Core agent unit tests |
| `tests/test_memory_unit.py` | 10 | Memory manager unit tests |
| `tests/test_memory_loop.py` | 2 | Before/after memory comparison |
| `tests/test_cli_workflow.py` | 14 | End-to-end lifecycle tests |
| `tests/test_environment.py` | 3 | Config and data loading |
| `tests/test_security_reliability.py` | 22 | Security regression tests |
| `tests/test_streamlit_ui.py` | 2 | Streamlit UI smoke tests |
| `tests/test_ai_reliability.py` | 55 | AI reliability with synthetic incidents |
| `tests/test_memory_integration.py` | 67 | Hindsight memory integration |
| `tests/test_security_injection.py` | 44 | Security and fault injection |
| `tests/test_branch_coverage.py` | 11 | Branch coverage completion |
| `tests/test_agent_optimization.py` | 26 | Agent optimization (truncation, structured output, recall limits) |
| `webapp-backend/tests/test_api.py` | 62 | FastAPI endpoint tests (in-process) |
| `webapp-backend/tests/test_api_live.py` | 12 | Live HTTP integration tests |
| `tests/real_services/test_live_services.py` | 2 | Opt-in live LLM/Hindsight (skipped) |
| **Total** | **326 passed, 14 skipped** | |

### 3.1 Coverage Report

```
Name                         Stmts   Miss   BrPart   Cover   Missing
------------------------------------------------------------------------
agent/core.py                   53      0       0     100%
memory/hindsight_client.py      61      0       0     100%
------------------------------------------------------------------------
TOTAL                          114      0       0     100%
```

---

## 4. Skipped Tests (14)

### 4.1 Live LLM/Hindsight Integration (2 tests)

**File:** `tests/real_services/test_live_services.py`  
**Reason:** Require `SENTRYMIND_RUN_LIVE_INTEGRATION=1` and configured external services.  
**Status:** The local llama.cpp server IS running and verified working. These tests require a real Hindsight Cloud service which is not available.

```bash
# To run (requires Hindsight service):
export HINDSIGHT_API_URL=http://localhost:8080
SENTRYMIND_RUN_LIVE_INTEGRATION=1 .venv/bin/python -m pytest tests/real_services/ -v
```

### 4.2 Live HTTP Integration (12 tests)

**File:** `webapp-backend/tests/test_api_live.py`  
**Reason:** Require `SENTRYMIND_RUN_LIVE_INTEGRATION=1` and a running Uvicorn server on port 8001.  
**Status:** All 12 tests pass when the server is running.

```bash
# To run:
cd webapp-backend
SENTRYMIND_RUN_LIVE_INTEGRATION=1 ../.venv/bin/python -m pytest tests/test_api_live.py -v
```

---

## 5. Real Service Verification

### 5.1 Local Inference (llama.cpp + Vulkan)

| Metric | Value |
|--------|-------|
| Model | Qwen2.5-3B-Instruct Q4_K_M |
| VRAM usage | 1.90 GB / 3.98 GB (48%) |
| TTFT | 23ms |
| Throughput | ~40 tokens/sec |
| Mean analysis latency | 2.86s |
| Structured output | Parsed correctly |

### 5.2 Live HTTP Endpoints

| Endpoint | Status | Response |
|----------|--------|----------|
| GET `/` | 200 | `{"status":"ok","message":"SentryMind Backend API is running!"}` |
| GET `/health` | 200 | `{"status":"healthy","inference_available":true,"queue_size":0}` |
| GET `/config` | 200 | Model config (non-sensitive) |
| POST `/analyze` | 200 | Structured analysis with latency |
| GET `/nonexistent` | 404 | Safe JSON error |
| POST `/` | 405 | Method not allowed |

---

## 6. Defects Found and Fixed

### Defect 1: `recall_resolution` Crash on Non-String Queries

**Severity:** Medium  
**File:** `memory/hindsight_client.py`  
**Fix:** Added `isinstance` check + `str()` coercion.  
**Regression test:** `tests/test_memory_integration.py::TestEdgeCases::test_recall_with_none_query`

### Defect 2: Secrets in Recalled Memory Not Redacted

**Severity:** Medium (Security)  
**File:** `agent/core.py`  
**Fix:** Added `self._redact_secrets(fact)` to recalled facts.  
**Regression test:** `tests/test_security_injection.py::TestCredentialLeakage::test_secret_in_recalled_memory_redacted`

---

## 7. Optimization Changes

### 7.1 Agent (`agent/core.py`)

- Compact system prompt with safety constraints
- Structured output schema (diagnosis, evidence, confidence, uncertainty, next_checks, remediation)
- Bounded log truncation preserving critical error lines
- Recall limiting (top-k=3, token budget=500)
- Configurable parameters via environment variables

### 7.2 Backend (`webapp-backend/main.py`)

- Async inference endpoint (`/analyze`) with thread pool
- Bounded request queue (semaphore=1, max queue=5)
- Health check with inference availability
- Config endpoint (non-sensitive)

### 7.3 Streamlit UI (`app.py`)

- Side-by-side first-time vs memory-assisted analysis
- Explainable diagnosis with evidence links
- Privacy protection display (secret redaction)
- Performance dashboard
- Clear "NOT verified" labeling on remediation

### 7.4 Configuration (`inference_config.py`)

- Centralized inference configuration
- All settings configurable via environment variables
- GPU device selection (defaults to discrete GPU)

---

## 8. Lint, Type Check, and Security Scan

| Tool | Result |
|------|--------|
| ruff check | All checks passed |
| bandit | 0 issues |
| mypy | No issues (7 source files) |
| pip-audit | No known vulnerabilities |

---

## 9. Performance Summary

| Metric | Value |
|--------|-------|
| API latency (in-process) | 0.38ms |
| API latency (live) | 0.41-0.57ms |
| Analysis latency (mocked LLM) | 0.012ms |
| Analysis latency (real LLM) | 2.86s |
| Memory retain | 0.009ms |
| Memory recall | 0.028ms |
| Server RSS | 52.7 MB |
| Cold start | 453.6ms |
| VRAM usage | 1.90 GB / 3.98 GB |

---

## 10. Untested Scenarios

| Scenario | Reason |
|----------|--------|
| Real Hindsight Cloud integration | No Hindsight service available |
| 4096 context window | May exceed 4GB VRAM |
| High-concurrency stress test | Hardware constraints |
| Long-duration stability | Hardware constraints |
| Streamlit browser testing | No browser; AppTest used |
| GPU memory exhaustion recovery | Requires OOM condition |

---

## 11. Reproduction Commands

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

# Live integration tests
cd webapp-backend
SENTRYMIND_RUN_LIVE_INTEGRATION=1 ../.venv/bin/python -m pytest tests/test_api_live.py -v

# Start demo
./start_demo.sh

# Real inference benchmark
.venv/bin/python -c "
import time, statistics
from agent.core import SentryMindAgent
agent = SentryMindAgent()
log = 'FATAL: remaining connection slots are reserved'
agent.analyze_log(log, use_memory=False)
times = []
for i in range(5):
    start = time.perf_counter()
    agent.analyze_log(log, use_memory=False)
    times.append(time.perf_counter() - start)
print(f'Mean: {statistics.mean(times):.2f}s')
"
```

---

## 12. Conclusion

The SentryMind repository has been thoroughly tested, optimized, and verified. **326 tests pass** with **100% coverage** on core modules. Real local inference produces evidence-grounded analyses in ~2.9s with 48% VRAM utilization. The system demonstrates graceful failure handling, secret redaction, and transparent uncertainty. Ready for hackathon demonstration.
