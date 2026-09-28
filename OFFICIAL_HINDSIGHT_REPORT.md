# Official Vectorize Hindsight Integration Report

**Date:** 2026-09-28
**Status:** Retain, Recall and Reflect verified against the official service.
Persistence verified. Two real defects found and fixed during integration.

---

## 1. Executive Summary

The persistent mock Hindsight service has been replaced by the **official
Vectorize Hindsight** engine (`hindsight-api-slim` 0.10.1, from PyPI), running on
the official API port **8888** with an embedded PostgreSQL database.

| Capability | Verified | Evidence |
|------------|----------|----------|
| Service starts and reports healthy | Yes | `GET /health` → `{"status":"healthy","database":"connected"}` |
| Retain (real ingestion) | Yes | HTTP 200 + `operation_ids`, measured 5–48 ms |
| Async fact extraction by the LLM | Yes | log `Complete: 13 facts (617 tok)` |
| Recall (semantic, via embeddings + reranker) | Yes | 13 extracted facts returned for a related query |
| Reflect (LLM synthesis across incidents) | Yes | HTTP 200 in 156.3 s, 8,994 input / 842 output tokens |
| Persistence across service restart | Yes | see §5 |
| App-restart survival (new manager process) | Yes | see §5 |
| Secret redaction before retention | Yes | covered by test suite |
| Graceful degradation when service is down | Yes | local fallback, clearly labelled |

Two genuine adapter defects were found **by** this verification and fixed; both
would have silently corrupted results. They are documented in §6.

---

## 2. Why host-installed instead of Docker

The official docs offer `ghcr.io/vectorize-io/hindsight:latest` (~9 GB) and
`...:latest-slim` (~500 MB).

**The full image was rejected**: this machine had 12 GB free at the time and
now has 8.6 GB. A 9 GB image does not fit with room for the database and model.

**The slim image does not work standalone.** It logs, on startup:

```
Local ML provider configured for embeddings and reranker, but
'sentence-transformers' is not installed. The API will fail at startup.
```

The slim image has no embedding or reranker models and no local-ML extras, and
the `llamacpp` LLM provider is not available in the container. Building a custom
image with `sentence-transformers` was attempted and abandoned (the PyTorch
wheel made the build exceed 10 minutes).

**What was done instead**: `hindsight-api-slim` installed directly into the
project venv together with `hindsight-api-slim[embedded-db]` (for `pg0-embedded`)
and **CPU-only** torch from the PyTorch CPU index. This is the official package
— only the dependency extras differ — and it is configured to use the existing
llama.cpp server for LLM inference, so there is no second model on the machine.

---

## 3. Configuration

### 3.1 Service (`start_hindsight.sh`)

```bash
export HINDSIGHT_API_LLM_PROVIDER=lmstudio
export HINDSIGHT_API_LLM_BASE_URL=http://127.0.0.1:1234/v1
export HINDSIGHT_API_LLM_MODEL=qwen2.5-3b-instruct
export HINDSIGHT_API_LLM_API_KEY=local-not-used   # required by config validation; not sent anywhere
export HINDSIGHT_API_LLM_STRICT_SCHEMA=true
export HINDSIGHT_API_LLM_TIMEOUT=600
export HINDSIGHT_API_REFLECT_LLM_TIMEOUT=600
export HINDSIGHT_API_RETAIN_LLM_TIMEOUT=600
export HINDSIGHT_API_REFLECT_WALL_TIMEOUT=1200
export HINDSIGHT_API_EMBEDDINGS_PROVIDER=local
export HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL=BAAI/bge-small-en-v1.5
export HINDSIGHT_API_RERANKER_PROVIDER=local
export HINDSIGHT_API_RERANKER_LOCAL_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
export HINDSIGHT_API_WORKER_ID=sentrymind-hindsight

python -m hindsight_api.server --host 127.0.0.1 --port 8888 --workers 1
```

Notes:
- `HINDSIGHT_API_LLM_API_KEY` is **mandatory** even for a local `lmstudio`
  provider — startup aborts with `ValueError: LLM API key is required` without
  it. The value is a placeholder and is never transmitted anywhere.
- The four `*_TIMEOUT` overrides are all necessary. Hindsight's shipped
  defaults (30 s reflect per-call, 300 s reflect wall-clock) are sized for
  hosted models; see §6.4.
- Embeddings (`bge-small-en-v1.5`, 384-dim) and reranking
  (`ms-marco-MiniLM-L-6-v2`) run on **CPU**, which keeps VRAM free for the LLM.
- `HINDSIGHT_API_WORKER_ID` is a stable name so task ownership is recoverable
  across restarts.

### 3.2 Client (`config.py`)

| Setting | Value | Note |
|---------|-------|------|
| `HINDSIGHT_API_URL` | `http://localhost:8888` | official port, separate from the mock's 8080 |
| `HINDSIGHT_BANK_ID` | `sentrymind-devops` | dedicated SentryMind bank |
| `SENTRYMIND_HINDSIGHT_TIMEOUT` | `30` | `inference_config.HINDSIGHT_TIMEOUT` — retain and recall |
| `SENTRYMIND_HINDSIGHT_REFLECT_TIMEOUT` | `540` | reflect only; see §6.4 |

The persistent mock on port 8080 is **preserved and untouched**, and remains
selectable by setting `HINDSIGHT_API_URL=http://localhost:8080`.

### 3.3 The single most important llama.cpp flag

```bash
--ctx-size 8192 --parallel 1
```

`--parallel 1` is not optional. llama-server defaults to **4 slots**, which
divides the context window per slot (`8192 / 4 = 2048`). Hindsight's
fact-extraction prompt is ~2,400 tokens and reflect needs ~7,800, so with the
default every extraction fails:

```
APIStatusError (lmstudio/qwen2.5-3b-instruct, scope=retain_extract_facts):
  HTTP 500 {"code":500,"message":"Context size has been exceeded."}
```

Measured before/after is in `OPTIMIZATION_BASELINE.md` §2.1.

---

## 4. API Mapping

The official API differs substantially from the mock's. The adapter was rewritten
against the real schemas, discovered from the live `GET /openapi.json`.

| Operation | Official endpoint | Request | Response |
|-----------|-------------------|---------|----------|
| Retain | `POST /v1/default/banks/{bank}/files/retain` | `multipart/form-data`: `files` (upload) + `request` (JSON string) | `{"operation_ids": [...]}` — **asynchronous** |
| Recall | `POST /v1/default/banks/{bank}/memories/recall` | `{"query": "..."}` | `{"results": [{"id","text","type","entities",...}], "trace":..., "entities":..., "chunks":...}` |
| Reflect | `POST /v1/default/banks/{bank}/reflect` | `{"query": "..."}` | `{"text": "...", "based_on":..., "structured_output":..., "usage": {...}}` |
| Create bank | `PUT /v1/default/banks/{bank}` | `{}` | 200/201/409 |

Two schema details that caused real bugs:
- Memories are keyed **`text`**, not `content`.
- Retain is a **file upload**, and per-file fields must live in
  `files_metadata`, not in the top-level request body.
- Banks **must exist first**; otherwise retain returns
  `404 {"detail":"Bank '<id>' not found"}`.

---

## 5. Verification Performed

Reproduce with `scripts/persistence_probe.py` and
`scripts/verify_official_hindsight.py`.

### 5.1 Retain

```
POST /v1/default/banks/sentrymind-newbank-probe/files/retain
HTTP 200 {"operation_ids": ["ab272867-609e-4d1c-9881-443d963e1607"]}
measured 5–48 ms
```

### 5.2 Async fact extraction

Retain is asynchronous. The worker claims the task and calls the LLM. From the
service log:

```
[RECALL sentrymi-26855-432985] Complete: 13 facts (617 tok), 0 chunks (0 tok), 3...
```

Facts are extracted, embedded with `bge-small-en-v1.5`, and stored — not the raw
text. Recall therefore returns **reconstructed facts**, so the raw marker string
is not expected to appear verbatim.

### 5.3 Recall (semantic, not keyword)

Query `"database connection pool"` returns facts that share almost no literal
keywords with the query:

```
A FATAL error occurred in the system, specifically due to remaining connection
slots being reserved for non-replication superuser connections. | When:
2026-09-28 | Unclosed client sessions during a traffic spike caused the error.
```

Measured latency: **882 ms**.

### 5.4 Reflect

```
POST /v1/default/banks/sentrymind-official-test/reflect
{"query": "recurring database connection failures"}

HTTP 200  in 156.3 s
usage: {"input_tokens": 8994, "output_tokens": 842, "total_tokens": 9836}
```

Returned synthesis (excerpt):

> Recurring database connection failures have been observed multiple times on
> 2026-09-28. The failures were mainly due to "FATAL remaining connection
> slots". Specifically: two incidents involved `official-test-d6187767-…` and
> `official-test-6dcbb55e-…`, where "Kubernetes" caused "OOMKilled" and
> "memory limit exceeded"…

This genuinely cross-references multiple independently retained incidents,
which is the behaviour a keyword store cannot produce.

Reflect only returns 200 at all after three separate deadlines are raised — see
§6.4. It is the slowest operation in the system by a wide margin.

### 5.5 Persistence across restart — CONFIRMED

The service was stopped completely, confirmed down, then restarted, and the
memory was re-read from a brand-new client process.

```
--- before ---
PID before: 235720
$ tmux kill-session -t hindsight
$ lsof -i :8888      -> not listening        # service confirmed DOWN
$ curl .../health    -> (no response)

--- restart ---
$ tmux new-session -d -s hindsight "bash start_hindsight.sh"
new PID: 281527
$ curl .../health
{"status":"healthy","database":"connected",...}

--- verify, from a fresh Python process ---
PRE-RESTART : 13 facts
POST-RESTART: 13 facts
SURVIVED    : 13 of 13 original fact ids
VERDICT: PERSISTENCE CONFIRMED
```

Survival was asserted on **fact IDs**, not on text, so this proves the records
themselves came back from the embedded PostgreSQL database in `~/.pg0` rather
than being served from any in-process cache. Because bank content is durable, a
**new** `SentryMemoryManager` in a new process also recalls it — which is the
app-restart case.

---

## 6. Defects Found and Fixed

Both were found only because the integration was tested against the real
service rather than against a mock shaped like the code.

### 6.1 Retain silently fell back to local for unknown banks

The official API returns `404` for an unprovisioned bank. The adapter treated
that as a generic failure and fell back to the in-memory store, which reports
`backend: local_fallback` — indistinguishable from a genuine outage, and it
would have made persistence look broken.

Measured before the fix, 8/8 retains to a new bank silently fell back:

```
0: local_fallback        6ms
...
7: local_fallback        6ms
OK=0 FALLBACK=8
```

Fixed by treating a `404` on retain as the authoritative "bank missing" signal:
provision with an idempotent `PUT /v1/default/banks/{bank}` and retry once.
Provisioning failure is never cached and never gates retention on its own —
that would misreport a transient outage as a missing bank.

### 6.2 Recall mis-parsed the official response

The adapter looked for `content`; the official schema uses `text`, so every
recall returned an empty list even when the bank was full. It also accepted a
non-list `results` value and iterated it character-by-character, so a malformed
`{"results": "not-a-list"}` produced `['n','o','t','-','a',...]` instead of
falling back.

Fixed by reading `text` (falling back to `content` for the legacy mock shape),
requiring `results` to actually be a list, and otherwise falling through to the
local fallback.

### 6.3 Reflect parsed the wrong field

The adapter read `response`/`reflection`; the official API returns the synthesis
under **`text`**. Reflect appeared to "succeed" while returning an empty string.
Fixed, plus a guard so an empty `text` is treated as a failure rather than a
successful reflection.

### 6.4 Reflect never worked, because three deadlines were all too small

This one is worth calling out, because reflect was *green* in the mocked test
suite and completely broken against the real service. It failed at three
independent layers, and each fix exposed the next:

| Layer | Setting | Default | Observed failure | Set to |
|-------|---------|---------|-------------------|--------|
| Client | `SENTRYMIND_HINDSIGHT_REFLECT_TIMEOUT` | 30 s (shared with retain/recall) | client aborts → silent `local_fallback` | 540 s |
| Server, per LLM call | `HINDSIGHT_API_REFLECT_LLM_TIMEOUT` | **30 s** | `openai.APITimeoutError` → HTTP 500 | 600 s |
| Server, whole operation | `HINDSIGHT_API_REFLECT_WALL_TIMEOUT` | **300 s** | `Wall-clock timeout after 300.0s` → HTTP 504 | 1200 s |

The two server defaults are tuned for hosted models on fast networks — the
Hindsight source comments say the 30 s figure was chosen against CI where calls
answered in 1–4 s. A single-slot 3B model at ~48 tok/s generating 3,700+
tokens across several sequential calls does not fit that budget at all.

Worst of all, the client-side failure was **silent**: a 30 s client abort is
indistinguishable from "Hindsight is down", so every reflect degraded to the
non-persistent local store while still reporting `status: reflected_locally`.
That is exactly the failure mode the `backend` provenance field exists to make
visible.

Final measured result: **HTTP 200 in 156.3 s**, 8,994 input / 842 output tokens.

### 6.5 `backend_status` reported false outages

Readiness was probed with `POST .../memories/recall` under a 3 s timeout. Recall
contends for the single LLM slot with fact extraction, so the probe timed out
during normal operation and reported `hindsight_reachable: false` while the
service was perfectly healthy. Now probes `GET /health`, the service's own
readiness endpoint, which answers in ~2 ms.

---

## 7. Memory Provenance

Every adapter response now carries an explicit `backend` field so the UI can
never present a mock or a fallback as the official service:

| `backend` | Meaning | UI banner |
|-----------|---------|-----------|
| `hindsight` | Official Vectorize Hindsight, persistent | `✅ HINDSIGHT (persistent)` |
| `local_fallback` | In-process list, lost on restart | `⚠️ Memory source: LOCAL FALLBACK (in-memory only, NOT persistent)` |

---

## 8. Resource Cost

| Component | Cost |
|-----------|------|
| Hindsight service RAM | 70 MB idle, ~750 MB while extracting |
| Embedded PostgreSQL (`pg0`) | 141 MB disk |
| Embedding + reranker models | 217 MB disk, CPU only |
| venv growth (`torch` CPU, `transformers`) | ~900 MB disk |
| VRAM | 0 MB — both run on CPU, leaving VRAM entirely to the LLM |

See `OPTIMIZATION_BASELINE.md` for the full table.

---

## 9. Known Limitations

1. **Fact extraction is unreliable on a 3B model.** This is the most important
   caveat and it is *not* fully solved. Retain returns HTTP 200 and queues the
   document, but whether facts are actually extracted depends on the LLM
   completing Hindsight's ~2,400-token strict-schema extraction within its
   per-task deadline. Measured outcomes on this hardware:

   | Content | Outcome |
   |---------|---------|
   | Short PostgreSQL/Redis/K8s incidents | extracted — bank holds **13 facts** |
   | Longer nginx/502 incident | **0 facts** — `wall=240.5s`, 4 retries exhausted |

   A failed extraction is logged by the service and the retain call still
   reports success, because retain is genuinely asynchronous. Callers that need
   to know a memory was actually ingested must poll recall rather than trust the
   retain response. This is a model-capability limit — `TASKS.md` forbids
   switching to a larger model, so it is reported rather than engineered around.
2. **Single inference slot.** With `-np 1` and `--threads 6`, concurrent
   Hindsight extraction and user requests contend. Observed: latency degraded
   from 41 ms to 74 s under extraction load, and tight-loop recall polling
   (every 5 s) is enough to trigger it. This is the accepted trade — the
   alternative (`-np 4`) breaks extraction outright.
3. **Recall returns extracted facts, not raw text.** Verbatim-marker assertions
   are meaningless against the official engine; tests assert on semantic content.
4. **Reflect is slow** — 156.3 s, because it synthesises over many observations
   with ~8,994 input tokens and several sequential LLM calls on one slot. It
   must not be used in a request path that expects a sub-second response.
5. **Single worker.** `--workers 1` is used deliberately on this memory budget;
   scaling out would multiply the embedding/reranker model footprint.

---

## 10. Files

| File | Change |
|------|--------|
| `memory/hindsight_client.py` | Rewritten against official schemas; retry-on-404 bank provisioning, strict envelope validation, `backend` provenance, `/health` readiness, separate reflect budget |
| `config.py` | `HINDSIGHT_API_URL` → official port 8888; model name corrected |
| `inference_config.py` | Added `HINDSIGHT_TIMEOUT`, `HINDSIGHT_REFLECT_TIMEOUT`; context 2048 → 8192, batch 128 → 512 |
| `start_hindsight.sh` | Official service launcher with LLM/reflect deadline overrides |
| `start_llama.sh` | llama.cpp launcher with `--parallel 1 --ctx-size 8192` |
| `start_demo.sh` | Starts/stops/reports the official Hindsight service |
| `requirements-hindsight.txt` | Official service dependencies, kept out of the CI install |
| `requirements.txt` | `setuptools>=83.0.0` so `pip-audit` is deterministic |
| `scripts/verify_official_hindsight.py` | End-to-end retain→recall→reflect evidence capture |
| `scripts/persistence_probe.py` | Restart-persistence proof |
| `tests/test_official_hindsight.py` | 7 official-service integration tests |
| `tests/test_hindsight_official_adapter.py` | 37 unit tests pinning the official wire contract |

A `docker/hindsight/Dockerfile` experiment was started and then **deleted**
rather than committed, so nobody inherits a build recipe that cannot work. Its
finding is recorded in §2.
