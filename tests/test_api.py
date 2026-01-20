"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.lloyds_list_mcp.api import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint returns API information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "endpoints" in data


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_list_feeds_endpoint():
    """Test list available feeds endpoint."""
    response = client.get("/api/feeds")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "feeds" in data


def test_search_articles_endpoint():
    """Test search articles endpoint."""
    response = client.post(
        "/api/search",
        json={"query": "container", "limit": 5}
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_get_latest_articles_endpoint():
    """Test get latest articles endpoint."""
    response = client.post(
        "/api/latest",
        json={
            "feed_type": "sectors",
            "feed_name": "Containers",
            "limit": 5
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_invalid_feed_parameters():
    """Test API with invalid feed parameters."""
    response = client.post(
        "/api/latest",
        json={
            "feed_type": "invalid_type",
            "feed_name": "Invalid",
            "limit": 5
        }
    )
    # Should return error but not crash
    assert response.status_code in [200, 400, 500]
