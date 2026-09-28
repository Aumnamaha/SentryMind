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

---

## 2. Running the Full Test Suite

### 2.1 All Tests (Deterministic)

```bash
cd /home/knk/SentryMind
.venv/bin/python -m pytest tests/ webapp-backend/tests/ -v --tb=short
```

**Expected:** 294 passed, 14 skipped

### 2.2 With Coverage

```bash
.venv/bin/python -m pytest tests/ webapp-backend/tests/ \
  --cov=agent --cov=memory --cov-report=term-missing
```

**Expected:** 100% coverage on agent/core.py and memory/hindsight_client.py

### 2.3 Live Integration Tests

```bash
# Terminal 1: Start server
cd webapp-backend
../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001

# Terminal 2: Run live tests
cd webapp-backend
SENTRYMIND_RUN_LIVE_INTEGRATION=1 ../.venv/bin/python -m pytest tests/test_api_live.py -v
```

**Expected:** 12 passed

### 2.4 Live LLM/Hindsight Integration Tests

```bash
# Requires LM Studio and Hindsight running
export LOCAL_LLM_URL=http://localhost:1234/v1
export HINDSIGHT_API_URL=http://localhost:8080
SENTRYMIND_RUN_LIVE_INTEGRATION=1 .venv/bin/python -m pytest tests/real_services/test_live_services.py -v
```

**Expected:** 2 passed (if services are running)

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
| `webapp-backend/tests/test_api.py` | 56 | FastAPI endpoint tests (in-process) |
| `webapp-backend/tests/test_api_live.py` | 12 | Live HTTP integration tests |
| `tests/real_services/test_live_services.py` | 2 | Opt-in live LLM/Hindsight |
| `tests/performance_benchmark.py` | — | Performance benchmark script |

---

## 8. Understanding Test Markers

### 8.1 Integration Marker

Tests marked with `@pytest.mark.integration` require external services:
- `tests/real_services/test_live_services.py` — requires LM Studio and Hindsight
- `webapp-backend/tests/test_api_live.py` — requires Uvicorn on port 8001

These tests are **skipped by default** and only run when `SENTRYMIND_RUN_LIVE_INTEGRATION=1` is set.

### 8.2 Hypothesis

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

### 9.4 Coverage Below 100%

**Cause:** New code added without tests.  
**Fix:** Run `coverage report -m` to find uncovered lines.

---

## 10. CI/CD Integration

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request:

1. **SentryMind job:** ruff, black, mypy, pip-audit, bandit, pytest with coverage
2. **webapp-backend job:** ruff, black, mypy, pip-audit, bandit, pytest with coverage
3. **webapp-frontend job:** eslint, prettier, npm audit, build

All jobs must pass before merging.
