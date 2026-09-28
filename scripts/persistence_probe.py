"""Persistence proof: retain -> recall -> RESTART SERVICE -> recall again.

Usage:
  python scripts/persistence_probe.py retain   # before restart
  python scripts/persistence_probe.py recall   # after restart
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
BANK = "sentrymind-persist"
STATE = os.getenv(
    "SENTRYMIND_PERSIST_STATE",
    os.path.join(tempfile.gettempdir(), "persist_marker.json"),
)


def manager():
    return SentryMemoryManager(base_url=URL, bank_id=BANK, timeout=120)


def do_retain():
    marker = f"persist-{uuid.uuid4()}"
    mgr = manager()
    content = (
        f"Incident ID: {marker}. Gateway nginx returned HTTP 502 Bad Gateway "
        "to upstream checkout-service. Root cause was an exhausted keepalive "
        "connection pool after a rolling deploy. Verified fix: raise "
        "keepalive_requests_per_connection in nginx.conf and redeploy."
    )
    t0 = time.perf_counter()
    res = mgr.retain_incident(content, context="persistence_probe")
    print(
        f"retain: backend={res.get('backend')} "
        f"({(time.perf_counter() - t0) * 1000:.0f} ms) -> {json.dumps(res)[:180]}"
    )
    with open(STATE, "w") as fh:
        json.dump({"marker": marker, "content": content}, fh)

    print("waiting for async fact extraction...")
    query = "gateway bad gateway upstream connection pool"
    for i in range(40):
        time.sleep(5)
        r = mgr.recall_resolution(query=query)
        if r.get("results"):
            print(f"RECALLABLE after {(i + 1) * 5}s, {len(r['results'])} results")
            for item in r["results"][:4]:
                print("   *", item[:200])
            print("\nPRE-RESTART STATE WRITTEN. Restart the Hindsight service now.")
            return 0
    print("NOT recallable within 200s")
    return 1


def do_recall():
    # The marker is only evidence of what was sent; the real check is whether
    # the bank still answers semantically after the service has been restarted.
    with open(STATE) as fh:
        marker = json.load(fh).get("marker", "")
    mgr = manager()
    r = mgr.recall_resolution(query="gateway bad gateway upstream connection pool")
    print(
        f"recall: backend={r.get('backend')} results={len(r.get('results', []))} "
        f"(retained marker was {marker})"
    )
    for item in r.get("results", [])[:6]:
        print("   *", item[:220])
    # Official Hindsight stores *extracted facts*, not the raw text, so the
    # marker string is not expected to come back verbatim. Assert on the
    # semantic content of the incident instead.
    blob = " ".join(r.get("results", []))
    hit = "502" in blob or "keepalive" in blob or "nginx" in blob.lower()
    print(f"\nPOST-RESTART MEMORY SURVIVED: {hit}")
    return 0 if hit else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "retain"
    if cmd == "retain":
        health = requests.get(f"{URL}/health", timeout=10).json()
        print("health:", health.get("status"))
        sys.exit(do_retain())
    sys.exit(do_recall())
