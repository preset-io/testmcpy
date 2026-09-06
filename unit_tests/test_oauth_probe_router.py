"""HTTP adapter coverage for the OAuth probe UI API."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402, I001
from fastapi.testclient import TestClient  # noqa: E402

from testmcpy.server.routers import oauth_probe  # noqa: E402


MANIFEST = """schema: testmcpy.io/oauth-smoke/v1
targets:
  edge:
    mcp_url: https://mcp.example.test/mcp
    oauth:
      flow: none
"""


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(oauth_probe.router)
    return TestClient(app)


def test_schema_and_validate_endpoints() -> None:
    client = _client()
    manifest_schema = client.get("/api/oauth-probe/schema/manifest")
    report_schema = client.get("/api/oauth-probe/schema/report")
    validated = client.post("/api/oauth-probe/validate", json={"manifest": MANIFEST})

    assert manifest_schema.status_code == report_schema.status_code == 200
    assert manifest_schema.json()["$id"] == "testmcpy.io/oauth-smoke/v1"
    assert report_schema.json()["$id"] == "testmcpy.io/oauth-smoke-report/v1"
    assert validated.json() == {
        "valid": True,
        "schema": "testmcpy.io/oauth-smoke/v1",
        "targets": ["edge"],
        "profiles": [],
    }


def test_validate_rejects_invalid_and_oversized_manifests() -> None:
    client = _client()
    invalid = client.post("/api/oauth-probe/validate", json={"manifest": "not: [yaml"})
    oversized = client.post(
        "/api/oauth-probe/validate",
        json={"manifest": "é" * (oauth_probe._MAX_MANIFEST_BYTES // 2 + 1)},
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]
    assert oversized.status_code == 413
    assert "1 MiB" in oversized.json()["detail"]


def test_check_forwards_selection_and_correlation() -> None:
    report = Mock()
    report.to_dict.return_value = {"schema": "testmcpy.io/oauth-smoke-report/v1"}
    run_manifest = AsyncMock(return_value=report)
    with patch.object(oauth_probe, "ProbeRunner") as runner_type:
        runner_type.return_value.run_manifest = run_manifest
        response = _client().post(
            "/api/oauth-probe/check",
            json={
                "manifest": MANIFEST,
                "targets": ["edge"],
                "profile": "strict",
                "run_id": "run-7",
                "service": "gateway",
                "region": "us-east-1",
                "revision": "abc",
                "deployment_id": "dep-1",
            },
        )

    assert response.status_code == 200
    assert response.json()["schema"].endswith("report/v1")
    kwargs = run_manifest.await_args.kwargs
    assert kwargs["target_ids"] == ["edge"]
    assert kwargs["profile"] == "strict"
    assert kwargs["run_id"] == "run-7"
    correlation = kwargs["correlation_override"]
    assert correlation.service == "gateway"
    assert correlation.region == "us-east-1"
    assert correlation.revision == "abc"
    assert correlation.deployment_id == "dep-1"


def test_check_turns_selection_errors_into_422() -> None:
    with patch.object(oauth_probe, "ProbeRunner") as runner_type:
        runner_type.return_value.run_manifest = AsyncMock(
            side_effect=ValueError("Unknown target: missing")
        )
        response = _client().post(
            "/api/oauth-probe/check", json={"manifest": MANIFEST, "targets": ["missing"]}
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown target: missing"}
