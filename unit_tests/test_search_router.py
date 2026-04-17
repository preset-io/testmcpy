"""
Unit tests for the search endpoint (Cmd+K command palette).
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Create a test client with temporary test directory."""
    # Create test files
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health_check.yaml").write_text(
        'version: "1.0"\ntests:\n  - name: test_basic_health\n    prompt: "Check health"\n'
    )
    subfolder = tests_dir / "charts"
    subfolder.mkdir()
    (subfolder / "chart_tests.yaml").write_text(
        'version: "1.0"\ntests:\n  - name: test_list_charts\n    prompt: "List charts"\n'
    )

    with patch.object(Path, "cwd", return_value=tmp_path):
        from fastapi import FastAPI

        from testmcpy.server.routers.search import router

        app = FastAPI()
        app.include_router(router)
        yield TestClient(app)


def test_search_pages(client):
    """Search should return matching pages."""
    res = client.get("/api/search?q=reports")
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) > 0
    page_results = [r for r in data["results"] if r["type"] == "page"]
    assert any("Reports" in r["name"] for r in page_results)


def test_search_test_files(client):
    """Search should find test files by name."""
    res = client.get("/api/search?q=health")
    assert res.status_code == 200
    data = res.json()
    test_results = [r for r in data["results"] if r["type"] == "test"]
    assert len(test_results) > 0


def test_search_test_names(client):
    """Search should find tests by test case name."""
    res = client.get("/api/search?q=list_charts")
    assert res.status_code == 200
    data = res.json()
    test_results = [r for r in data["results"] if r["type"] == "test"]
    assert any("test_list_charts" in r["name"] for r in test_results)


def test_search_empty_query_rejected(client):
    """Empty query should be rejected."""
    res = client.get("/api/search?q=")
    assert res.status_code == 422


def test_search_no_results(client):
    """Query with no matches returns empty results."""
    res = client.get("/api/search?q=zzzznonexistent")
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 0


def test_search_deduplicates(client):
    """Results should be deduplicated."""
    res = client.get("/api/search?q=test")
    assert res.status_code == 200
    data = res.json()
    seen = set()
    for r in data["results"]:
        key = (r["type"], r["name"], r["url"])
        assert key not in seen, f"Duplicate result: {key}"
        seen.add(key)
