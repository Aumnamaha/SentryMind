"""
Unit tests for SentryMindAgent core logic.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager


class TestSentryMindAgentUnit:
    """Unit tests for SentryMindAgent methods."""

    def test_init_default_memory_manager(self):
        agent = SentryMindAgent()
        assert agent.memory is not None
        assert isinstance(agent.memory, SentryMemoryManager)

    def test_init_custom_memory_manager(self):
        custom_mgr = SentryMemoryManager()
        agent = SentryMindAgent(memory_manager=custom_mgr)
        assert agent.memory is custom_mgr

    def test_query_local_qwen_success(self):
        agent = SentryMindAgent()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        with patch("agent.core.requests.post", return_value=mock_response):
            result = agent.query_local_qwen("test prompt")
            assert result == "Test response"

    def test_query_local_qwen_offline_fallback(self):
        agent = SentryMindAgent()
        with patch(
            "agent.core.requests.post",
            side_effect=requests.RequestException("Connection error"),
        ):
            result = agent.query_local_qwen("test prompt")
            assert (
                "Offline" in result
                or "Fallback" in result
                or "Local Fallback" in result
            )

    def test_analyze_log_without_memory(self):
        agent = SentryMindAgent()
        with patch.object(agent, "query_local_qwen", return_value="Generic advice"):
            result = agent.analyze_log("some error", use_memory=False)
            assert result["use_memory"] is False
            assert result["memory_active"] is False
            assert "Low" in result["confidence"]

    def test_analyze_log_with_memory_no_recall(self):
        agent = SentryMindAgent()
        with (
            patch.object(agent, "query_local_qwen", return_value="Generic advice"),
            patch.object(
                agent.memory, "recall_resolution", return_value={"results": []}
            ),
        ):
            result = agent.analyze_log("some error", use_memory=True)
            assert result["use_memory"] is True
            assert result["memory_active"] is False

    def test_analyze_log_with_memory_recall(self):
        agent = SentryMindAgent()
        with (
            patch.object(agent, "query_local_qwen", return_value="Specific runbook"),
            patch.object(
                agent.memory,
                "recall_resolution",
                return_value={"results": ["fix: restart service"]},
            ),
        ):
            result = agent.analyze_log("some error", use_memory=True)
            assert result["use_memory"] is True
            assert result["memory_active"] is True
            assert "High" in result["confidence"]

    def test_resolve_and_retain(self):
        agent = SentryMindAgent()
        with patch.object(
            agent.memory, "retain_incident", return_value={"status": "ok"}
        ):
            result = agent.resolve_and_retain("INC-001", "error", "cause", "fix")
            assert result["status"] == "success"
            assert "INC-001" in result["retained_content"]
