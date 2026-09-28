"""Tests for hypothesis/evidence distinction and memory source tracking."""

import os
import sys
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager


@pytest.fixture
def offline_manager():
    manager = SentryMemoryManager(base_url="http://unused.invalid")
    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        yield manager


@pytest.fixture
def agent(offline_manager):
    ag = SentryMindAgent(offline_manager)
    with patch.object(ag, "query_local_qwen", return_value="mocked"):
        yield ag


class TestHypothesisVsEvidence:
    """Agent must distinguish between what the log proves and hypotheses."""

    def test_prompt_includes_hypothesis_instruction(self, agent):
        """Prompt must instruct the LLM to separate diagnosis from hypotheses."""
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        assert "hypotheses" in prompt.lower()
        assert "unverified" in prompt.lower()

    def test_prompt_includes_confidence_calibration(self, agent):
        """Prompt must include confidence calibration rules."""
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        assert "low" in prompt
        assert "single log" in prompt.lower() or "single" in prompt.lower()

    def test_response_includes_hypotheses_field(self, agent):
        """Response must include a hypotheses field."""
        result = agent.analyze_log("test error", use_memory=False)
        assert "hypotheses" in result
        assert isinstance(result["hypotheses"], list)

    def test_structured_output_with_hypotheses_parsed(self, agent):
        """When LLM returns hypotheses, they should be in the response."""
        structured_json = (
            '{"diagnosis": "connection slots exhausted", '
            '"hypotheses": ["unclosed sessions (unverified)", "traffic spike (unverified)"], '
            '"evidence": ["FATAL: remaining connection slots"], '
            '"confidence": "low", '
            '"uncertainty": "root cause unknown", '
            '"next_checks": ["check connections"], '
            '"remediation": "review connection pool"}'
        )
        with patch.object(agent, "query_local_qwen", return_value=structured_json):
            result = agent.analyze_log("test error", use_memory=False)
        assert result["hypotheses"] == [
            "unclosed sessions (unverified)",
            "traffic spike (unverified)",
        ]
        assert result["root_cause"] == "connection slots exhausted"
        assert result["confidence"] == "low"

    def test_diagnosis_labels_proves_vs_hypotheses(self, agent):
        """Diagnosis should be labeled as what the log proves, not the cause."""
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        assert "proves" in prompt.lower() or "what the log" in prompt.lower()


class TestMemorySourceTracking:
    """Agent must clearly distinguish local fallback from remote Hindsight."""

    def test_no_memory_response_has_source_none(self, agent):
        """When no memory is used, source should be 'none'."""
        result = agent.analyze_log("test error", use_memory=False)
        assert result["memory_source"] == "none"

    def test_local_fallback_source_identified(self, offline_manager, agent):
        """When recall falls back to local, source should be 'local_fallback'."""
        offline_manager.retain_incident("test error database connection failed")
        result = agent.analyze_log("test error", use_memory=True)
        assert result["memory_source"] == "local_fallback"
        assert result["memory_active"] is True

    def test_remote_hindsight_source_identified(self, offline_manager, agent):
        """When recall uses remote Hindsight, source should be 'hindsight'."""
        from unittest.mock import MagicMock

        response = MagicMock(status_code=200)
        response.json.return_value = {
            "results": ["remote incident fix"],
            "status": "recalled",
        }
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = agent.analyze_log("test error", use_memory=True)
        assert result["memory_source"] == "hindsight"
        assert result["memory_active"] is True

    def test_memory_source_in_response_dict(self, agent):
        """memory_source must be a top-level field in the response."""
        result = agent.analyze_log("test error", use_memory=False)
        assert "memory_source" in result

    def test_local_fallback_not_mistaken_for_persistent(self, offline_manager, agent):
        """Local fallback must not be presented as persistent memory."""
        offline_manager.retain_incident("test error database connection failed")
        result = agent.analyze_log("test error", use_memory=True)
        # The source must clearly indicate this is local, not persistent
        assert result["memory_source"] == "local_fallback"
        # The recalled content should still be present
        assert len(result["recalled_context"]) > 0


class TestConfidenceCalibration:
    """Agent must not overstate confidence from limited evidence."""

    def test_single_log_line_not_high_confidence(self, agent):
        """A single log line should not produce 'high' confidence."""
        structured_json = (
            '{"diagnosis": "connection slots exhausted", '
            '"hypotheses": [], '
            '"evidence": ["FATAL: remaining connection slots"], '
            '"confidence": "low", '
            '"uncertainty": "root cause unknown from single line", '
            '"next_checks": ["check connections"], '
            '"remediation": "review pool"}'
        )
        with patch.object(agent, "query_local_qwen", return_value=structured_json):
            result = agent.analyze_log(
                "FATAL: remaining connection slots", use_memory=False
            )
        # Confidence should be low for a single log line
        assert result["confidence"] == "low"

    def test_prompt_includes_confidence_rules(self, agent):
        """Prompt must include explicit confidence calibration rules."""
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        # Should mention when to use each confidence level
        assert "low" in prompt
        assert "medium" in prompt
        assert "high" in prompt
