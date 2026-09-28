# SentryMind Demo Guide

**Date:** 2026-09-28  
**Purpose:** Reliable 3-minute live demonstration for hackathon

---

## 1. Pre-Demo Checklist

### 1.1 Start Services

```bash
# Terminal 1: Start inference server (takes ~30s to load model)
cd /home/knk/SentryMind/models
/tmp/opencode/llama.cpp/build/bin/llama-server \
  -m Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 1234 \
  --ctx-size 2048 --n-gpu-layers 99 \
  --batch-size 128 --ubatch-size 128 \
  --threads 6

# Wait for "listening on http://127.0.0.1:1234"

# Terminal 2: Start Streamlit UI
cd /home/knk/SentryMind
.venv/bin/streamlit run app.py

# Open http://localhost:8501 in browser
```

### 1.2 Verify Services

```bash
# Check inference server
curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool

# Check VRAM usage
cat /sys/class/drm/card1/device/mem_info_vram_used | awk '{printf "%.2f GB\n", $1/1024/1024/1024}'
```

---

## 2. Three-Minute Demo Script

### Minute 1: First-Time Analysis (No Memory)

1. **Select incident:** "INC-001 - PostgreSQL Connection Pool Exhausted"
2. **Click:** "Analyze Log (Without Memory)"
3. **Observe:**
   - Latency: ~2-3s
   - Confidence: "Low (Baseline Local LLM Guess)"
   - Diagnosis: Generic "connection pool exhausted" hypothesis
   - No recalled context
   - Remediation labeled "NOT verified"

**Narrative:** *"Without memory, the AI gives a generic guess. It knows connection pools can exhaust, but has no historical context."*

### Minute 2: Memory-Assisted Analysis

1. **Click:** "Analyze Log (With Memory Recall)"
2. **Observe:**
   - Latency: ~2-3s
   - Confidence: "Moderate (Historical context; verify before action)"
   - Diagnosis: Specific reference to PostgreSQL connection slots
   - Recalled context: Shows the stored incident post-mortem
   - Evidence: Links to specific log lines
   - Remediation: References the historical fix (flush_pool.sh)

**Narrative:** *"With memory, the AI recalls a similar past incident and its verified fix. Notice the evidence links and the clear 'NOT verified' label — the AI suggests, the operator disposes."*

### Minute 3: Privacy & Performance

1. **Expand:** "Show secret redaction in action"
2. **Observe:** API key and password redacted before LLM
3. **Toggle:** "Show Performance Dashboard"
4. **Observe:**
   - Analysis latency
   - Memory bank size
   - Inference status (green = running)

**Narrative:** *"SentryMind redacts secrets before any external call, and runs entirely on your laptop — no cloud, no data leaves the machine."*

---

## 3. Synthetic Incident Fixtures

### 3.1 Pre-Loaded Incidents

| ID | Title | Error Log |
|----|-------|-----------|
| INC-001 | PostgreSQL Connection Pool Exhausted | `FATAL: remaining connection slots are reserved for non-replication superuser connections` |
| INC-002 | Redis OOM Maxmemory Limit Reached | `OOM command not allowed when used memory > 'maxmemory'` |
| INC-003 | Kubernetes CrashLoopBackOff on Auth Microservice | `Error: Invalid OAUTH_CACHE_TTL format '300s' expected integer milliseconds` |

### 3.2 Custom Incident (for Retain Demo)

```
Incident ID: INC-004
Raw Log: ERROR: Redis Connection Timeout on Port 6379
Root Cause: Stale DNS record on Auth Gateway
Verified Fix: Run systemctl restart systemd-resolved
```

---

## 4. Expected Observable Behavior

### 4.1 First-Time Analysis (No Memory)

| Field | Expected Value |
|-------|---------------|
| Latency | 2-4s |
| Confidence | Low |
| Memory Active | No |
| Recalled Context | Empty |
| Remediation | Generic ("Restart service") |

### 4.2 Memory-Assisted Analysis

| Field | Expected Value |
|-------|---------------|
| Latency | 2-4s |
| Confidence | Moderate |
| Memory Active | Yes |
| Recalled Context | 1-3 items |
| Evidence | Specific log lines |
| Remediation | References historical fix |

### 4.3 Secret Redaction

| Input | Output |
|-------|--------|
| `api_key=sk-test-12345` | `api_key=[REDACTED]` |
| `password=hunter2` | `password=[REDACTED]` |
| `AKIA1234567890ABCDEF` | `[REDACTED_AWS_KEY]` |

---

## 5. Fallback Plan

### 5.1 If Inference Server Fails to Start

**Symptom:** Streamlit shows "🔴 Local LLM is not available"

**Fix:**
```bash
# Check server logs
tail -20 /tmp/opencode/llama-server.log

# Common issues:
# 1. Port already in use: kill existing process
kill $(lsof -t -i:1234)

# 2. Model file not found
ls -la /home/knk/SentryMind/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf

# 3. Vulkan not working: restart with CPU fallback
/tmp/opencode/llama.cpp/build/bin/llama-server \
  -m Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 1234 \
  --ctx-size 2048 --n-gpu-layers 0 --threads 12
```

### 5.2 If Streamlit Fails to Start

**Symptom:** Cannot open http://localhost:8501

**Fix:**
```bash
# Check if streamlit is installed
.venv/bin/python -c "import streamlit; print(streamlit.__version__)"

# Reinstall if needed
.venv/bin/pip install streamlit

# Start with explicit port
.venv/bin/streamlit run app.py --server.port 8501
```

### 5.3 If VRAM is Exhausted

**Symptom:** Server crashes or shows OOM errors

**Fix:**
```bash
# Reduce context size
export SENTRYMIND_CONTEXT_SIZE=1024

# Or use CPU fallback (slower but stable)
--n-gpu-layers 0 --threads 12
```

### 5.4 If Memory Service is Unavailable

**Behavior:** Agent falls back to local in-memory store (transparent)

**User Impact:** Memory works locally but is not persistent across restarts

**Demo Impact:** None — the fallback is seamless and clearly indicated

---

## 6. Demo Recovery Procedure

If anything goes wrong during the demo:

1. **Don't panic** — the system is designed to degrade gracefully
2. **Check inference server:** `curl -s http://127.0.0.1:1234/v1/models`
3. **Restart if needed:** Use the commands in Section 1.1
4. **Fallback to CPU:** If Vulkan fails, use `--n-gpu-layers 0`
5. **Continue demo:** The UI works even without the LLM (shows fallback messages)

---

## 7. Key Talking Points

1. **"Runs entirely on your laptop"** — No cloud, no data leaves the machine
2. **"Evidence-grounded diagnosis"** — Every conclusion links to specific log lines
3. **"Memory-assisted, not memory-dependent"** — Works with or without historical context
4. **"Privacy by design"** — Secrets redacted before any external call
5. **"Transparent uncertainty"** — Confidence levels and uncertainty clearly displayed
6. **"Suggests, doesn't execute"** — All remediation labeled "NOT verified"

---

## 8. Post-Demo Cleanup

```bash
# Stop inference server
kill $(lsof -t -i:1234)

# Stop Streamlit
# Ctrl+C in the Streamlit terminal

# Verify GPU memory released
cat /sys/class/drm/card1/device/mem_info_vram_used | awk '{printf "%.2f GB\n", $1/1024/1024/1024}'
# Should show ~0 GB
```
