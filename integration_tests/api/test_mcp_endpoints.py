"""Tests for MCP tools, resources, and prompts endpoints."""

from unittest.mock import patch


class TestListMCPTools:
    """Tests for GET /api/mcp/tools."""

    def test_tools_no_profiles_returns_empty(self, client):
        resp = client.get("/api/mcp/tools")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_tools_with_profile_param(self, client, mock_mcp_client):
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 200
            tools = resp.json()
            assert len(tools) == 2
            assert tools[0]["name"] == "health_check"
            assert tools[1]["name"] == "get_data"

    def test_tools_include_mcp_source(self, client, mock_mcp_client):
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test:Test MCP"})
            tools = resp.json()
            for tool in tools:
                assert tool["mcp_source"] == "Test MCP"

    def test_tools_have_input_schema(self, client, mock_mcp_client):
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test:Test MCP"})
            tools = resp.json()
            for tool in tools:
                assert "input_schema" in tool

    def test_tools_connection_error_returns_503(self, client):
        async def fail_connect(*args, **kwargs):
            raise ConnectionError("Connection refused")

        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            side_effect=fail_connect,
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 503

    def test_tools_auth_error_returns_503(self, client):
        async def fail_auth(*args, **kwargs):
            raise RuntimeError("401 Unauthorized")

        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            side_effect=fail_auth,
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 503

    def test_tools_generic_error_returns_500(self, client):
        async def fail_generic(*args, **kwargs):
            raise RuntimeError("Something unexpected")

        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            side_effect=fail_generic,
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 500

    def test_tools_legacy_profile_format(self, client, mock_mcp_client):
        with patch(
            "testmcpy.server.api.get_mcp_clients_for_profile",
            return_value=[("Test MCP", mock_mcp_client)],
        ):
            resp = client.get("/api/mcp/tools", params={"profiles": "test"})
            assert resp.status_code == 200
            tools = resp.json()
            assert len(tools) == 2

    def test_tools_multiple_profiles(self, client, mock_mcp_client):
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get(
                "/api/mcp/tools",
                params={"profiles": ["test:Test MCP", "test:Test MCP"]},
            )
            assert resp.status_code == 200
            tools = resp.json()
            assert len(tools) == 4  # 2 tools * 2 profiles


class TestListMCPResources:
    """Tests for GET /api/mcp/resources."""

    def test_resources_no_profiles_returns_empty(self, client):
        resp = client.get("/api/mcp/resources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_resources_with_profile(self, client, mock_mcp_client):
        mock_mcp_client.list_resources.return_value = [
            {"uri": "file://test.txt", "name": "test.txt"}
        ]
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/resources", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 200
            resources = resp.json()
            assert len(resources) == 1
            assert resources[0]["uri"] == "file://test.txt"

    def test_resources_error_skips_silently(self, client):
        async def fail_resources(*args, **kwargs):
            raise RuntimeError("Not supported")

        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            side_effect=fail_resources,
        ):
            resp = client.get("/api/mcp/resources", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 200
            assert resp.json() == []

    def test_resources_adds_mcp_source(self, client, mock_mcp_client):
        mock_mcp_client.list_resources.return_value = [{"uri": "file://a.txt", "name": "a.txt"}]
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/resources", params={"profiles": "test:Test MCP"})
            resources = resp.json()
            assert resources[0]["mcp_source"] == "Test MCP"


class TestListMCPPrompts:
    """Tests for GET /api/mcp/prompts."""

    def test_prompts_no_profiles_returns_empty(self, client):
        resp = client.get("/api/mcp/prompts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_prompts_with_profile(self, client, mock_mcp_client):
        mock_mcp_client.list_prompts.return_value = [{"name": "greet", "description": "Greet user"}]
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/prompts", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 200
            prompts = resp.json()
            assert len(prompts) == 1
            assert prompts[0]["name"] == "greet"

    def test_prompts_error_skips_silently(self, client):
        async def fail_prompts(*args, **kwargs):
            raise RuntimeError("Not supported")

        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            side_effect=fail_prompts,
        ):
            resp = client.get("/api/mcp/prompts", params={"profiles": "test:Test MCP"})
            assert resp.status_code == 200
            assert resp.json() == []

    def test_prompts_adds_mcp_source(self, client, mock_mcp_client):
        mock_mcp_client.list_prompts.return_value = [{"name": "greet", "description": "Greet user"}]
        with patch(
            "testmcpy.server.api.get_mcp_client_for_server",
            return_value=mock_mcp_client,
        ):
            resp = client.get("/api/mcp/prompts", params={"profiles": "test:Test MCP"})
            prompts = resp.json()
            assert prompts[0]["mcp_source"] == "Test MCP"
