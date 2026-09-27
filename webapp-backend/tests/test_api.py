"""
API endpoint tests for the FastAPI backend.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_ok_status(self):
        response = client.get("/")
        data = response.json()
        assert data["status"] == "ok"

    def test_root_returns_message(self):
        response = client.get("/")
        data = response.json()
        assert "message" in data
        assert isinstance(data["message"], str)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_healthy(self):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"


class TestNotFound:
    """Tests for 404 handling."""

    def test_nonexistent_endpoint_returns_404(self):
        response = client.get("/nonexistent")
        assert response.status_code == 404
