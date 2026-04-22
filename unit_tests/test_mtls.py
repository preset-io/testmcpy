"""
Unit tests for mTLS client certificate support.

Tests the SSL context factory, certificate loading, and error handling.

Story: SC-103118 — mTLS client certificate and custom CA bundle support
"""

import ssl
from unittest.mock import patch

import pytest


class TestCreateMTLSFactory:
    """Tests for create_mtls_httpx_factory."""

    def test_factory_returns_callable(self, tmp_path):
        """Factory function returns a callable."""
        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        cert.write_text("CERT")
        key.write_text("KEY")

        with patch("ssl.SSLContext.load_cert_chain"):
            factory = create_mtls_httpx_factory(str(cert), str(key))
            assert callable(factory)

    def test_factory_loads_cert_chain(self, tmp_path):
        """Factory should call ssl_context.load_cert_chain with correct args."""
        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        cert.write_text("CERT")
        key.write_text("KEY")

        with patch("ssl.SSLContext.load_cert_chain") as mock_load:
            create_mtls_httpx_factory(str(cert), str(key))
            mock_load.assert_called_once_with(certfile=str(cert), keyfile=str(key))

    def test_factory_loads_ca_bundle(self, tmp_path):
        """Factory should load CA bundle when provided."""
        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        cert = tmp_path / "cert.pem"
        ca = tmp_path / "ca.pem"
        cert.write_text("CERT")
        ca.write_text("CA")

        with (
            patch("ssl.SSLContext.load_cert_chain"),
            patch("ssl.SSLContext.load_verify_locations") as mock_verify,
        ):
            create_mtls_httpx_factory(str(cert), ca_bundle=str(ca))
            mock_verify.assert_called_once_with(str(ca))

    def test_factory_no_ca_bundle(self, tmp_path):
        """Without CA bundle, load_verify_locations should not be called."""
        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        cert = tmp_path / "cert.pem"
        cert.write_text("CERT")

        with (
            patch("ssl.SSLContext.load_cert_chain"),
            patch("ssl.SSLContext.load_verify_locations") as mock_verify,
        ):
            create_mtls_httpx_factory(str(cert))
            mock_verify.assert_not_called()

    def test_factory_no_key(self, tmp_path):
        """Cert without separate key (combined PEM) should work."""
        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        cert = tmp_path / "combined.pem"
        cert.write_text("CERT+KEY")

        with patch("ssl.SSLContext.load_cert_chain") as mock_load:
            create_mtls_httpx_factory(str(cert), client_key=None)
            mock_load.assert_called_once_with(certfile=str(cert), keyfile=None)

    def test_factory_invalid_cert_raises(self):
        """Loading a non-existent cert should raise."""
        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        with pytest.raises((FileNotFoundError, ssl.SSLError)):
            create_mtls_httpx_factory("/nonexistent/cert.pem", "/nonexistent/key.pem")

    def test_factory_produces_async_client(self, tmp_path):
        """Factory should produce an httpx.AsyncClient when called."""
        import httpx

        from testmcpy.src.mcp_client import create_mtls_httpx_factory

        cert = tmp_path / "cert.pem"
        cert.write_text("CERT")

        with patch("ssl.SSLContext.load_cert_chain"):
            factory = create_mtls_httpx_factory(str(cert))
            client = factory()
            assert isinstance(client, httpx.AsyncClient)


class TestMTLSAuthConfig:
    """Tests for mTLS fields in AuthConfig."""

    def test_auth_config_mtls_fields(self):
        """AuthConfig should store mTLS fields."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="bearer",
            token="tok",
            client_cert="/path/cert.pem",
            client_key="/path/key.pem",
            ca_bundle="/path/ca.pem",
        )
        assert config.client_cert == "/path/cert.pem"
        assert config.client_key == "/path/key.pem"
        assert config.ca_bundle == "/path/ca.pem"

    def test_auth_config_mtls_to_dict(self):
        """mTLS fields should appear in to_dict output."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(
            auth_type="bearer",
            token="tok",
            client_cert="/cert.pem",
            client_key="/key.pem",
            ca_bundle="/ca.pem",
        )
        d = config.to_dict()
        assert d["client_cert"] == "/cert.pem"
        assert d["client_key"] == "/key.pem"
        assert d["ca_bundle"] == "/ca.pem"

    def test_auth_config_no_mtls(self):
        """AuthConfig without mTLS fields should not include them."""
        from testmcpy.mcp_profiles import AuthConfig

        config = AuthConfig(auth_type="bearer", token="tok")
        d = config.to_dict()
        # These should be None or absent
        assert d.get("client_cert") is None
        assert d.get("client_key") is None
        assert d.get("ca_bundle") is None
