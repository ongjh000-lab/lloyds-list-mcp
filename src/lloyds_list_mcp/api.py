"""FastAPI wrapper for Lloyd's List MCP Server - Exposes MCP tools as HTTP/REST endpoints."""

import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import server as mcp_server
from .config import settings

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Lloyd's List MCP Server",
    description="Maritime intelligence API powered by Model Context Protocol",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================


class SearchArticlesRequest(BaseModel):
    """Request model for searching articles."""

    query: str = Field(..., description="Search keywords")
    sector: Optional[str] = Field(None, description="Optional sector filter")
    category: Optional[str] = Field(None, description="Optional category filter")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of results")


class GetLatestArticlesRequest(BaseModel):
    """Request model for getting latest articles."""

    feed_type: str = Field(..., description="Feed type: sectors, topics, or regulars")
    feed_name: str = Field(..., description="Specific feed name")
    limit: int = Field(10, ge=1, le=50, description="Number of articles to retrieve")


class GetArticleContentRequest(BaseModel):
    """Request model for fetching article content."""

    article_url: str = Field(..., description="Full URL of the article")
    user_session: Optional[str] = Field(None, description="Optional session token for paywalled content")


class AuthenticateRequest(BaseModel):
    """Request model for user authentication."""

    username: str = Field(..., description="Lloyd's List username/email")
    password: str = Field(..., description="Lloyd's List password")


class SummarizeArticlesRequest(BaseModel):
    """Request model for summarizing articles."""

    article_urls: List[str] = Field(..., description="List of article URLs to summarize")
    summary_length: str = Field("brief", description="Summary length: brief, detailed, or full")
    user_session: Optional[str] = Field(None, description="Optional session token for paywalled content")


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "Lloyd's List MCP Server",
        "version": "0.1.0",
        "description": "Maritime intelligence API via Model Context Protocol",
        "docs": "/docs",
        "endpoints": {
            "public": [
                "/api/search",
                "/api/latest",
                "/api/feeds",
            ],
            "authenticated": [
                "/api/article",
                "/api/auth/login",
                "/api/summarize",
            ],
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "environment": settings.environment}


# ============================================================================
# PUBLIC ENDPOINTS (No Authentication Required)
# ============================================================================


@app.post("/api/search")
async def search_articles(request: SearchArticlesRequest):
    """
    Search for articles by keyword across public RSS feeds.

    Returns articles with titles, URLs, summaries, and images from public feeds.
    No authentication required.
    """
    try:
        result_json = await mcp_server.search_articles(
            query=request.query,
            sector=request.sector,
            category=request.category,
            limit=request.limit,
        )

        import json
        result = json.loads(result_json)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Search failed"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in search endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@app.post("/api/latest")
async def get_latest_articles(request: GetLatestArticlesRequest):
    """
    Get the most recent articles from a specific RSS feed.

    Returns latest articles with titles, URLs, summaries, images, and metadata.
    No authentication required.
    """
    try:
        result_json = await mcp_server.get_latest_articles(
            feed_type=request.feed_type,
            feed_name=request.feed_name,
            limit=request.limit,
        )

        import json
        result = json.loads(result_json)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Invalid feed parameters"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in latest articles endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@app.get("/api/feeds")
async def list_available_feeds():
    """
    List all available RSS feeds by category.

    Returns complete list of Lloyd's List feeds organized by type:
    sectors, topics, and regulars. No authentication required.
    """
    try:
        result_json = await mcp_server.list_available_feeds()

        import json
        result = json.loads(result_json)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to list feeds"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in list feeds endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


# ============================================================================
# AUTHENTICATED ENDPOINTS (User Session Required for Paywalled Content)
# ============================================================================


@app.post("/api/article")
async def get_article_content(request: GetArticleContentRequest):
    """
    Fetch full article text with intelligent paywall detection.

    First attempts to fetch without authentication. If article is free to read,
    returns full content immediately. If paywalled, requires valid user session.

    Returns:
        - If free: Full article content
        - If paywalled + no session: authentication_required response
        - If paywalled + valid session: Full article content
    """
    try:
        result_json = await mcp_server.get_article_content(
            article_url=request.article_url,
            user_session=request.user_session,
        )

        import json
        result = json.loads(result_json)

        if result.get("status") == "authentication_required":
            return result  # Return as-is, client should prompt for login

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to fetch article"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in article content endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@app.post("/api/auth/login")
async def authenticate_user(request: AuthenticateRequest):
    """
    Authenticate a user with Lloyd's List and create a session.

    Handles user login via browser automation and returns session token
    for accessing paywalled content.

    Returns:
        Session token and expiration information
    """
    try:
        result_json = await mcp_server.authenticate_user(
            username=request.username,
            password=request.password,
        )

        import json
        result = json.loads(result_json)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result.get("message", "Authentication failed"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in authentication endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@app.post("/api/summarize")
async def summarize_articles(request: SummarizeArticlesRequest):
    """
    Generate summaries of one or more articles.

    Supports different summary lengths:
    - "brief": Uses public RSS summaries (no auth required)
    - "detailed": Requires full article access (auth needed if paywalled)
    - "full": Complete article summary (auth needed if paywalled)

    Returns:
        Summaries for each article or authentication_required for paywalled content
    """
    try:
        result_json = await mcp_server.summarize_articles(
            article_urls=request.article_urls,
            summary_length=request.summary_length,
            user_session=request.user_session,
        )

        import json
        result = json.loads(result_json)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to summarize articles"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in summarize endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize server components on startup."""
    logger.info(f"Starting Lloyd's List MCP Server (environment: {settings.environment})")
    logger.info(f"Server will listen on {settings.host}:{settings.port}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown."""
    logger.info("Shutting down Lloyd's List MCP Server...")
    await mcp_server.cleanup()
    logger.info("Server shutdown complete")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "lloyds_list_mcp.api:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
