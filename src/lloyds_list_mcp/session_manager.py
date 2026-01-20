"""Session management for user authentication tokens."""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from .config import settings

logger = logging.getLogger(__name__)


class SessionStore(ABC):
    """Abstract base class for session storage."""

    @abstractmethod
    async def set(self, session_id: str, data: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store session data."""
        pass

    @abstractmethod
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data."""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Delete session data."""
        pass

    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        pass


class MemorySessionStore(SessionStore):
    """In-memory session storage (not suitable for production multi-instance deployments)."""

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._store: Dict[str, tuple[Dict[str, Any], float]] = {}
        self._lock = asyncio.Lock()

    async def set(self, session_id: str, data: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store session data with expiration."""
        ttl = ttl or settings.session_ttl
        expires_at = time.time() + ttl
        async with self._lock:
            self._store[session_id] = (data, expires_at)
        logger.debug(f"Session stored: {session_id} (expires in {ttl}s)")

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data if not expired."""
        async with self._lock:
            if session_id not in self._store:
                return None

            data, expires_at = self._store[session_id]

            # Check expiration
            if time.time() > expires_at:
                del self._store[session_id]
                logger.debug(f"Session expired: {session_id}")
                return None

            return data

    async def delete(self, session_id: str) -> None:
        """Delete session data."""
        async with self._lock:
            self._store.pop(session_id, None)
        logger.debug(f"Session deleted: {session_id}")

    async def exists(self, session_id: str) -> bool:
        """Check if session exists and is valid."""
        return await self.get(session_id) is not None

    async def cleanup(self) -> None:
        """Remove expired sessions."""
        async with self._lock:
            now = time.time()
            expired = [sid for sid, (_, exp) in self._store.items() if now > exp]
            for sid in expired:
                del self._store[sid]
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")


class RedisSessionStore(SessionStore):
    """Redis-based session storage for distributed deployments."""

    def __init__(self, redis_url: str) -> None:
        """Initialize Redis connection."""
        try:
            import redis.asyncio as aioredis

            self.redis_url = redis_url
            self.redis: Optional[aioredis.Redis] = None
        except ImportError:
            raise ImportError("redis package required for RedisSessionStore. Install with: pip install redis")

    async def _get_redis(self) -> Any:
        """Get or create Redis connection."""
        if self.redis is None:
            import redis.asyncio as aioredis

            self.redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self.redis

    async def set(self, session_id: str, data: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store session data in Redis with expiration."""
        redis = await self._get_redis()
        ttl = ttl or settings.session_ttl
        key = f"session:{session_id}"
        await redis.setex(key, ttl, json.dumps(data))
        logger.debug(f"Session stored in Redis: {session_id} (expires in {ttl}s)")

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data from Redis."""
        redis = await self._get_redis()
        key = f"session:{session_id}"
        data = await redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def delete(self, session_id: str) -> None:
        """Delete session data from Redis."""
        redis = await self._get_redis()
        key = f"session:{session_id}"
        await redis.delete(key)
        logger.debug(f"Session deleted from Redis: {session_id}")

    async def exists(self, session_id: str) -> bool:
        """Check if session exists in Redis."""
        redis = await self._get_redis()
        key = f"session:{session_id}"
        return await redis.exists(key) > 0

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.aclose()


class SessionManager:
    """Manages user sessions with encryption and storage."""

    def __init__(self) -> None:
        """Initialize session manager with configured storage backend."""
        # Initialize encryption
        secret_key = settings.session_secret_key.encode()
        # Ensure key is valid Fernet key (32 url-safe base64-encoded bytes)
        if len(secret_key) < 32:
            # Pad with zeros if too short (for dev only)
            secret_key = secret_key.ljust(32, b"0")
        # Generate proper Fernet key from secret
        import base64
        key = base64.urlsafe_b64encode(secret_key[:32])
        self.cipher = Fernet(key)

        # Initialize storage backend
        if settings.session_store == "redis":
            self.store: SessionStore = RedisSessionStore(settings.redis_url)
        else:
            self.store = MemorySessionStore()

        logger.info(f"Session manager initialized with {settings.session_store} storage")

    async def create_session(
        self,
        user_id: str,
        playwright_session: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> str:
        """Create a new encrypted session and return session ID."""
        import secrets

        session_id = secrets.token_urlsafe(32)

        # Store session data
        session_data = {
            "user_id": user_id,
            "created_at": time.time(),
            "playwright_session": playwright_session,
        }

        # Encrypt sensitive data (playwright session)
        encrypted_session = self.cipher.encrypt(json.dumps(playwright_session).encode())
        session_data["playwright_session"] = encrypted_session.decode()

        await self.store.set(session_id, session_data, ttl=ttl)

        logger.info(f"Created session for user: {user_id}")
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt session data."""
        session_data = await self.store.get(session_id)
        if not session_data:
            return None

        # Decrypt playwright session
        try:
            encrypted_session = session_data["playwright_session"].encode()
            decrypted = self.cipher.decrypt(encrypted_session)
            session_data["playwright_session"] = json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt session {session_id}: {e}")
            await self.store.delete(session_id)
            return None

        return session_data

    async def validate_session(self, session_id: str) -> bool:
        """Check if session exists and is valid."""
        return await self.store.exists(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        await self.store.delete(session_id)
        logger.info(f"Deleted session: {session_id}")

    async def close(self) -> None:
        """Close storage backend connections."""
        if hasattr(self.store, "close"):
            await self.store.close()
