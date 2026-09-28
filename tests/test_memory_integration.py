"""Hindsight memory tests for SentryMemoryManager.

Covers: incident retention, accurate recall, duplicate retention,
unrelated incident isolation, conflicting historical resolutions,
empty memory banks, service unavailability, recovery after reconnection,
concurrent memory access, and persistence distinction between
in-memory fallback and genuinely persistent Hindsight storage.
"""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory.hindsight_client import SentryMemoryManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def local_manager():
    """Memory manager with all remote calls failing (local fallback only)."""
    manager = SentryMemoryManager(base_url="http://unused.invalid")
    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        yield manager


@pytest.fixture
def remote_manager():
    """Memory manager with mocked remote Hindsight service."""
    manager = SentryMemoryManager(base_url="http://hindsight.test", bank_id="test-bank")
    return manager


def make_mock_response(status_code=200, json_data=None):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


# ---------------------------------------------------------------------------
# Incident retention
# ---------------------------------------------------------------------------


class TestIncidentRetention:
    """Basic retention operations."""

    def test_retain_stores_in_local_fallback(self, local_manager):
        result = local_manager.retain_incident("Test incident", context="test")
        assert result["status"] == "retained_locally"
        assert len(local_manager.local_store) == 1
        assert local_manager.local_store[0]["content"] == "Test incident"
        assert local_manager.local_store[0]["context"] == "test"

    def test_retain_with_default_context(self, local_manager):
        local_manager.retain_incident("Test incident")
        assert local_manager.local_store[0]["context"] == "incident_postmortem"

    def test_retain_with_custom_context(self, local_manager):
        local_manager.retain_incident("Test incident", context="production_postmortem")
        assert local_manager.local_store[0]["context"] == "production_postmortem"

    def test_retain_includes_bank_id(self, local_manager):
        local_manager.retain_incident("Test incident")
        assert local_manager.local_store[0]["bank_id"] == local_manager.bank_id

    def test_retain_multiple_incidents(self, local_manager):
        for i in range(10):
            local_manager.retain_incident(f"Incident {i}")
        assert len(local_manager.local_store) == 10

    def test_retain_empty_content(self, local_manager):
        result = local_manager.retain_incident("")
        assert result["status"] == "retained_locally"
        assert len(local_manager.local_store) == 1

    def test_retain_very_long_content(self, local_manager):
        long_content = "x" * 100000
        result = local_manager.retain_incident(long_content)
        assert result["status"] == "retained_locally"
        assert local_manager.local_store[0]["content"] == long_content

    def test_retain_unicode_content(self, local_manager):
        content = "Ошибка базы данных: соединение прервано 🛡️"
        result = local_manager.retain_incident(content)
        assert result["status"] == "retained_locally"
        assert local_manager.local_store[0]["content"] == content

    def test_retain_with_remote_success(self, remote_manager):
        """When remote Hindsight succeeds, should return remote response."""
        response = make_mock_response(200, {"id": "hs-123", "status": "retained"})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = remote_manager.retain_incident("Test incident")
        assert result == {"id": "hs-123", "status": "retained"}
        # Should NOT store locally when remote succeeds
        assert len(remote_manager.local_store) == 0

    def test_retain_with_remote_failure_falls_back(self, remote_manager):
        """When remote fails, should fall back to local storage."""
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = remote_manager.retain_incident("Test incident")
        assert result["status"] == "retained_locally"
        assert len(remote_manager.local_store) == 1

    def test_retain_with_remote_timeout_falls_back(self, remote_manager):
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.Timeout("slow"),
        ):
            result = remote_manager.retain_incident("Test incident")
        assert result["status"] == "retained_locally"

    def test_retain_with_remote_500_falls_back(self, remote_manager):
        """Non-200 status should fall back to local storage."""
        response = make_mock_response(500, {"error": "internal"})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = remote_manager.retain_incident("Test incident")
        assert result["status"] == "retained_locally"
        assert len(remote_manager.local_store) == 1


# ---------------------------------------------------------------------------
# Accurate recall
# ---------------------------------------------------------------------------


class TestAccurateRecall:
    """Recall accuracy tests."""

    def test_recall_finds_matching_incident(self, local_manager):
        local_manager.retain_incident(
            "PostgreSQL connection pool exhausted by idle sessions"
        )
        result = local_manager.recall_resolution("PostgreSQL connection slots exhausted")
        assert result["status"] == "recalled_locally"
        assert len(result["results"]) == 1
        assert "PostgreSQL" in result["results"][0]

    def test_recall_returns_empty_for_no_match(self, local_manager):
        local_manager.retain_incident("Redis OOM maxmemory eviction policy exhausted")
        result = local_manager.recall_resolution("Kubernetes pod OOMKilled")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_recall_empty_store_returns_empty(self, local_manager):
        result = local_manager.recall_resolution("anything")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_recall_with_empty_query(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.recall_resolution("")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_recall_with_whitespace_query(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.recall_resolution("   ")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_recall_with_stop_words_only(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.recall_resolution("the and for with")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_recall_with_single_significant_word(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.recall_resolution("database")
        assert result["status"] == "recalled_locally"
        assert len(result["results"]) == 1

    def test_recall_is_case_insensitive(self, local_manager):
        local_manager.retain_incident("Database Connection Timeout")
        result = local_manager.recall_resolution("database connection timeout")
        assert result["status"] == "recalled_locally"
        assert len(result["results"]) >= 1

    def test_recall_with_remote_success(self, remote_manager):
        response = make_mock_response(200, {"results": ["fix1", "fix2"]})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = remote_manager.recall_resolution("test query")
        assert result == {"results": ["fix1", "fix2"]}

    def test_recall_with_remote_failure_falls_back(self, remote_manager):
        remote_manager.retain_incident("database connection timeout")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = remote_manager.recall_resolution("database connection")
        assert result["status"] == "recalled_locally"
        assert len(result["results"]) >= 1

    def test_recall_with_remote_malformed_response_falls_back(self, remote_manager):
        """Remote returning invalid JSON should fall back to local."""
        remote_manager.retain_incident("database connection timeout")
        response = make_mock_response(200)
        response.json.side_effect = ValueError("invalid")
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = remote_manager.recall_resolution("database connection")
        assert result["status"] == "recalled_locally"

    def test_recall_with_remote_non_dict_response_falls_back(self, remote_manager):
        remote_manager.retain_incident("database connection timeout")
        response = make_mock_response(200, ["not", "a", "dict"])
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = remote_manager.recall_resolution("database connection")
        assert result["status"] == "recalled_locally"

    def test_recall_with_remote_results_not_list_falls_back(self, remote_manager):
        remote_manager.retain_incident("database connection timeout")
        response = make_mock_response(200, {"results": "not-a-list"})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = remote_manager.recall_resolution("database connection")
        assert result["status"] == "recalled_locally"


# ---------------------------------------------------------------------------
# Duplicate retention
# ---------------------------------------------------------------------------


class TestDuplicateRetention:
    """Duplicate incident retention tests."""

    def test_duplicate_retain_stored_once(self, local_manager):
        for _ in range(5):
            local_manager.retain_incident("same incident", context="test")
        assert len(local_manager.local_store) == 1

    def test_duplicate_retain_different_context_stored_twice(self, local_manager):
        local_manager.retain_incident("same incident", context="context_a")
        local_manager.retain_incident("same incident", context="context_b")
        assert len(local_manager.local_store) == 2

    def test_duplicate_retain_different_content_stored_twice(self, local_manager):
        local_manager.retain_incident("incident A", context="test")
        local_manager.retain_incident("incident B", context="test")
        assert len(local_manager.local_store) == 2

    def test_many_duplicates_stored_once(self, local_manager):
        for _ in range(100):
            local_manager.retain_incident("identical incident")
        assert len(local_manager.local_store) == 1


# ---------------------------------------------------------------------------
# Unrelated incident isolation
# ---------------------------------------------------------------------------


class TestUnrelatedIncidentIsolation:
    """Unrelated incidents should not match in recall."""

    def test_redis_incident_not_recalled_by_k8s_query(self, local_manager):
        local_manager.retain_incident("Redis OOM maxmemory eviction policy exhausted")
        result = local_manager.recall_resolution("Kubernetes pod OOMKilled memory limit")
        assert result["results"] == []

    def test_pg_incident_not_recalled_by_redis_query(self, local_manager):
        local_manager.retain_incident("PostgreSQL connection pool exhausted")
        result = local_manager.recall_resolution("Redis OOM maxmemory")
        assert result["results"] == []

    def test_multiple_unrelated_incidents_no_cross_match(self, local_manager):
        local_manager.retain_incident("Redis OOM maxmemory eviction policy exhausted")
        local_manager.retain_incident("PostgreSQL connection pool exhausted")
        local_manager.retain_incident("Kubernetes OOMKilled memory limit exceeded")

        result_redis = local_manager.recall_resolution("Redis OOM maxmemory")
        result_pg = local_manager.recall_resolution("PostgreSQL connection pool")
        result_k8s = local_manager.recall_resolution("Kubernetes OOMKilled memory")

        assert len(result_redis["results"]) == 1
        assert len(result_pg["results"]) == 1
        assert len(result_k8s["results"]) == 1
        assert "Redis" in result_redis["results"][0]
        assert "PostgreSQL" in result_pg["results"][0]
        assert "Kubernetes" in result_k8s["results"][0]


# ---------------------------------------------------------------------------
# Conflicting historical resolutions
# ---------------------------------------------------------------------------


class TestConflictingHistoricalResolutions:
    """Conflicting resolutions in memory should all be returned."""

    def test_conflicting_fixes_all_recalled(self, local_manager):
        local_manager.retain_incident(
            "Database connection timeout. Verified Fix: restart service."
        )
        local_manager.retain_incident(
            "Database connection timeout. Verified Fix: increase pool size."
        )
        result = local_manager.recall_resolution("database connection timeout")
        assert len(result["results"]) == 2

    def test_conflicting_fixes_not_reconciled(self, local_manager):
        """Agent should not pick one fix over another — both are context."""
        local_manager.retain_incident(
            "Database connection timeout. Verified Fix: restart service."
        )
        local_manager.retain_incident(
            "Database connection timeout. Verified Fix: do NOT restart service."
        )
        result = local_manager.recall_resolution("database connection timeout")
        # Both should be returned as untrusted context
        assert len(result["results"]) == 2


# ---------------------------------------------------------------------------
# Empty memory banks
# ---------------------------------------------------------------------------


class TestEmptyMemoryBanks:
    """Behavior with empty memory banks."""

    def test_recall_from_empty_bank(self, local_manager):
        result = local_manager.recall_resolution("anything")
        assert result["status"] == "recalled_locally"
        assert result["results"] == []

    def test_reflect_from_empty_bank(self, local_manager):
        result = local_manager.reflect_patterns("test")
        assert result["status"] == "reflected_locally"
        assert "No incidents" in result["reflection"]

    def test_retain_to_empty_bank(self, local_manager):
        result = local_manager.retain_incident("first incident")
        assert result["status"] == "retained_locally"
        assert len(local_manager.local_store) == 1

    def test_multiple_operations_on_empty_bank(self, local_manager):
        local_manager.retain_incident("incident")
        local_manager.recall_resolution("query")
        local_manager.reflect_patterns("query")
        assert len(local_manager.local_store) == 1


# ---------------------------------------------------------------------------
# Service unavailability and recovery
# ---------------------------------------------------------------------------


class TestServiceUnavailabilityAndRecovery:
    """Behavior when Hindsight service is unavailable and recovers."""

    def test_retain_during_outage(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = manager.retain_incident("incident during outage")
        assert result["status"] == "retained_locally"
        assert len(manager.local_store) == 1

    def test_recall_during_outage(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            manager.retain_incident("database connection timeout")
            result = manager.recall_resolution("database connection")
        assert result["status"] == "recalled_locally"
        assert len(result["results"]) == 1

    def test_retain_after_recovery(self):
        """After service recovers, retain should use remote."""
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        # During outage
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            manager.retain_incident("incident during outage")

        # After recovery
        response = make_mock_response(200, {"id": "hs-456"})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.retain_incident("incident after recovery")
        assert result == {"id": "hs-456"}

    def test_recall_after_recovery(self):
        """After service recovers, recall should use remote."""
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        # During outage
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            manager.retain_incident("database connection timeout")

        # After recovery
        response = make_mock_response(200, {"results": ["remote fix"]})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.recall_resolution("database connection")
        assert result == {"results": ["remote fix"]}

    def test_intermittent_outage_retain(self):
        """Intermittent failures should fall back gracefully."""
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        call_count = 0

        def intermittent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 1:
                raise requests.ConnectionError("offline")
            return make_mock_response(200, {"id": f"hs-{call_count}"})

        with patch("memory.hindsight_client.requests.post", side_effect=intermittent):
            r1 = manager.retain_incident("incident 1")
            r2 = manager.retain_incident("incident 2")
            r3 = manager.retain_incident("incident 3")

        assert r1["status"] == "retained_locally"
        assert r2 == {"id": "hs-2"}
        assert r3["status"] == "retained_locally"

    def test_intermittent_outage_recall(self):
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        call_count = 0

        def intermittent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 1:
                raise requests.ConnectionError("offline")
            return make_mock_response(200, {"results": [f"fix-{call_count}"]})

        with patch("memory.hindsight_client.requests.post", side_effect=intermittent):
            r1 = manager.recall_resolution("query")
            r2 = manager.recall_resolution("query")

        assert r1["status"] == "recalled_locally"
        assert r2 == {"results": ["fix-2"]}


# ---------------------------------------------------------------------------
# Concurrent memory access
# ---------------------------------------------------------------------------


class TestConcurrentMemoryAccess:
    """Thread-safety tests."""

    def test_concurrent_retains_no_data_loss(self, local_manager):
        incidents = [f"database shard{i} connection pool timeout" for i in range(50)]
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(local_manager.retain_incident, incidents))
        assert len(local_manager.local_store) == 50

    def test_concurrent_duplicate_retains_deduplicated(self, local_manager):
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(
                pool.map(
                    lambda _: local_manager.retain_incident("same event"),
                    range(100),
                )
            )
        assert len(local_manager.local_store) == 1

    def test_concurrent_retain_and_recall(self, local_manager):
        """Concurrent retains and recalls should not crash."""
        errors = []

        def retain_task():
            try:
                for i in range(20):
                    local_manager.retain_incident(f"incident {i}")
            except (TypeError, ValueError, KeyError) as e:
                errors.append(e)

        def recall_task():
            try:
                for _ in range(20):
                    local_manager.recall_resolution("incident")
            except (TypeError, ValueError, KeyError) as e:
                errors.append(e)

        threads = [
            threading.Thread(target=retain_task),
            threading.Thread(target=recall_task),
            threading.Thread(target=retain_task),
            threading.Thread(target=recall_task),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_recalls_consistent(self, local_manager):
        local_manager.retain_incident("database connection pool timeout")
        results = []
        errors = []

        def recall():
            try:
                r = local_manager.recall_resolution("database connection")
                results.append(len(r["results"]))
            except (TypeError, ValueError, KeyError) as e:
                errors.append(e)

        threads = [threading.Thread(target=recall) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == 1 for r in results)


# ---------------------------------------------------------------------------
# Persistence distinction
# ---------------------------------------------------------------------------


class TestPersistenceDistinction:
    """Distinguish in-memory fallback from genuinely persistent storage."""

    def test_local_fallback_not_persistent_across_instances(self):
        """In-memory fallback is per-instance — new instance has empty store."""
        manager1 = SentryMemoryManager(base_url="http://unused.invalid")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            manager1.retain_incident("incident in manager1")

        # New instance (simulating app restart) should NOT have the incident
        manager2 = SentryMemoryManager(base_url="http://unused.invalid")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = manager2.recall_resolution("incident in manager1")
        assert result["results"] == []

    def test_local_fallback_not_persistent_across_restart(self):
        """Simulating app restart: new manager instance loses local store."""
        manager = SentryMemoryManager(base_url="http://unused.invalid")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            manager.retain_incident("database connection timeout")
            assert len(manager.local_store) == 1

        # Simulate restart by creating new instance
        new_manager = SentryMemoryManager(base_url="http://unused.invalid")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = new_manager.recall_resolution("database connection")
        assert result["results"] == []

    def test_remote_storage_persists_across_instances(self):
        """Remote Hindsight storage persists across manager instances."""
        manager1 = SentryMemoryManager(base_url="http://hindsight.test")
        response = make_mock_response(200, {"id": "hs-789"})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            manager1.retain_incident("persistent incident")

        # New instance should recall from remote
        manager2 = SentryMemoryManager(base_url="http://hindsight.test")
        response2 = make_mock_response(200, {"results": ["persistent incident"]})
        with patch("memory.hindsight_client.requests.post", return_value=response2):
            result = manager2.recall_resolution("persistent incident")
        assert result == {"results": ["persistent incident"]}

    def test_local_fallback_is_transparent(self):
        """Local fallback should be clearly indicated in response."""
        manager = SentryMemoryManager(base_url="http://unused.invalid")
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = manager.retain_incident("test")
        assert result["status"] == "retained_locally"
        # The response should make it clear this is local, not remote
        assert "entry" in result

    def test_remote_response_does_not_claim_local(self):
        """Remote success should not claim to be local."""
        manager = SentryMemoryManager(base_url="http://hindsight.test")
        response = make_mock_response(200, {"id": "hs-999"})
        with patch("memory.hindsight_client.requests.post", return_value=response):
            result = manager.retain_incident("test")
        assert result == {"id": "hs-999"}
        assert "retained_locally" not in str(result)


# ---------------------------------------------------------------------------
# Reflect patterns
# ---------------------------------------------------------------------------


class TestReflectPatterns:
    """Pattern reflection tests."""

    def test_reflect_empty_store(self, local_manager):
        result = local_manager.reflect_patterns("test")
        assert result["status"] == "reflected_locally"
        assert "No incidents" in result["reflection"]

    def test_reflect_with_incidents(self, local_manager):
        local_manager.retain_incident("Connection timeout on database server")
        local_manager.retain_incident("Memory cache OOM error")
        result = local_manager.reflect_patterns("test")
        assert result["status"] == "reflected_locally"
        assert "Observed patterns" in result["reflection"]

    def test_reflect_detects_connection_pattern(self, local_manager):
        local_manager.retain_incident("Connection timeout database")
        local_manager.retain_incident("Connection refused database")
        result = local_manager.reflect_patterns("test")
        assert "connection" in result["reflection"].lower()

    def test_reflect_detects_oom_pattern(self, local_manager):
        local_manager.retain_incident("OOM error memory")
        result = local_manager.reflect_patterns("test")
        assert "oom" in result["reflection"].lower()

    def test_reflect_with_no_matching_keywords(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.reflect_patterns("test")
        # Should still return a valid response
        assert result["status"] == "reflected_locally"
        assert "reflection" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary and edge case tests."""

    def test_retain_with_none_content(self, local_manager):
        """None content should be handled."""
        result = local_manager.retain_incident(None)
        assert result["status"] == "retained_locally"

    def test_retain_with_numeric_content(self, local_manager):
        result = local_manager.retain_incident(12345)
        assert result["status"] == "retained_locally"

    def test_recall_with_none_query(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.recall_resolution(None)
        assert result["status"] == "recalled_locally"

    def test_recall_with_numeric_query(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        result = local_manager.recall_resolution(12345)
        assert result["status"] == "recalled_locally"

    def test_very_long_query(self, local_manager):
        local_manager.retain_incident("database connection timeout")
        long_query = "database " * 1000
        result = local_manager.recall_resolution(long_query)
        assert result["status"] == "recalled_locally"

    def test_special_characters_in_content(self, local_manager):
        content = "ERROR: <script>alert('xss')</script> database failed"
        result = local_manager.retain_incident(content)
        assert result["status"] == "retained_locally"
        assert local_manager.local_store[0]["content"] == content

    def test_newlines_in_content(self, local_manager):
        content = "ERROR: line1\nline2\nline3"
        result = local_manager.retain_incident(content)
        assert result["status"] == "retained_locally"
        assert local_manager.local_store[0]["content"] == content

    def test_manager_with_custom_bank_id(self):
        manager = SentryMemoryManager(
            base_url="http://unused.invalid", bank_id="custom-bank"
        )
        with patch(
            "memory.hindsight_client.requests.post",
            side_effect=requests.ConnectionError("offline"),
        ):
            manager.retain_incident("test")
        assert manager.local_store[0]["bank_id"] == "custom-bank"

    def test_manager_default_bank_id(self):
        manager = SentryMemoryManager(base_url="http://unused.invalid")
        assert manager.bank_id is not None
        assert len(manager.bank_id) > 0
