# SentryMind Testing Guide

**Date:** 2026-09-28  
**Purpose:** Instructions for reproducing all tests in the SentryMind repository

---

## 1. Prerequisites

### 1.1 Environment

```bash
cd /home/knk/SentryMind
source .venv/bin/activate  # or use .venv/bin/python directly
```

### 1.2 Required Tools

All tools are in the project `.venv`:
- `pytest` — test runner
- `pytest-cov` — coverage
- `ruff` — linter
- `bandit` — security scanner
- `mypy` — type checker
- `pip-audit` — dependency auditor
- `httpx` — ASGI transport for tests

### 1.3 Start the Live Server (for live tests)

```bash
cd webapp-backend
../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001 &
```

### 1.4 Start the Official Hindsight Service (optional)

The default test run does **not** need this — every memory test uses mocks and
`conftest.py` blocks outbound HTTP. Only the live tests in §2.5 need it.

```bash
cd /home/knk/SentryMind
.venv/bin/pip install -r requirements-hindsight.txt   # once
bash start_hindsight.sh                               # official API, port 8888
curl -s http://127.0.0.1:8888/health
# Expected: {"status":"healthy","database":"connected",...}
```

Note the port: the **official** service is on 8888. A legacy mock service may
also be running on 8080; point `HINDSIGHT_API_URL` at whichever you intend to
test, and be explicit about it, because the two have different response
schemas. See `OFFICIAL_HINDSIGHT_REPORT.md` §4.

llama.cpp must be running for Hindsight to be able to do any LLM work, and it
**must** use `--parallel 1` — see `MODEL_CONFIG.md` §4.2.

---

## 2. Running the Full Test Suite

### 2.1 All Tests (Deterministic)

```bash
cd /home/knk/SentryMind
.venv/bin/python -m pytest tests/ webapp-backend/tests/ -v --tb=short
```

**Expected:** 375 passed, 21 skipped

### 2.2 With Coverage (exactly as CI runs it)

```bash
.venv/bin/python -m pytest tests/ --cov=agent --cov=memory \
  --cov-report=term-missing --cov-fail-under=90
```

**Expected:** ~97% total; the gate is 90%

```text
Name                         Stmts   Miss Branch BrPart  Cover
agent/core.py                  109      3     34      3    96%
memory/hindsight_client.py     134      0     50      4    98%
TOTAL                          243      3     84      7    97%
```

### 2.3 Live API Tests

```bash
# Terminal 1: Start server
cd webapp-backend
../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001

# Terminal 2: Run live tests
cd webapp-backend
SENTRYMIND_RUN_LIVE_INTEGRATION=1 ../.venv/bin/python -m pytest tests/test_api_live.py -v
```

**Expected:** 12 passed

### 2.4 Official Hindsight Protocol Tests (no live service needed)

```bash
.venv/bin/python -m pytest tests/test_hindsight_official_adapter.py -v
```

**Expected:** 37 passed. These pin the official API wire contract — multipart
retain, `404`-then-provision, `text` vs `content`, `results` must be a list,
reflect reads `text`, `/health` readiness — entirely with mocks.

### 2.5 Live LLM + Official Hindsight Tests

Requires llama.cpp on 1234 and Hindsight on 8888.

```bash
export LOCAL_LLM_URL=http://127.0.0.1:1234/v1
export HINDSIGHT_API_URL=http://127.0.0.1:8888
SENTRYMIND_RUN_LIVE_INTEGRATION=1 .venv/bin/python -m pytest \
  tests/real_services/test_live_services.py tests/test_official_hindsight.py -v
```

**Expected:** 9 passed. Allow ~4 minutes — the reflect test alone measures
156 s against the real service.

---

## 3. Running Individual Test Suites

### 3.1 Agent Unit Tests

```bash
.venv/bin/python -m pytest tests/test_agent_unit.py -v
```

### 3.2 Memory Unit Tests

```bash
.venv/bin/python -m pytest tests/test_memory_unit.py -v
```

### 3.3 AI Reliability Tests

```bash
.venv/bin/python -m pytest tests/test_ai_reliability.py -v
```

### 3.4 Memory Integration Tests

```bash
.venv/bin/python -m pytest tests/test_memory_integration.py -v
```

### 3.5 Security Injection Tests

```bash
.venv/bin/python -m pytest tests/test_security_injection.py -v
```

### 3.6 Branch Coverage Tests

```bash
.venv/bin/python -m pytest tests/test_branch_coverage.py -v
```

### 3.7 Backend API Tests (In-Process)

```bash
cd webapp-backend
../.venv/bin/python -m pytest tests/test_api.py -v
```

### 3.8 Backend API Tests (Live)

```bash
cd webapp-backend
SENTRYMIND_RUN_LIVE_INTEGRATION=1 ../.venv/bin/python -m pytest tests/test_api_live.py -v
```

### 3.9 Streamlit UI Tests

```bash
.venv/bin/python -m pytest tests/test_streamlit_ui.py -v
```

### 3.10 Security Reliability Tests

```bash
.venv/bin/python -m pytest tests/test_security_reliability.py -v
```

### 3.11 Official Hindsight Adapter Tests (mocked)

```bash
.venv/bin/python -m pytest tests/test_hindsight_official_adapter.py -v
```

### 3.12 Official Hindsight Live Tests

```bash
SENTRYMIND_RUN_LIVE_INTEGRATION=1 HINDSIGHT_API_URL=http://127.0.0.1:8888 \
  .venv/bin/python -m pytest tests/test_official_hindsight.py -v
```

Skipped unless `SENTRYMIND_RUN_LIVE_INTEGRATION=1` **and** the service is up.

---

## 4. Lint, Type Check, and Security Scan

### 4.1 Ruff

```bash
.venv/bin/ruff check .
```

**Expected:** All checks passed

### 4.2 Bandit

```bash
.venv/bin/bandit -r agent memory app.py config.py data -ll
```

**Expected:** 0 issues

### 4.3 mypy

```bash
.venv/bin/mypy agent/ memory/ config.py app.py --ignore-missing-imports
```

**Expected:** No issues

### 4.4 pip-audit

```bash
.venv/bin/pip-audit
```

**Expected:** No known vulnerabilities

---

## 5. Performance Benchmark

```bash
.venv/bin/python tests/performance_benchmark.py
```

**Expected output:**
```
--- API Latency (in-process ASGI) ---
GET /           mean=0.385ms  median=0.378ms  p95=0.405ms
GET /health     mean=0.381ms  median=0.375ms  p95=0.401ms

--- Incident Analysis Latency (mocked LLM) ---
analyze (no mem) mean=0.012ms  median=0.011ms  p95=0.014ms
analyze (w/ mem) mean=0.054ms  median=0.035ms  p95=0.045ms

--- Memory Latency (local fallback) ---
retain_incident  mean=0.009ms  median=0.008ms  p95=0.012ms
recall_resolution mean=0.028ms  median=0.026ms  p95=0.031ms
```

---

## 6. Live HTTP Checks (Manual)

### 6.1 Start Server

```bash
cd webapp-backend
../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

### 6.2 Check Endpoints

```bash
# Root
curl -s http://localhost:8001/
# Expected: {"status":"ok","message":"Backend API is running!"}

# Health
curl -s http://localhost:8001/health
# Expected: {"status":"healthy"}

# 404
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/nonexistent
# Expected: 404

# OpenAPI spec
curl -s http://localhost:8001/openapi.json | python3 -m json.tool

# Docs
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/docs
# Expected: 200
```

### 6.3 Check Server Resources

```bash
ps aux | grep "uvicorn.*8001" | grep -v grep | awk '{print "CPU:", $3"%", "MEM:", $4"%", "RSS:", $6/1024"MB"}'
```

---

## 7. Test File Reference

| File | Tests | Description |
|------|-------|-------------|
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
| `tests/test_hindsight_official_adapter.py` | 37 | Official Hindsight wire contract (mocked) |
| `tests/test_official_hindsight.py` | 7 | Opt-in live official Hindsight |
| `webapp-backend/tests/test_api.py` | 56 | FastAPI endpoint tests (in-process) |
| `webapp-backend/tests/test_api_live.py` | 12 | Live HTTP integration tests |
| `tests/real_services/test_live_services.py` | 2 | Opt-in live LLM/Hindsight |
| `tests/performance_benchmark.py` | — | Performance benchmark script |

---

## 8. Understanding Test Markers

### 8.1 Integration Marker

Tests marked with `@pytest.mark.integration` require external services:
- `tests/real_services/test_live_services.py` — requires llama.cpp on 1234 and Hindsight
- `tests/test_official_hindsight.py` — requires the official Hindsight on 8888
- `webapp-backend/tests/test_api_live.py` — requires Uvicorn on port 8001

These tests are **skipped by default** and only run when `SENTRYMIND_RUN_LIVE_INTEGRATION=1` is set.

### 8.2 Timeouts

`pyproject.toml` sets a global `--timeout=20`. Live LLM tests override it with
an explicit marker (`@pytest.mark.timeout(120)` for the LLM, `400` for
reflect). This is not slack: llama.cpp runs with `--parallel 1` so Hindsight's
~2.4k-token extraction prompt gets the full 8,192-token context, which means
there is exactly one inference slot and requests queue behind each other. A
20 s budget is a coin flip under those conditions.

### 8.3 Hypothesis

`tests/test_security_reliability.py` uses Hypothesis for property-based testing:
- `test_arbitrary_incident_text_never_crashes_analysis` — tests with random text inputs

---

## 9. Troubleshooting

### 9.1 Tests Fail with ConnectionError

**Cause:** The `conftest.py` autouse fixture blocks all external HTTP requests in deterministic tests.  
**Fix:** This is expected behavior. Use mocking for service calls.

### 9.2 Live Tests Skip

**Cause:** `SENTRYMIND_RUN_LIVE_INTEGRATION` is not set.  
**Fix:** `export SENTRYMIND_RUN_LIVE_INTEGRATION=1`

### 9.3 Server Already Running on Port 8001

**Fix:** `kill $(lsof -t -i:8001)` or use a different port.

### 9.4 Coverage Below the 90% Gate

**Cause:** New code added without tests. CI runs
`pytest tests/ --cov=agent --cov=memory --cov-fail-under=90`.  
**Fix:** Run `coverage report -m` to find uncovered lines. The gate is 90%, not
100% — but the official Hindsight adapter must stay well above it, because it is
the component whose bugs were silent.

### 9.5 `test_official_reflect_returns_synthesis` Times Out

**Cause:** Reflect is a multi-call synthesis on a single inference slot. It
measures 156 s; the marker allows 400 s. Anything that issues LLM requests
concurrently — notably tight-loop recall polling — will make it slower still.  
**Fix:** Stop polling recall in a loop while the suite runs. The service log at
`tmux capture-pane -t hindsight -p -S -200` shows slot contention.

### 9.6 Live Memory Test Fails Because `HINDSIGHT_API_URL` Is Unset

**By design.** `tests/real_services/test_live_services.py` calls
`pytest.fail` when the variable is missing, so a live run cannot silently pass
by skipping the memory check. Set it explicitly:

```bash
export HINDSIGHT_API_URL=http://127.0.0.1:8888
```

---

## 10. CI/CD Integration

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request:

1. **SentryMind job:** ruff, black, mypy, pip-audit, bandit, pytest with coverage
2. **webapp-backend job:** ruff, black, mypy, pip-audit, bandit, pytest with coverage
3. **webapp-frontend job:** eslint, prettier, npm audit, build

All jobs must pass before merging.
