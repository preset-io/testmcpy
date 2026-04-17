"""
Token management with automatic refresh and expiry handling.

Provides a thread-safe (asyncio) TokenManager that stores access tokens,
refresh tokens, and expiry timestamps. Automatically refreshes tokens
when they are expired or near-expiry.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Buffer before actual expiry to trigger proactive refresh (seconds)
EXPIRY_BUFFER_SECONDS = 30


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""


@dataclass
class TokenData:
    """Holds token data and metadata."""

    access_token: str
    refresh_token: str | None = None
    token_url: str | None = None
    expiry: float | None = None  # Unix timestamp when token expires
    token_type: str = "Bearer"
    scope: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class TokenManager:
    """Manages OAuth/JWT tokens with automatic refresh.

    Thread-safe via asyncio lock. Supports:
    - Checking token expiry with configurable buffer
    - Automatic refresh using refresh_token grant
    - Manual refresh trigger
    - Token replacement (e.g., after initial auth)

    Args:
        access_token: Current access token
        refresh_token: Refresh token for obtaining new access tokens
        token_url: Token endpoint URL for refresh requests
        expiry: Unix timestamp when the access token expires
        client_id: OAuth client ID (needed for some refresh flows)
        client_secret: OAuth client secret (needed for some refresh flows)
        verify_ssl: Whether to verify SSL certificates
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        token_url: str | None = None,
        expiry: float | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        verify_ssl: bool = True,
    ):
        self._token_data = TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            token_url=token_url,
            expiry=expiry,
        )
        self._client_id = client_id
        self._client_secret = client_secret
        self._verify_ssl = verify_ssl
        self._lock = asyncio.Lock()
        self._refresh_count = 0

    @property
    def access_token(self) -> str:
        """Current access token (may be expired)."""
        return self._token_data.access_token

    @property
    def refresh_token(self) -> str | None:
        """Current refresh token."""
        return self._token_data.refresh_token

    @property
    def expiry(self) -> float | None:
        """Token expiry as Unix timestamp."""
        return self._token_data.expiry

    @property
    def refresh_count(self) -> int:
        """Number of times the token has been refreshed."""
        return self._refresh_count

    def is_expired(self, buffer_seconds: float = EXPIRY_BUFFER_SECONDS) -> bool:
        """Check if the token is expired or near-expiry.

        Args:
            buffer_seconds: Seconds before actual expiry to consider token expired.
                Defaults to EXPIRY_BUFFER_SECONDS (30s).

        Returns:
            True if token is expired or will expire within buffer_seconds.
            False if no expiry is set (token assumed valid).
        """
        if self._token_data.expiry is None:
            return False
        return time.time() >= (self._token_data.expiry - buffer_seconds)

    async def get_token(self) -> str:
        """Get a valid access token, refreshing if expired.

        Returns:
            A valid access token string.

        Raises:
            TokenRefreshError: If token is expired and refresh fails.
        """
        if not self.is_expired():
            return self._token_data.access_token

        # Token is expired or near-expiry, try to refresh
        if self._token_data.refresh_token and self._token_data.token_url:
            await self.refresh()
            return self._token_data.access_token

        # No refresh token available, return current token anyway
        # (caller will get a 401 and can handle it)
        logger.warning("Token is expired but no refresh_token/token_url configured")
        return self._token_data.access_token

    async def refresh(self) -> TokenData:
        """Refresh the access token using the refresh_token grant.

        Thread-safe: only one refresh runs at a time.

        Returns:
            Updated TokenData with new access token.

        Raises:
            TokenRefreshError: If refresh fails (no refresh_token, no token_url,
                or HTTP error).
        """
        async with self._lock:
            # Double-check: another coroutine may have refreshed while we waited
            if not self.is_expired():
                return self._token_data

            if not self._token_data.refresh_token:
                raise TokenRefreshError("No refresh_token available")
            if not self._token_data.token_url:
                raise TokenRefreshError("No token_url configured for refresh")

            logger.info("Refreshing access token via %s", self._token_data.token_url)

            data: dict[str, str] = {
                "grant_type": "refresh_token",
                "refresh_token": self._token_data.refresh_token,
            }
            if self._client_id:
                data["client_id"] = self._client_id
            if self._client_secret:
                data["client_secret"] = self._client_secret

            try:
                async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                    response = await client.post(
                        self._token_data.token_url,
                        data=data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    result = response.json()
            except httpx.HTTPStatusError as e:
                raise TokenRefreshError(
                    f"Token refresh failed with status {e.response.status_code}: {e.response.text[:100]}"
                )
            except httpx.HTTPError as e:
                raise TokenRefreshError(f"Token refresh HTTP error: {e}")

            new_access = result.get("access_token")
            if not new_access:
                raise TokenRefreshError("No access_token in refresh response")

            # Update token data
            self._token_data.access_token = new_access

            # Update refresh token if rotated
            if "refresh_token" in result:
                self._token_data.refresh_token = result["refresh_token"]

            # Update expiry
            if "expires_in" in result:
                self._token_data.expiry = time.time() + result["expires_in"]

            self._token_data.token_type = result.get("token_type", "Bearer")
            self._token_data.scope = result.get("scope")

            self._refresh_count += 1
            logger.info("Token refreshed successfully (refresh #%d)", self._refresh_count)

            return self._token_data

    def update_token(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expiry: float | None = None,
    ) -> None:
        """Manually update the stored token.

        Args:
            access_token: New access token
            refresh_token: New refresh token (if rotated)
            expiry: New expiry timestamp
        """
        self._token_data.access_token = access_token
        if refresh_token is not None:
            self._token_data.refresh_token = refresh_token
        if expiry is not None:
            self._token_data.expiry = expiry
