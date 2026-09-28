# 🛡️ SentryMind: Autonomous DevOps Incident Response Agent

> **An LLM-assisted incident triage tool that retrieves historical context for operator review.**

---

## Executive Overview

**SentryMind** sends redacted incident text to a configured local LLM and retrieves matching incident history from Hindsight. Retrieved notes are untrusted historical context: the agent asks operators to review and verify any suggested action. The local fallback uses keyword overlap and can miss relevant incidents or return imperfect matches.

---

## Key Features

- **Side-by-Side Memory Contrast** — The Streamlit UI compares generic triage with analysis that includes historical context.
- **Dynamic Hindsight Retain & Recall Pipeline** — Ingest new incidents in real-time through the UI; the agent immediately starts recalling them on future alerts.
- **Offline Fallback Support** — Hindsight failures use an in-memory keyword fallback. LLM failures return an offline status; deterministic CI tests mock service calls.

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SentryMind Agent                             │
│                                                                     │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│   │ Error Log │───▶│ Analyze Log  │───▶│ Use Memory?              │  │
│   │ Ingested  │    │ (core.py)    │    │                          │  │
│   └──────────┘    └──────┬───────┘    ├──────────────┬───────────┤  │
│                         │             │              │            │  │
│                    [No Memory]     [Yes — Recall]   │            │  │
│                         │             │              │            │  │
│                  ┌──────▼──────┐      │    ┌─────────▼────────┐   │  │
│                  │ Stateless   │      │    │ Hindsight Memory  │   │  │
│                  │ LLM Query   │      │    │ Bank (Cloud/Local)│   │  │
│                  │ → Generic   │      │    └───────┬──────────┘   │  │
│                  │ "Restart"    │      │            │              │  │
│                  │ advice       │      │   ┌────────▼────────┐    │  │
│                  └──────┬──────┘      │   │ Semantic Match   │    │  │
│                         │             │   │ → Verified Fix   │    │  │
│                    ┌────▼────┐        │   └────────┬────────┘    │  │
│                    │ LLM     │        │            │              │  │
│                    │ Response│        │   ┌────────▼────────┐    │  │
│                    │ + High-Confidence Action  │            │  │
│                    └────┬────┘        │            │          │  │
│                         │             │            │          │  │
│              ┌──────────▼─────────────▼────────────▼───────┐   │
│              │           SentryMemoryManager                │   │
│              │                                            │   │
│              │  retain()  → Store incident in bank         │   │
│              │  recall()  → Semantic search past incidents  │   │
│              │  reflect() → Pattern analysis over memory    │   │
│              └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Mermaid Diagram:**

```mermaid
flowchart TD
    A[Incoming Error Log] --> B{SentryMind Agent}
    B -->|use_memory=False| C[Stateless LLM Query]
    B -->|use_memory=True| D[Hindsight Memory Bank]
    C --> E[Generic 'Restart' Advice\nLow Confidence]
    D --> F[Semantic Recall of Past Post-Mortems]
    F --> G[Historical Context\nOperator Verification Required]
    H[New Incident Resolved] --> I[resolve_and_retain]\
    I --> J[Store in Memory Bank]

    style A fill:#1a1a2e,color:#fff
    style B fill:#16213e,color:#fff
    style D fill:#0f3460,color:#fff
    style G fill:#533483,color:#fff
    style J fill:#e94560,color:#fff
```

---

## Quickstart Guide

### Prerequisites

- Python 3.11+
- [LM Studio](https://lmstudio.ai/) running a Qwen model (optional — for local inference)
- Hindsight Cloud account or local instance (optional — falls back to in-memory store)

### Step 1: Clone & Setup Environment

```bash
cd "Microsoft Hackathon"
python -m venv finalenv
source finalenv/bin/activate       # Linux/macOS
# finalenv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### Step 2: Configure Credentials (Optional)

Create a `.env` file in the project root:

```bash
LOCAL_LLM_URL=http://localhost:1234/v1
LOCAL_MODEL_NAME=qwen2.5-35b-instruct
HINDSIGHT_API_URL=https://api.vectorize.io/api/v1/hindsight  # or local instance
HINDSIGHT_BANK_ID=sentrymind-devops
```

> **Note:** All external services are optional — the agent gracefully falls back to a local in-memory store when no services are available.

### Step 3: Seed Local Memory

Load synthetic incident post-mortems into the memory bank:

```bash
python data/seed_memory.py
# Output: Seeding 3 incident post-mortems locally...
#         Retained [INC-001]: retained_locally
#         Retained [INC-002]: retained_locally
#         Retained [INC-003]: retained_locally
```

### Step 4: Run the Streamlit UI

Launch the interactive side-by-side visualizer:

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser. Select an incident, then click **"Analyze Log (Without Memory)"** and **"Analyze Log (With Hindsight Recall)"** to see the contrast. Use the **"Retain New Incident Learnings"** form at the bottom to push new incidents into memory in real-time.

### Step 5: Run the Test Suite

```bash
python -m pytest tests/ -v --tb=short
# The deterministic suite blocks external HTTP calls; optional live checks are separate.
```

---

## Hindsight Memory Deep Dive

SentryMind integrates three core Hindsight operations through `memory/hindsight_client.py` and `agent/core.py`:

### `retain()` — Store Incident Knowledge

**Endpoint:** `POST /banks/{bank_id}/retain`

Stores a resolved incident as structured text in the memory bank:

```python
# In agent/core.py → resolve_and_retain()
content = (
    f"Incident ID: {incident_id}. "
    f"Error: {raw_log}. "
    f"Root Cause: {root_cause}. "
    f"Verified Fix: {fix_action}"
)
result = self.memory.retain_incident(content=content, context="resolved_incident")
```

The `context` field tags the entry (e.g., `"production_postmortem"` or `"resolved_incident"`), enabling future filtering and pattern analysis. When Hindsight Cloud is unreachable, entries are stored in a local Python list as a transparent fallback.

### `recall()` — Retrieve Matching Past Fixes

**Endpoint:** `POST /banks/{bank_id}/recall`

Given an error log query, performs semantic search across all retained incidents:

```python
# In agent/core.py → analyze_log()
recalled_facts = self.memory.recall_resolution(query=raw_log)
# Returns: {"results": [matching incident descriptions]}
```

The local fallback uses token-boundary keyword overlap (tokens longer than three characters) and requires multiple matching terms for multi-term queries. It is not semantic search. Remote recall behavior depends on the configured Hindsight service and its response format. All returned context must be reviewed; a match does not prove that a suggested fix is safe or applicable.

### `reflect()` — Analyze Memory Patterns

**Endpoint:** `POST /banks/{bank_id}/reflect`

Runs pattern analysis over retained incidents to surface recurring themes:

```python
# In agent/core.py (future use)
reflection = self.memory.reflect_patterns("connection timeout")
# Returns: "Repeated connection and cache failure patterns observed."
```

Currently returns a basic aggregation; ready for advanced analytics as the memory bank grows.

### How It All Fits Together in `analyze_log()`

```python
def analyze_log(self, raw_log: str, use_memory: bool = True):
    if use_memory:
        # 1. Query Hindsight for matching past incidents
        recalled_facts = self.memory.recall_resolution(query=raw_log)

    if not use_memory or not recalled_facts:
        # Stateless path — generic LLM guess with low confidence
        return {"confidence": "Low", ...}

    # Memory-augmented path — prompt includes recalled post-mortems
    prompt = f"Error Log: {raw_log}\nRecalled: {recalled_facts}\nProvide fix."
    llm_output = self.query_local_qwen(prompt)
    return {"confidence": "High", "recalled_context": recalled_facts, ...}
```

---

## Project Structure

```
Microsoft Hackathon/
├── app.py                          # Streamlit UI (Before vs After visualizer)
├── config.py                       # Environment variable loader (.env)
├── requirements.txt                # Python dependencies
│
├── agent/
│   └── core.py                     # SentryMindAgent: reasoning loop & log parsing
│
├── memory/
│   └── hindsight_client.py         # SentryMemoryManager: retain / recall / reflect
│
├── data/
│   ├── incident_logs.json          # 3 synthetic production incident scenarios
│   └── seed_memory.py              # CLI script to ingest incidents into memory bank
│
├── tests/
│   ├── test_environment.py         # Config loading & agent instantiation checks
│   ├── test_memory_loop.py         # Before/After memory comparison + retain test
│   └── test_cli_workflow.py        # 14 end-to-end lifecycle integration tests
│
├── social_post.txt                 # LinkedIn/X promotion post (Karpathy-style)
└── video_script.md                 # 3-minute OBS demo recording script
```

---

## Links & Resources

| Resource | Link |
| :--- | :--- |
| **Hindsight GitHub** | <https://github.com/vectorize-io/hindsight> |
| **Hindsight Docs** | <https://hindsight.vectorize.io/> |
| **Vectorize Agent Memory** | <https://vectorize.io/what-is-agent-memory> |
| **LM Studio** | <https://lmstudio.ai/> |

---

## License & Author

**Author:** Aum Namaha — Final-Year CSE/AIML Student  
**License:** MIT
