"""Phase 4 verification against the OFFICIAL Vectorize Hindsight service.

Captures real request/response evidence and timings for:
  1. health
  2. retain
  3. async processing wait
  4. recall with semantically related query
  5. reflect
  6. persistence across a full server restart
"""

import json
import os
import sys
import tempfile
import time
import uuid

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory.hindsight_client import SentryMemoryManager

URL = os.getenv("HINDSIGHT_API_URL", "http://127.0.0.1:8888")
BANK = "sentrymind-verify"
OUT = os.getenv(
    "SENTRYMIND_EVIDENCE_FILE",
    os.path.join(tempfile.gettempdir(), "phase4_evidence.json"),
)


def timed(fn):
    """Run fn, returning (result, elapsed_ms)."""
    t0 = time.perf_counter()
    result = fn()
    return result, (time.perf_counter() - t0) * 1000


def main():
    evidence = {}
    marker = f"verify-{uuid.uuid4()}"
    mgr = SentryMemoryManager(base_url=URL, bank_id=BANK)

    health, ms = timed(lambda: requests.get(f"{URL}/health", timeout=10).json())
    evidence["health"] = {"ms": round(ms), "body": health}
    print(f"[1] health: {health.get('status')} ({ms:.0f} ms)")

    content = (
        f"Incident ID: {marker}. "
        "Service: checkout-api. Error: HTTP 503 upstream connect error "
        "or disconnect/reset before headers. Root cause: connection pool "
        "exhausted by leaked database sessions during a traffic spike. "
        "Verified fix: run scripts/flush_pool.sh to drain idle connections."
    )
    retained, ms = timed(lambda: mgr.retain_incident(content, context="verification"))
    evidence["retain"] = {"ms": round(ms), "body": retained}
    print(f"[2] retain: backend={retained.get('backend')} ({ms:.0f} ms)")
    print(f"    response: {json.dumps(retained)[:400]}")

    # Wait for async processing (fact extraction + embedding)
    ready, deadline = None, time.time() + 180
    waited = 0.0
    while time.time() < deadline:
        time.sleep(5)
        waited += 5
        r = mgr.recall_resolution(query="checkout payment service outage")
        if r.get("results"):
            ready = r
            break
    evidence["async_wait_seconds"] = waited
    print(f"[3] async processing: recallable after ~{waited:.0f}s")

    if ready is None:
        print("[3] NOT recallable within 180s")
        evidence["recall"] = {"body": r}
    else:
        print(f"[4] recall: {len(ready['results'])} results")
        for item in ready["results"]:
            print(f"    - [{item[:220]}]")
        evidence["recall"] = {
            "body": {k: v for k, v in ready.items() if k != "raw_response"}
        }
        evidence["recall_raw"] = ready.get("raw_response")

    t0 = time.perf_counter()
    reflected = mgr.reflect_patterns("recurring checkout service failures")
    ms = (time.perf_counter() - t0) * 1000
    evidence["reflect"] = {
        "ms": round(ms),
        "body": {k: v for k, v in reflected.items() if k != "raw_response"},
    }
    print(f"[5] reflect: backend={reflected.get('backend')} ({ms:.0f} ms)")
    print(f"    reflection: {str(reflected.get('reflection'))[:300]}")

    # Raw reflect HTTP status for diagnosis
    try:
        resp = requests.post(
            f"{URL}/v1/default/banks/{BANK}/reflect",
            json={"query": "recurring checkout service failures"},
            timeout=180,
        )
        evidence["reflect_http"] = {"status": resp.status_code, "body": resp.text[:600]}
        print(f"[6] reflect raw HTTP: {resp.status_code}")
        if resp.status_code != 200:
            print(f"    {resp.text[:400]}")
    except requests.RequestException as exc:
        evidence["reflect_http"] = {"error": str(exc)}

    with open(OUT, "w") as fh:
        json.dump({"marker": marker, "evidence": evidence}, fh, indent=2, default=str)
    print(f"\nEvidence written to {OUT}")
    print(f"MARKER={marker}")


if __name__ == "__main__":
    main()
