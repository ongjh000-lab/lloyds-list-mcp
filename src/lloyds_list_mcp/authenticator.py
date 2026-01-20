"""Playwright-based authentication for Lloyd's List."""

import logging
from typing import Any, Dict, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class LloydsListAuthenticator:
    """Handles authentication to Lloyd's List using Playwright."""

    LOGIN_URL = "https://lloydslist.maritimeintelligence.informa.com/user/login"

    def __init__(self) -> None:
        """Initialize authenticator."""
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Any] = None

    async def initialize(self) -> None:
        """Initialize Playwright browser."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            logger.info("Playwright browser initialized")

    async def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and return Playwright storage state.

        Args:
            username: Lloyd's List username/email
            password: Lloyd's List password

        Returns:
            Dictionary containing storage state (cookies, localStorage)

        Raises:
            AuthenticationError: If login fails
        """
        if not self.browser:
            await self.initialize()

        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        try:
            # Create new context
            context = await self.browser.new_context()
            page = await context.new_page()

            logger.info(f"Authenticating user: {username}")

            # Navigate to login page
            await page.goto(self.LOGIN_URL, wait_until="networkidle", timeout=30000)

            # Fill in credentials
            # Note: Selectors may need adjustment based on actual Lloyd's List login form
            await page.fill('input[name="email"], input[type="email"], input#email', username)
            await page.fill('input[name="password"], input[type="password"], input#password', password)

            # Submit form
            await page.click('button[type="submit"], input[type="submit"], button:has-text("Sign In")')

            # Wait for navigation after login
            try:
                await page.wait_for_url("**/dashboard", timeout=15000)
                logger.info("Login successful - redirected to dashboard")
            except Exception:
                # Alternative: check if we're no longer on login page
                current_url = page.url
                if "login" in current_url.lower():
                    # Still on login page - likely failed
                    error_msg = await self._check_for_error_message(page)
                    raise AuthenticationError(f"Login failed: {error_msg}")
                logger.info(f"Login successful - navigated to: {current_url}")

            # Extract storage state (cookies, localStorage, sessionStorage)
            storage_state = await context.storage_state()

            logger.info(f"Successfully authenticated user: {username}")
            return storage_state

        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise AuthenticationError(f"Failed to authenticate: {str(e)}")
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def _check_for_error_message(self, page: Page) -> str:
        """Check for error messages on login page."""
        try:
            # Common error message selectors
            error_selectors = [
                ".error-message",
                ".alert-danger",
                "[role='alert']",
                ".login-error",
                "[class*='error']",
            ]

            for selector in error_selectors:
                element = await page.query_selector(selector)
                if element:
                    error_text = await element.inner_text()
                    if error_text:
                        return error_text.strip()

            return "Invalid credentials or login failed"
        except Exception:
            return "Unknown authentication error"

    async def verify_session(self, storage_state: Dict[str, Any]) -> bool:
        """
        Verify that a stored session is still valid.

        Args:
            storage_state: Playwright storage state from previous authentication

        Returns:
            True if session is valid, False otherwise
        """
        if not self.browser:
            await self.initialize()

        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        try:
            # Create context with stored session
            context = await self.browser.new_context(storage_state=storage_state)
            page = await context.new_page()

            # Try to access a protected page
            test_url = "https://lloydslist.maritimeintelligence.informa.com"
            await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)

            # Check if we're redirected to login (session expired)
            current_url = page.url
            if "login" in current_url.lower():
                logger.info("Session expired - redirected to login")
                return False

            logger.info("Session is valid")
            return True

        except Exception as e:
            logger.error(f"Session verification error: {e}")
            return False
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def close(self) -> None:
        """Close Playwright browser and cleanup resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Playwright browser closed")


class AuthenticationError(Exception):
    """Custom exception for authentication failures."""

    pass
