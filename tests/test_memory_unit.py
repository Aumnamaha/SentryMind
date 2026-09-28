"""
Unit tests for SentryMemoryManager.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory.hindsight_client import SentryMemoryManager


class TestSentryMemoryManagerUnit:
    """Unit tests for SentryMemoryManager methods."""

    def test_init_defaults(self):
        mgr = SentryMemoryManager()
        assert mgr.local_store == []
        assert mgr.base_url is not None
        assert mgr.bank_id is not None

    def test_init_custom(self):
        mgr = SentryMemoryManager(base_url="http://example.com", bank_id="test-bank")
        assert mgr.base_url == "http://example.com"
        assert mgr.bank_id == "test-bank"

    def test_retain_incident_local_fallback(self):
        mgr = SentryMemoryManager(base_url="http://127.0.0.1:1")
        result = mgr.retain_incident("Test incident", context="test")
        assert result["status"] == "retained_locally"
        assert len(mgr.local_store) == 1
        assert mgr.local_store[0]["content"] == "Test incident"

    def test_retain_incident_api_success(self):
        mgr = SentryMemoryManager()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "123",
            "status": "retained",
            "backend": "hindsight",
        }
        with patch("memory.hindsight_client.requests.post", return_value=mock_response):
            result = mgr.retain_incident("Test incident")
            assert result.get("backend") == "hindsight"
            assert len(mgr.local_store) == 0

    def test_recall_resolution_local_fallback(self):
        mgr = SentryMemoryManager(base_url="http://127.0.0.1:1")
        mgr.retain_incident("Database connection timeout on port 5432")
        result = mgr.recall_resolution("database connection")
        assert result["status"] == "recalled_locally"
        assert len(result["results"]) >= 1

    def test_recall_resolution_api_success(self):
        mgr = SentryMemoryManager()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": ["fix1", "fix2"],
            "status": "recalled",
            "backend": "hindsight",
        }
        with patch("memory.hindsight_client.requests.post", return_value=mock_response):
            result = mgr.recall_resolution("test query")
            assert result.get("backend") == "hindsight"
            assert "fix1" in result.get("results", [])

    def test_recall_resolution_empty_store(self):
        mgr = SentryMemoryManager(base_url="http://127.0.0.1:1")
        result = mgr.recall_resolution("anything")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_reflect_patterns_empty(self):
        mgr = SentryMemoryManager()
        result = mgr.reflect_patterns("test")
        assert result["status"] == "reflected_locally"
        assert "No incidents in memory yet" in result["reflection"]

    def test_reflect_patterns_with_data(self):
        mgr = SentryMemoryManager(base_url="http://127.0.0.1:1")
        mgr.retain_incident("Connection timeout on database server")
        mgr.retain_incident("Memory cache OOM error")
        result = mgr.reflect_patterns("test")
        assert result["status"] == "reflected_locally"
        assert "Observed patterns" in result["reflection"]
