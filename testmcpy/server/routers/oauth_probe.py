"""UI adapter for the shared, versioned OAuth/MCP smoke probe."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from testmcpy_oauth_probe.config import ConfigError
from testmcpy_oauth_probe.models import Correlation

from testmcpy.oauth_probe import (
    ProbeRunner,
    loads_manifest,
    manifest_json_schema,
    report_json_schema,
)

router = APIRouter(prefix="/api/oauth-probe", tags=["oauth-probe"])

_MAX_MANIFEST_BYTES = 1_048_576


class ManifestRequest(BaseModel):
    manifest: str = Field(min_length=1)


class ProbeRequest(ManifestRequest):
    targets: list[str] | None = None
    profile: str | None = None
    run_id: str | None = None
    service: str | None = None
    region: str | None = None
    revision: str | None = None
    deployment_id: str | None = None


def _load(content: str):
    if len(content.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        raise HTTPException(status_code=413, detail="Manifest exceeds the 1 MiB limit")
    try:
        return loads_manifest(content, source="UI request")
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/schema/{kind}")
async def schema(kind: Literal["manifest", "report"]):
    return report_json_schema() if kind == "report" else manifest_json_schema()


@router.post("/validate")
async def validate(request: ManifestRequest):
    manifest = _load(request.manifest)
    return {
        "valid": True,
        "schema": manifest.schema,
        "targets": list(manifest.targets),
        "profiles": list(manifest.profiles),
    }


@router.post("/check")
async def check(request: ProbeRequest):
    manifest = _load(request.manifest)
    try:
        report = await ProbeRunner().run_manifest(
            manifest,
            target_ids=request.targets,
            profile=request.profile,
            run_id=request.run_id,
            correlation_override=Correlation(
                service=request.service,
                region=request.region,
                revision=request.revision,
                deployment_id=request.deployment_id,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.to_dict()
