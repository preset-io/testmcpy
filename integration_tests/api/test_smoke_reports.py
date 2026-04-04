"""Tests for smoke reports endpoints."""

import json


def _make_smoke_report(
    server_url="http://mock:3000/mcp",
    profile_id="test",
    profile_name="Test",
    passed=3,
    failed=1,
):
    """Build a minimal smoke report payload."""
    total = passed + failed
    return {
        "server_url": server_url,
        "profile_id": profile_id,
        "profile_name": profile_name,
        "timestamp": "2025-01-01T00:00:00",
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "success_rate": (passed / total * 100) if total > 0 else 0,
        "duration_ms": 1500,
        "tool_results": [
            {
                "tool_name": f"tool_{i}",
                "success": i < passed,
                "duration_ms": 300,
                "error": None if i < passed else "timeout",
            }
            for i in range(total)
        ],
    }


def _save_smoke_report_to_disk(tmp_workspace, report_data):
    """Save a smoke report directly to disk and return the report_id."""
    import uuid
    from datetime import datetime

    report_id = str(uuid.uuid4())[:8] + "_20250101_000000"
    report_data["report_id"] = report_id
    report_data["saved_at"] = datetime.now().isoformat()
    report_file = tmp_workspace / "tests" / ".smoke_reports" / f"{report_id}.json"
    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2, default=str)
    return report_id


class TestListSmokeReports:
    """Tests for GET /api/smoke-reports/list."""

    def test_list_empty(self, client):
        resp = client.get("/api/smoke-reports/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert data["total"] == 0

    def test_list_after_save(self, client, tmp_workspace):
        report = _make_smoke_report()
        _save_smoke_report_to_disk(tmp_workspace, report)
        resp = client.get("/api/smoke-reports/list")
        data = resp.json()
        assert data["total"] >= 1

    def test_list_filter_by_server_url(self, client, tmp_workspace):
        _save_smoke_report_to_disk(
            tmp_workspace,
            _make_smoke_report(server_url="http://a:3000/mcp"),
        )
        _save_smoke_report_to_disk(
            tmp_workspace,
            _make_smoke_report(server_url="http://b:3000/mcp"),
        )
        resp = client.get(
            "/api/smoke-reports/list",
            params={"server_url": "http://a:3000/mcp"},
        )
        data = resp.json()
        for report in data["reports"]:
            assert report["server_url"] == "http://a:3000/mcp"

    def test_list_filter_by_profile_id(self, client, tmp_workspace):
        _save_smoke_report_to_disk(tmp_workspace, _make_smoke_report(profile_id="alpha"))
        _save_smoke_report_to_disk(tmp_workspace, _make_smoke_report(profile_id="beta"))
        resp = client.get("/api/smoke-reports/list", params={"profile_id": "alpha"})
        data = resp.json()
        for report in data["reports"]:
            assert report["profile_id"] == "alpha"

    def test_list_respects_limit(self, client, tmp_workspace):
        for _ in range(5):
            _save_smoke_report_to_disk(tmp_workspace, _make_smoke_report())
        resp = client.get("/api/smoke-reports/list", params={"limit": 2})
        data = resp.json()
        assert len(data["reports"]) <= 2

    def test_list_report_has_summary_fields(self, client, tmp_workspace):
        _save_smoke_report_to_disk(tmp_workspace, _make_smoke_report())
        resp = client.get("/api/smoke-reports/list")
        data = resp.json()
        report = data["reports"][0]
        assert "report_id" in report
        assert "server_url" in report
        assert "total_tests" in report
        assert "passed" in report
        assert "failed" in report
        assert "success_rate" in report
        assert "duration_ms" in report


class TestGetSmokeReport:
    """Tests for GET /api/smoke-reports/report/{report_id}."""

    def test_get_existing_report(self, client, tmp_workspace):
        report = _make_smoke_report()
        report_id = _save_smoke_report_to_disk(tmp_workspace, report)
        resp = client.get(f"/api/smoke-reports/report/{report_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == report_id

    def test_get_nonexistent_report(self, client):
        resp = client.get("/api/smoke-reports/report/nonexistent_id")
        assert resp.status_code == 404

    def test_get_report_has_tool_results(self, client, tmp_workspace):
        report = _make_smoke_report()
        report_id = _save_smoke_report_to_disk(tmp_workspace, report)
        resp = client.get(f"/api/smoke-reports/report/{report_id}")
        data = resp.json()
        assert "tool_results" in data
        assert len(data["tool_results"]) == 4


class TestDeleteSmokeReport:
    """Tests for DELETE /api/smoke-reports/report/{report_id}."""

    def test_delete_existing_report(self, client, tmp_workspace):
        report = _make_smoke_report()
        report_id = _save_smoke_report_to_disk(tmp_workspace, report)
        resp = client.delete(f"/api/smoke-reports/report/{report_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True

    def test_delete_nonexistent_report(self, client):
        resp = client.delete("/api/smoke-reports/report/nonexistent_id")
        assert resp.status_code == 404

    def test_delete_then_get_returns_404(self, client, tmp_workspace):
        report = _make_smoke_report()
        report_id = _save_smoke_report_to_disk(tmp_workspace, report)
        client.delete(f"/api/smoke-reports/report/{report_id}")
        resp = client.get(f"/api/smoke-reports/report/{report_id}")
        assert resp.status_code == 404


class TestClearAllSmokeReports:
    """Tests for DELETE /api/smoke-reports/clear."""

    def test_clear_empty(self, client):
        resp = client.delete("/api/smoke-reports/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 0

    def test_clear_all(self, client, tmp_workspace):
        for _ in range(3):
            _save_smoke_report_to_disk(tmp_workspace, _make_smoke_report())
        resp = client.delete("/api/smoke-reports/clear")
        data = resp.json()
        assert data["deleted"] == 3

    def test_clear_then_list_is_empty(self, client, tmp_workspace):
        for _ in range(3):
            _save_smoke_report_to_disk(tmp_workspace, _make_smoke_report())
        client.delete("/api/smoke-reports/clear")
        resp = client.get("/api/smoke-reports/list")
        data = resp.json()
        assert data["total"] == 0
