"""Tests for article content fetcher."""

import pytest
from unittest.mock import AsyncMock, patch

from src.lloyds_list_mcp.article_fetcher import ArticleFetcher


@pytest.mark.asyncio
async def test_detect_paywall_free_article(mock_article_html):
    """Test paywall detection on free article."""
    fetcher = ArticleFetcher()

    is_paywalled, reason = fetcher._detect_paywall(mock_article_html)

    assert not is_paywalled
    assert reason is None


@pytest.mark.asyncio
async def test_detect_paywall_paywalled_article(mock_paywalled_article_html):
    """Test paywall detection on paywalled article."""
    fetcher = ArticleFetcher()

    is_paywalled, reason = fetcher._detect_paywall(mock_paywalled_article_html)

    assert is_paywalled
    assert reason is not None
    assert "paywall" in reason.lower() or "sign in" in reason.lower()


@pytest.mark.asyncio
async def test_extract_article_content(mock_article_html):
    """Test article content extraction."""
    fetcher = ArticleFetcher()

    url = "https://example.com/article"
    article_data = fetcher._extract_article_content(mock_article_html, url)

    assert article_data["title"] == "Test Article Title"
    assert "first paragraph" in article_data["full_text"]
    assert article_data["author"] == "John Doe"
    assert article_data["url"] == url


@pytest.mark.asyncio
async def test_extract_images(mock_article_html):
    """Test image extraction from article."""
    fetcher = ArticleFetcher()

    url = "https://example.com/article"
    article_data = fetcher._extract_article_content(mock_article_html, url)

    assert len(article_data["images"]) > 0
    assert article_data["images"][0]["url"] == "https://example.com/image.jpg"
