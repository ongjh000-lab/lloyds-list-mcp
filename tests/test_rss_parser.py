"""Tests for RSS feed parser."""

import pytest
from unittest.mock import AsyncMock, patch

from src.lloyds_list_mcp.rss_parser import RSSFeedManager


@pytest.mark.asyncio
async def test_list_available_feeds():
    """Test listing available RSS feeds."""
    manager = RSSFeedManager()
    feeds = manager.list_available_feeds()

    assert "sectors" in feeds
    assert "topics" in feeds
    assert "regulars" in feeds

    assert "Containers" in feeds["sectors"]
    assert "Decarbonisation" in feeds["topics"]
    assert "Daily Briefing" in feeds["regulars"]


@pytest.mark.asyncio
async def test_parse_entry_with_image(mock_rss_feed):
    """Test parsing RSS entry with image extraction."""
    manager = RSSFeedManager()

    entry = mock_rss_feed["entries"][0]
    assert entry["title"] == "Container rates surge in Q1 2026"
    assert entry["image_url"] is not None
    assert "lloydslist" in entry["url"]


@pytest.mark.asyncio
async def test_search_articles_no_results(mock_rss_feed):
    """Test search with no matching articles."""
    manager = RSSFeedManager()

    # Mock the get_all_feeds method
    with patch.object(manager, "get_all_feeds", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"sectors/Containers": mock_rss_feed}

        results = await manager.search_articles(query="nonexistent term", limit=10)

        assert len(results) == 0


@pytest.mark.asyncio
async def test_cache_validation(temp_cache_dir):
    """Test cache TTL validation."""
    manager = RSSFeedManager()
    manager.cache_dir = temp_cache_dir

    url = "https://example.com/feed.xml"
    cache_path = manager._get_cache_path(url)

    # Initially no cache
    assert not manager._is_cache_valid(cache_path)

    # Create cache file
    cache_path.write_text('{"test": "data"}')

    # Should be valid now
    assert manager._is_cache_valid(cache_path)
