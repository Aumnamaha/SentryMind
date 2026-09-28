# SentryMind Optimization Baseline

**Date:** 2026-09-28
**Commit:** `78fd634` (+ working tree)
**Purpose:** Phase 0 record of measured state before resource optimization, per `TASKS.md`.

All figures below are **measured**, not estimated. Commands used are given so each
number can be reproduced.

---

## 1. Environment

| Property | Value | How measured |
|----------|-------|--------------|
| CPU | Ryzen 5 5600H, 12 threads | `nproc` |
| RAM total | 15,310 MB | `free -m` |
| RAM available (idle) | 9,386 MB | `free -m` |
| Disk free (`/home`) | 8.6 GB of 235 GB | `df -h /home` |
| GPU (discrete) | AMD Radeon RX 6500M (NAVI24) | `lspci` |
| GPU VRAM total | 3.98 GB | `cat /sys/class/drm/card1/device/mem_info_vram_total` |
| GPU (integrated) | AMD Radeon (RENOIR), 512 MB | `lspci` |
| OS | CachyOS / Linux | `uname -r` |
| Vulkan driver | Mesa RADV 26.2.3 | `pacman -Q` |

---

## 2. Model Configuration

| Property | Value |
|----------|-------|
| Model | Qwen2.5-3B-Instruct |
| Quantization | Q4_K_M (GGUF) |
| File | `models/Qwen2.5-3B-Instruct-Q4_K_M.gguf` |
| Size on disk | 2.1 GB |
| Runtime | llama.cpp v0.5.0, built `-DGGML_VULKAN=ON` |
| Binary | `/tmp/opencode/llama.cpp/build/bin/llama-server` |
| Port | 1234 (OpenAI-compatible) |

### 2.1 llama-server flags (current)

```
--ctx-size 8192 --parallel 1 --n-gpu-layers 99 \
--batch-size 512 --ubatch-size 512 --threads 6
```

`--parallel 1` is required. llama-server defaults to **4 slots**, which divides
the context window per slot (`n_ctx / 4 = 2048`). Hindsight's fact-extraction
prompt is ~2.4k tokens and reflect needs ~7.8k, so a split context makes every
extraction fail with `Context size has been exceeded`. Measured proof:

| Prompt size | `-np 4` (default) | `-np 1` |
|-------------|-------------------|---------|
| 3,000 words | HTTP 200 | HTTP 200 |
| 5,000 words | **HTTP 500** `Context size has been exceeded.` | HTTP 200 |
| 7,000 words | **HTTP 500** | HTTP 200 |
| 8,000 words | **HTTP 500** | HTTP 500 (genuinely over 8192) |

---

## 3. Inference Performance (measured)

Benchmark: `"Reply with the single word: ready"`, `max_tokens=8`, no concurrent load.

| Metric | Value |
|--------|-------|
| Latency (mean of 3) | **41 ms** |
| Generation throughput | **~48 tok/s** |
| Prompt tokens | 36 |
| Completion tokens | 2 |

> **Contention caveat:** when Hindsight's background extraction worker is actively
> issuing LLM calls, measured latency rose to 74,000 ms (0.3 tok/s). This is queue
> contention on a single inference slot, not a configuration regression. Polling
> recall in a tight loop (every 5 s) is enough to trigger it.

---

## 4. VRAM Usage

| State | VRAM used | VRAM total |
|-------|-----------|------------|
| Model loaded, idle | **2.17 GB** | 3.98 GB |
| Headroom | 1.81 GB | — |

Breakdown: ~1.9 GB Q4_K_M weights + ~0.27 GB KV cache for an 8,192-token context
on a single slot.

---

## 5. RAM Usage

| Process | RSS | CPU |
|---------|-----|-----|
| `llama-server` | 594 MB | 30.1% |
| `hindsight_api.server` (idle) | 70 MB | 2.2% |
| `hindsight_api.server` (extracting) | ~750 MB | up to 100% of 1 core |
| pg0 embedded PostgreSQL | 10 MB | ~0% |
| Streamlit | 14 MB | ~0% |
| FastAPI backend | 10 MB | ~0% |

System-wide: **5,924 MB used / 15,310 MB** at idle with everything running.

---

## 6. Hindsight Configuration (OFFICIAL Vectorize)

| Property | Value |
|----------|-------|
| Package | `hindsight-api-slim` 0.10.1 (official, from PyPI) |
| Extras | `hindsight-api-slim[embedded-db]` (`pg0-embedded` 0.15.2) |
| Local ML | `torch` 2.14.0+cpu, `sentence-transformers` 6.1.0, `transformers` 5.17.0 |
| API URL | `http://127.0.0.1:8888` |
| Port | 8888 (official API port) |
| LLM provider | `lmstudio` → the llama.cpp server on 1234 |
| LLM model | `qwen2.5-3b-instruct` |
| Structured output | `HINDSIGHT_API_LLM_STRICT_SCHEMA=true` |
| Embeddings | `local` / `BAAI/bge-small-en-v1.5` (384-dim, CPU) |
| Reranker | `local` / `cross-encoder/ms-marco-MiniLM-L-6-v2` (CPU) |
| Worker ID | `sentrymind-hindsight` (stable) |
| Database | embedded PostgreSQL via `pg0`, data in `~/.pg0` (141 MB) |
| Model cache | `~/.cache/huggingface` (217 MB) |

### 6.1 Measured endpoint latency

| Endpoint | HTTP | Latency |
|----------|------|---------|
| `GET /health` | 200 | 2 ms |
| `POST .../memories/recall` | 200 | 882 ms |

### 6.2 Memory banks in use

| Bank | Facts recalled | Purpose |
|------|----------------|---------|
| `sentrymind-devops` | 0 | production bank (`HINDSIGHT_BANK_ID`) |
| `sentrymind-official-test` | **13** | integration tests |
| `sentrymind-verify`, `sentrymind-persist`, `sentrymind-newbank-probe` | 0 | verification scratch banks |

---

## 7. Test Count

| Suite | Result |
|-------|--------|
| `pytest tests/ webapp-backend/tests/` (no live flag) | **352 passed** |
| `pytest tests/ webapp-backend/tests/` with `SENTRYMIND_RUN_LIVE_INTEGRATION=1` | **358 passed, 0 skipped** |

The 6-test delta is `tests/test_official_hindsight.py` (official-service suite).

---

## 8. Disk Footprint

| Item | Size |
|------|------|
| `.venv` (after official Hindsight install) | 2.7 GB |
| ├─ `torch` (CPU-only) | 772 MB |
| ├─ `transformers` | 116 MB |
| └─ `sentence-transformers` | 6 MB |
| `models/Qwen2.5-3B-Instruct-Q4_K_M.gguf` | 2.1 GB |
| `~/.pg0` (embedded Postgres) | 141 MB |
| `~/.cache/huggingface` (bge + reranker) | 217 MB |

Disk headroom is the binding constraint on this machine: only **8.6 GB free**.
This is why the official full Docker image (~9 GB) was rejected in favour of
`hindsight-api-slim` + CPU-only torch on the host.

---

## 9. Git State

```
78fd634 Fix black formatting for CI pipeline compliance
030586a Add comprehensive testing, optimization, and hackathon demo features
f281deb Fix webapp-backend ruff scope and import order
```

Modified at baseline time: `config.py`, `inference_config.py`,
`memory/hindsight_client.py`, `tests/*`, plus new `scripts/`, `docker/`,
`start_hindsight.sh`, `start_llama.sh`, `tests/test_official_hindsight.py`.

No unrelated user changes were overwritten. The n8n Docker stack and the
persistent mock Hindsight on port 8080 were left untouched.
