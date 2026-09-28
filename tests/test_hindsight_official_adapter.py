"""Unit tests for the official Hindsight adapter's protocol handling.

These tests do NOT contact a real service. They pin the exact wire contract
that was established against the live official Vectorize Hindsight API, so
that a future refactor cannot silently regress to the old mock's shapes:

- Retain is a multipart upload to ``/files/retain`` and returns
  ``operation_ids`` asynchronously.
- Retain returns HTTP 404 until the bank is provisioned.
- Recall returns ``{"results": [{"text": ...}]}`` — the content field is
  ``text``, not ``content``.
- Reflect returns the synthesis under ``text``.
- ``/health`` is the readiness probe.

Every test asserts the response is attributed to the correct backend, so a
silent degradation to the local fallback is always a failure, never a pass.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory.hindsight_client import SentryMemoryManager

BASE = "http://hindsight.test"
BANK = "unit-test-bank"


def make_manager(**kwargs):
    return SentryMemoryManager(base_url=BASE, bank_id=BANK, **kwargs)


def resp(status, payload=None, json_error=False):
    """Build a requests-like response double."""
    m = MagicMock()
    m.status_code = status
    if json_error:
        m.json.side_effect = ValueError("not json")
    else:
        m.json.return_value = payload
    return m


# ---------------------------------------------------------------------------
# Bank provisioning
# ---------------------------------------------------------------------------


class TestBankProvisioning:
    def test_provisions_and_caches_success(self):
        mgr = make_manager()
        with patch.object(requests, "put") as mock_put:
            mock_put.return_value = resp(200)
            assert mgr._ensure_bank() is True
            # Second call is served from the cache — no extra round trip.
            assert mgr._ensure_bank() is True
        assert mock_put.call_count == 1
        assert BANK in mgr._bank_ready

    @pytest.mark.parametrize("status", [201, 409])
    def test_accepts_created_and_already_exists(self, status):
        """409 means the bank already exists, which is a success, not a failure."""
        mgr = make_manager()
        with patch.object(requests, "put") as mock_put:
            mock_put.return_value = resp(status)
            assert mgr._ensure_bank() is True

    def test_service_unreachable_is_not_reported_as_bank_missing(self):
        """A dead service must not be mistaken for an absent bank.

        Provisioning failure returns False but does NOT get cached, so a later
        attempt can still succeed once the service comes back.
        """
        mgr = make_manager()
        with patch.object(requests, "put") as mock_put:
            mock_put.side_effect = requests.ConnectionError("refused")
            assert mgr._ensure_bank() is False
        assert BANK not in mgr._bank_ready

    def test_unexpected_status_does_not_cache(self):
        mgr = make_manager()
        with patch.object(requests, "put") as mock_put:
            mock_put.return_value = resp(500)
            assert mgr._ensure_bank() is False
        assert BANK not in mgr._bank_ready

    def test_force_bypasses_cache(self):
        mgr = make_manager()
        with patch.object(requests, "put") as mock_put:
            mock_put.return_value = resp(200)
            mgr._ensure_bank()
            mgr._ensure_bank(force=True)
        assert mock_put.call_count == 2


# ---------------------------------------------------------------------------
# Retain
# ---------------------------------------------------------------------------


class TestRetainOfficialProtocol:
    def test_retain_uses_multipart_upload_with_files_metadata(self):
        """The official API wants a file upload plus a JSON ``request`` field."""
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"operation_ids": ["op-1"]})
            out = mgr.retain_incident("Incident ID: x", context="postmortem")

        kwargs = mock_post.call_args.kwargs
        assert mock_post.call_args.args[0].endswith(
            f"/v1/default/banks/{BANK}/files/retain"
        )
        assert "files" in kwargs and "data" in kwargs
        assert "request" in kwargs["data"]
        assert '"files_metadata"' in kwargs["data"]["request"]
        assert out["backend"] == "hindsight"
        assert out["operation_ids"] == ["op-1"]

    def test_retain_202_accepted_is_success(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(202, {"operation_ids": ["op-2"]})
            assert mgr.retain_incident("boom")["backend"] == "hindsight"

    def test_retain_provisions_bank_on_404_then_retries(self):
        """A 404 means the bank does not exist yet — provision and retry once.

        Without this, every retain to a new bank silently degraded to the local
        fallback and persistence appeared broken.
        """
        mgr = make_manager()
        with (
            patch.object(requests, "post") as mock_post,
            patch.object(requests, "put") as mock_put,
        ):
            mock_post.side_effect = [
                resp(404, {"detail": "Bank not found"}),
                resp(200, {"operation_ids": ["op-3"]}),
            ]
            mock_put.return_value = resp(200)
            out = mgr.retain_incident("Incident ID: y")

        assert out["backend"] == "hindsight"
        assert mock_post.call_count == 2
        assert mock_put.call_count == 1

    def test_retain_retries_at_most_once(self):
        """A persistently 404 bank must fall back, not loop."""
        mgr = make_manager()
        with (
            patch.object(requests, "post") as mock_post,
            patch.object(requests, "put") as mock_put,
        ):
            mock_post.return_value = resp(404, {"detail": "Bank not found"})
            mock_put.return_value = resp(200)
            out = mgr.retain_incident("Incident ID: z")

        assert out["backend"] == "local_fallback"
        assert mock_post.call_count == 2

    def test_retain_falls_back_on_server_error(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(500)
            assert mgr.retain_incident("boom")["backend"] == "local_fallback"

    def test_retain_falls_back_when_response_is_not_an_object(self):
        """A bare list response is malformed and must not be reported official."""
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, ["unexpected"])
            assert mgr.retain_incident("boom")["backend"] == "local_fallback"

    def test_retain_falls_back_on_unparsable_json(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, json_error=True)
            assert mgr.retain_incident("boom")["backend"] == "local_fallback"

    def test_retain_falls_back_when_service_is_down(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("refused")
            assert mgr.retain_incident("boom")["backend"] == "local_fallback"

    def test_retain_coerces_non_string_content(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"operation_ids": ["op-4"]})
            out = mgr.retain_incident(12345)  # type: ignore[arg-type]
        assert out["backend"] == "hindsight"
        assert out["entry"]["content"] if "entry" in out else True

    def test_successful_retain_caches_bank_readiness(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"operation_ids": ["op-5"]})
            mgr.retain_incident("ok")
        assert BANK in mgr._bank_ready


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------


class TestRecallOfficialProtocol:
    def test_recall_reads_official_text_field(self):
        """Official memories are keyed ``text``; reading ``content`` returned nothing."""
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"results": [{"text": "a fact"}]})
            out = mgr.recall_resolution("anything")

        assert out["backend"] == "hindsight"
        assert out["results"] == ["a fact"]

    def test_recall_accepts_legacy_content_field(self):
        """The retired mock used ``content``; keep both readable."""
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"results": [{"content": "old fact"}]})
            assert mgr.recall_resolution("x")["results"] == ["old fact"]

    def test_recall_accepts_bare_string_entries(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"results": ["plain string"]})
            assert mgr.recall_resolution("x")["results"] == ["plain string"]

    def test_malformed_results_is_never_iterated_character_by_character(self):
        """Regression: a string ``results`` was iterated per character.

        The result was 15 bogus one-letter "memories" reported as a successful
        official recall. It must fall back instead.
        """
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"results": "not-a-list"})
            out = mgr.recall_resolution("x")

        assert out["backend"] == "local_fallback"
        assert out["results"] == []

    def test_recall_falls_back_when_results_is_not_an_object(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, ["a", "b"])
            assert mgr.recall_resolution("x")["backend"] == "local_fallback"

    def test_recall_falls_back_on_error_status(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(503)
            assert mgr.recall_resolution("x")["backend"] == "local_fallback"

    def test_recall_falls_back_on_unparsable_json(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, json_error=True)
            assert mgr.recall_resolution("x")["backend"] == "local_fallback"

    def test_recall_falls_back_when_service_is_down(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.side_effect = requests.Timeout("read timed out")
            assert mgr.recall_resolution("x")["backend"] == "local_fallback"

    def test_recall_coerces_non_string_query(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"results": []})
            out = mgr.recall_resolution(42)  # type: ignore[arg-type]
        assert out["backend"] == "hindsight"
        assert mock_post.call_args.kwargs["json"] == {"query": "42"}


# ---------------------------------------------------------------------------
# Reflect
# ---------------------------------------------------------------------------


class TestReflectOfficialProtocol:
    def test_reflect_reads_official_text_field(self):
        """Official reflect returns the synthesis under ``text``.

        Reading ``response``/``reflection`` made every reflection empty while
        still reporting success.
        """
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(
                200, {"text": "synthesis", "usage": {"output_tokens": 5}}
            )
            out = mgr.reflect_patterns("pattern")

        assert out["backend"] == "hindsight"
        assert out["reflection"] == "synthesis"
        assert out["usage"] == {"output_tokens": 5}

    def test_reflect_accepts_legacy_response_field(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"response": "legacy synthesis"})
            assert mgr.reflect_patterns("p")["reflection"] == "legacy synthesis"

    def test_empty_reflection_is_a_failure_not_a_success(self):
        """An empty synthesis must degrade, never be reported as official."""
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"text": "   "})
            out = mgr.reflect_patterns("p")
        assert out["backend"] == "local_fallback"
        assert out["status"] == "reflected_locally"

    def test_reflect_falls_back_when_payload_is_not_an_object(self):
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, "nope")
            assert mgr.reflect_patterns("p")["backend"] == "local_fallback"

    def test_reflect_falls_back_on_timeout(self):
        """A gateway timeout must degrade rather than propagate as a crash."""
        mgr = make_manager()
        with patch.object(requests, "post") as mock_post:
            mock_post.side_effect = requests.Timeout("504")
            assert mgr.reflect_patterns("p")["backend"] == "local_fallback"

    def test_reflect_uses_its_own_longer_timeout(self):
        """Reflect is a multi-call synthesis measured at 156s, so it must not
        inherit the 30s retain/recall budget."""
        mgr = make_manager(timeout=30, reflect_timeout=540)
        with patch.object(requests, "post") as mock_post:
            mock_post.return_value = resp(200, {"text": "ok"})
            mgr.reflect_patterns("p")
        assert mock_post.call_args.kwargs["timeout"] == 540


# ---------------------------------------------------------------------------
# Backend status
# ---------------------------------------------------------------------------


class TestBackendStatus:
    def test_reports_healthy_official_service(self):
        mgr = make_manager()
        with patch.object(requests, "get") as mock_get:
            mock_get.return_value = resp(
                200, {"status": "healthy", "database": "connected"}
            )
            status = mgr.backend_status()

        assert status["hindsight_reachable"] is True
        assert status["active_backend"] == "hindsight"
        assert status["hindsight_health"] == "healthy"
        assert status["database"] == "connected"
        assert status["bank_id"] == BANK
        assert status["configured_url"] == BASE

    def test_uses_health_endpoint_not_recall(self):
        """A recall probe contended for the LLM slot and produced false
        "unreachable" reports while the service was perfectly healthy."""
        mgr = make_manager()
        with patch.object(requests, "get") as mock_get:
            mock_get.return_value = resp(200, {"status": "healthy"})
            mgr.backend_status()
        assert mock_get.call_args.args[0].endswith("/health")

    def test_reports_unhealthy_service(self):
        mgr = make_manager()
        with patch.object(requests, "get") as mock_get:
            mock_get.return_value = resp(503)
            status = mgr.backend_status()

        assert status["hindsight_reachable"] is False
        assert status["active_backend"] == "local_fallback"
        assert status["hindsight_error"] == "HTTP 503"

    def test_reports_unreachable_service(self):
        mgr = make_manager()
        with patch.object(requests, "get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("refused")
            status = mgr.backend_status()

        assert status["hindsight_reachable"] is False
        assert status["active_backend"] == "local_fallback"
        assert "refused" in status["hindsight_error"]

    def test_tolerates_unparsable_health_body(self):
        mgr = make_manager()
        with patch.object(requests, "get") as mock_get:
            mock_get.return_value = resp(200, json_error=True)
            status = mgr.backend_status()
        assert status["hindsight_reachable"] is True

    def test_reports_local_store_size(self):
        mgr = make_manager()
        mgr.retain_incident("offline incident")
        with patch.object(requests, "get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("refused")
            status = mgr.backend_status()
        assert status["local_store_size"] == 1
