"""Tests for uncovered branches in agent/core.py and memory/hindsight_client.py."""

import os
import sys
from unittest.mock import MagicMock, patch

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


class TestAgentRecallEdgeCases:
    """Cover branches where recall returns unexpected types."""

    def test_recall_returns_non_dict(self, agent):
        """recall_res is a list, not a dict → recalled_facts stays empty."""
        with patch.object(
            agent.memory, "recall_resolution", return_value=["not", "a", "dict"]
        ):
            result = agent.analyze_log("test", use_memory=True)
        assert result["memory_active"] is False
        assert result["recalled_context"] == []

    def test_recall_returns_dict_without_results(self, agent):
        """recall_res is a dict but has no 'results' key."""
        with patch.object(
            agent.memory, "recall_resolution", return_value={"status": "ok"}
        ):
            result = agent.analyze_log("test", use_memory=True)
        assert result["memory_active"] is False
        assert result["recalled_context"] == []

    def test_recall_returns_dict_with_non_list_results(self, agent):
        """recall_res has 'results' but it's not a list."""
        with patch.object(
            agent.memory,
            "recall_resolution",
            return_value={"results": "not-a-list"},
        ):
            result = agent.analyze_log("test", use_memory=True)
        assert result["memory_active"] is False
        assert result["recalled_context"] == []

    def test_recall_returns_none(self, agent):
        with patch.object(agent.memory, "recall_resolution", return_value=None):
            result = agent.analyze_log("test", use_memory=True)
        assert result["memory_active"] is False

    def test_recall_returns_empty_dict(self, agent):
        with patch.object(agent.memory, "recall_resolution", return_value={}):
            result = agent.analyze_log("test", use_memory=True)
        assert result["memory_active"] is False

    def test_recall_results_with_mixed_types(self, agent):
        """Non-string items in results should be filtered out."""
        with patch.object(
            agent.memory,
            "recall_resolution",
            return_value={"results": ["valid", 123, None, "also valid"]},
        ):
            result = agent.analyze_log("test", use_memory=True)
        assert result["memory_active"] is True
        assert len(result["recalled_context"]) == 2
        assert all(isinstance(item, str) for item in result["recalled_context"])


class TestHindsightRemoteNon200:
    """Cover branch where remote recall returns non-200 status."""

    def test_recall_remote_returns_500(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        response = MagicMock(status_code=500)
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.recall_resolution("test")
        assert result["status"] == "recalled_locally"

    def test_recall_remote_returns_404(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        response = MagicMock(status_code=404)
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.recall_resolution("test")
        assert result["status"] == "recalled_locally"

    def test_retain_remote_returns_500(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        response = MagicMock(status_code=500)
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.retain_incident("test")
        assert result["status"] == "retained_locally"

    def test_retain_remote_returns_404(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        response = MagicMock(status_code=404)
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.retain_incident("test")
        assert result["status"] == "retained_locally"

    def test_retain_remote_returns_200_with_non_dict(self):
        """Remote returns 200 but body is not a dict → fall back to local."""
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        response = MagicMock(status_code=200)
        response.json.return_value = ["not", "a", "dict"]
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.retain_incident("test")
        assert result["status"] == "retained_locally"
