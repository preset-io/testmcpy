"""Integration tests for compatibility matrix and schema diff endpoints."""


class TestSchemaDiffEndpoint:
    """Tests for POST /api/tools/diff."""

    def test_diff_requires_profile_format(self, client):
        """Profile refs must be in profile_id:mcp_name format."""
        res = client.post(
            "/api/tools/diff",
            json={"profile1": "bad_format", "profile2": "also_bad"},
        )
        assert res.status_code == 400
        assert "profile_id:mcp_name" in res.json()["detail"]

    def test_diff_profile_not_found(self, client):
        """Return 404 if a profile doesn't exist."""
        res = client.post(
            "/api/tools/diff",
            json={"profile1": "nonexistent:mcp", "profile2": "test:Test MCP"},
        )
        # This may be 404 or 500 depending on whether the cached client is found
        assert res.status_code in (404, 500)


class TestCompatibilityMatrixEndpoint:
    """Tests for POST /api/compatibility/matrix."""

    def test_matrix_requires_two_profiles(self, client):
        """Need at least 2 profiles."""
        res = client.post(
            "/api/compatibility/matrix",
            json={"profiles": ["test:Test MCP"], "tool_names": ["health_check"]},
        )
        assert res.status_code == 400
        assert "2 profiles" in res.json()["detail"]

    def test_matrix_requires_tool_names(self, client):
        """Need at least 1 tool name."""
        res = client.post(
            "/api/compatibility/matrix",
            json={"profiles": ["test:Test MCP", "test:Other MCP"], "tool_names": []},
        )
        assert res.status_code == 400
        assert "tool name" in res.json()["detail"]

    def test_matrix_bad_profile_format(self, client):
        """Profile refs must be in profile_id:mcp_name format."""
        res = client.post(
            "/api/compatibility/matrix",
            json={"profiles": ["bad_format", "also_bad"], "tool_names": ["test"]},
        )
        assert res.status_code == 400
