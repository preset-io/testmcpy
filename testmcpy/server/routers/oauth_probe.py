"""UI adapter for the shared, versioned OAuth/MCP smoke probe."""

from __future__ import annotations

import os
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
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
_ENV_SUBSTITUTION = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}")


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


def _load(content: str, *, web_safe: bool = False):
    if len(content.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        raise HTTPException(status_code=413, detail="Manifest exceeds the 1 MiB limit")
    if web_safe and _ENV_SUBSTITUTION.search(content):
        raise HTTPException(
            status_code=422,
            detail="Environment substitution is not available through the web adapter",
        )
    try:
        manifest = loads_manifest(content, source="UI request")
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if web_safe and any(
        target.allow_http_loopback or target.allow_private_network
        for target in manifest.targets.values()
    ):
        raise HTTPException(
            status_code=422,
            detail="Loopback and private-network targets are not available through the web adapter",
        )
    return manifest


def _require_probe_auth(authorization: str | None) -> None:
    api_key = os.environ.get("TESTMCPY_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OAuth probe execution requires TESTMCPY_API_KEY",
        )
    scheme, _, credential = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(credential, api_key):
        raise HTTPException(status_code=401, detail="Invalid OAuth probe credentials")


@router.get("/schema/{kind}")
async def schema(kind: Literal["manifest", "report"]):
    return report_json_schema() if kind == "report" else manifest_json_schema()


@router.post("/validate")
async def validate(request: ManifestRequest):
    manifest = _load(request.manifest, web_safe=True)
    return {
        "valid": True,
        "schema": manifest.schema,
        "targets": list(manifest.targets),
        "profiles": list(manifest.profiles),
    }


@router.post("/check")
async def check(request: ProbeRequest, authorization: str | None = Header(default=None)):
    _require_probe_auth(authorization)
    manifest = _load(request.manifest, web_safe=True)
    try:
        # The web adapter never inherits server credentials. Secret-bearing
        # probes belong in the CLI, where the manifest author controls the process.
        report = await ProbeRunner(environ={}).run_manifest(
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
