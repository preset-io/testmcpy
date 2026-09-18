"""Guards the two-distribution split that makes the probe adoptable.

`testmcpy_oauth_probe` imports only httpx and pyyaml, but for as long as the
only way to obtain the `testmcpy-oauth` console script was `pip install
testmcpy`, installing it also resolved the agent/server stack — sqlalchemy,
fastmcp, anthropic, textual, uvicorn and the rest. Release pipelines that pin
conflicting versions of those libraries could not install the probe at all.

These assertions are about packaging metadata rather than behaviour, because
that is exactly where the defect lived: nothing in the runtime was wrong.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.version import Version

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on the 3.10 CI leg
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO_ROOT / "oauth-probe"
PROBE_DIST = "testmcpy-oauth-probe"
CONSOLE_SCRIPT = "testmcpy-oauth"

# Distributions whose presence in the probe's dependency closure would defeat
# the split. These are the ones that actually blocked adoption.
FORBIDDEN_PROBE_DEPENDENCIES = frozenset(
    {
        "alembic",
        "anthropic",
        "claude-agent-sdk",
        "fastapi",
        "fastmcp",
        "google-adk",
        "mcp",
        "ollama",
        "openai-agents",
        "sqlalchemy",
        "starlette",
        "testmcpy",
        "textual",
        "typer",
        "uvicorn",
    }
)


def _pyproject(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def probe_project() -> dict[str, Any]:
    return _pyproject(PROBE_DIR / "pyproject.toml")


@pytest.fixture(scope="module")
def root_project() -> dict[str, Any]:
    return _pyproject(REPO_ROOT / "pyproject.toml")


def _canonical(name: str) -> str:
    return name.lower().replace("_", "-")


def test_probe_distribution_declares_only_httpx_and_pyyaml(probe_project: dict[str, Any]) -> None:
    project = probe_project["project"]
    assert project["name"] == PROBE_DIST
    required = {_canonical(Requirement(item).name) for item in project["dependencies"]}
    assert required == {"httpx", "pyyaml"}, (
        "the probe is release-pipeline infrastructure; its dependency closure is "
        f"part of its contract, but it now declares: {sorted(required)}"
    )
    assert not project.get("optional-dependencies"), (
        "an extra on this distribution would reintroduce a way to install the "
        "heavy stack through the probe's own name"
    )


def test_probe_distribution_owns_the_console_script(probe_project: dict[str, Any]) -> None:
    scripts = probe_project["project"]["scripts"]
    assert scripts[CONSOLE_SCRIPT] == "testmcpy_oauth_probe.cli:main"


def test_testmcpy_does_not_also_ship_the_probe(root_project: dict[str, Any]) -> None:
    """Two distributions must not both install `testmcpy_oauth_probe`."""
    find = root_project["tool"]["setuptools"]["packages"]["find"]
    assert "oauth-probe" not in find["where"], (
        "testmcpy is vendoring the probe package again; a consumer installing "
        "both distributions would get the same import package twice"
    )
    package_data = root_project["tool"]["setuptools"]["package-data"]
    assert "testmcpy_oauth_probe" not in package_data

    scripts = root_project["project"]["scripts"]
    assert CONSOLE_SCRIPT not in scripts, (
        f"{CONSOLE_SCRIPT} belongs to {PROBE_DIST}; declaring it here too makes "
        "two distributions fight over one console script"
    )


def test_testmcpy_depends_on_the_published_probe(
    root_project: dict[str, Any], probe_project: dict[str, Any]
) -> None:
    """`testmcpy auth` is an adapter over the probe, so the dep is required."""
    requirements = [Requirement(item) for item in root_project["project"]["dependencies"]]
    matches = [item for item in requirements if _canonical(item.name) == PROBE_DIST]
    assert matches, (
        f"testmcpy no longer bundles the probe, so it must depend on {PROBE_DIST}; "
        "without this, `testmcpy auth` and testmcpy.oauth_probe break on a clean install"
    )
    requirement = matches[0]
    assert not requirement.marker, "the probe dependency must not be conditional"

    declared = Version(probe_project["project"]["version"])
    assert requirement.specifier.contains(declared, prereleases=True), (
        f"testmcpy requires {requirement}, which excludes the probe version "
        f"currently in-tree ({declared}); a release would publish an uninstallable testmcpy"
    )


def test_publish_workflow_releases_the_probe_before_testmcpy() -> None:
    """A dist nobody publishes is not separately installable."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["publish"]["steps"]
    commands = [(step.get("name", ""), step.get("run", "")) for step in steps]

    built = [name for name, run in commands if "build oauth-probe" in run]
    assert built, "the publish workflow never builds the oauth-probe distribution"

    def upload_index(*, probe: bool) -> int:
        for index, (_, run) in enumerate(commands):
            if "twine upload" not in run:
                continue
            if ("oauth-probe/dist" in run) is probe:
                return index
        target = "the probe" if probe else "testmcpy"
        raise AssertionError(f"no `twine upload` step publishing {target}")

    probe_upload = upload_index(probe=True)
    testmcpy_upload = upload_index(probe=False)
    assert probe_upload < testmcpy_upload, (
        "testmcpy declares a hard dependency on the probe, so publishing testmcpy "
        "first leaves a window where `pip install testmcpy` cannot resolve"
    )


def test_release_script_publishes_the_probe_before_testmcpy() -> None:
    """The workflow is not the only release path; scripts/publish.sh is used by hand.

    testmcpy 0.11.21 shipped depending on a distribution that was never
    uploaded, because this script built and uploaded the root project only.
    """
    script = (REPO_ROOT / "scripts/publish.sh").read_text(encoding="utf-8")

    assert "build oauth-probe" in script, (
        "scripts/publish.sh never builds the probe distribution; a release cut "
        "with it publishes a testmcpy that pip cannot resolve"
    )

    uploads = [
        index
        for index, line in enumerate(script.splitlines())
        if "twine upload" in line and not line.strip().startswith("#")
    ]
    assert len(uploads) >= 2, "scripts/publish.sh uploads only one distribution"

    lines = script.splitlines()
    probe_upload = next(index for index in uploads if "oauth-probe/dist" in lines[index])
    testmcpy_upload = next(index for index in uploads if "oauth-probe/dist" not in lines[index])
    assert probe_upload < testmcpy_upload, (
        "scripts/publish.sh uploads testmcpy before the probe it depends on"
    )


def test_source_installs_use_the_in_tree_probe() -> None:
    """A source checkout must test its own probe, not the last PyPI release."""
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    for source, text in (("ci.yml", ci), ("Dockerfile", dockerfile)):
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if "pip install" not in stripped or "oauth-probe" in stripped:
                continue
            # Only editable/local installs of testmcpy itself are in scope.
            if not any(token in stripped for token in ('-e ".', 'install ".', "install .")):
                continue
            assert "./oauth-probe" in text, (
                f"{source}:{line_number} installs testmcpy from source without first "
                "installing ./oauth-probe; the build would resolve the probe from PyPI"
            )


@pytest.mark.skipif(
    not (PROBE_DIR / "pyproject.toml").exists(), reason="probe subproject is absent"
)
def test_probe_metadata_resolves_to_two_requirements() -> None:
    """Build the real metadata — comments in pyproject are not a contract."""
    result = subprocess.run(
        [sys.executable, "-c", "import setuptools.build_meta as b; print(b.__name__)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:  # pragma: no cover - build backend always present in dev
        pytest.skip("setuptools build backend unavailable")

    from importlib.metadata import PackageNotFoundError, requires

    try:
        declared = requires(PROBE_DIST)
    except PackageNotFoundError:
        pytest.skip(f"{PROBE_DIST} is not installed in this environment")
    assert declared is not None
    names = {_canonical(Requirement(item).name) for item in declared}
    assert not names & FORBIDDEN_PROBE_DEPENDENCIES, (
        f"the installed {PROBE_DIST} pulls in {sorted(names & FORBIDDEN_PROBE_DEPENDENCIES)}"
    )
