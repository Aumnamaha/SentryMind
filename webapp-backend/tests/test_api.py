"""Comprehensive API endpoint tests using in-process ASGI transport.

Covers valid requests, invalid methods, malformed inputs, unicode,
large payloads, repeated requests, OpenAPI spec, docs endpoints,
and error-format safety. No network listener is required.
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

import httpx

from main import app


def get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


# ---------------------------------------------------------------------------
# Valid requests and expected responses
# ---------------------------------------------------------------------------


def test_root_returns_ok_message():
    response = get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "message" in response.json()


def test_health_returns_healthy():
    response = get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_content_type_is_json():
    response = get("/")
    assert response.headers["content-type"] == "application/json"


def test_health_content_type_is_json():
    response = get("/health")
    assert response.headers["content-type"] == "application/json"


def test_root_response_is_valid_json():
    response = get("/")
    data = response.json()
    assert isinstance(data, dict)
    assert "status" in data
    assert "message" in data


def test_health_response_is_valid_json():
    response = get("/health")
    data = response.json()
    assert isinstance(data, dict)
    assert "status" in data


# ---------------------------------------------------------------------------
# Invalid HTTP methods → 405
# ---------------------------------------------------------------------------


def test_post_to_root_returns_405():
    assert request("POST", "/").status_code == 405


def test_put_to_root_returns_405():
    assert request("PUT", "/").status_code == 405


def test_delete_to_root_returns_405():
    assert request("DELETE", "/").status_code == 405


def test_patch_to_root_returns_405():
    assert request("PATCH", "/").status_code == 405


def test_head_to_root_returns_405():
    assert request("HEAD", "/").status_code == 405


def test_options_to_root_returns_405():
    assert request("OPTIONS", "/").status_code == 405


def test_post_to_health_returns_405():
    assert request("POST", "/health").status_code == 405


def test_put_to_health_returns_405():
    assert request("PUT", "/health").status_code == 405


def test_delete_to_health_returns_405():
    assert request("DELETE", "/health").status_code == 405


def test_patch_to_health_returns_405():
    assert request("PATCH", "/health").status_code == 405


def test_head_to_health_returns_405():
    assert request("HEAD", "/health").status_code == 405


def test_options_to_health_returns_405():
    assert request("OPTIONS", "/health").status_code == 405


def test_405_response_includes_allow_header():
    response = request("POST", "/")
    assert response.status_code == 405
    assert "allow" in response.headers
    assert "GET" in response.headers["allow"]


# ---------------------------------------------------------------------------
# 404 for unknown paths
# ---------------------------------------------------------------------------


def test_nonexistent_endpoint_returns_404():
    assert get("/nonexistent").status_code == 404


def test_deep_nonexistent_path_returns_404():
    assert get("/a/b/c/d/e").status_code == 404


def test_nonexistent_path_with_query_returns_404():
    assert get("/nonexistent?foo=bar").status_code == 404


def test_404_response_is_json():
    response = get("/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert isinstance(data, dict)
    assert "detail" in data


def test_404_does_not_expose_stack_trace():
    response = get("/nonexistent")
    body = response.text
    assert "traceback" not in body.lower()
    assert "stack" not in body.lower()
    assert "File \"" not in body


# ---------------------------------------------------------------------------
# Trailing slashes and path variations
# ---------------------------------------------------------------------------


def test_root_with_trailing_slash():
    response = get("/")
    assert response.status_code == 200


def test_health_with_trailing_slash_redirects_or_succeeds():
    response = get("/health/")
    assert response.status_code in (200, 307, 308)


def test_encoded_slash_in_path_returns_404():
    # httpx ASGITransport normalizes "//" to "/", so test encoded slash instead
    assert get("/%2F").status_code == 404


# ---------------------------------------------------------------------------
# Query parameters (should be ignored by these simple endpoints)
# ---------------------------------------------------------------------------


def test_root_with_query_params():
    response = get("/?foo=bar&baz=1")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_with_query_params():
    response = get("/health?verbose=true")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_with_many_query_params():
    params = "&".join(f"key{i}=value{i}" for i in range(50))
    response = get(f"/?{params}")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Unicode and special characters in paths
# ---------------------------------------------------------------------------


def test_unicode_path_returns_404():
    assert get("/café").status_code == 404


def test_unicode_emoji_path_returns_404():
    assert get("/🛡️").status_code == 404


def test_special_chars_path_returns_404():
    assert get("/%00%01%02").status_code == 404


def test_path_with_spaces_encoded_returns_404():
    assert get("/path%20with%20spaces").status_code == 404


def test_path_with_null_byte_returns_404():
    assert get("/test%00").status_code == 404


def test_very_long_path_returns_404():
    assert get("/" + "a" * 2000).status_code == 404


# ---------------------------------------------------------------------------
# Extremely large inputs
# ---------------------------------------------------------------------------


def test_very_large_query_string():
    large_value = "x" * 10000
    response = get(f"/?data={large_value}")
    assert response.status_code == 200


def test_very_large_path_returns_404():
    response = get("/" + "b" * 5000)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Repeated requests (idempotency / consistency)
# ---------------------------------------------------------------------------


def test_repeated_root_requests_are_consistent():
    responses = [get("/") for _ in range(20)]
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["status"] == "ok" for r in responses)


def test_repeated_health_requests_are_consistent():
    responses = [get("/health") for _ in range(20)]
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["status"] == "healthy" for r in responses)


def test_alternating_requests_are_consistent():
    for _ in range(10):
        assert get("/").status_code == 200
        assert get("/health").status_code == 200


# ---------------------------------------------------------------------------
# OpenAPI specification
# ---------------------------------------------------------------------------


def test_openapi_spec_is_accessible():
    response = get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "openapi" in spec
    assert "paths" in spec


def test_openapi_spec_contains_root_endpoint():
    spec = get("/openapi.json").json()
    assert "/" in spec["paths"]
    assert "get" in spec["paths"]["/"]


def test_openapi_spec_contains_health_endpoint():
    spec = get("/openapi.json").json()
    assert "/health" in spec["paths"]
    assert "get" in spec["paths"]["/health"]


def test_openapi_spec_contains_all_endpoints():
    spec = get("/openapi.json").json()
    paths = set(spec["paths"].keys())
    assert "/" in paths
    assert "/health" in paths
    assert "/analyze" in paths
    assert "/config" in paths


# ---------------------------------------------------------------------------
# Documentation endpoints
# ---------------------------------------------------------------------------


def test_docs_endpoint_returns_200():
    response = get("/docs")
    assert response.status_code == 200


def test_redoc_endpoint_returns_200():
    response = get("/redoc")
    assert response.status_code == 200


def test_docs_content_type_is_html():
    response = get("/docs")
    assert "text/html" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Error format safety — no stack traces or sensitive data
# ---------------------------------------------------------------------------


def test_404_error_format_is_safe():
    response = get("/nonexistent")
    body = response.text
    assert "traceback" not in body.lower()
    assert "stack" not in body.lower()
    assert "File \"" not in body
    assert "site-packages" not in body


def test_405_error_format_is_safe():
    response = request("POST", "/")
    body = response.text
    assert "traceback" not in body.lower()
    assert "stack" not in body.lower()
    assert "File \"" not in body


def test_error_responses_are_json():
    for path in ["/nonexistent", "/also-missing"]:
        response = get(path)
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"


# ---------------------------------------------------------------------------
# Concurrent requests
# ---------------------------------------------------------------------------


def test_concurrent_requests_all_succeed():
    async def concurrent():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            tasks = [client.get("/") for _ in range(10)]
            tasks += [client.get("/health") for _ in range(10)]
            return await asyncio.gather(*tasks)

    responses = asyncio.run(concurrent())
    assert len(responses) == 20
    assert all(r.status_code == 200 for r in responses)


# ---------------------------------------------------------------------------
# Request with body on GET (should be ignored or rejected gracefully)
# ---------------------------------------------------------------------------


def test_get_with_json_body():
    response = request("GET", "/", json={"key": "value"})
    assert response.status_code == 200


def test_get_with_text_body():
    response = request("GET", "/", content=b"some body")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Malformed request handling
# ---------------------------------------------------------------------------


def test_malformed_query_string():
    response = get("/?%zz=invalid")
    assert response.status_code == 200


def test_fragment_in_path():
    response = get("/#fragment")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Config endpoint
# ---------------------------------------------------------------------------


def test_config_endpoint_returns_200():
    response = get("/config")
    assert response.status_code == 200
    data = response.json()
    assert "model" in data
    assert "max_output_tokens" in data
    assert "temperature" in data


def test_config_endpoint_does_not_expose_secrets():
    response = get("/config")
    body = response.text
    assert "api_key" not in body.lower()
    assert "password" not in body.lower()
    assert "secret" not in body.lower()
    # Check for actual secret values, not just the word "token" in "max_output_tokens"
    assert "bearer" not in body.lower()
    assert "authorization" not in body.lower()


# ---------------------------------------------------------------------------
# Analyze endpoint (mocked inference)
# ---------------------------------------------------------------------------


def test_analyze_endpoint_returns_200():
    """Analyze endpoint should return 200 with mocked inference."""
    from unittest.mock import patch

    with patch("main._analyze_sync") as mock_analyze:
        mock_analyze.return_value = {
            "raw_log": "test error",
            "use_memory": False,
            "memory_active": False,
            "root_cause": "test cause",
            "recommended_action": "test action",
            "llm_response": "test response",
            "confidence": "low",
            "recalled_context": [],
            "evidence": [],
            "uncertainty": "",
            "next_checks": [],
        }
        response = request("POST", "/analyze", json={"log": "test error", "use_memory": False})
        assert response.status_code == 200
        data = response.json()
        assert data["root_cause"] == "test cause"
        assert data["latency_ms"] >= 0


def test_analyze_endpoint_returns_503_when_queue_full():
    """Analyze endpoint should return 503 when queue is full."""
    import main

    original = main._request_queue_size
    main._request_queue_size = main._max_queue_size
    try:
        response = request("POST", "/analyze", json={"log": "test", "use_memory": False})
        assert response.status_code == 503
    finally:
        main._request_queue_size = original


def test_analyze_endpoint_returns_500_on_inference_failure():
    """Analyze endpoint should return 500 when inference fails."""
    from unittest.mock import patch

    with patch("main._analyze_sync", side_effect=RuntimeError("inference failed")):
        response = request("POST", "/analyze", json={"log": "test", "use_memory": False})
        assert response.status_code == 500


def test_analyze_endpoint_validates_request():
    """Analyze endpoint should validate request body."""
    response = request("POST", "/analyze", json={})
    assert response.status_code == 422  # Missing required 'log' field
