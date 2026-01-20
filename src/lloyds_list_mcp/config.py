"""Configuration management for Lloyd's List MCP Server."""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    environment: Literal["development", "production"] = "development"

    # Cache Configuration
    cache_dir: str = ".cache"
    feed_cache_ttl: int = 300  # 5 minutes

    # Session Management
    session_store: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    session_ttl: int = 86400  # 24 hours
    session_secret_key: str = "dev-secret-key-change-in-production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = Settings()
