"""Shared test fixtures for Lloyd's List MCP Server tests."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.fixture
def mock_rss_feed():
    """Provide sample RSS feed data for testing."""
    return {
        "feed": {
            "title": "Lloyd's List - Containers",
            "link": "https://lloydslist.maritimeintelligence.informa.com",
            "description": "Latest container shipping news",
            "updated": "2026-01-20T10:00:00Z",
        },
        "entries": [
            {
                "title": "Container rates surge in Q1 2026",
                "url": "https://lloydslist.maritimeintelligence.informa.com/LL1156104",
                "date": "Mon, 20 Jan 2026 10:00:00 GMT",
                "summary": "Container shipping rates increased 15% in early 2026...",
                "author": "John Doe",
                "tags": ["Containers", "Markets"],
                "image_url": "https://lloydslist.maritimeintelligence.informa.com/images/article.jpg",
            },
            {
                "title": "Port congestion eases at major hubs",
                "url": "https://lloydslist.maritimeintelligence.informa.com/LL1156105",
                "date": "Mon, 20 Jan 2026 09:00:00 GMT",
                "summary": "Major container ports report reduced congestion...",
                "author": "Jane Smith",
                "tags": ["Containers", "Ports"],
                "image_url": None,
            },
        ],
        "fetched_at": 1737369600.0,
    }


@pytest.fixture
def mock_auth_session(tmp_path):
    """Provide mock authentication session state."""
    auth_data = {
        "cookies": [
            {
                "name": "session_id",
                "value": "mock_session_123",
                "domain": ".lloydslist.maritimeintelligence.informa.com",
                "path": "/",
            }
        ],
        "origins": [],
    }
    return auth_data


@pytest.fixture
def mock_article_html():
    """Provide sample article HTML for parsing."""
    return """
    <html>
        <head>
            <title>Test Article Title</title>
            <meta property="og:image" content="https://example.com/image.jpg">
            <meta name="author" content="John Doe">
            <meta property="article:published_time" content="2026-01-20T10:00:00Z">
        </head>
        <body>
            <article>
                <h1 class="article-title">Test Article Title</h1>
                <div class="article-body">
                    <p>This is the first paragraph of the article.</p>
                    <p>This is the second paragraph with more content.</p>
                    <p>And a third paragraph to make it substantial.</p>
                </div>
            </article>
        </body>
    </html>
    """


@pytest.fixture
def mock_paywalled_article_html():
    """Provide sample paywalled article HTML."""
    return """
    <html>
        <head>
            <title>Premium Article</title>
        </head>
        <body>
            <article>
                <h1>Premium Article Title</h1>
                <div class="article-body">
                    <p>This is a preview of the article...</p>
                    <div class="paywall">
                        <p>Sign in to continue reading</p>
                        <button>Subscribe Now</button>
                    </div>
                </div>
            </article>
        </body>
    </html>
    """


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
async def async_http_client():
    """Provide async HTTP client for testing."""
    async with AsyncClient() as client:
        yield client
