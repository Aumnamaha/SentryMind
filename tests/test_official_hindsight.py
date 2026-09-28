"""Official Hindsight integration tests.

These tests run against the official Vectorize Hindsight server on port 8888.

Fact extraction is real and works, but it is only *reliable* for short
incidents on Qwen2.5-3B-Instruct:

- Short PostgreSQL/Redis/K8s incidents extract cleanly; the
  ``sentrymind-official-test`` bank holds 13 extracted facts.
- Longer incidents exhaust Hindsight's per-task deadline and produce 0 facts.

These tests therefore assert on the contract SentryMind can guarantee (the
request reaches the official API, and the response is correctly attributed to
the ``hindsight`` backend) rather than on facts having been extracted, which is
model-dependent. Polling recall until facts appear is deliberately *not* done
here: it would hold the single llama.cpp inference slot for minutes and make
the suite flaky.

See OFFICIAL_HINDSIGHT_REPORT.md section 9 for the full limitation list.
"""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager

pytestmark = pytest.mark.integration

OFFICIAL_HINDSIGHT_URL = "http://127.0.0.1:8888"
TEST_BANK_ID = "sentrymind-official-test"


def require_official_hindsight():
    if os.getenv("SENTRYMIND_RUN_LIVE_INTEGRATION") != "1":
        pytest.skip(
            "Set SENTRYMIND_RUN_LIVE_INTEGRATION=1 to enable official Hindsight tests"
        )
    try:
        resp = requests.get(f"{OFFICIAL_HINDSIGHT_URL}/health", timeout=3)
        if resp.status_code != 200:
            pytest.fail(f"Official Hindsight not healthy: {resp.status_code}")
    except requests.RequestException as e:
        pytest.fail(f"Official Hindsight not reachable: {e}")


def test_official_hindsight_health():
    """Verify the official Hindsight server is running and healthy."""
    require_official_hindsight()
    resp = requests.get(f"{OFFICIAL_HINDSIGHT_URL}/health", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_official_backend_status():
    """Verify backend_status correctly identifies official Hindsight."""
    require_official_hindsight()
    manager = SentryMemoryManager(base_url=OFFICIAL_HINDSIGHT_URL, bank_id=TEST_BANK_ID)
    status = manager.backend_status()
    assert status["hindsight_reachable"] is True
    assert status["active_backend"] == "hindsight"


def test_official_secret_redaction():
    """Verify secrets are redacted before retention."""
    require_official_hindsight()
    agent = SentryMindAgent(
        memory_manager=SentryMemoryManager(
            base_url=OFFICIAL_HINDSIGHT_URL, bank_id=TEST_BANK_ID
        )
    )
    raw = "ERROR api_key=official-secret-123 database connection failed"
    redacted = agent._redact_secrets(raw)
    assert "official-secret-123" not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.timeout(60)
def test_official_retain_reaches_official_api():
    """Retain must reach the official API and be attributed to it.

    Retain is asynchronous: the server returns operation_ids immediately and
    extracts facts in the background. So we assert the request was accepted by
    the official service, not that facts exist yet.
    """
    require_official_hindsight()
    marker = f"official-test-{uuid.uuid4()}"
    manager = SentryMemoryManager(base_url=OFFICIAL_HINDSIGHT_URL, bank_id=TEST_BANK_ID)
    content = f"Incident ID: {marker}. Error: FATAL remaining connection slots."
    retained = manager.retain_incident(content=content, context="test_incident")

    # A silent local fallback here would mean the official service is broken
    # while still reporting success to the caller.
    assert (
        retained["backend"] == "hindsight"
    ), f"retain fell back to {retained['backend']} instead of the official service"
    assert retained["status"] == "retained"
    assert retained["operation_ids"], "official retain must return operation_ids"


@pytest.mark.timeout(60)
def test_official_recall_returns_persisted_facts():
    """Recall must return facts that were previously extracted by the LLM.

    The test bank is seeded by test_official_retain_reaches_official_api
    across runs, so this asserts the official service can answer a semantic
    query with the official ``{"results": [...]}`` envelope.
    """
    require_official_hindsight()
    manager = SentryMemoryManager(base_url=OFFICIAL_HINDSIGHT_URL, bank_id=TEST_BANK_ID)
    recalled = manager.recall_resolution(query="database connection pool")

    assert (
        recalled["backend"] == "hindsight"
    ), f"recall fell back to {recalled['backend']} instead of the official service"
    assert recalled["status"] == "recalled"
    assert isinstance(recalled["results"], list)
    # Facts are extracted and embedded, so this is semantic recall, not a
    # keyword match on the marker string.
    for text in recalled["results"]:
        assert isinstance(text, str)


@pytest.mark.timeout(400)
def test_official_reflect_returns_synthesis():
    """Reflect must return a non-empty LLM synthesis from the official service.

    Measured 156.3 s wall clock (8,994 input / 842 output tokens) on a single
    llama.cpp slot at ~48 tok/s. This is why start_hindsight.sh raises
    HINDSIGHT_API_REFLECT_LLM_TIMEOUT and HINDSIGHT_API_REFLECT_WALL_TIMEOUT
    above their 30 s / 300 s defaults — at the defaults every reflect call
    timed out and returned HTTP 504.
    """
    require_official_hindsight()
    manager = SentryMemoryManager(base_url=OFFICIAL_HINDSIGHT_URL, bank_id=TEST_BANK_ID)
    result = manager.reflect_patterns("recurring database connection failures")

    assert (
        result["backend"] == "hindsight"
    ), f"reflect fell back to {result['backend']} instead of the official service"
    assert result["status"] == "reflected"
    assert result["reflection"].strip(), "official reflect must return a synthesis"


@pytest.mark.timeout(60)
def test_official_malformed_envelope_falls_back():
    """A malformed official response must degrade, never be reported as official.

    The official recall envelope is {"results": [...]}. A non-list ``results``
    must not be iterated (which previously produced one bogus memory per
    character) and must not be labelled as the official backend.
    """
    require_official_hindsight()
    manager = SentryMemoryManager(base_url=OFFICIAL_HINDSIGHT_URL, bank_id=TEST_BANK_ID)

    with patch.object(requests, "post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": "not-a-list"},
        )
        recalled = manager.recall_resolution(query="database connection")

    assert recalled["backend"] == "local_fallback"
    assert recalled["results"] == []
