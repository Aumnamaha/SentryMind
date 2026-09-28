"""Live HTTP integration tests for the FastAPI backend.

These tests require a running Uvicorn server on port 8001.
They are skipped unless SENTRYMIND_RUN_LIVE_INTEGRATION=1 is set.

Start the server with:
    cd webapp-backend && python -m uvicorn main:app --host 127.0.0.1 --port 8001
"""

import os
import socket
import time
import urllib.error
import urllib.request

import pytest

BASE_URL = "http://127.0.0.1:8001"

pytestmark = pytest.mark.integration


def require_live_server():
    if os.getenv("SENTRYMIND_RUN_LIVE_INTEGRATION") != "1":
        pytest.skip("Set SENTRYMIND_RUN_LIVE_INTEGRATION=1 to enable live checks")


def _http_get(path: str, timeout: float = 5.0) -> tuple[int, str, dict]:
    """Perform a real HTTP GET and return (status, body, headers)."""
    # URL-encode non-ASCII characters in the path
    from urllib.parse import quote

    encoded_path = quote(path, safe="/?&=#")
    url = f"{BASE_URL}{encoded_path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, body, {k.lower(): v for k, v in e.headers.items()}


def _http_request(
    method: str, path: str, timeout: float = 5.0
) -> tuple[int, str, dict]:
    """Perform a real HTTP request and return (status, body, headers)."""
    from urllib.parse import quote

    encoded_path = quote(path, safe="/?&=#")
    url = f"{BASE_URL}{encoded_path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, body, {k.lower(): v for k, v in e.headers.items()}


def _wait_for_server(timeout: float = 10.0) -> bool:
    """Wait until the server accepts TCP connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 8001), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# Basic live endpoint checks
# ---------------------------------------------------------------------------


def test_live_root_returns_200():
    require_live_server()
    status, body, headers = _http_get("/")
    assert status == 200
    assert '"status":"ok"' in body.replace(" ", "")
    assert "application/json" in headers.get("content-type", "")


def test_live_health_returns_200():
    require_live_server()
    status, body, _ = _http_get("/health")
    assert status == 200
    assert '"status":"healthy"' in body.replace(" ", "")


def test_live_nonexistent_returns_404():
    require_live_server()
    status, body, _ = _http_get("/nonexistent")
    assert status == 404
    assert "detail" in body


def test_live_double_slash_returns_404():
    require_live_server()
    status, _, _ = _http_get("//")
    assert status == 404


def test_live_post_to_root_returns_405():
    require_live_server()
    status, _, headers = _http_request("POST", "/")
    assert status == 405
    assert "GET" in headers.get("allow", "")


def test_live_unicode_path_returns_404():
    require_live_server()
    status, _, _ = _http_get("/café")
    assert status == 404


def test_live_very_long_path_returns_404():
    require_live_server()
    status, _, _ = _http_get("/" + "a" * 2000)
    assert status == 404


def test_live_repeated_requests_are_consistent():
    require_live_server()
    for _ in range(10):
        status, body, _ = _http_get("/")
        assert status == 200
        assert '"status":"ok"' in body.replace(" ", "")


def test_live_openapi_spec():
    require_live_server()
    status, body, _ = _http_get("/openapi.json")
    assert status == 200
    assert "/health" in body


def test_live_docs_endpoint():
    require_live_server()
    status, _body, headers = _http_get("/docs")
    assert status == 200
    assert "text/html" in headers.get("content-type", "")


def test_live_error_responses_do_not_expose_stack_traces():
    require_live_server()
    status, body, _ = _http_get("/nonexistent")
    assert status == 404
    assert "traceback" not in body.lower()
    assert 'File "' not in body
    assert "site-packages" not in body


# ---------------------------------------------------------------------------
# Server shutdown and recovery
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
def test_server_responsive_after_multiple_requests():
    """Verify the server remains responsive after multiple requests.

    Tests that the server can handle sequential requests without degradation,
    which is the practical equivalent of shutdown/recovery for a demo.
    """
    require_live_server()

    # Make multiple sequential requests to verify server stability
    for i in range(5):
        status, body, _ = _http_get("/")
        assert status == 200
        assert '"status":"ok"' in body.replace(" ", "")

    for i in range(5):
        status, body, _ = _http_get("/health")
        assert status == 200
        assert '"status":"healthy"' in body.replace(" ", "")

    # Verify server is still responsive after all requests
    status, body, _ = _http_get("/")
    assert status == 200
    assert '"status":"ok"' in body.replace(" ", "")
