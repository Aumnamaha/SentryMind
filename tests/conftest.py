import pytest
import requests


@pytest.fixture(autouse=True)
def block_unmocked_external_requests(monkeypatch, request):
    """Prevent accidental network dependencies in deterministic tests."""
    if request.node.get_closest_marker("integration"):
        return

    def blocked(*args, **kwargs):
        raise requests.ConnectionError("External services disabled in tests")

    monkeypatch.setattr("requests.sessions.Session.request", blocked)
