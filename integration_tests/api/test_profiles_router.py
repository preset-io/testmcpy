"""Tests for MCP profiles and LLM profiles CRUD endpoints."""


class TestListMCPProfiles:
    """Tests for GET /api/mcp/profiles."""

    def test_list_profiles_returns_200(self, client):
        resp = client.get("/api/mcp/profiles")
        assert resp.status_code == 200

    def test_list_profiles_has_profiles_key(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        assert "profiles" in data

    def test_list_profiles_has_default_key(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        assert "default" in data

    def test_list_profiles_contains_test_profile(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        profile_ids = [p["id"] for p in data["profiles"]]
        assert "test" in profile_ids

    def test_list_profiles_default_is_test(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        assert data["default"] == "test"

    def test_list_profiles_profile_has_mcps(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        test_profile = next(p for p in data["profiles"] if p["id"] == "test")
        assert "mcps" in test_profile
        assert len(test_profile["mcps"]) == 1

    def test_list_profiles_mcp_has_name_and_url(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        test_profile = next(p for p in data["profiles"] if p["id"] == "test")
        mcp = test_profile["mcps"][0]
        assert mcp["name"] == "Test MCP"
        assert mcp["mcp_url"] == "http://mock:3000/mcp"

    def test_list_profiles_mcp_has_auth(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        test_profile = next(p for p in data["profiles"] if p["id"] == "test")
        mcp = test_profile["mcps"][0]
        assert "auth" in mcp
        assert mcp["auth"]["type"] == "none"

    def test_list_profiles_default_selection(self, client):
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        assert "default_selection" in data


class TestCreateMCPProfile:
    """Tests for POST /api/mcp/profiles."""

    def test_create_profile_success(self, client):
        resp = client.post(
            "/api/mcp/profiles",
            json={"name": "new-profile", "description": "A new profile"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "profile_id" in data

    def test_create_profile_appears_in_list(self, client):
        client.post(
            "/api/mcp/profiles",
            json={"name": "new-profile", "description": "A new profile"},
        )
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        ids = [p["id"] for p in data["profiles"]]
        assert "new-profile" in ids

    def test_create_profile_set_as_default(self, client):
        client.post(
            "/api/mcp/profiles",
            json={
                "name": "default-profile",
                "description": "",
                "set_as_default": True,
            },
        )
        resp = client.get("/api/mcp/profiles")
        data = resp.json()
        assert data["default"] == "default-profile"

    def test_create_profile_empty_name_rejected(self, client):
        resp = client.post(
            "/api/mcp/profiles",
            json={"name": "", "description": ""},
        )
        assert resp.status_code == 422

    def test_create_profile_invalid_name_rejected(self, client):
        resp = client.post(
            "/api/mcp/profiles",
            json={"name": "has spaces!", "description": ""},
        )
        assert resp.status_code == 422


class TestUpdateMCPProfile:
    """Tests for PUT /api/mcp/profiles/{profile_id}."""

    def test_update_profile_name(self, client):
        resp = client.put(
            "/api/mcp/profiles/test",
            json={"name": "Updated Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_update_nonexistent_profile(self, client):
        resp = client.put(
            "/api/mcp/profiles/nonexistent",
            json={"name": "Updated"},
        )
        assert resp.status_code == 404

    def test_update_profile_set_default(self, client):
        # Create a second profile first
        client.post(
            "/api/mcp/profiles",
            json={"name": "second-profile"},
        )
        resp = client.put(
            "/api/mcp/profiles/second-profile",
            json={"set_as_default": True},
        )
        assert resp.status_code == 200


class TestDeleteMCPProfile:
    """Tests for DELETE /api/mcp/profiles/{profile_id}."""

    def test_delete_profile_success(self, client):
        # Create, then delete
        client.post("/api/mcp/profiles", json={"name": "to-delete"})
        resp = client.delete("/api/mcp/profiles/to-delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_delete_nonexistent_profile(self, client):
        resp = client.delete("/api/mcp/profiles/nonexistent")
        assert resp.status_code == 404

    def test_delete_removes_from_list(self, client):
        client.post("/api/mcp/profiles", json={"name": "to-delete"})
        client.delete("/api/mcp/profiles/to-delete")
        resp = client.get("/api/mcp/profiles")
        ids = [p["id"] for p in resp.json()["profiles"]]
        assert "to-delete" not in ids


class TestDuplicateMCPProfile:
    """Tests for POST /api/mcp/profiles/{profile_id}/duplicate."""

    def test_duplicate_profile_success(self, client):
        resp = client.post("/api/mcp/profiles/test/duplicate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "profile_id" in data

    def test_duplicate_nonexistent_profile(self, client):
        resp = client.post("/api/mcp/profiles/nonexistent/duplicate")
        assert resp.status_code == 404


class TestSetDefaultProfile:
    """Tests for PUT /api/mcp/profiles/default/{profile_id}."""

    def test_set_default_profile(self, client):
        resp = client.put("/api/mcp/profiles/default/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_set_default_nonexistent(self, client):
        resp = client.put("/api/mcp/profiles/default/nonexistent")
        assert resp.status_code == 404


class TestAddMCPToProfile:
    """Tests for POST /api/mcp/profiles/{profile_id}/mcps."""

    def test_add_mcp_success(self, client):
        resp = client.post(
            "/api/mcp/profiles/test/mcps",
            json={
                "name": "New MCP",
                "mcp_url": "http://new:3000/mcp",
                "auth": {"type": "none"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_add_duplicate_mcp_name_rejected(self, client):
        resp = client.post(
            "/api/mcp/profiles/test/mcps",
            json={
                "name": "Test MCP",
                "mcp_url": "http://new:3000/mcp",
                "auth": {"type": "none"},
            },
        )
        assert resp.status_code == 400

    def test_add_mcp_to_nonexistent_profile(self, client):
        resp = client.post(
            "/api/mcp/profiles/nonexistent/mcps",
            json={
                "name": "New MCP",
                "mcp_url": "http://new:3000/mcp",
                "auth": {"type": "none"},
            },
        )
        assert resp.status_code == 404


class TestDeleteMCPFromProfile:
    """Tests for DELETE /api/mcp/profiles/{profile_id}/mcps/{mcp_index}."""

    def test_delete_mcp_success(self, client):
        resp = client.delete("/api/mcp/profiles/test/mcps/0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_delete_mcp_invalid_index(self, client):
        resp = client.delete("/api/mcp/profiles/test/mcps/99")
        assert resp.status_code == 404

    def test_delete_mcp_nonexistent_profile(self, client):
        resp = client.delete("/api/mcp/profiles/nonexistent/mcps/0")
        assert resp.status_code == 404


class TestExportProfile:
    """Tests for GET /api/mcp/profiles/{profile_id}/export."""

    def test_export_profile_success(self, client):
        resp = client.get("/api/mcp/profiles/test/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "yaml" in data
        assert "filename" in data

    def test_export_nonexistent_profile(self, client):
        resp = client.get("/api/mcp/profiles/nonexistent/export")
        assert resp.status_code == 404


class TestLLMProfiles:
    """Tests for LLM profile endpoints under /api/llm/profiles."""

    def test_list_llm_profiles_returns_200(self, client):
        resp = client.get("/api/llm/profiles")
        assert resp.status_code == 200

    def test_list_llm_profiles_has_profiles_key(self, client):
        resp = client.get("/api/llm/profiles")
        data = resp.json()
        assert "profiles" in data
