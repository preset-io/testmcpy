"""
Unit tests for advanced auth features:
- TokenManager (auto-refresh, expiry handling)
- JWTClaimsValidEvaluator
- PKCEFlow (code_verifier/challenge generation)
- API Key and Custom Header auth injection
"""

import base64
import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testmcpy.evals.auth_evaluators import JWTClaimsValidEvaluator
from testmcpy.src.oauth_flows import PKCEChallenge, PKCEFlow
from testmcpy.src.token_manager import (
    EXPIRY_BUFFER_SECONDS,
    TokenManager,
    TokenRefreshError,
)


# ---------------------------------------------------------------------------
# Helper: create a fake JWT token with specific claims
# ---------------------------------------------------------------------------
def make_jwt(payload: dict, header: dict | None = None) -> str:
    """Create a fake JWT token (no real signature)."""
    if header is None:
        header = {"alg": "HS256", "typ": "JWT"}
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    s = base64.urlsafe_b64encode(b"fakesignature").decode().rstrip("=")
    return f"{h}.{p}.{s}"


# ===========================================================================
# TokenManager Tests
# ===========================================================================


class TestTokenManager:
    """Tests for TokenManager."""

    def test_is_expired_no_expiry(self):
        """Token with no expiry is never considered expired."""
        tm = TokenManager(access_token="tok123")
        assert tm.is_expired() is False

    def test_is_expired_future(self):
        """Token with future expiry is not expired."""
        tm = TokenManager(
            access_token="tok123",
            expiry=time.time() + 3600,
        )
        assert tm.is_expired() is False

    def test_is_expired_past(self):
        """Token with past expiry is expired."""
        tm = TokenManager(
            access_token="tok123",
            expiry=time.time() - 10,
        )
        assert tm.is_expired() is True

    def test_is_expired_within_buffer(self):
        """Token expiring within buffer is considered expired."""
        tm = TokenManager(
            access_token="tok123",
            expiry=time.time() + 10,  # 10s left, but buffer is 30s
        )
        assert tm.is_expired(buffer_seconds=EXPIRY_BUFFER_SECONDS) is True

    def test_is_expired_custom_buffer(self):
        """Custom buffer changes the threshold."""
        tm = TokenManager(
            access_token="tok123",
            expiry=time.time() + 10,
        )
        # With a 5s buffer, 10s remaining is not expired
        assert tm.is_expired(buffer_seconds=5) is False

    @pytest.mark.asyncio
    async def test_get_token_not_expired(self):
        """get_token returns current token when not expired."""
        tm = TokenManager(
            access_token="valid_token",
            expiry=time.time() + 3600,
        )
        token = await tm.get_token()
        assert token == "valid_token"

    @pytest.mark.asyncio
    async def test_get_token_no_expiry(self):
        """get_token returns current token when no expiry set."""
        tm = TokenManager(access_token="no_expiry_token")
        token = await tm.get_token()
        assert token == "no_expiry_token"

    @pytest.mark.asyncio
    async def test_get_token_expired_no_refresh(self):
        """get_token returns expired token when no refresh is configured."""
        tm = TokenManager(
            access_token="expired_token",
            expiry=time.time() - 100,
        )
        # Should return the expired token (caller handles 401)
        token = await tm.get_token()
        assert token == "expired_token"

    @pytest.mark.asyncio
    async def test_refresh_no_refresh_token(self):
        """refresh raises error when no refresh_token."""
        tm = TokenManager(
            access_token="tok",
            token_url="https://auth.example.com/token",
            expiry=time.time() - 100,  # Must be expired to trigger refresh logic
        )
        with pytest.raises(TokenRefreshError, match="No refresh_token"):
            await tm.refresh()

    @pytest.mark.asyncio
    async def test_refresh_no_token_url(self):
        """refresh raises error when no token_url."""
        tm = TokenManager(
            access_token="tok",
            refresh_token="refresh_tok",
            expiry=time.time() - 100,  # Must be expired to trigger refresh logic
        )
        with pytest.raises(TokenRefreshError, match="No token_url"):
            await tm.refresh()

    @pytest.mark.asyncio
    async def test_refresh_success(self):
        """refresh updates token on successful HTTP response."""
        tm = TokenManager(
            access_token="old_token",
            refresh_token="my_refresh",
            token_url="https://auth.example.com/token",
            expiry=time.time() - 100,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("testmcpy.src.token_manager.httpx.AsyncClient", return_value=mock_client):
            result = await tm.refresh()

        assert result.access_token == "new_token"
        assert result.refresh_token == "new_refresh"
        assert tm.access_token == "new_token"
        assert tm.refresh_token == "new_refresh"
        assert tm.refresh_count == 1
        assert tm.is_expired() is False

    @pytest.mark.asyncio
    async def test_refresh_http_error(self):
        """refresh raises TokenRefreshError on HTTP error."""
        import httpx

        tm = TokenManager(
            access_token="old_token",
            refresh_token="my_refresh",
            token_url="https://auth.example.com/token",
            expiry=time.time() - 100,
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("testmcpy.src.token_manager.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(TokenRefreshError, match="Token refresh failed"):
                await tm.refresh()

    def test_update_token(self):
        """update_token replaces stored token data."""
        tm = TokenManager(access_token="old", refresh_token="old_refresh")
        tm.update_token(access_token="new", refresh_token="new_refresh", expiry=9999999999.0)
        assert tm.access_token == "new"
        assert tm.refresh_token == "new_refresh"
        assert tm.expiry == 9999999999.0

    def test_properties(self):
        """Properties return correct values."""
        tm = TokenManager(
            access_token="tok",
            refresh_token="ref",
            expiry=1234567890.0,
        )
        assert tm.access_token == "tok"
        assert tm.refresh_token == "ref"
        assert tm.expiry == 1234567890.0
        assert tm.refresh_count == 0


# ===========================================================================
# JWTClaimsValidEvaluator Tests
# ===========================================================================


class TestJWTClaimsValidEvaluator:
    """Tests for JWTClaimsValidEvaluator."""

    def test_no_token(self):
        """Fails when no token in metadata."""
        evaluator = JWTClaimsValidEvaluator()
        result = evaluator.evaluate({"metadata": {}})
        assert result.passed is False
        assert "No JWT token" in result.reason

    def test_invalid_jwt_structure(self):
        """Fails on non-JWT string."""
        evaluator = JWTClaimsValidEvaluator()
        result = evaluator.evaluate({"metadata": {"auth_token": "not-a-jwt"}})
        assert result.passed is False
        assert "Invalid JWT" in result.reason or "Failed to decode" in result.reason

    def test_valid_token_no_checks(self):
        """Passes with valid JWT and no specific checks."""
        token = make_jwt({"sub": "user1", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(args={"check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_iss_check_pass(self):
        """Passes when iss matches."""
        token = make_jwt({"iss": "https://auth.example.com", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(
            args={"iss": "https://auth.example.com", "check_exp": True}
        )
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_iss_check_fail(self):
        """Fails when iss does not match."""
        token = make_jwt({"iss": "https://wrong.example.com", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(
            args={"iss": "https://auth.example.com", "check_exp": True}
        )
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is False
        assert "iss" in result.reason

    def test_aud_check_string(self):
        """Passes when aud (string) matches."""
        token = make_jwt({"aud": "my-api", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(args={"aud": "my-api", "check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_aud_check_list(self):
        """Passes when aud (list) contains expected value."""
        token = make_jwt({"aud": ["api-1", "my-api"], "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(args={"aud": "my-api", "check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_aud_check_fail(self):
        """Fails when aud does not match."""
        token = make_jwt({"aud": "other-api", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(args={"aud": "my-api", "check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is False

    def test_exp_expired(self):
        """Fails when token is expired."""
        token = make_jwt({"exp": int(time.time()) - 100})
        evaluator = JWTClaimsValidEvaluator(args={"check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is False
        assert "expired" in result.reason.lower()

    def test_exp_missing(self):
        """Fails when exp claim is missing and check is enabled."""
        token = make_jwt({"sub": "user1"})
        evaluator = JWTClaimsValidEvaluator(args={"check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is False
        assert "exp" in result.reason

    def test_exp_check_disabled(self):
        """Passes when exp check is disabled."""
        token = make_jwt({"sub": "user1"})
        evaluator = JWTClaimsValidEvaluator(args={"check_exp": False})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_custom_claims_pass(self):
        """Passes when custom claims match."""
        token = make_jwt({"role": "admin", "org": "preset", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(
            args={
                "custom_claims": {"role": "admin", "org": "preset"},
                "check_exp": True,
            }
        )
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_custom_claims_fail(self):
        """Fails when custom claim does not match."""
        token = make_jwt({"role": "viewer", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(
            args={
                "custom_claims": {"role": "admin"},
                "check_exp": True,
            }
        )
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is False
        assert "role" in result.reason

    def test_sub_check(self):
        """Passes when sub matches."""
        token = make_jwt({"sub": "user123", "exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(args={"sub": "user123", "check_exp": True})
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is True

    def test_custom_token_field(self):
        """Uses custom token_field from args."""
        token = make_jwt({"exp": int(time.time()) + 3600})
        evaluator = JWTClaimsValidEvaluator(args={"token_field": "my_jwt", "check_exp": True})
        result = evaluator.evaluate({"metadata": {"my_jwt": token}})
        assert result.passed is True

    def test_decode_jwt_payload_static(self):
        """Static method correctly decodes JWT payload."""
        payload = {"sub": "test", "iss": "me"}
        token = make_jwt(payload)
        decoded = JWTClaimsValidEvaluator.decode_jwt_payload(token)
        assert decoded["sub"] == "test"
        assert decoded["iss"] == "me"

    def test_score_partial_claims(self):
        """Score reflects partial claim pass/fail ratio."""
        token = make_jwt(
            {
                "iss": "correct",
                "aud": "wrong",
                "exp": int(time.time()) + 3600,
            }
        )
        evaluator = JWTClaimsValidEvaluator(
            args={"iss": "correct", "aud": "expected", "check_exp": True}
        )
        result = evaluator.evaluate({"metadata": {"auth_token": token}})
        assert result.passed is False
        # 2 passed (iss, exp) out of 3 total
        assert 0.5 < result.score < 0.8

    def test_name_and_description(self):
        """Properties return meaningful strings."""
        evaluator = JWTClaimsValidEvaluator(args={"iss": "test", "aud": "api", "check_exp": True})
        assert evaluator.name == "jwt_claims_valid"
        assert "iss" in evaluator.description
        assert "aud" in evaluator.description


# ===========================================================================
# PKCEFlow Tests
# ===========================================================================


class TestPKCEFlow:
    """Tests for PKCE code verifier and challenge generation."""

    def test_generate_code_verifier_length(self):
        """Code verifier has correct length."""
        verifier = PKCEFlow.generate_code_verifier(64)
        assert len(verifier) == 64

    def test_generate_code_verifier_min_length(self):
        """Code verifier respects minimum length (43)."""
        verifier = PKCEFlow.generate_code_verifier(43)
        assert len(verifier) == 43

    def test_generate_code_verifier_max_length(self):
        """Code verifier respects maximum length (128)."""
        verifier = PKCEFlow.generate_code_verifier(128)
        assert len(verifier) == 128

    def test_generate_code_verifier_too_short(self):
        """Raises ValueError for length < 43."""
        with pytest.raises(ValueError, match="between 43 and 128"):
            PKCEFlow.generate_code_verifier(42)

    def test_generate_code_verifier_too_long(self):
        """Raises ValueError for length > 128."""
        with pytest.raises(ValueError, match="between 43 and 128"):
            PKCEFlow.generate_code_verifier(129)

    def test_generate_code_verifier_randomness(self):
        """Two verifiers should be different."""
        v1 = PKCEFlow.generate_code_verifier()
        v2 = PKCEFlow.generate_code_verifier()
        assert v1 != v2

    def test_generate_code_challenge_s256(self):
        """Code challenge is correct S256 hash of verifier."""
        verifier = "test_verifier_string_that_is_at_least_43_chars_long_for_pkce_test"
        challenge = PKCEFlow.generate_code_challenge(verifier)

        # Manually compute expected challenge
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).decode("ascii").rstrip("=")

        assert challenge == expected_challenge

    def test_generate_pkce_pair(self):
        """generate_pkce_pair returns valid PKCEChallenge."""
        pair = PKCEFlow.generate_pkce_pair()
        assert isinstance(pair, PKCEChallenge)
        assert len(pair.code_verifier) == 64
        assert pair.code_challenge_method == "S256"

        # Verify challenge matches verifier
        expected = PKCEFlow.generate_code_challenge(pair.code_verifier)
        assert pair.code_challenge == expected

    def test_generate_pkce_pair_custom_length(self):
        """generate_pkce_pair respects custom length."""
        pair = PKCEFlow.generate_pkce_pair(length=96)
        assert len(pair.code_verifier) == 96

    def test_build_authorization_url(self):
        """build_authorization_url returns valid URL with PKCE params."""
        flow = PKCEFlow(
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            client_id="my-client",
            redirect_uri="http://localhost:8080/callback",
            scopes=["openid", "profile"],
        )

        request = flow.build_authorization_url(state="test-state")

        assert "https://auth.example.com/authorize?" in request.authorization_url
        assert "client_id=my-client" in request.authorization_url
        assert "code_challenge=" in request.authorization_url
        assert "code_challenge_method=S256" in request.authorization_url
        assert "state=test-state" in request.authorization_url
        assert "scope=openid+profile" in request.authorization_url
        assert "response_type=code" in request.authorization_url
        assert request.code_verifier is not None
        assert request.code_challenge is not None
        assert request.state == "test-state"

    def test_build_authorization_url_auto_state(self):
        """build_authorization_url generates random state if not provided."""
        flow = PKCEFlow(
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            client_id="my-client",
        )

        r1 = flow.build_authorization_url()
        r2 = flow.build_authorization_url()
        assert r1.state != r2.state  # Random states should differ

    def test_code_verifier_characters(self):
        """Code verifier only contains URL-safe characters."""
        import re

        for _ in range(10):
            verifier = PKCEFlow.generate_code_verifier()
            # RFC 7636 unreserved chars + base64url chars
            assert re.match(r"^[A-Za-z0-9_\-]+$", verifier), f"Bad verifier: {verifier}"


# ===========================================================================
# API Key and Custom Header Auth Tests
# ===========================================================================


class TestAPIKeyAuth:
    """Tests for API Key authentication configuration."""

    def test_api_key_to_dict(self):
        """AuthConfig with api_key produces correct dict."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="api_key",
            header_name="X-Custom-Key",
            api_key="my-secret-key",
        )
        d = config.to_dict()
        assert d["type"] == "api_key"
        assert d["header_name"] == "X-Custom-Key"
        assert d["api_key"] == "my-secret-key"

    def test_api_key_default_header(self):
        """AuthConfig uses default X-API-Key header."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="api_key",
            api_key="key123",
        )
        d = config.to_dict()
        assert d["header_name"] == "X-API-Key"

    def test_api_key_env_resolution(self):
        """AuthConfig resolves api_key from environment variable."""
        import os

        from testmcpy.mcp_profiles import AuthConfig

        os.environ["TEST_API_KEY_12345"] = "env-secret-key"
        try:
            config = AuthConfig(
                auth_type="api_key",
                api_key_env="TEST_API_KEY_12345",
            )
            d = config.to_dict()
            assert d["api_key"] == "env-secret-key"
        finally:
            del os.environ["TEST_API_KEY_12345"]

    def test_custom_headers_to_dict(self):
        """AuthConfig with custom_headers produces correct dict."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="custom_headers",
            headers={"X-Org": "preset", "X-Token": "abc123"},
        )
        d = config.to_dict()
        assert d["type"] == "custom_headers"
        assert d["headers"]["X-Org"] == "preset"
        assert d["headers"]["X-Token"] == "abc123"


class TestMTLSConfig:
    """Tests for mTLS configuration in AuthConfig."""

    def test_mtls_to_dict(self):
        """AuthConfig with mTLS fields produces correct dict."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="bearer",
            token="tok",
            client_cert="/path/to/cert.pem",
            client_key="/path/to/key.pem",
            ca_bundle="/path/to/ca.pem",
        )
        d = config.to_dict()
        assert d["client_cert"] == "/path/to/cert.pem"
        assert d["client_key"] == "/path/to/key.pem"
        assert d["ca_bundle"] == "/path/to/ca.pem"

    def test_mtls_fields_absent_by_default(self):
        """mTLS fields are not in dict when not set."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(auth_type="none")
        d = config.to_dict()
        assert "client_cert" not in d
        assert "client_key" not in d
        assert "ca_bundle" not in d


class TestOAuthAdvancedConfig:
    """Tests for advanced OAuth config fields."""

    def test_pkce_fields(self):
        """AuthConfig with PKCE fields produces correct dict."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="oauth",
            client_id="cid",
            token_url="https://auth.example.com/token",
            grant_type="authorization_code",
            redirect_uri="http://localhost:8080/callback",
            use_pkce=True,
            authorization_url="https://auth.example.com/authorize",
            token_introspection_url="https://auth.example.com/introspect",
        )
        d = config.to_dict()
        assert d["grant_type"] == "authorization_code"
        assert d["use_pkce"] is True
        assert d["redirect_uri"] == "http://localhost:8080/callback"
        assert d["authorization_url"] == "https://auth.example.com/authorize"
        assert d["token_introspection_url"] == "https://auth.example.com/introspect"

    def test_refresh_token_fields(self):
        """AuthConfig with refresh token fields produces correct dict."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="oauth",
            client_id="cid",
            token_url="https://auth.example.com/token",
            refresh_token="my_refresh",
            token_expiry=1234567890.0,
        )
        d = config.to_dict()
        assert d["refresh_token"] == "my_refresh"
        assert d["token_expiry"] == 1234567890.0

    def test_parse_auth_new_fields(self):
        """_parse_auth handles new auth fields."""
        from testmcpy.mcp_profiles import MCPProfileConfig

        config = MCPProfileConfig.__new__(MCPProfileConfig)
        config.global_config = {}

        auth_data = {
            "type": "api_key",
            "header_name": "Authorization",
            "api_key": "Bearer mykey",
        }
        auth = config._parse_auth(auth_data)
        assert auth.auth_type == "api_key"
        assert auth.header_name == "Authorization"
        assert auth.api_key == "Bearer mykey"

    def test_parse_auth_custom_headers(self):
        """_parse_auth handles custom_headers type."""
        from testmcpy.mcp_profiles import MCPProfileConfig

        config = MCPProfileConfig.__new__(MCPProfileConfig)
        config.global_config = {}

        auth_data = {
            "type": "custom_headers",
            "headers": {"X-A": "1", "X-B": "2"},
        }
        auth = config._parse_auth(auth_data)
        assert auth.auth_type == "custom_headers"
        assert auth.headers == {"X-A": "1", "X-B": "2"}

    def test_parse_auth_mtls(self):
        """_parse_auth handles mTLS fields."""
        from testmcpy.mcp_profiles import MCPProfileConfig

        config = MCPProfileConfig.__new__(MCPProfileConfig)
        config.global_config = {}

        auth_data = {
            "type": "bearer",
            "token": "tok",
            "client_cert": "/cert.pem",
            "client_key": "/key.pem",
            "ca_bundle": "/ca.pem",
        }
        auth = config._parse_auth(auth_data)
        assert auth.client_cert == "/cert.pem"
        assert auth.client_key == "/key.pem"
        assert auth.ca_bundle == "/ca.pem"
