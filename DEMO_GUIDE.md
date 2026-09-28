# SentryMind Demo Guide

**Date:** 2026-09-28  
**Purpose:** Reliable 3-minute live demonstration for hackathon

---

## 1. Pre-Demo Checklist

### 1.1 Start Services

The simplest path — `start_demo.sh` brings up llama.cpp, the official Hindsight
service, and the UI, and waits for each to be healthy:

```bash
cd /home/knk/SentryMind
./start_demo.sh              # add --no-memory to skip Hindsight
./start_demo.sh --status     # check what is running
```

To start them by hand instead:

```bash
# Terminal 1: inference server (takes ~30s to load the model)
# NOTE --parallel 1 is required. llama-server defaults to 4 slots and splits
# the context window between them, which breaks every Hindsight extraction
# with "Context size has been exceeded". See MODEL_CONFIG.md section 4.2.
cd /home/knk/SentryMind/models
/tmp/opencode/llama.cpp/build/bin/llama-server \
  -m Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 1234 \
  --ctx-size 8192 --parallel 1 --n-gpu-layers 99 \
  --batch-size 512 --ubatch-size 512 \
  --threads 6

# Wait for "listening on http://127.0.0.1:1234"

# Terminal 2: official Vectorize Hindsight (port 8888, persistent)
cd /home/knk/SentryMind
bash start_hindsight.sh

# Wait for {"status":"healthy","database":"connected"}

# Terminal 3: Streamlit UI
cd /home/knk/SentryMind
.venv/bin/streamlit run app.py

# Open http://localhost:8501 in browser
```

### 1.2 Verify Services

```bash
# Check inference server
curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool

# Check the official memory service (port 8888, not 8080)
curl -s http://127.0.0.1:8888/health

# Check VRAM usage
cat /sys/class/drm/card1/device/mem_info_vram_used | awk '{printf "%.2f GB\n", $1/1024/1024/1024}'
# Expected: ~2.17 GB of 3.98 GB
```

### 1.3 Know the Memory Banner

The UI labels the memory source explicitly, and the label is never
misleading — a mock or a fallback is never shown as official Hindsight:

| Banner | Meaning |
|--------|---------|
| `HINDSIGHT (persistent)` | Official Vectorize Hindsight. Survives restarts. |
| `LOCAL FALLBACK (in-memory only, NOT persistent)` | Service unreachable. Memory is lost on restart. |

If you see the fallback banner during a demo, stop and fix it — the "it
remembers" narrative does not hold without the real service.

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

**Note:** measured VRAM at the full 8,192 context is only 2.17 GB of 3.98 GB,
so this is unlikely with the shipped flags. Qwen2.5-3B's grouped-query
attention keeps the KV cache small.

**Fix, in order of preference:**
```bash
# 1. Reduce batch size first — this costs the least (no context reduction)
--batch-size 256 --ubatch-size 256

# 2. Only if that is not enough, reduce the context.
#    WARNING: below 8192 Hindsight fact extraction (~2.4k tokens) and
#    reflect (~8k tokens) will fail. Do not drop below 4096 if you are
#    demoing memory.
--ctx-size 4096

# 3. Last resort, CPU-only. Usable but ~10x slower:
--n-gpu-layers 0 --threads 12
```

### 5.4 If the Official Memory Service is Unavailable

**Behavior:** the agent falls back to a local in-memory store and the UI shows
`LOCAL FALLBACK (in-memory only, NOT persistent)`.

**User impact:** memory works for the current session but is lost on restart.

**Demo impact:** this *does* undercut the "it remembers across restarts"
narrative. Fix it rather than demoing around it:

```bash
curl -s http://127.0.0.1:8888/health    # expect "healthy"

# If it is down, restart it and wait ~30s for model load
tmux kill-session -t hindsight 2>/dev/null
tmux new-session -d -s hindsight "bash /home/knk/SentryMind/start_hindsight.sh"

# Prove persistence is real (this is the strongest demo moment available)
.venv/bin/python scripts/persistence_probe.py retain
# restart the service, then:
.venv/bin/python scripts/persistence_probe.py recall
# -> "POST-RESTART MEMORY SURVIVED: True"
```

If you genuinely cannot get it running, demo without memory
(`./start_demo.sh --no-memory`) and say so plainly. Do not let the fallback
banner stand in for the real service.

### 5.5 If Retain Appears to Succeed but Nothing Is Remembered

**This is expected behaviour and it will bite you during a demo.** Retain is
asynchronous: it returns HTTP 200 with `operation_ids` immediately and the LLM
extracts facts in the background. On a 3B model, extraction of a *short*
incident reliably succeeds, but a *long* one exhausts Hindsight's per-task
deadline and yields 0 facts while retain still reported success.

**Fix:** use a short incident for the retain demo. Keep it to one or two
sentences — the short PostgreSQL/Redis/Kubernetes incidents in §3.1 all extract
cleanly. Then wait a few seconds before the recall step.

---

## 6. Demo Recovery Procedure

If anything goes wrong during the demo:

1. **Don't panic** — the system is designed to degrade gracefully
2. **Check inference server:** `curl -s http://127.0.0.1:1234/v1/models`
3. **Check memory service:** `curl -s http://127.0.0.1:8888/health`
4. **Restart if needed:** Use the commands in Section 1.1
5. **Fallback to CPU:** If Vulkan fails, use `--n-gpu-layers 0`
6. **Continue demo:** the UI works even without the LLM — but say out loud that
   you are now in degraded mode rather than pretending it is the real thing

---

## 7. Key Talking Points

1. **"Runs entirely on your laptop"** — No cloud, no data leaves the machine
2. **"Evidence-grounded diagnosis"** — Every conclusion links to specific log lines
3. **"Memory-assisted, not memory-dependent"** — Works with or without historical context
4. **"Privacy by design"** — Secrets redacted before any external call
5. **"Transparent uncertainty"** — Confidence levels and uncertainty clearly displayed
6. **"Suggests, doesn't execute"** — All remediation labeled "NOT verified"
7. **"The memory is real and it's yours"** — Official Vectorize Hindsight with
   an embedded PostgreSQL database on disk. Restart the service live and recall
   the same incident; the bank survives because the records came back from the
   database, not from a cache. We verified 13/13 fact IDs surviving a full
   restart.

---

## 8. Post-Demo Cleanup

```bash
# Stop everything
./start_demo.sh --stop

# Verify GPU memory released
cat /sys/class/drm/card1/device/mem_info_vram_used | awk '{printf "%.2f GB\n", $1/1024/1024/1024}'
# Should show ~0 GB
```

Hindsight's data is **not** deleted by `--stop`: the embedded PostgreSQL lives
in `~/.pg0`, so memories persist across demo sessions. Remove it only if you
want a clean slate:

```bash
rm -rf ~/.pg0
```
