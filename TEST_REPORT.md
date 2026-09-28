# SentryMind Test Report

**Date:** 2026-09-28  
**Tester:** Senior QA, AI Reliability and Security Engineer  
**Repository:** SentryMind (commit `78fd634` + official Hindsight integration)

---

## 1. Executive Summary

**375 automated tests pass** (396 collected, 21 skipped without the live flag)
with **97% branch coverage** on `agent/` and `memory/` against a 90% CI gate.

The significant change in this round is that memory is now backed by the
**official Vectorize Hindsight engine** rather than a mock, and it was verified
against the running service rather than against a test double:

- retain → genuine LLM fact extraction (**13 facts** extracted into a bank)
- recall → semantic retrieval through local embeddings + a cross-encoder reranker
- reflect → cross-incident synthesis, **HTTP 200 in 156.3 s** (8,994 in / 842 out tokens)
- persistence → **13 of 13 fact IDs survived a full service restart**

Six genuine defects were found and fixed in the adapter, all of which had been
**invisible to the mocked test suite** because the mocks were shaped like the
code rather than like the real API. The most serious: reflect had never worked
at all, and degraded silently to a non-persistent local store on every call.
See `OFFICIAL_HINDSIGHT_REPORT.md` §6 for the full account.

No critical security vulnerabilities remain. `pip-audit`, `bandit` and
`ruff`/`black`/`mypy` are all clean.

---

## 2. Test Environment

| Component | Version/Details |
|-----------|----------------|
| OS | CachyOS Linux |
| Python | 3.14.7 |
| FastAPI | 0.141.1 |
| llama.cpp | 0.5.0-dev (Vulkan), `--ctx-size 8192 --parallel 1` |
| Model | Qwen2.5-3B-Instruct Q4_K_M (2.1 GB) |
| GPU | AMD Radeon RX 6500M (4 GB VRAM, RADV NAVI24) |
| CPU | AMD Ryzen 5 5600H (6 cores / 12 threads) |
| RAM | 16 GB |
| Memory service | `hindsight-api-slim` 0.10.1 + pg0-embedded PostgreSQL, port 8888 |

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
| `tests/test_agent_optimization.py` | 26 | Agent optimization |
| `tests/test_hindsight_official_adapter.py` | 37 | **New** — official wire contract, mocked |
| `tests/test_official_hindsight.py` | 7 | **New** — live official service (skipped) |
| `webapp-backend/tests/test_api.py` | 62 | FastAPI endpoint tests (in-process) |
| `webapp-backend/tests/test_api_live.py` | 12 | Live HTTP integration tests (skipped) |
| `tests/real_services/test_live_services.py` | 2 | Opt-in live LLM/Hindsight (skipped) |
| **Total** | **375 passed, 21 skipped** | |

### 3.1 Coverage Report (as CI runs it)

```
.venv/bin/python -m pytest tests/ --cov=agent --cov=memory --cov-fail-under=90

Name                         Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------
agent/core.py                  109      3     34      3    96%   132->138, 139->141, 171-172, 200
memory/hindsight_client.py     134      0     50      4    98%   84->114, 156->151, 251->271, 324->335
------------------------------------------------------------------------
TOTAL                          243      3     84      7    97%
```

Gate is 90%; `memory/hindsight_client.py` is at 98% because it is the component
whose failures were silent, so its protocol handling is pinned by 37 dedicated
tests. Webapp backend is at 91% against its own 90% gate.

### 3.2 Live run (services up)

With `SENTRYMIND_RUN_LIVE_INTEGRATION=1`, `LOCAL_LLM_URL=http://127.0.0.1:1234/v1`
and `HINDSIGHT_API_URL=http://127.0.0.1:8888`, all 396 tests pass with **0
skipped**, including the live official-Hindsight suite.

---

## 4. Skipped Tests (21 without the live flag)

### 4.1 Live LLM/Hindsight Integration (2 tests)

**File:** `tests/real_services/test_live_services.py`  
**Reason:** Require `SENTRYMIND_RUN_LIVE_INTEGRATION=1` and configured external services.  
**Status:** verified working live — see §3.2.

```bash
# To run (requires llama.cpp on 1234 and the official Hindsight on 8888):
export LOCAL_LLM_URL=http://127.0.0.1:1234/v1
export HINDSIGHT_API_URL=http://127.0.0.1:8888
SENTRYMIND_RUN_LIVE_INTEGRATION=1 .venv/bin/python -m pytest tests/real_services/ -v
```

### 4.2 Official Hindsight Live Integration (7 tests)

**File:** `tests/test_official_hindsight.py`  
**Reason:** Require `SENTRYMIND_RUN_LIVE_INTEGRATION=1` and the official Hindsight
service on port 8888.  
**Status:** all 7 pass live, including retain/recall/reflect against real
extracted facts. Allow ~4 minutes: reflect alone measures 156 s.

```bash
export HINDSIGHT_API_URL=http://127.0.0.1:8888
SENTRYMIND_RUN_LIVE_INTEGRATION=1 .venv/bin/python -m pytest tests/test_official_hindsight.py -v
```

### 4.3 Live HTTP Integration (12 tests)

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
| Context | 8,192 (`--parallel 1`, mandatory — see MODEL_CONFIG.md §4.2) |
| VRAM usage | 2.17 GB / 3.98 GB (55%) |
| Latency (uncontended) | 41 ms |
| Throughput | ~48 tok/s |
| Throughput under extraction load | 0.3 tok/s (single slot, see §7) |

### 5.2 Official Hindsight (verified, not mocked)

| Operation | Result |
|-----------|--------|
| `GET /health` | `{"status":"healthy","database":"connected"}` in 2 ms |
| Retain | HTTP 200 + `operation_ids`, 5–48 ms (asynchronous) |
| Fact extraction | 13 facts from a genuine LLM extraction (617 tokens) |
| Recall | 13 semantic results in 882 ms |
| Reflect | HTTP 200 in 156.3 s (8,994 in / 842 out tokens) |
| Persistence | 13/13 fact IDs survived a full process restart |

Full evidence and method: `OFFICIAL_HINDSIGHT_REPORT.md`.

### 5.3 Live HTTP Endpoints

| Endpoint | Status | Response |
|----------|--------|----------|
| GET `/` | 200 | `{"status":"ok","message":"SentryMind Backend API is running!"}` |
| GET `/health` | 200 | `{"status":"healthy","inference_available":true,"queue_size":0}` |
| GET `/config` | 200 | Model config (non-sensitive) |
| POST `/analyze` | 200 | Structured analysis with latency |
| GET `/nonexistent` | 404 | Safe JSON error, no stack trace |
| POST `/` | 405 | Method not allowed |

---

## 6. Defects Found and Fixed

### 6.0 Official Hindsight adapter (all found by testing against the real service)

| # | Defect | Impact |
|---|--------|--------|
| 1 | Retain returned 404 for unprovisioned banks and degraded silently | 8/8 retains fell back; persistence looked broken |
| 2 | Recall read `content`; official schema uses `text` | Every recall returned empty |
| 3 | A string `results` was iterated character-by-character | 15 bogus one-letter "memories" reported as a successful official recall |
| 4 | Reflect read `response`/`reflection`; official returns `text` | Every reflection empty, reported as success |
| 5 | Reflect hit three successive deadline limits (client 30 s, server 30 s/call, server 300 s wall) | **Reflect never worked at all** and failed silently to a non-persistent store |
| 6 | `backend_status` probed readiness with a contended recall under a 3 s timeout | False "unreachable" reports while healthy |

Defect 5 is the important one: the mocked suite was green throughout, because
the mock returned instantly and never enforced a deadline. Full write-up in
`OFFICIAL_HINDSIGHT_REPORT.md` §6.

### 6.1 `recall_resolution` crash on non-string queries

**Severity:** Medium  
**File:** `memory/hindsight_client.py`  
**Fix:** Added `isinstance` check + `str()` coercion.  
**Regression test:** `tests/test_memory_integration.py::TestEdgeCases::test_recall_with_none_query`

### 6.2 Secrets in Recalled Memory Not Redacted

**Severity:** Medium (Security)  
**File:** `agent/core.py`  
**Fix:** Added `self._redact_secrets(fact)` to recalled facts.  
**Regression test:** `tests/test_security_injection.py::TestCredentialLeakage::test_secret_in_recalled_memory_redacted`

---

## 7. Known Limitations

These are real and are not worked around — `TASKS.md` forbids the obvious fix
(a larger model), so they are reported instead.

1. **Fact extraction is unreliable for long incidents on a 3B model.** Retain
   returns HTTP 200 and queues the document, but extraction only completes if
   the LLM finishes Hindsight's ~2,400-token strict-schema call inside the
   per-task deadline. Measured: short PostgreSQL/Redis/K8s incidents extract
   (13 facts); a longer nginx/502 incident yields **0 facts** after
   `wall=240.5s` and 4 exhausted retries. Because retain is asynchronous, the
   caller cannot tell the difference from the retain response alone — callers
   that need certainty must poll recall.
2. **Single inference slot.** `--parallel 1` is mandatory (§5.1), which means
   one slot shared by Hindsight extraction and user requests. Under extraction
   load, LLM latency degrades from 41 ms to as much as 74 s. Tight-loop recall
   polling (every 5 s) is enough to trigger it. The alternative would break
   extraction outright, so this is the accepted trade.
3. **Recall returns extracted facts, not raw text.** Verbatim-marker
   assertions are meaningless against the official engine; tests assert on
   semantic content instead.
4. **Reflect takes 156 s.** Not suitable for any interactive request path.

---

## 8. Optimization Changes

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

### 8.4 Configuration (`inference_config.py`)

- Centralized inference configuration
- All settings configurable via environment variables
- GPU device selection (defaults to discrete GPU)
- Context default raised 2048 → 8192 and batch 128 → 512 for Hindsight
- Separate `HINDSIGHT_REFLECT_TIMEOUT` (540 s) from `HINDSIGHT_TIMEOUT` (30 s)

### 8.5 Memory service

- `start_hindsight.sh` — official Vectorize Hindsight on port 8888 with CPU
  embeddings/reranking and LLM deadlines sized for a 3B model
- `requirements-hindsight.txt` — official service deps, kept out of the CI
  install so CI stays lean and hermetic
- `start_demo.sh` — starts/stops/reports the service alongside the rest

---

## 9. Lint, Type Check, and Security Scan

| Tool | Result |
|------|--------|
| ruff check | All checks passed |
| bandit | 0 issues |
| mypy | No issues (7 source files) |
| pip-audit | No known vulnerabilities |

---

## 10. Performance Summary

| Metric | Value |
|--------|-------|
| API latency (in-process) | 0.38ms |
| Analysis latency (mocked LLM) | 0.013ms |
| Analysis latency (real LLM) | ~2.9s |
| LLM latency, uncontended | 41 ms |
| LLM latency, under extraction load | up to 74 s (single slot, §7.2) |
| Hindsight `GET /health` | 2 ms |
| Hindsight recall | 882 ms |
| Hindsight reflect | 156.3 s |
| Hindsight retain (enqueue only) | 5–48 ms |
| Hindsight process RSS | 70 MB idle, ~1.1 GB while extracting |
| VRAM usage | 2.17 GB / 3.98 GB |

---

## 11. Untested Scenarios

| Scenario | Reason |
|----------|--------|
| Higher-context model behaviour | `TASKS.md` forbids switching models |
| High-concurrency stress test | Hardware constraints (single inference slot by design) |
| Long-duration stability soak | Hardware constraints |
| Streamlit browser testing | No browser; AppTest used |
| GPU memory exhaustion recovery | Requires OOM condition |

Official Hindsight integration is **not** in this list — it is tested against
the live service (§5.2).

---

## 12. Reproduction Commands

```bash
# Full test suite
cd /home/knk/SentryMind
.venv/bin/python -m pytest tests/ webapp-backend/tests/ -v

# Coverage, exactly as CI runs it
.venv/bin/python -m pytest tests/ --cov=agent --cov=memory \
  --cov-report=term-missing --cov-fail-under=90

# Official Hindsight protocol tests (mocked, fast)
.venv/bin/python -m pytest tests/test_hindsight_official_adapter.py -v

# Lint
.venv/bin/ruff check .
.venv/bin/black --check .

# Security scan
.venv/bin/bandit -r agent memory app.py config.py data -ll

# Type check
.venv/bin/mypy agent/ memory/ config.py app.py --ignore-missing-imports

# Live integration tests (llama.cpp on 1234 + Hindsight on 8888)
SENTRYMIND_RUN_LIVE_INTEGRATION=1 \
LOCAL_LLM_URL=http://127.0.0.1:1234/v1 \
HINDSIGHT_API_URL=http://127.0.0.1:8888 \
.venv/bin/python -m pytest tests/ webapp-backend/tests/ -q

# Live API tests
cd webapp-backend
SENTRYMIND_RUN_LIVE_INTEGRATION=1 ../.venv/bin/python -m pytest tests/test_api_live.py -v

# Start the demo stack (llama.cpp + official Hindsight + UI)
./start_demo.sh

# Prove memory persists across a service restart
.venv/bin/python scripts/persistence_probe.py retain
#   ... restart Hindsight ...
.venv/bin/python scripts/persistence_probe.py recall
```

---

## 13. Conclusion

**396 tests pass** (0 skipped with the live flag) with **97% branch coverage**
against a 90% gate, and all lint, type-check and security gates are clean.

The substantive result of this round is that memory is now genuinely
persistent, official, and verified end to end: facts are extracted by a real
LLM, embedded, retrieved semantically, synthesised across incidents, and
**proven to survive a service restart** by matching fact IDs rather than
trusting a status code.

Equally important is what testing against the real service exposed. Six
defects lived in the adapter, and the one that mattered — reflect never having
worked — was completely invisible to a test suite built on a mock that returned
instantly and enforced no deadlines. The lesson recorded in
`OFFICIAL_HINDSIGHT_REPORT.md` is that the `backend` provenance field and the
mocked protocol tests exist precisely so that this class of silent degradation
cannot pass unnoticed again.
