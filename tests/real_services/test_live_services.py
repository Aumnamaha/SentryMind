"""Opt-in smoke tests for configured real LLM and Hindsight services."""

import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager

pytestmark = pytest.mark.integration


def require_live_services():
    if os.getenv("SENTRYMIND_RUN_LIVE_INTEGRATION") != "1":
        pytest.skip("Set SENTRYMIND_RUN_LIVE_INTEGRATION=1 to enable live checks")


def test_live_llm_returns_text():
    require_live_services()
    if not os.getenv("LOCAL_LLM_URL"):
        pytest.fail("LOCAL_LLM_URL must be configured for live LLM integration")
    response = SentryMindAgent().query_local_qwen("Reply with the word ready.")
    assert isinstance(response, str)
    assert response and "Error" not in response and "Offline" not in response


def test_live_hindsight_retains_and_recalls_synthetic_incident():
    require_live_services()
    if not os.getenv("HINDSIGHT_API_URL"):
        pytest.fail("HINDSIGHT_API_URL must be configured for live memory integration")
    marker = f"synthetic-integration-{uuid.uuid4()}"
    manager = SentryMemoryManager()
    retained = manager.retain_incident(
        content=f"{marker} database connection pool timeout", context="test"
    )
    assert retained.get("status") != "retained_locally"
    recalled = manager.recall_resolution(query=f"{marker} database connection pool")
    assert any(
        marker in result
        for result in recalled.get("results", [])
        if isinstance(result, str)
    )
