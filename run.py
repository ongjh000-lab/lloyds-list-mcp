#!/usr/bin/env python3
"""Simple script to run the Lloyd's List MCP Server."""

import uvicorn

from src.lloyds_list_mcp.config import settings

if __name__ == "__main__":
    print(f"Starting Lloyd's List MCP Server on {settings.host}:{settings.port}")
    print(f"Environment: {settings.environment}")
    print(f"API docs: http://{settings.host}:{settings.port}/docs")
    print("-" * 60)

    uvicorn.run(
        "src.lloyds_list_mcp.api:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
