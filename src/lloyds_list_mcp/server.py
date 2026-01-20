"""Lloyd's List MCP Server - Maritime intelligence via Model Context Protocol."""

import logging
from typing import Any, Dict, List, Optional

from mcp_use.server import MCPServer, Context

from .article_fetcher import ArticleFetcher
from .authenticator import LloydsListAuthenticator, AuthenticationError
from .config import settings
from .rss_parser import RSSFeedManager
from .session_manager import SessionManager

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize MCP server
server = MCPServer(name="lloyds-list-mcp")

# Initialize components (will be done lazily)
rss_manager: Optional[RSSFeedManager] = None
session_manager: Optional[SessionManager] = None
authenticator: Optional[LloydsListAuthenticator] = None
article_fetcher: Optional[ArticleFetcher] = None


def get_rss_manager() -> RSSFeedManager:
    """Get or create RSS manager instance."""
    global rss_manager
    if rss_manager is None:
        rss_manager = RSSFeedManager()
        logger.info("RSS manager initialized")
    return rss_manager


def get_session_manager() -> SessionManager:
    """Get or create session manager instance."""
    global session_manager
    if session_manager is None:
        session_manager = SessionManager()
        logger.info("Session manager initialized")
    return session_manager


def get_authenticator() -> LloydsListAuthenticator:
    """Get or create authenticator instance."""
    global authenticator
    if authenticator is None:
        authenticator = LloydsListAuthenticator()
        logger.info("Authenticator initialized")
    return authenticator


def get_article_fetcher() -> ArticleFetcher:
    """Get or create article fetcher instance."""
    global article_fetcher
    if article_fetcher is None:
        article_fetcher = ArticleFetcher()
        logger.info("Article fetcher initialized")
    return article_fetcher


# ============================================================================
# TIER 1: PUBLIC TOOLS (No Authentication Required)
# ============================================================================


@server.tool()
async def search_articles(
    query: str,
    sector: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> str:
    """
    Search for articles by keyword across public RSS feeds.

    Searches Lloyd's List RSS feeds for articles matching the query.
    Results include titles, URLs, summaries, and images from public feeds.

    Args:
        query: Search keywords to match against article titles/summaries
        sector: Optional sector filter (Containers, Dry Bulk, Tankers & Gas, etc.)
        category: Optional category filter (Decarbonisation, Red Sea Risk, etc.)
        limit: Maximum number of results to return (default: 10)

    Returns:
        JSON string with list of matching articles including images
    """
    import json

    logger.info(f"Searching articles: query='{query}', sector={sector}, category={category}, limit={limit}")

    try:
        manager = get_rss_manager()
        results = await manager.search_articles(
            query=query,
            sector=sector,
            category=category,
            limit=limit,
        )

        response = {
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results,
        }

        return json.dumps(response, indent=2, default=str)

    except Exception as e:
        logger.error(f"Error searching articles: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to search articles: {str(e)}",
        })


@server.tool()
async def get_latest_articles(
    feed_type: str,
    feed_name: str,
    limit: int = 10,
) -> str:
    """
    Get the most recent articles from a specific RSS feed.

    Retrieves latest articles from Lloyd's List public RSS feeds.
    Includes titles, URLs, summaries, images, and metadata.

    Args:
        feed_type: Type of feed - "sectors", "topics", or "regulars"
        feed_name: Specific feed name (e.g., "Containers", "Decarbonisation", "Daily Briefing")
        limit: Number of articles to retrieve (default: 10)

    Returns:
        JSON string with list of recent articles including images
    """
    import json

    logger.info(f"Getting latest articles: feed_type={feed_type}, feed_name={feed_name}, limit={limit}")

    try:
        manager = get_rss_manager()
        results = await manager.get_latest_articles(
            feed_type=feed_type,
            feed_name=feed_name,
            limit=limit,
        )

        response = {
            "status": "success",
            "feed_type": feed_type,
            "feed_name": feed_name,
            "count": len(results),
            "results": results,
        }

        return json.dumps(response, indent=2, default=str)

    except ValueError as e:
        logger.error(f"Invalid feed parameters: {e}")
        return json.dumps({
            "status": "error",
            "message": str(e),
        })
    except Exception as e:
        logger.error(f"Error getting latest articles: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to get articles: {str(e)}",
        })


@server.tool()
async def list_available_feeds() -> str:
    """
    List all available RSS feeds by category.

    Returns the complete list of Lloyd's List RSS feeds organized by type:
    - sectors: Container shipping, dry bulk, tankers, etc.
    - topics: Decarbonisation, sanctions, Ukraine crisis, etc.
    - regulars: Daily briefing, podcasts, special reports, etc.

    Returns:
        JSON string with categorized list of available feeds
    """
    import json

    logger.info("Listing available feeds")

    try:
        manager = get_rss_manager()
        feeds = manager.list_available_feeds()

        response = {
            "status": "success",
            "feeds": feeds,
        }

        return json.dumps(response, indent=2)

    except Exception as e:
        logger.error(f"Error listing feeds: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to list feeds: {str(e)}",
        })


# ============================================================================
# TIER 2: AUTHENTICATED TOOLS (User Session Required)
# ============================================================================


@server.tool()
async def get_article_content(
    article_url: str,
    user_session: Optional[str] = None,
) -> str:
    """
    Fetch full article text with intelligent paywall detection.

    First attempts to fetch without authentication. If article is free to read,
    returns full content immediately. If paywalled, requires valid user session.

    Args:
        article_url: Full URL of the Lloyd's List article
        user_session: Optional user authentication session token (only needed if paywalled)

    Returns:
        JSON string with article content or authentication_required status
    """
    import json

    logger.info(f"Fetching article: {article_url}, has_session={bool(user_session)}")

    try:
        fetcher = get_article_fetcher()

        # Get storage state if session provided
        storage_state = None
        if user_session:
            sess_mgr = get_session_manager()
            session_data = await sess_mgr.get_session(user_session)
            if session_data:
                storage_state = session_data.get("playwright_session")
            else:
                return json.dumps({
                    "status": "error",
                    "message": "Invalid or expired session",
                })

        # Fetch article (will detect paywall and handle accordingly)
        result = await fetcher.fetch_article(article_url, storage_state)

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error(f"Error fetching article content: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to fetch article: {str(e)}",
        })


@server.tool()
async def authenticate_user(username: str, password: str) -> str:
    """
    Authenticate a user with Lloyd's List and create a session.

    This tool handles user login via Playwright browser automation and
    returns a session token for accessing paywalled content.

    Args:
        username: Lloyd's List username/email
        password: Lloyd's List password

    Returns:
        JSON string with session token or error message
    """
    import json

    logger.info(f"Authenticating user: {username}")

    try:
        auth = get_authenticator()
        await auth.initialize()

        # Authenticate and get storage state
        storage_state = await auth.authenticate(username, password)

        # Create session
        sess_mgr = get_session_manager()
        session_id = await sess_mgr.create_session(
            user_id=username,
            playwright_session=storage_state,
        )

        response = {
            "status": "success",
            "message": "Authentication successful",
            "session_token": session_id,
            "expires_in": settings.session_ttl,
        }

        return json.dumps(response, indent=2)

    except AuthenticationError as e:
        logger.error(f"Authentication failed for {username}: {e}")
        return json.dumps({
            "status": "error",
            "message": str(e),
        })
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Authentication failed: {str(e)}",
        })


@server.tool()
async def summarize_articles(
    article_urls: List[str],
    summary_length: str = "brief",
    user_session: Optional[str] = None,
) -> str:
    """
    Generate summaries of one or more articles.

    Supports different summary lengths:
    - "brief": Uses public RSS summaries (no auth required)
    - "detailed": Requires full article access (auth needed if paywalled)
    - "full": Complete article summary (auth needed if paywalled)

    Args:
        article_urls: List of article URLs to summarize
        summary_length: Summary length - "brief", "detailed", or "full" (default: "brief")
        user_session: User session token (required for detailed/full summaries of paywalled content)

    Returns:
        JSON string with summaries for each article
    """
    import json

    logger.info(f"Summarizing {len(article_urls)} articles, length={summary_length}")

    try:
        summaries = []

        if summary_length == "brief":
            # Use RSS summaries - no auth needed
            manager = get_rss_manager()
            all_feeds = await manager.get_all_feeds()

            for url in article_urls:
                # Find article in feeds
                found = False
                for feed_data in all_feeds.values():
                    for entry in feed_data.get("entries", []):
                        if entry["url"] == url:
                            summaries.append({
                                "url": url,
                                "title": entry["title"],
                                "summary": entry["summary"],
                                "length": "brief",
                            })
                            found = True
                            break
                    if found:
                        break

                if not found:
                    summaries.append({
                        "url": url,
                        "status": "not_found",
                        "message": "Article not found in RSS feeds",
                    })

        else:
            # Detailed/full summaries require full article access
            fetcher = get_article_fetcher()

            # Get storage state if session provided
            storage_state = None
            if user_session:
                sess_mgr = get_session_manager()
                session_data = await sess_mgr.get_session(user_session)
                if session_data:
                    storage_state = session_data.get("playwright_session")

            for url in article_urls:
                article_data = await fetcher.fetch_article(url, storage_state)

                if article_data.get("status") == "authentication_required":
                    summaries.append({
                        "url": url,
                        "status": "authentication_required",
                        "message": article_data.get("message"),
                    })
                elif article_data.get("status") == "success":
                    # Generate summary from full text
                    full_text = article_data.get("full_text", "")
                    if summary_length == "detailed":
                        # First 500 chars
                        summary_text = full_text[:500] + ("..." if len(full_text) > 500 else "")
                    else:  # full
                        summary_text = full_text

                    summaries.append({
                        "url": url,
                        "title": article_data.get("title"),
                        "summary": summary_text,
                        "length": summary_length,
                        "author": article_data.get("author"),
                        "date": article_data.get("date"),
                    })
                else:
                    summaries.append({
                        "url": url,
                        "status": "error",
                        "message": article_data.get("message", "Failed to fetch article"),
                    })

        response = {
            "status": "success",
            "count": len(summaries),
            "summaries": summaries,
        }

        return json.dumps(response, indent=2, default=str)

    except Exception as e:
        logger.error(f"Error summarizing articles: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to summarize articles: {str(e)}",
        })


# Cleanup on server shutdown
@server.on_shutdown
async def cleanup() -> None:
    """Cleanup resources on server shutdown."""
    logger.info("Shutting down server, cleaning up resources...")

    if rss_manager:
        await rss_manager.close()
    if session_manager:
        await session_manager.close()
    if authenticator:
        await authenticator.close()
    if article_fetcher:
        await article_fetcher.close()

    logger.info("Server shutdown complete")
