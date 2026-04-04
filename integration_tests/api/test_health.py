"""Tests for health, version, config, and models endpoints."""


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_status_healthy(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_shows_mcp_connected(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["mcp_connected"] is True

    def test_health_shows_mcp_disconnected(self, client_no_mcp):
        resp = client_no_mcp.get("/api/health")
        data = resp.json()
        assert data["mcp_connected"] is False

    def test_health_has_timestamp(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "timestamp" in data
        assert len(data["timestamp"]) > 0

    def test_health_has_config_info(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "has_config" in data
        assert "profile_count" in data
        assert "mcp_server_count" in data

    def test_health_cached_clients_count(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "mcp_clients_cached" in data
        assert isinstance(data["mcp_clients_cached"], int)

    def test_health_profile_count_from_config(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["has_config"] is True
        assert data["profile_count"] >= 1

    def test_health_mcp_server_count(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["mcp_server_count"] >= 1


class TestVersionEndpoint:
    """Tests for GET /api/version."""

    def test_version_returns_200(self, client):
        resp = client.get("/api/version")
        assert resp.status_code == 200

    def test_version_has_version_key(self, client):
        resp = client.get("/api/version")
        data = resp.json()
        assert "version" in data

    def test_version_is_string(self, client):
        resp = client.get("/api/version")
        data = resp.json()
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestConfigEndpoint:
    """Tests for GET /api/config."""

    def test_config_returns_200(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200

    def test_config_returns_dict(self, client):
        resp = client.get("/api/config")
        data = resp.json()
        assert isinstance(data, dict)

    def test_config_values_have_source(self, client):
        resp = client.get("/api/config")
        data = resp.json()
        for key, entry in data.items():
            assert "value" in entry, f"Config key '{key}' missing 'value'"
            assert "source" in entry, f"Config key '{key}' missing 'source'"

    def test_config_masks_sensitive_keys(self, client):
        """Sensitive keys like API_KEY should be masked."""
        resp = client.get("/api/config")
        data = resp.json()
        for key, entry in data.items():
            if any(s in key for s in ("API_KEY", "TOKEN", "SECRET")):
                if entry["value"] is not None:
                    assert "..." in entry["value"] or entry["value"] == "***"


class TestModelsEndpoint:
    """Tests for GET /api/models."""

    def test_models_returns_200(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200

    def test_models_has_providers(self, client):
        resp = client.get("/api/models")
        data = resp.json()
        assert "anthropic" in data
        assert "openai" in data
        assert "ollama" in data

    def test_models_anthropic_has_entries(self, client):
        resp = client.get("/api/models")
        data = resp.json()
        assert len(data["anthropic"]) > 0

    def test_models_entries_have_required_fields(self, client):
        resp = client.get("/api/models")
        data = resp.json()
        for provider, models in data.items():
            for model in models:
                assert "id" in model, f"Model in {provider} missing 'id'"
                assert "name" in model, f"Model in {provider} missing 'name'"
                assert "description" in model, f"Model in {provider} missing 'description'"
