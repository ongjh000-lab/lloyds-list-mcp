"""RSS feed parser for Lloyd's List with caching and image extraction."""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup

from .config import settings

logger = logging.getLogger(__name__)


class RSSFeedManager:
    """Manages Lloyd's List RSS feeds with caching and image extraction."""

    # Lloyd's List RSS feed mapping
    FEEDS = {
        "sectors": {
            "Containers": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/containers",
            "Dry Bulk": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/dry-bulk",
            "Tankers & Gas": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/tankers-gas",
            "Ports & Logistics": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/ports-logistics",
            "Technology & Innovation": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/technology-innovation",
            "Finance": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/finance",
            "Insurance": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/insurance",
            "Law & Regulation": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/law-regulation",
            "Safety": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/safety",
            "Crew Welfare": "https://lloydslist.maritimeintelligence.informa.com/rss/sectors/crew-welfare",
        },
        "topics": {
            "Red Sea Risk": "https://lloydslist.maritimeintelligence.informa.com/rss/topics/red-sea-risk",
            "Ukraine Crisis": "https://lloydslist.maritimeintelligence.informa.com/rss/topics/ukraine-crisis",
            "Decarbonisation": "https://lloydslist.maritimeintelligence.informa.com/rss/topics/decarbonisation",
            "Sanctions": "https://lloydslist.maritimeintelligence.informa.com/rss/topics/sanctions",
            "Digitalisation": "https://lloydslist.maritimeintelligence.informa.com/rss/topics/digitalisation",
            "Piracy & Security": "https://lloydslist.maritimeintelligence.informa.com/rss/topics/piracy-security",
        },
        "regulars": {
            "Daily Briefing": "https://lloydslist.maritimeintelligence.informa.com/rss/daily-briefing",
            "The View": "https://lloydslist.maritimeintelligence.informa.com/rss/the-view",
            "Special Reports": "https://lloydslist.maritimeintelligence.informa.com/rss/special-reports",
            "Podcasts & Video": "https://lloydslist.maritimeintelligence.informa.com/rss/podcasts-video",
        },
    }

    def __init__(self) -> None:
        """Initialize RSS feed manager with cache directory."""
        self.cache_dir = Path(settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = settings.feed_cache_ttl
        self.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    def _get_cache_path(self, url: str) -> Path:
        """Generate cache file path for a feed URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"feed_{url_hash}.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached feed is still valid (within TTL)."""
        if not cache_path.exists():
            return False
        cache_age = time.time() - cache_path.stat().st_mtime
        return cache_age < self.cache_ttl

    async def _fetch_feed(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        """Fetch RSS feed with optional caching."""
        cache_path = self._get_cache_path(url)

        # Try cache first if enabled
        if use_cache and self._is_cache_valid(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                logger.debug(f"Using cached feed: {url}")
                return cached_data
            except Exception as e:
                logger.warning(f"Cache read error for {url}: {e}")

        # Fetch fresh feed
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            feed_content = response.text

            # Parse with feedparser
            feed = feedparser.parse(feed_content)

            if feed.bozo:  # feedparser detected malformed XML
                logger.warning(f"Malformed feed detected: {url}")

            feed_data = {
                "feed": {
                    "title": feed.feed.get("title", ""),
                    "link": feed.feed.get("link", ""),
                    "description": feed.feed.get("description", ""),
                    "updated": feed.feed.get("updated", ""),
                },
                "entries": [self._parse_entry(entry) for entry in feed.entries],
                "fetched_at": time.time(),
            }

            # Save to cache
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(feed_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Cache write error for {url}: {e}")

            logger.info(f"Fetched feed: {url} ({len(feed_data['entries'])} entries)")
            return feed_data

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching feed {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching feed {url}: {e}")
            raise

    def _parse_entry(self, entry: Any) -> Dict[str, Any]:
        """Parse a feed entry and extract metadata including images."""
        # Extract basic metadata
        article_data = {
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "date": entry.get("published", entry.get("updated", "")),
            "summary": self._clean_summary(entry.get("summary", entry.get("description", ""))),
            "author": entry.get("author", None),
            "tags": self._extract_tags(entry),
            "image_url": self._extract_image(entry),
        }

        return article_data

    def _clean_summary(self, summary: str) -> str:
        """Clean HTML from summary and extract plain text."""
        if not summary:
            return ""
        soup = BeautifulSoup(summary, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # Limit to ~2 sentences (roughly 200 chars)
        if len(text) > 200:
            text = text[:197] + "..."
        return text

    def _extract_tags(self, entry: Any) -> List[str]:
        """Extract tags/categories from feed entry."""
        tags = []
        if hasattr(entry, "tags"):
            tags = [tag.get("term", "") for tag in entry.tags if tag.get("term")]
        elif hasattr(entry, "categories"):
            tags = list(entry.categories)
        return tags

    def _extract_image(self, entry: Any) -> Optional[str]:
        """Extract featured image URL from feed entry."""
        # Try media:content (common in RSS 2.0)
        if hasattr(entry, "media_content") and entry.media_content:
            for media in entry.media_content:
                if media.get("medium") == "image" or "image" in media.get("type", ""):
                    return media.get("url")

        # Try enclosures
        if hasattr(entry, "enclosures") and entry.enclosures:
            for enclosure in entry.enclosures:
                if "image" in enclosure.get("type", ""):
                    return enclosure.get("href")

        # Try media:thumbnail
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            return entry.media_thumbnail[0].get("url")

        # Try to extract from summary/description HTML
        summary_html = entry.get("summary", entry.get("description", ""))
        if summary_html:
            soup = BeautifulSoup(summary_html, "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                # Make absolute URL if relative
                img_url = img.get("src")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    base_url = entry.get("link", "https://lloydslist.maritimeintelligence.informa.com")
                    img_url = urljoin(base_url, img_url)
                return img_url

        return None

    async def get_feed(
        self, feed_type: str, feed_name: str, use_cache: bool = True
    ) -> Dict[str, Any]:
        """Get a specific RSS feed by type and name."""
        if feed_type not in self.FEEDS:
            raise ValueError(f"Invalid feed type: {feed_type}. Must be one of {list(self.FEEDS.keys())}")

        if feed_name not in self.FEEDS[feed_type]:
            available = list(self.FEEDS[feed_type].keys())
            raise ValueError(f"Invalid feed name: {feed_name}. Available: {available}")

        url = self.FEEDS[feed_type][feed_name]
        return await self._fetch_feed(url, use_cache=use_cache)

    async def get_all_feeds(self, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
        """Fetch all RSS feeds concurrently."""
        tasks = []
        feed_keys = []

        for feed_type, feeds in self.FEEDS.items():
            for feed_name, url in feeds.items():
                tasks.append(self._fetch_feed(url, use_cache=use_cache))
                feed_keys.append((feed_type, feed_name))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_feeds = {}
        for (feed_type, feed_name), result in zip(feed_keys, results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching {feed_type}/{feed_name}: {result}")
                continue
            key = f"{feed_type}/{feed_name}"
            all_feeds[key] = result

        return all_feeds

    async def search_articles(
        self,
        query: str,
        sector: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for articles across RSS feeds."""
        query_lower = query.lower()
        results = []

        # Determine which feeds to search
        feeds_to_search = []
        if sector:
            if sector in self.FEEDS["sectors"]:
                feeds_to_search.append(("sectors", sector))
        elif category:
            if category in self.FEEDS["topics"]:
                feeds_to_search.append(("topics", category))
        else:
            # Search all feeds
            for feed_type, feeds in self.FEEDS.items():
                for feed_name in feeds.keys():
                    feeds_to_search.append((feed_type, feed_name))

        # Fetch and search feeds
        for feed_type, feed_name in feeds_to_search:
            try:
                feed_data = await self.get_feed(feed_type, feed_name)
                for entry in feed_data["entries"]:
                    # Search in title and summary
                    title_match = query_lower in entry["title"].lower()
                    summary_match = query_lower in entry["summary"].lower()

                    if title_match or summary_match:
                        results.append(entry)

                        if len(results) >= limit:
                            return results[:limit]
            except Exception as e:
                logger.error(f"Error searching feed {feed_type}/{feed_name}: {e}")
                continue

        return results[:limit]

    async def get_latest_articles(
        self, feed_type: str, feed_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get the latest articles from a specific feed."""
        feed_data = await self.get_feed(feed_type, feed_name)
        return feed_data["entries"][:limit]

    def list_available_feeds(self) -> Dict[str, List[str]]:
        """List all available RSS feeds by category."""
        return {feed_type: list(feeds.keys()) for feed_type, feeds in self.FEEDS.items()}

    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()
