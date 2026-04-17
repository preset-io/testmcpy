"""
Advanced OAuth flows for testmcpy.

Provides:
- PKCEFlow: Authorization Code with PKCE (S256) support
- TokenIntrospection: RFC 7662 token introspection
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


class OAuthFlowError(Exception):
    """Raised when an OAuth flow operation fails."""


@dataclass
class PKCEChallenge:
    """PKCE code verifier and challenge pair."""

    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"


@dataclass
class AuthorizationRequest:
    """Parameters for an authorization URL."""

    authorization_url: str
    code_verifier: str
    code_challenge: str
    state: str


class PKCEFlow:
    """Authorization Code flow with PKCE (Proof Key for Code Exchange).

    Implements RFC 7636 PKCE with S256 challenge method.

    Args:
        authorization_url: Authorization endpoint URL
        token_url: Token endpoint URL
        client_id: OAuth client ID
        redirect_uri: Redirect URI for the authorization callback
        scopes: List of OAuth scopes to request
        verify_ssl: Whether to verify SSL certificates
    """

    def __init__(
        self,
        authorization_url: str,
        token_url: str,
        client_id: str,
        redirect_uri: str = "http://localhost:8080/callback",
        scopes: list[str] | None = None,
        verify_ssl: bool = True,
    ):
        self.authorization_url = authorization_url
        self.token_url = token_url
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scopes = scopes or []
        self._verify_ssl = verify_ssl

    @staticmethod
    def generate_code_verifier(length: int = 64) -> str:
        """Generate a cryptographically random code verifier.

        Per RFC 7636, the code verifier must be between 43 and 128 characters,
        using unreserved characters [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~".

        Args:
            length: Length of the code verifier (43-128). Defaults to 64.

        Returns:
            URL-safe random string suitable as a PKCE code verifier.

        Raises:
            ValueError: If length is outside the valid range.
        """
        if length < 43 or length > 128:
            raise ValueError("Code verifier length must be between 43 and 128")
        # Generate random bytes and base64url encode them
        random_bytes = secrets.token_bytes(length)
        # base64url encode without padding, truncate to desired length
        verifier = base64.urlsafe_b64encode(random_bytes).decode("ascii").rstrip("=")
        return verifier[:length]

    @staticmethod
    def generate_code_challenge(code_verifier: str) -> str:
        """Generate S256 code challenge from a code verifier.

        Per RFC 7636: code_challenge = BASE64URL(SHA256(code_verifier))

        Args:
            code_verifier: The PKCE code verifier string.

        Returns:
            Base64url-encoded SHA-256 hash of the code verifier.
        """
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    def generate_pkce_pair(length: int = 64) -> PKCEChallenge:
        """Generate a PKCE code verifier and challenge pair.

        Args:
            length: Length of the code verifier. Defaults to 64.

        Returns:
            PKCEChallenge with verifier and S256 challenge.
        """
        verifier = PKCEFlow.generate_code_verifier(length)
        challenge = PKCEFlow.generate_code_challenge(verifier)
        return PKCEChallenge(
            code_verifier=verifier,
            code_challenge=challenge,
            code_challenge_method="S256",
        )

    def build_authorization_url(self, state: str | None = None) -> AuthorizationRequest:
        """Build the authorization URL with PKCE parameters.

        Args:
            state: Optional state parameter for CSRF protection.
                If not provided, a random one is generated.

        Returns:
            AuthorizationRequest with the full URL and PKCE parameters.
        """
        pkce = self.generate_pkce_pair()
        if state is None:
            state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": pkce.code_challenge_method,
            "state": state,
        }
        if self.scopes:
            params["scope"] = " ".join(self.scopes)

        url = f"{self.authorization_url}?{urlencode(params)}"

        return AuthorizationRequest(
            authorization_url=url,
            code_verifier=pkce.code_verifier,
            code_challenge=pkce.code_challenge,
            state=state,
        )

    async def exchange_code(
        self,
        authorization_code: str,
        code_verifier: str,
        timeout: float = 30.0,
    ) -> dict:
        """Exchange an authorization code for tokens.

        Args:
            authorization_code: The authorization code from the callback.
            code_verifier: The PKCE code verifier used in the authorization request.
            timeout: Request timeout in seconds.

        Returns:
            Token response dict with access_token, refresh_token, etc.

        Raises:
            OAuthFlowError: If the token exchange fails.
        """
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }

        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            raise OAuthFlowError(
                f"Token exchange failed with status {e.response.status_code}: {e.response.text[:100]}"
            )
        except httpx.HTTPError as e:
            raise OAuthFlowError(f"Token exchange HTTP error: {e}")


@dataclass
class IntrospectionResult:
    """Result from token introspection (RFC 7662)."""

    active: bool
    scope: str | None = None
    client_id: str | None = None
    username: str | None = None
    token_type: str | None = None
    exp: int | None = None
    iat: int | None = None
    nbf: int | None = None
    sub: str | None = None
    aud: str | None = None
    iss: str | None = None
    jti: str | None = None
    extra: dict | None = None


class TokenIntrospection:
    """RFC 7662 Token Introspection client.

    Calls a token introspection endpoint to validate and inspect tokens.

    Args:
        introspection_url: Token introspection endpoint URL
        client_id: Client ID for authenticating the introspection request
        client_secret: Client secret for authenticating the introspection request
        verify_ssl: Whether to verify SSL certificates
    """

    def __init__(
        self,
        introspection_url: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        verify_ssl: bool = True,
    ):
        self.introspection_url = introspection_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._verify_ssl = verify_ssl

    async def introspect(
        self,
        token: str,
        token_type_hint: str | None = None,
        timeout: float = 30.0,
    ) -> IntrospectionResult:
        """Introspect a token at the introspection endpoint.

        Args:
            token: The token to introspect.
            token_type_hint: Optional hint about the token type
                ("access_token" or "refresh_token").
            timeout: Request timeout in seconds.

        Returns:
            IntrospectionResult with token metadata.

        Raises:
            OAuthFlowError: If the introspection request fails.
        """
        data: dict[str, str] = {"token": token}
        if token_type_hint:
            data["token_type_hint"] = token_type_hint

        auth = None
        if self.client_id and self.client_secret:
            auth = httpx.BasicAuth(self.client_id, self.client_secret)

        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                response = await client.post(
                    self.introspection_url,
                    data=data,
                    auth=auth,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=timeout,
                )
                response.raise_for_status()
                result = response.json()
        except httpx.HTTPStatusError as e:
            raise OAuthFlowError(
                f"Token introspection failed with status {e.response.status_code}: "
                f"{e.response.text[:100]}"
            )
        except httpx.HTTPError as e:
            raise OAuthFlowError(f"Token introspection HTTP error: {e}")

        # Parse standard RFC 7662 fields
        known_fields = {
            "active",
            "scope",
            "client_id",
            "username",
            "token_type",
            "exp",
            "iat",
            "nbf",
            "sub",
            "aud",
            "iss",
            "jti",
        }
        extra = {k: v for k, v in result.items() if k not in known_fields}

        return IntrospectionResult(
            active=result.get("active", False),
            scope=result.get("scope"),
            client_id=result.get("client_id"),
            username=result.get("username"),
            token_type=result.get("token_type"),
            exp=result.get("exp"),
            iat=result.get("iat"),
            nbf=result.get("nbf"),
            sub=result.get("sub"),
            aud=result.get("aud"),
            iss=result.get("iss"),
            jti=result.get("jti"),
            extra=extra if extra else None,
        )
