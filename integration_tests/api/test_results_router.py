"""Tests for results endpoints (save, list, get, history, compare, delete)."""

import json


def _make_test_run_payload(test_file="health/test.yaml", passed=2, failed=1):
    """Build a minimal test run payload for saving."""
    return {
        "test_file": test_file,
        "test_file_path": f"/tmp/tests/{test_file}",
        "provider": "claude-cli",
        "model": "claude-sonnet-4-20250514",
        "mcp_profile": "test",
        "results": [
            {
                "test_name": f"test_{i}",
                "passed": i < passed,
                "score": 1.0 if i < passed else 0.0,
                "duration": 1.5,
                "cost": 0.001,
                "token_usage": {"total": 100},
            }
            for i in range(passed + failed)
        ],
        "summary": {"passed": passed, "failed": failed},
    }


class TestSaveTestRun:
    """Tests for POST /api/results/save."""

    def test_save_returns_200(self, client):
        resp = client.post("/api/results/save", json=_make_test_run_payload())
        assert resp.status_code == 200

    def test_save_returns_run_id(self, client):
        resp = client.post("/api/results/save", json=_make_test_run_payload())
        data = resp.json()
        assert "run_id" in data
        assert data["saved"] is True

    def test_save_creates_file(self, client, tmp_workspace):
        resp = client.post("/api/results/save", json=_make_test_run_payload())
        run_id = resp.json()["run_id"]
        result_file = tmp_workspace / "tests" / ".results" / f"{run_id}.json"
        assert result_file.exists()

    def test_save_file_content_valid_json(self, client, tmp_workspace):
        resp = client.post("/api/results/save", json=_make_test_run_payload())
        run_id = resp.json()["run_id"]
        result_file = tmp_workspace / "tests" / ".results" / f"{run_id}.json"
        with open(result_file) as f:
            data = json.load(f)
        assert "metadata" in data
        assert "results" in data
        assert "summary" in data

    def test_save_metadata_fields(self, client):
        resp = client.post("/api/results/save", json=_make_test_run_payload())
        run_id = resp.json()["run_id"]
        get_resp = client.get(f"/api/results/run/{run_id}")
        meta = get_resp.json()["metadata"]
        assert meta["provider"] == "claude-cli"
        assert meta["model"] == "claude-sonnet-4-20250514"
        assert meta["test_file"] == "health/test.yaml"
        assert meta["total_tests"] == 3
        assert meta["passed"] == 2
        assert meta["failed"] == 1

    def test_save_empty_results(self, client):
        payload = _make_test_run_payload(passed=0, failed=0)
        payload["results"] = []
        payload["summary"] = {"passed": 0, "failed": 0}
        resp = client.post("/api/results/save", json=payload)
        assert resp.status_code == 200


class TestListTestRuns:
    """Tests for GET /api/results/list."""

    def test_list_empty(self, client):
        resp = client.get("/api/results/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data

    def test_list_after_save(self, client):
        client.post("/api/results/save", json=_make_test_run_payload())
        resp = client.get("/api/results/list")
        data = resp.json()
        assert data["total"] >= 1

    def test_list_filter_by_test_file(self, client):
        client.post(
            "/api/results/save",
            json=_make_test_run_payload(test_file="a/test.yaml"),
        )
        client.post(
            "/api/results/save",
            json=_make_test_run_payload(test_file="b/test.yaml"),
        )
        resp = client.get("/api/results/list", params={"test_file": "a/test.yaml"})
        data = resp.json()
        for run in data["runs"]:
            assert run["test_file"] == "a/test.yaml"

    def test_list_respects_limit(self, client):
        for _ in range(5):
            client.post("/api/results/save", json=_make_test_run_payload())
        resp = client.get("/api/results/list", params={"limit": 2})
        data = resp.json()
        assert len(data["runs"]) <= 2


class TestGetTestRun:
    """Tests for GET /api/results/run/{run_id}."""

    def test_get_existing_run(self, client):
        save_resp = client.post("/api/results/save", json=_make_test_run_payload())
        run_id = save_resp.json()["run_id"]
        resp = client.get(f"/api/results/run/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["run_id"] == run_id

    def test_get_nonexistent_run(self, client):
        resp = client.get("/api/results/run/nonexistent_id")
        assert resp.status_code == 404


class TestTestHistory:
    """Tests for GET /api/results/history/{test_file}."""

    def test_history_returns_200(self, client):
        resp = client.get("/api/results/history/health/test.yaml")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert data["test_file"] == "health/test.yaml"

    def test_history_after_multiple_saves(self, client):
        for _ in range(3):
            client.post("/api/results/save", json=_make_test_run_payload())
        resp = client.get("/api/results/history/health/test.yaml")
        data = resp.json()
        assert data["total"] == 3

    def test_history_has_pass_rate(self, client):
        client.post("/api/results/save", json=_make_test_run_payload())
        resp = client.get("/api/results/history/health/test.yaml")
        data = resp.json()
        entry = data["history"][0]
        assert "pass_rate" in entry
        assert 0 <= entry["pass_rate"] <= 1


class TestCompareRuns:
    """Tests for GET /api/results/compare."""

    def test_compare_two_runs(self, client):
        r1 = client.post("/api/results/save", json=_make_test_run_payload()).json()
        r2 = client.post("/api/results/save", json=_make_test_run_payload()).json()
        resp = client.get(
            "/api/results/compare",
            params={"run_ids": f"{r1['run_id']},{r2['run_id']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "tests" in data
        assert len(data["runs"]) == 2

    def test_compare_too_few_ids(self, client):
        r1 = client.post("/api/results/save", json=_make_test_run_payload()).json()
        resp = client.get("/api/results/compare", params={"run_ids": r1["run_id"]})
        assert resp.status_code == 400

    def test_compare_nonexistent_ids(self, client):
        resp = client.get("/api/results/compare", params={"run_ids": "fake1,fake2"})
        assert resp.status_code == 404


class TestDeleteTestRun:
    """Tests for DELETE /api/results/run/{run_id}."""

    def test_delete_existing_run(self, client):
        save_resp = client.post("/api/results/save", json=_make_test_run_payload())
        run_id = save_resp.json()["run_id"]
        resp = client.delete(f"/api/results/run/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True

    def test_delete_nonexistent_run(self, client):
        resp = client.delete("/api/results/run/nonexistent_id")
        assert resp.status_code == 404

    def test_delete_then_get_returns_404(self, client):
        save_resp = client.post("/api/results/save", json=_make_test_run_payload())
        run_id = save_resp.json()["run_id"]
        client.delete(f"/api/results/run/{run_id}")
        resp = client.get(f"/api/results/run/{run_id}")
        assert resp.status_code == 404
