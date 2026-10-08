"""Guards the tag-driven PyPI Trusted Publishing release path.

Covers four things that together make a release safe:

* ``scripts/release_check.py``  -- tag/version validation and artifact verification
* ``scripts/update_homebrew_formula.py`` -- formula url+sha256 sync
* ``.github/workflows/publish.yml`` -- privilege separation, pinning, ordering, and the
  real shell of the verify / dependency-gate steps (executed, not just inspected)
* ``scripts/publish.sh`` -- prepares and tags a release but never uploads

Nothing here talks to PyPI, TestPyPI or GitHub; HTTP is served from localhost.
"""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github/workflows/publish.yml"
PUBLISH_SH = REPO_ROOT / "scripts/publish.sh"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


release_check = _load("release_check")
update_formula = _load("update_homebrew_formula")


# --------------------------------------------------------------------------- helpers


def _write_repo(
    root: Path, *, main: str = "0.2.0", probe: str = "0.1.0", pin: str = ">=0.1.0,<0.2.0"
) -> None:
    (root / "oauth-probe").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "testmcpy"\nversion = "{main}"\n'
        f'dependencies = [\n    "testmcpy-oauth-probe{pin}",\n    "httpx>=0.27",\n]\n'
    )
    (root / "oauth-probe" / "pyproject.toml").write_text(
        f'[project]\nname = "testmcpy-oauth-probe"\nversion = "{probe}"\ndependencies = []\n'
    )


def _fake_dist(
    directory: Path, name: str, version: str, *, meta_version: str | None = None
) -> None:
    """A minimal wheel + sdist with real, parseable metadata."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = name.replace("-", "_")
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {meta_version or version}\n\nbody\n"
    with zipfile.ZipFile(directory / f"{stem}-{version}-py3-none-any.whl", "w") as wheel:
        wheel.writestr(f"{stem}-{version}.dist-info/METADATA", metadata)
    with tarfile.open(directory / f"{stem}-{version}.tar.gz", "w:gz") as sdist:
        data = metadata.encode()
        info = tarfile.TarInfo(f"{stem}-{version}/PKG-INFO")
        info.size = len(data)
        sdist.addfile(info, io.BytesIO(data))


def _write_release_dir(
    release: Path, plan: dict[str, Any], *, versions: dict[str, str] | None = None
) -> None:
    release.mkdir(parents=True, exist_ok=True)
    (release / "plan.json").write_text(json.dumps(plan))
    for dist in plan["distributions"]:
        version = (versions or {}).get(dist["name"], dist["version"])
        _fake_dist(release / dist["dir"], dist["name"], version)
    sums = subprocess.run(
        "find . -type f ! -name SHA256SUMS | sort | xargs sha256sum",
        shell=True,
        cwd=release,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (release / "SHA256SUMS").write_text(sums)


PROBE = {"name": "testmcpy-oauth-probe", "version": "0.1.0", "dir": "probe"}
MAIN = {"name": "testmcpy", "version": "0.2.0", "dir": "testmcpy"}


def _plan(tag: str, *dists: dict[str, str]) -> dict[str, Any]:
    return {
        "tag": tag,
        "probe_version": "0.1.0",
        "probe_requirement": ">=0.1.0,<0.2.0",
        "distributions": list(dists),
    }


@pytest.fixture
def pypi(monkeypatch: pytest.MonkeyPatch) -> set[tuple[str, str]]:
    """Stand-in for 'what is already on PyPI'; tests add (name, version) pairs."""
    released: set[tuple[str, str]] = set()
    monkeypatch.setattr(
        release_check, "pypi_has_version", lambda name, version, **_: (name, version) in released
    )
    return released


# --------------------------------------------------------------- tag / version planning


def test_main_tag_releases_probe_first_when_probe_is_unpublished(
    tmp_path: Path, pypi: set[tuple[str, str]]
) -> None:
    _write_repo(tmp_path)
    plan = release_check.build_plan(tmp_path, "v0.2.0")
    assert [d["name"] for d in plan["distributions"]] == ["testmcpy-oauth-probe", "testmcpy"]
    assert plan["probe_version"] == "0.1.0"


def test_independent_versions_skip_an_already_published_probe(
    tmp_path: Path, pypi: set[tuple[str, str]]
) -> None:
    """testmcpy 0.2.0 against an unchanged probe 0.1.0 must not re-upload the probe."""
    _write_repo(tmp_path)
    pypi.add(("testmcpy-oauth-probe", "0.1.0"))
    plan = release_check.build_plan(tmp_path, "v0.2.0")
    assert [d["name"] for d in plan["distributions"]] == ["testmcpy"]


def test_probe_only_tag_is_rejected(tmp_path: Path, pypi: set[tuple[str, str]]) -> None:
    """The `pypi` environment admits `v*` tags only, so `oauth-probe-v*` is not a release tag."""
    _write_repo(tmp_path, probe="0.1.3")
    with pytest.raises(release_check.ReleaseError, match="does not match"):
        release_check.build_plan(tmp_path, "oauth-probe-v0.1.3")


def test_an_unpublished_probe_is_released_with_the_next_main_tag(
    tmp_path: Path, pypi: set[tuple[str, str]]
) -> None:
    _write_repo(tmp_path, probe="0.1.3", pin=">=0.1.0,<0.2.0")
    plan = release_check.build_plan(tmp_path, "v0.2.0")
    assert [(d["name"], d["version"]) for d in plan["distributions"]] == [
        ("testmcpy-oauth-probe", "0.1.3"),
        ("testmcpy", "0.2.0"),
    ]


@pytest.mark.parametrize(
    "tag",
    [
        "v0.2.1",  # newer than the tree
        "v0.1.9",  # older than the tree
        "v1.0.0",
        "v0.2.0.1",
    ],
)
def test_tag_that_disagrees_with_the_package_version_fails(
    tmp_path: Path, pypi: set[tuple[str, str]], tag: str
) -> None:
    _write_repo(tmp_path)
    with pytest.raises(release_check.ReleaseError, match="mismatched|does not match"):
        release_check.build_plan(tmp_path, tag)


@pytest.mark.parametrize(
    "tag",
    [
        "0.2.0",
        "v0.2",
        "v0.2.0-beta",
        "vX.Y.Z",
        "release-0.2.0",
        "oauth-probe-0.1.0",
        "oauth-probe-v0.1.0",  # probe-only tags are not accepted
        "oauth-probe-v0.2.0",
        "v0.2.0 ",
        "",
    ],
)
def test_malformed_tags_are_rejected(tmp_path: Path, pypi: set[tuple[str, str]], tag: str) -> None:
    _write_repo(tmp_path)
    with pytest.raises(release_check.ReleaseError, match="does not match"):
        release_check.build_plan(tmp_path, tag)


def test_prerelease_tags_are_supported(tmp_path: Path, pypi: set[tuple[str, str]]) -> None:
    _write_repo(tmp_path, main="0.3.0rc1")
    plan = release_check.build_plan(tmp_path, "v0.3.0rc1")
    assert plan["distributions"][-1]["version"] == "0.3.0rc1"


def test_releasing_a_version_already_on_pypi_fails(
    tmp_path: Path, pypi: set[tuple[str, str]]
) -> None:
    _write_repo(tmp_path)
    pypi.add(("testmcpy", "0.2.0"))
    with pytest.raises(release_check.ReleaseError, match="already on PyPI"):
        release_check.build_plan(tmp_path, "v0.2.0")


def test_pin_that_excludes_the_in_tree_probe_fails(
    tmp_path: Path, pypi: set[tuple[str, str]]
) -> None:
    """Bumping the probe past testmcpy's pin would publish an uninstallable testmcpy."""
    _write_repo(tmp_path, probe="0.2.0", pin=">=0.1.0,<0.2.0")
    with pytest.raises(release_check.ReleaseError, match="excludes the in-tree"):
        release_check.build_plan(tmp_path, "v0.2.0")


def test_the_real_tree_plans_cleanly(pypi: set[tuple[str, str]]) -> None:
    """Whatever versions are in the tree, their own tags must validate."""
    main = release_check.read_project(REPO_ROOT)["version"]
    probe = release_check.read_project(REPO_ROOT, "oauth-probe")["version"]
    assert release_check.build_plan(REPO_ROOT, f"v{main}")["distributions"][-1]["version"] == main
    plan = release_check.build_plan(REPO_ROOT, f"v{main}")
    assert plan["probe_version"] == probe


def test_pypi_lookup_distinguishes_missing_from_broken() -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            status = {"/pypi/pkg/1.0/json": 200, "/pypi/pkg/2.0/json": 404}.get(self.path, 503)
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert release_check.pypi_has_version("pkg", "1.0", index=base) is True
        assert release_check.pypi_has_version("pkg", "2.0", index=base) is False
        with pytest.raises(release_check.ReleaseError, match="HTTP 503"):
            release_check.pypi_has_version("pkg", "3.0", index=base)  # never guess on errors
    finally:
        server.shutdown()


# -------------------------------------------------------------------- artifact verification


def test_verify_dists_accepts_matching_artifacts(tmp_path: Path) -> None:
    plan = _plan("v0.2.0", PROBE, MAIN)
    _write_release_dir(tmp_path, plan)
    release_check.verify_dists(plan, tmp_path)


def test_verify_dists_rejects_a_wrong_version_inside_the_metadata(tmp_path: Path) -> None:
    """Filenames can lie; the version that pip reads is in the metadata."""
    plan = _plan("v0.2.0", MAIN)
    release = tmp_path / "release"
    release.mkdir()
    _fake_dist(release / "testmcpy", "testmcpy", "0.2.0", meta_version="0.1.9")
    with pytest.raises(release_check.ReleaseError, match="metadata says"):
        release_check.verify_dists(plan, release)


def test_verify_dists_rejects_a_stale_artifact_version(tmp_path: Path) -> None:
    plan = _plan("v0.2.0", MAIN)
    release = tmp_path / "release"
    release.mkdir()
    _fake_dist(release / "testmcpy", "testmcpy", "0.1.9")
    with pytest.raises(release_check.ReleaseError, match="not testmcpy 0.2.0|are not"):
        release_check.verify_dists(plan, release)


def test_verify_dists_rejects_unplanned_or_missing_files(tmp_path: Path) -> None:
    plan = _plan("v0.2.0", MAIN)
    _write_release_dir(tmp_path, plan)
    _fake_dist(tmp_path / "probe", "testmcpy-oauth-probe", "0.1.0")  # rides along uninvited
    with pytest.raises(release_check.ReleaseError, match="do not match plan"):
        release_check.verify_dists(plan, tmp_path)

    shutil.rmtree(tmp_path / "probe")
    next((tmp_path / "testmcpy").glob("*.tar.gz")).unlink()
    with pytest.raises(release_check.ReleaseError, match="exactly one wheel and one sdist"):
        release_check.verify_dists(plan, tmp_path)


@pytest.mark.skipif(
    not (shutil.which("python") and importlib.util.find_spec("build")),
    reason="`build` is not installed",
)
def test_real_builds_of_both_distributions_verify(tmp_path: Path) -> None:
    """Build the actual projects (no network: setuptools is already installed)."""
    if importlib.util.find_spec("setuptools") is None or importlib.util.find_spec("wheel") is None:
        pytest.skip("offline build needs setuptools and wheel installed")
    main = release_check.read_project(REPO_ROOT)["version"]
    probe = release_check.read_project(REPO_ROOT, "oauth-probe")["version"]
    plan = _plan(
        f"v{main}",
        {"name": "testmcpy-oauth-probe", "version": probe, "dir": "probe"},
        {"name": "testmcpy", "version": main, "dir": "testmcpy"},
    )
    for dist in plan["distributions"]:
        source = REPO_ROOT / "oauth-probe" if dist["dir"] == "probe" else REPO_ROOT
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                str(source),
                "--outdir",
                str(tmp_path / dist["dir"]),
            ],
            check=True,
            capture_output=True,
        )
    release_check.verify_dists(plan, tmp_path)


# ------------------------------------------------------------------- Homebrew formula sync

FORMULA = """class Testmcpy < Formula
  desc "demo"
  url "https://files.example.test/old/testmcpy-0.1.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "Apache-2.0"
end
"""


def _sdist_bytes(
    name: str = "testmcpy", version: str = "0.2.0", pkg_version: str | None = None
) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        data = (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {pkg_version or version}\n\n".encode()
        )
        info = tarfile.TarInfo(f"{name}-{version}/PKG-INFO")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


class _PyPI:
    """Tiny fake PyPI: JSON metadata + file download, with per-test overrides."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, bytes]] = {}
        self.metadata_hits = 0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.endswith("/json"):
                    outer.metadata_hits += 1
                status, body = outer.routes.get(self.path, (404, b"{}"))
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def publish(
        self,
        version: str,
        payload: bytes,
        *,
        digest: str | None = None,
        file_status: int = 200,
        file_body: bytes | None = None,
    ) -> None:
        file_path = f"/files/testmcpy-{version}.tar.gz"
        meta = {
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": f"{self.base}{file_path}",
                    "digests": {"sha256": digest or hashlib.sha256(payload).hexdigest()},
                }
            ]
        }
        self.routes[f"/pypi/testmcpy/{version}/json"] = (200, json.dumps(meta).encode())
        self.routes[file_path] = (file_status, payload if file_body is None else file_body)


@pytest.fixture
def fake_pypi() -> Iterator[_PyPI]:
    server = _PyPI()
    yield server
    server.server.shutdown()


def _formula(tmp_path: Path) -> Path:
    path = tmp_path / "testmcpy.rb"
    path.write_text(FORMULA)
    return path


def test_formula_url_and_sha_are_both_derived_from_the_real_sdist(
    tmp_path: Path, fake_pypi: _PyPI
) -> None:
    payload = _sdist_bytes()
    fake_pypi.publish("0.2.0", payload)
    formula = _formula(tmp_path)

    assert update_formula.update_formula(formula, "0.2.0", index=fake_pypi.base, attempts=1) is True

    text = formula.read_text()
    assert f'url "{fake_pypi.base}/files/testmcpy-0.2.0.tar.gz"' in text
    assert f'sha256 "{hashlib.sha256(payload).hexdigest()}"' in text
    assert "0.1.0" not in text, "the old url must not survive: url and sha256 move together"
    assert 'license "Apache-2.0"' in text  # untouched

    assert (
        update_formula.update_formula(formula, "0.2.0", index=fake_pypi.base, attempts=1) is False
    )


@pytest.mark.parametrize(
    "case",
    ["http_error", "empty_body", "digest_mismatch", "not_a_tarball", "wrong_version", "wrong_name"],
)
def test_formula_is_left_untouched_by_any_invalid_download(
    tmp_path: Path, fake_pypi: _PyPI, case: str
) -> None:
    good = _sdist_bytes()
    if case == "http_error":
        fake_pypi.publish("0.2.0", good, file_status=500)
    elif case == "empty_body":
        fake_pypi.publish("0.2.0", b"", digest=hashlib.sha256(b"").hexdigest())
    elif case == "digest_mismatch":
        fake_pypi.publish("0.2.0", good, digest="f" * 64)
    elif case == "not_a_tarball":
        junk = b"<html>CDN error page</html>"
        fake_pypi.publish("0.2.0", junk)
    elif case == "wrong_version":
        fake_pypi.publish("0.2.0", _sdist_bytes(pkg_version="0.1.0"))
    else:
        fake_pypi.publish("0.2.0", _sdist_bytes(name="other"))
    formula = _formula(tmp_path)

    with pytest.raises(update_formula.FormulaError):
        update_formula.update_formula(formula, "0.2.0", index=fake_pypi.base, attempts=1)
    assert formula.read_text() == FORMULA

    assert (
        update_formula.main(
            ["0.2.0", "--formula", str(formula), "--index", fake_pypi.base, "--attempts", "1"]
        )
        == 1
    ), "the CLI (what the workflow runs) must exit non-zero, not report success"


def test_formula_sync_waits_for_pypi_to_publish_the_release(
    tmp_path: Path, fake_pypi: _PyPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_formula.time, "sleep", lambda _: None)
    payload = _sdist_bytes()
    formula = _formula(tmp_path)
    original_get = update_formula._get
    calls = {"n": 0}

    def flaky(url: str) -> bytes:
        calls["n"] += 1
        if calls["n"] == 1:
            raise update_formula.FormulaError(f"GET {url} returned HTTP 404")
        return bytes(original_get(url))

    fake_pypi.publish("0.2.0", payload)
    monkeypatch.setattr(update_formula, "_get", flaky)
    assert update_formula.update_formula(
        formula, "0.2.0", index=fake_pypi.base, attempts=3, delay=0
    )

    # ... but a release that never appears is an error, not a skip.
    monkeypatch.setattr(update_formula, "_get", original_get)
    with pytest.raises(update_formula.FormulaError, match="404"):
        update_formula.update_formula(
            _formula(tmp_path), "9.9.9", index=fake_pypi.base, attempts=2, delay=0
        )


def test_formula_with_ambiguous_url_lines_is_rejected(tmp_path: Path, fake_pypi: _PyPI) -> None:
    fake_pypi.publish("0.2.0", _sdist_bytes())
    formula = tmp_path / "testmcpy.rb"
    formula.write_text(FORMULA + '  url "https://example.test/second.tar.gz"\n')
    with pytest.raises(update_formula.FormulaError, match="exactly one"):
        update_formula.update_formula(formula, "0.2.0", index=fake_pypi.base, attempts=1)


# ------------------------------------------------------------------------- workflow shape


def _workflow() -> dict[Any, Any]:
    workflow: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow


def _steps(job: str) -> list[dict[str, Any]]:
    return list(_workflow()["jobs"][job]["steps"])


def test_workflow_is_triggered_only_by_release_tags() -> None:
    triggers = _workflow()[True]  # PyYAML parses the bare key `on` as boolean True
    assert set(triggers) == {"push"}, "no release/workflow_dispatch/PR triggers"
    # The `pypi` environment's deployment policy admits only `v*` tags; any other tag
    # trigger would start a run that is rejected at the environment gate.
    assert triggers["push"]["tags"] == ["v*"]
    assert "branches" not in triggers["push"]


def test_workflow_consumes_no_pypi_token_or_twine() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("PYPI_API_TOKEN", "TWINE_", "twine upload", "secrets.", "password"):
        assert forbidden not in code, f"publish.yml must not reference {forbidden!r}"


def test_oidc_is_scoped_to_the_publish_job_only() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {}, "default token must start with no permissions"
    jobs = workflow["jobs"]
    assert set(jobs) == {"build", "publish", "homebrew"}
    assert jobs["publish"]["permissions"] == {"id-token": "write"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["homebrew"]["permissions"] == {"contents": "write"}
    for name in ("build", "homebrew"):
        assert "id-token" not in jobs[name]["permissions"]
        assert "environment" not in jobs[name]


def test_publish_job_is_approval_gated_and_runs_no_repository_code() -> None:
    job = _workflow()["jobs"]["publish"]
    assert job["environment"]["name"] == "pypi"
    assert job["needs"] == "build"

    uses = [step["uses"].split("@")[0] for step in job["steps"] if "uses" in step]
    assert set(uses) == {"actions/download-artifact", "pypa/gh-action-pypi-publish"}, (
        "the OIDC job must not check out or set up anything: it verifies and uploads"
    )
    for step in job["steps"]:
        run = step.get("run", "")
        assert "scripts/" not in run and "pip install" not in run, (
            "code from the repository or from PyPI must never run in the job that can mint "
            f"a PyPI upload token: {step.get('name')}"
        )


def test_every_action_is_pinned_to_a_full_commit_sha_with_a_version_comment() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", text, flags=re.MULTILINE)
    assert uses
    for ref, rest in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), f"{ref} is not pinned by SHA"
        assert re.match(r"\s*#\s*v\d", rest), f"{ref} needs its version in a trailing comment"
    assert any(ref.startswith("pypa/gh-action-pypi-publish@") for ref, _ in uses)


def test_publish_order_is_probe_then_dependency_gate_then_testmcpy() -> None:
    steps = _steps("publish")
    names = [step["name"] for step in steps]
    probe = names.index("Publish testmcpy-oauth-probe to PyPI")
    gate = names.index("Verify the probe dependency is installable from PyPI")
    main = names.index("Publish testmcpy to PyPI")
    assert probe < gate < main, "testmcpy hard-depends on the probe; it must go up last"
    assert steps[probe]["with"]["packages-dir"] == "release/probe/"
    assert steps[main]["with"]["packages-dir"] == "release/testmcpy/"
    for index in (probe, main):
        assert "skip-existing" not in steps[index]["with"], (
            "skip-existing would hide an artifact that differs from what is on PyPI"
        )


def test_build_job_validates_tests_builds_and_hands_off_by_artifact() -> None:
    steps = _steps("build")
    runs = "\n".join(step.get("run", "") for step in steps)
    for expected in (
        "release_check.py plan",
        "release_check.py build",
        "release_check.py verify-dists",
        "twine check --strict",
        "pytest",
        "pip check",
    ):
        assert expected in runs, f"build job no longer does `{expected}`"
    upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact"))
    download = next(
        s for s in _steps("publish") if s.get("uses", "").startswith("actions/download-artifact")
    )
    assert upload["with"]["name"] == download["with"]["name"]
    assert upload["with"]["if-no-files-found"] == "error"
    assert _workflow()["jobs"]["homebrew"]["needs"] == ["build", "publish"]


def test_homebrew_job_cannot_swallow_failures() -> None:
    steps = _steps("homebrew")
    runs = "\n".join(step.get("run", "") for step in steps)
    assert "update_homebrew_formula.py" in runs
    assert "|| true" not in runs and "|| echo" not in runs, (
        "a failed download or push must fail the job, not be reported as success"
    )


# ------------------------------------------------- executing the real workflow shell steps


def _step_run(job: str, name: str) -> str:
    return str(next(step["run"] for step in _steps(job) if step.get("name") == name))


def _run_verify_step(tmp_path: Path, tag: str) -> tuple[subprocess.CompletedProcess[str], str]:
    output = tmp_path / "github_output"
    output.write_text("")
    env = dict(os.environ, GITHUB_REF_NAME=tag, GITHUB_OUTPUT=str(output))
    script = tmp_path / "verify.sh"
    script.write_text(
        "set -euo pipefail\n" + _step_run("publish", "Verify artifacts match the tag")
    )
    result = subprocess.run(
        ["bash", str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60
    )
    return result, output.read_text()


def test_publish_verify_step_accepts_a_consistent_release(tmp_path: Path) -> None:
    _write_release_dir(tmp_path / "release", _plan("v0.2.0", PROBE, MAIN))
    result, outputs = _run_verify_step(tmp_path, "v0.2.0")
    assert result.returncode == 0, result.stderr
    assert "publish_probe=true" in outputs
    assert "probe_version=0.1.0" in outputs


def test_publish_verify_step_supports_independent_versions(tmp_path: Path) -> None:
    _write_release_dir(tmp_path / "release", _plan("v0.2.0", MAIN))
    result, outputs = _run_verify_step(tmp_path, "v0.2.0")
    assert result.returncode == 0, result.stderr
    assert "publish_probe=false" in outputs


def test_publish_verify_step_rejects_a_probe_only_tag(tmp_path: Path) -> None:
    plan = _plan("oauth-probe-v0.1.0", PROBE)
    _write_release_dir(tmp_path / "release", plan)
    result, outputs = _run_verify_step(tmp_path, "oauth-probe-v0.1.0")
    assert result.returncode != 0
    assert "not a release tag" in result.stderr + result.stdout
    assert "publish_probe" not in outputs


@pytest.mark.parametrize(
    "scenario",
    [
        "tag_newer",
        "tag_malformed",
        "artifact_older",
        "tampered",
        "extra_file",
        "plan_for_other_tag",
    ],
)
def test_publish_verify_step_fails_on_any_mismatch(tmp_path: Path, scenario: str) -> None:
    plan = _plan("v0.2.0", PROBE, MAIN)
    tag = "v0.2.0"
    if scenario == "artifact_older":
        # Plan claims 0.2.0 but the files on disk are 0.1.9: must never "succeed".
        _write_release_dir(tmp_path / "release", plan, versions={"testmcpy": "0.1.9"})
    else:
        _write_release_dir(tmp_path / "release", plan)
    if scenario == "tag_newer":
        tag = "v0.2.1"
    elif scenario == "tag_malformed":
        tag = "v0.2"
    elif scenario == "tampered":
        wheel = next((tmp_path / "release" / "testmcpy").glob("*.whl"))
        wheel.write_bytes(wheel.read_bytes() + b"x")
    elif scenario == "extra_file":
        (tmp_path / "release" / "testmcpy" / "evil-1.0.tar.gz").write_bytes(b"x")
        (tmp_path / "release" / "SHA256SUMS").write_text(
            subprocess.run(
                "find . -type f ! -name SHA256SUMS | sort | xargs sha256sum",
                shell=True,
                cwd=tmp_path / "release",
                capture_output=True,
                text=True,
            ).stdout
        )
    elif scenario == "plan_for_other_tag":
        tag = "v0.2.0"
        plan_path = tmp_path / "release" / "plan.json"
        plan_path.write_text(json.dumps(_plan("v0.3.0", PROBE, MAIN)))
        (tmp_path / "release" / "SHA256SUMS").write_text(
            subprocess.run(
                "find . -type f ! -name SHA256SUMS | sort | xargs sha256sum",
                shell=True,
                cwd=tmp_path / "release",
                capture_output=True,
                text=True,
            ).stdout
        )
    result, outputs = _run_verify_step(tmp_path, tag)
    assert result.returncode != 0, f"{scenario}: verify step passed\n{result.stdout}"
    assert "publish_probe" not in outputs


def _run_dependency_gate(
    tmp_path: Path, *, pip_exit: int
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Execute the workflow's gate step with `python3 -m pip` and `sleep` stubbed."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    log = tmp_path / "calls.log"
    (fakebin / "python3").write_text(f'#!/bin/bash\necho "$*" >> "{log}"\nexit {pip_exit}\n')
    (fakebin / "sleep").write_text("#!/bin/bash\nexit 0\n")
    for tool in fakebin.iterdir():
        tool.chmod(0o755)
    script = tmp_path / "gate.sh"
    script.write_text(
        "set -euo pipefail\n"
        + _step_run("publish", "Verify the probe dependency is installable from PyPI")
    )
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", PROBE_VERSION="0.1.0")
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=60
    )
    return result, (log.read_text().splitlines() if log.exists() else [])


def test_dependency_gate_blocks_testmcpy_when_the_probe_never_resolves(tmp_path: Path) -> None:
    """This is the failure that shipped testmcpy 0.11.21 unresolvable."""
    result, calls = _run_dependency_gate(tmp_path, pip_exit=1)
    assert result.returncode != 0
    assert "refusing to publish testmcpy" in result.stdout
    assert len(calls) == 8, "should retry for index lag before giving up"
    assert all("testmcpy-oauth-probe==0.1.0" in call for call in calls), (
        "must check the exact in-tree probe version, not just any version in the pin's range"
    )


def test_dependency_gate_passes_once_the_probe_resolves(tmp_path: Path) -> None:
    result, calls = _run_dependency_gate(tmp_path, pip_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 1


def test_dependency_gate_downloads_only_wheels_without_dependencies(tmp_path: Path) -> None:
    result, calls = _run_dependency_gate(tmp_path, pip_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    args = shlex.split(calls[0])
    assert args[:3] == ["-m", "pip", "download"]
    assert "--no-deps" in args
    assert "--only-binary=:all:" in args, "sdist build backends must not run in the OIDC job"


def test_dependency_gate_rejects_a_source_only_probe_without_running_its_backend(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "backend-executed"
    files = {
        "pyproject.toml": (
            '[build-system]\nrequires = []\nbuild-backend = "backend"\nbackend-path = ["."]\n'
        ),
        "backend.py": (
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
            "raise RuntimeError('sdist backend must not execute')\n"
        ),
    }
    with tarfile.open(tmp_path / "testmcpy_oauth_probe-0.1.0.tar.gz", "w:gz") as sdist:
        for name, content in files.items():
            payload = content.encode()
            info = tarfile.TarInfo(f"testmcpy_oauth_probe-0.1.0/{name}")
            info.size = len(payload)
            sdist.addfile(info, io.BytesIO(payload))

    # Execute the actual workflow's pip command against an offline, source-only
    # index. The other gate tests exercise its surrounding retry shell.
    gate = _step_run("publish", "Verify the probe dependency is installable from PyPI")
    command = next(line.strip() for line in gate.splitlines() if "-m pip download" in line)
    args = shlex.split(command.removeprefix("if ").removesuffix("; then"))
    args[0] = sys.executable
    args[args.index("--dest") + 1] = str(tmp_path / "downloads")
    args[-1] = "testmcpy-oauth-probe==0.1.0"
    args.extend(["--no-index", "--find-links", str(tmp_path)])
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0, "a source-only probe must fail closed"
    assert not marker.exists(), result.stdout + result.stderr
    assert "No matching distribution found" in result.stderr


# ---------------------------------------------------------------------- scripts/publish.sh

_GIT_STUB = r"""#!/bin/bash
echo "git $*" >> "$CALL_LOG"
case "$1" in
  diff-index) exit "${DIRTY:-0}" ;;
  fetch) exit 0 ;;
  rev-parse)
    case "$*" in
      *--abbrev-ref*) echo "${BRANCH:-main}" ;;
      *"--verify refs/tags/"*) exit "${LOCAL_TAG_EXISTS:-1}" ;;
      *origin/main*) echo "${ORIGIN_SHA:-aaaa}" ;;
      *) echo "${HEAD_SHA:-aaaa}" ;;
    esac ;;
  ls-remote) exit "${REMOTE_TAG_EXISTS:-2}" ;;
  *) exit 0 ;;
esac
"""

_PYTHON_STUB = r"""#!/bin/bash
echo "python $*" >> "$CALL_LOG"
case "$*" in
  *release_check.py*plan*) exit "${PLAN_EXIT:-0}" ;;
  *"-m pytest"*) exit "${TESTS_EXIT:-0}" ;;
  *"-m ruff"*) exit "${LINT_EXIT:-0}" ;;
  *"-m twine upload"*) echo "UPLOAD ATTEMPTED" >> "$CALL_LOG"; exit 0 ;;
esac
exit 0
"""

_GH_STUB = r"""#!/bin/bash
set -f
echo "gh $*" >> "$CALL_LOG"
case "$1" in
  repo) echo "example/testmcpy" ;;
  api)
    case "$2" in
      */deployment-branch-policies)
        # The script's --jq already filters to tag policies; emit those names.
        case "${GH_POLICIES:-v*}" in
          none) ;;
          broken) echo "gh: server error (HTTP 500)" >&2; exit 1 ;;
          *) printf '%s\n' ${GH_POLICIES:-v*} ;;
        esac ;;
      *)
        case "${GH_MODE:-protected}" in
          protected) echo 1 ;;
          unprotected) echo 0 ;;
          missing) echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
          *) echo "gh: network down" >&2; exit 1 ;;
        esac ;;
    esac ;;
esac
"""


def _run_publish_sh(
    tmp_path: Path, *args: str, answer: str = "y\n", **env_overrides: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(PUBLISH_SH, repo / "scripts" / "publish.sh")
    _write_repo(repo, main="0.2.0", probe="0.1.0")
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for name, body in (("git", _GIT_STUB), ("python", _PYTHON_STUB), ("gh", _GH_STUB)):
        (fakebin / name).write_text(body)
        (fakebin / name).chmod(0o755)
    log = tmp_path / "calls.log"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", CALL_LOG=str(log))
    env.update(env_overrides)
    result = subprocess.run(
        ["bash", str(repo / "scripts" / "publish.sh"), *args],
        cwd=repo,
        input=answer,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return result, (log.read_text().splitlines() if log.exists() else [])


def _mutations(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith(("git tag", "git push"))]


def test_publish_sh_never_uploads_anything() -> None:
    code = "\n".join(
        line for line in PUBLISH_SH.read_text().splitlines() if not line.lstrip().startswith("#")
    )
    assert "twine upload" not in code
    assert "pypirc" not in code and "PYPI" not in code
    assert "git push origin ${BRANCH}" not in code, "only the tag is pushed"


def test_publish_sh_tags_locally_and_pushes_only_the_tag_after_confirmation(tmp_path: Path) -> None:
    result, calls = _run_publish_sh(tmp_path, answer="y\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "git tag -a v0.2.0 -m Release v0.2.0" in calls
    pushes = [c for c in calls if c.startswith("git push")]
    assert pushes == ["git push origin refs/tags/v0.2.0"]
    assert not any("UPLOAD" in c or "upload" in c for c in calls)

    build = next(i for i, c in enumerate(calls) if "release_check.py build" in c)
    verify = next(i for i, c in enumerate(calls) if "release_check.py verify-dists" in c)
    tag = calls.index("git tag -a v0.2.0 -m Release v0.2.0")
    assert build < verify < tag, "artifacts are built and verified before any tag exists"
    assert any("twine check" in c for c in calls)


@pytest.mark.parametrize("answer", ["n\n", "\n", ""])
def test_publish_sh_does_not_push_without_explicit_confirmation(
    tmp_path: Path, answer: str
) -> None:
    result, calls = _run_publish_sh(tmp_path, answer=answer)
    assert result.returncode == 0
    assert "git tag -a v0.2.0 -m Release v0.2.0" in calls
    assert not [c for c in calls if c.startswith("git push")]
    assert "git push origin refs/tags/v0.2.0" in result.stdout, "tells the maintainer how to push"


def test_publish_sh_dry_run_creates_and_pushes_nothing(tmp_path: Path) -> None:
    result, calls = _run_publish_sh(tmp_path, "--dry-run", GH_MODE="missing")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not _mutations(calls)
    assert "does not exist yet" in result.stdout  # reported, but dry-run still passes
    assert any("release_check.py build" in c for c in calls)


def test_publish_sh_probe_only_is_gone(tmp_path: Path) -> None:
    """No probe-only release: the `pypi` environment admits `v*` tags only."""
    result, calls = _run_publish_sh(tmp_path, "--probe-only")
    assert result.returncode != 0
    assert "v* is the only release tag" in result.stdout + result.stderr
    assert not _mutations(calls)
    assert not any("oauth-probe-v" in c for c in calls)


def test_publish_sh_only_ever_tags_with_v_star(tmp_path: Path) -> None:
    result, calls = _run_publish_sh(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not any("oauth-probe-v" in c for c in calls)
    assert any("--tag v0.2.0" in c for c in calls)


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"BRANCH": "feature"}, "main"),
        ({"DIRTY": "1"}, "uncommitted"),
        ({"ORIGIN_SHA": "bbbb"}, "origin/main"),
        ({"LOCAL_TAG_EXISTS": "0"}, "already exists locally"),
        ({"REMOTE_TAG_EXISTS": "0"}, "already exists on origin"),
        ({"PLAN_EXIT": "1"}, "plan validation"),
        ({"TESTS_EXIT": "1"}, ""),
        ({"LINT_EXIT": "1"}, ""),
        ({"GH_MODE": "missing"}, "does not exist"),
        ({"GH_MODE": "unprotected"}, "no required reviewers"),
        ({"GH_MODE": "broken"}, "Could not read"),
        ({"GH_POLICIES": "none"}, "no tag deployment policy covering v0.2.0"),
        ({"GH_POLICIES": "release-* oauth-probe-v*"}, "no tag deployment policy covering v0.2.0"),
        ({"GH_POLICIES": "broken"}, "deployment policies"),
    ],
)
def test_publish_sh_refuses_and_creates_no_tag(
    tmp_path: Path, env: dict[str, str], message: str
) -> None:
    result, calls = _run_publish_sh(tmp_path, **env)
    assert result.returncode != 0, result.stdout
    assert message in result.stdout + result.stderr
    assert not _mutations(calls)


@pytest.mark.parametrize("policies", ["v*", "v0.2.0", "release-* v*"])
def test_publish_sh_accepts_a_tag_policy_that_covers_the_tag(tmp_path: Path, policies: str) -> None:
    result, calls = _run_publish_sh(tmp_path, GH_POLICIES=policies)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "git push origin refs/tags/v0.2.0" in calls


def test_publish_sh_env_check_can_be_bypassed_only_explicitly(tmp_path: Path) -> None:
    result, calls = _run_publish_sh(tmp_path, GH_MODE="missing", RELEASE_SKIP_ENV_CHECK="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "git push origin refs/tags/v0.2.0" in calls


def test_publish_sh_skip_tests_skips_lint_and_pytest(tmp_path: Path) -> None:
    result, calls = _run_publish_sh(tmp_path, "--skip-tests", "--dry-run")
    assert result.returncode == 0
    assert not any("-m pytest" in c or "-m ruff" in c for c in calls)
    result, calls = _run_publish_sh(tmp_path / "again", "--dry-run")
    assert any("-m pytest" in c for c in calls)
