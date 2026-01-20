"""Article content extraction with paywall detection and authentication."""

import logging
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ArticleFetcher:
    """Fetches and extracts article content from Lloyd's List."""

    PAYWALL_INDICATORS = [
        # CSS classes that indicate paywalled content
        "paywall",
        "subscriber-only",
        "restricted-content",
        "premium-content",
        "subscription-required",
        # Text patterns
        "sign in to continue",
        "subscribe to read",
        "subscription required",
        "become a subscriber",
        "log in to view",
    ]

    def __init__(self) -> None:
        """Initialize article fetcher."""
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
        )

    async def fetch_article(
        self,
        url: str,
        storage_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch article with intelligent paywall detection.

        First attempts to fetch without authentication. If paywall detected,
        requires authentication via storage_state.

        Args:
            url: Article URL
            storage_state: Optional Playwright storage state for authenticated requests

        Returns:
            Dictionary with article data or paywall status
        """
        # Step 1: Try to fetch without authentication
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            html_content = response.text

            # Check for paywall
            is_paywalled, paywall_reason = self._detect_paywall(html_content)

            if not is_paywalled:
                # Free to read - extract and return content
                article_data = self._extract_article_content(html_content, url)
                article_data["paywall"] = False
                article_data["status"] = "success"
                logger.info(f"Successfully fetched free article: {url}")
                return article_data

            # Paywalled content detected
            logger.info(f"Paywall detected on {url}: {paywall_reason}")

            if not storage_state:
                # No authentication provided
                return {
                    "status": "authentication_required",
                    "paywall": True,
                    "message": "This article requires a Lloyd's List subscription",
                    "url": url,
                    "reason": paywall_reason,
                }

            # Step 2: Fetch with authentication
            return await self._fetch_authenticated(url, storage_state)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching article {url}: {e}")
            return {
                "status": "error",
                "message": f"Failed to fetch article: {str(e)}",
                "url": url,
            }
        except Exception as e:
            logger.error(f"Error fetching article {url}: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
                "url": url,
            }

    def _detect_paywall(self, html_content: str) -> tuple[bool, Optional[str]]:
        """
        Detect if article is behind a paywall.

        Returns:
            (is_paywalled, reason)
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Check for paywall CSS classes
        for indicator in self.PAYWALL_INDICATORS:
            if "class" in indicator or "-" in indicator:
                # CSS class check
                elements = soup.find_all(class_=lambda x: x and indicator in x.lower())
                if elements:
                    return True, f"Found paywall class: {indicator}"

        # Check for paywall text in content
        text_content = soup.get_text().lower()
        for indicator in self.PAYWALL_INDICATORS:
            if " " in indicator:  # Text pattern
                if indicator in text_content:
                    return True, f"Found paywall text: {indicator}"

        # Check for truncated content indicators
        truncation_indicators = [
            "continue reading",
            "read more",
            "view full article",
            "full story available to subscribers",
        ]
        for indicator in truncation_indicators:
            if indicator in text_content:
                # Check if article seems short (likely truncated)
                article_body = soup.find("article") or soup.find(class_=lambda x: x and "article" in str(x).lower())
                if article_body:
                    body_text = article_body.get_text(strip=True)
                    if len(body_text) < 500:  # Suspiciously short
                        return True, f"Truncated content detected: {indicator}"

        # Check for login/subscribe buttons
        buttons = soup.find_all(["button", "a"])
        for button in buttons:
            button_text = button.get_text().lower()
            if any(x in button_text for x in ["sign in", "log in", "subscribe", "become a member"]):
                # Check if it's a prominent CTA (not just header/footer)
                parent = button.find_parent(["main", "article", "div"])
                if parent and "header" not in str(parent.get("class", [])).lower():
                    return True, "Sign in/Subscribe button found in content area"

        return False, None

    async def _fetch_authenticated(
        self,
        url: str,
        storage_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fetch article using authenticated session."""
        try:
            # Extract cookies from Playwright storage state
            cookies = {}
            if "cookies" in storage_state:
                for cookie in storage_state["cookies"]:
                    cookies[cookie["name"]] = cookie["value"]

            # Fetch with cookies
            response = await self.http_client.get(url, cookies=cookies)
            response.raise_for_status()
            html_content = response.text

            # Extract content
            article_data = self._extract_article_content(html_content, url)
            article_data["paywall"] = True
            article_data["status"] = "success"

            logger.info(f"Successfully fetched authenticated article: {url}")
            return article_data

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching authenticated article {url}: {e}")
            return {
                "status": "error",
                "message": f"Failed to fetch authenticated article: {str(e)}",
                "url": url,
            }

    def _extract_article_content(self, html_content: str, url: str) -> Dict[str, Any]:
        """Extract article content from HTML."""
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract title
        title = self._extract_title(soup)

        # Extract main article body
        body_text = self._extract_body(soup)

        # Extract metadata
        author = self._extract_author(soup)
        date = self._extract_date(soup)
        tags = self._extract_tags(soup)
        images = self._extract_images(soup, url)

        return {
            "url": url,
            "title": title,
            "full_text": body_text,
            "author": author,
            "date": date,
            "tags": tags,
            "images": images,
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title."""
        # Try various title selectors
        title_selectors = [
            "h1.article-title",
            "h1[class*='title']",
            "article h1",
            ".article-header h1",
            "h1",
        ]

        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)

        # Fallback to page title
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)

        return "Untitled Article"

    def _extract_body(self, soup: BeautifulSoup) -> str:
        """Extract main article body text."""
        # Try various article body selectors
        body_selectors = [
            "article .article-body",
            ".article-content",
            "[class*='article-text']",
            "article",
            "main",
        ]

        for selector in body_selectors:
            element = soup.select_one(selector)
            if element:
                # Remove script and style tags
                for tag in element.find_all(["script", "style"]):
                    tag.decompose()

                # Extract text
                paragraphs = element.find_all("p")
                if paragraphs:
                    text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    if len(text) > 100:  # Ensure we got substantial content
                        return text

                # Fallback to all text
                text = element.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    return text

        return "Article content could not be extracted"

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article author."""
        # Try meta tag
        author_meta = soup.find("meta", {"name": "author"}) or soup.find("meta", {"property": "article:author"})
        if author_meta and author_meta.get("content"):
            return author_meta["content"]

        # Try CSS selectors
        author_selectors = [
            ".article-author",
            "[class*='author']",
            "[rel='author']",
        ]

        for selector in author_selectors:
            element = soup.select_one(selector)
            if element:
                author_text = element.get_text(strip=True)
                # Remove "By " prefix if present
                author_text = author_text.replace("By ", "").replace("by ", "")
                return author_text

        return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date."""
        # Try meta tags
        date_meta = (
            soup.find("meta", {"property": "article:published_time"})
            or soup.find("meta", {"name": "publish-date"})
            or soup.find("meta", {"name": "date"})
        )
        if date_meta and date_meta.get("content"):
            return date_meta["content"]

        # Try time tag
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            return time_tag["datetime"]

        return None

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """Extract article tags/categories."""
        tags = []

        # Try meta keywords
        keywords_meta = soup.find("meta", {"name": "keywords"})
        if keywords_meta and keywords_meta.get("content"):
            tags.extend([t.strip() for t in keywords_meta["content"].split(",") if t.strip()])

        # Try article tags/categories
        tag_elements = soup.select(".article-tags a, .tags a, [class*='category'] a")
        for elem in tag_elements:
            tag_text = elem.get_text(strip=True)
            if tag_text and tag_text not in tags:
                tags.append(tag_text)

        return tags

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """Extract article images."""
        images = []

        # Try Open Graph image
        og_image = soup.find("meta", {"property": "og:image"})
        if og_image and og_image.get("content"):
            images.append({"url": og_image["content"], "caption": "Featured image"})

        # Try article images
        article = soup.find("article") or soup.find("main")
        if article:
            for img in article.find_all("img"):
                img_url = img.get("src") or img.get("data-src")
                if img_url:
                    # Make absolute URL
                    if img_url.startswith("//"):
                        img_url = "https:" + img_url
                    elif img_url.startswith("/"):
                        from urllib.parse import urljoin
                        img_url = urljoin(base_url, img_url)

                    caption = img.get("alt", "") or img.get("title", "")
                    images.append({"url": img_url, "caption": caption})

        return images

    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()
