"""Persistent mock Hindsight service for testing.

Implements the same API as Hindsight but persists to disk (JSON file).
This allows testing persistence across restarts without the full Hindsight setup.

Endpoints:
- POST /banks/{bank_id}/retain  — store incident
- POST /banks/{bank_id}/recall   — recall incidents
- POST /banks/{bank_id}/reflect  — pattern analysis
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Hindsight Mock", version="0.1.0")

# Persistence file
DATA_DIR = Path(os.getenv("HINDSIGHT_MOCK_DATA_DIR", "/tmp/opencode/hindsight-data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "hindsight_store.json"

# In-memory store (loaded from disk)
_store: dict[str, list[dict[str, Any]]] = {}


def _load_store():
    """Load store from disk."""
    global _store
    if DATA_FILE.exists():
        with open(DATA_FILE, "r") as f:
            _store = json.load(f)
    else:
        _store = {}


def _save_store():
    """Save store to disk."""
    with open(DATA_FILE, "w") as f:
        json.dump(_store, f)


@app.on_event("startup")
def startup():
    _load_store()


class RetainRequest(BaseModel):
    content: str
    context: str = "incident_postmortem"


class RecallRequest(BaseModel):
    query: str


class ReflectRequest(BaseModel):
    query: str = ""


@app.post("/banks/{bank_id}/retain")
async def retain(bank_id: str, request: RetainRequest):
    """Store an incident in the memory bank."""
    if bank_id not in _store:
        _store[bank_id] = []

    entry = {
        "id": f"hs-{int(time.time() * 1000)}",
        "content": request.content,
        "context": request.context,
        "created_at": time.time(),
    }
    _store[bank_id].append(entry)
    _save_store()

    return {"id": entry["id"], "status": "retained", "bank_id": bank_id}


@app.post("/banks/{bank_id}/recall")
async def recall(bank_id: str, request: RecallRequest):
    """Recall incidents from the memory bank using keyword matching."""
    if bank_id not in _store:
        return {"results": [], "status": "recalled", "bank_id": bank_id}

    # Simple keyword matching (same as local fallback)
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "has",
        "have",
        "not",
        "but",
        "all",
        "can",
        "had",
        "her",
        "one",
        "our",
        "out",
        "day",
        "get",
        "him",
        "his",
        "how",
        "its",
        "may",
        "new",
        "now",
        "old",
        "see",
        "two",
        "way",
        "who",
        "did",
        "let",
        "put",
        "say",
        "she",
        "too",
        "use",
    }
    query_words = {
        w.lower()
        for w in re.findall(r"[a-zA-Z0-9_]+", request.query)
        if len(w) > 3 and w.lower() not in stop_words
    }

    matched = []
    for item in _store[bank_id]:
        content_words = set(re.findall(r"[a-zA-Z0-9_]+", item["content"].lower()))
        overlap = len(query_words & content_words)
        threshold = 1 if len(query_words) == 1 else (3 * len(query_words) + 3) // 4
        if overlap >= threshold:
            matched.append(item["content"])

    return {"results": matched, "status": "recalled", "bank_id": bank_id}


@app.post("/banks/{bank_id}/reflect")
async def reflect(bank_id: str, request: ReflectRequest):
    """Analyze patterns in the memory bank."""
    if bank_id not in _store or not _store[bank_id]:
        return {"reflection": "No incidents in memory yet.", "status": "reflected"}

    all_text = " ".join(item["content"].lower() for item in _store[bank_id])
    keywords = [
        "connection",
        "timeout",
        "memory",
        "cache",
        "oom",
        "fatal",
        "error",
        "crash",
    ]
    found = [kw for kw in keywords if kw in all_text]
    reflection = (
        f"Observed patterns: {', '.join(found)}."
        if found
        else "No recurring patterns detected yet."
    )
    return {"reflection": reflection, "status": "reflected"}


@app.get("/health")
async def health():
    return {"status": "healthy", "type": "hindsight_mock", "persistent": True}


@app.get("/banks/{bank_id}/stats")
async def stats(bank_id: str):
    """Get bank statistics."""
    count = len(_store.get(bank_id, []))
    return {"bank_id": bank_id, "incident_count": count, "persistent": True}
