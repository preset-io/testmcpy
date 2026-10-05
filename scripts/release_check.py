#!/usr/bin/env python3
"""Release validation shared by `scripts/publish.sh` and `.github/workflows/publish.yml`.

Two distributions ship from this repository and are versioned independently:

* ``testmcpy``             -- ``pyproject.toml``
* ``testmcpy-oauth-probe`` -- ``oauth-probe/pyproject.toml``

``testmcpy`` hard-depends on the probe, so a release must never publish
``testmcpy`` against a probe version that is not installable from PyPI.

Tag convention (the tag IS the release request):

* ``vX.Y.Z``               releases ``testmcpy`` X.Y.Z. X.Y.Z must equal the
                           version in ``pyproject.toml``. The in-tree probe
                           version is released first when it is not on PyPI yet.
* ``oauth-probe-vX.Y.Z``   releases only ``testmcpy-oauth-probe`` X.Y.Z. X.Y.Z
                           must equal the version in ``oauth-probe/pyproject.toml``.

Pre-releases use ``aN`` / ``bN`` / ``rcN`` suffixes (``v0.12.0rc1``). Any other
shape, and any mismatch between tag and package version, fails -- there is no
fallback that publishes "whatever was built".

Standard library only, so it can run before anything is installed.

Subcommands:  plan | build | verify-dists

The "probe must be installable from PyPI before testmcpy uploads" gate is NOT here: it
runs inside the privileged publish job in `.github/workflows/publish.yml`, which
deliberately executes no repository code.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 only; the dev extra installs tomli there
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]

MAIN_DIST = "testmcpy"
PROBE_DIST = "testmcpy-oauth-probe"

_VERSION = r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?"
MAIN_TAG_RE = re.compile(rf"^v({_VERSION})$")
PROBE_TAG_RE = re.compile(rf"^oauth-probe-v({_VERSION})$")

PYPI_URL = "https://pypi.org"


class ReleaseError(Exception):
    """A release precondition failed. The message is shown to the maintainer."""


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _file_stem(name: str) -> str:
    """Distribution name as it appears in wheel/sdist filenames."""
    return _canonical(name).replace("-", "_")


def read_project(root: Path, subdir: str = "") -> dict[str, Any]:
    path = root / subdir / "pyproject.toml" if subdir else root / "pyproject.toml"
    project: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    return project


def probe_requirement(main_project: dict[str, Any]) -> str:
    """The specifier string testmcpy declares on the probe (e.g. ``>=0.1.0,<0.2.0``)."""
    for dep in main_project["dependencies"]:
        match = re.match(r"^\s*([A-Za-z0-9._-]+)\s*(.*?)\s*(?:;.*)?$", dep)
        if match and _canonical(match.group(1)) == PROBE_DIST:
            return match.group(2)
    raise ReleaseError(f"pyproject.toml no longer declares a dependency on {PROBE_DIST}")


def _specifier_contains(specifier: str, version: str) -> bool:
    try:
        from packaging.specifiers import SpecifierSet
    except ModuleNotFoundError:
        raise ReleaseError(
            "`packaging` is required to evaluate the probe pin: pip install packaging"
        )
    return bool(SpecifierSet(specifier).contains(version, prereleases=True))


def pypi_has_version(name: str, version: str, *, index: str = PYPI_URL) -> bool:
    """True/False for 200/404; anything else is an error, never a guess."""
    url = f"{index}/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            return bool(response.status == 200)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise ReleaseError(f"could not query {url}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ReleaseError(f"could not query {url}: {exc.reason}") from exc


def build_plan(root: Path, tag: str, *, index: str = PYPI_URL) -> dict[str, Any]:
    """Validate ``tag`` against the in-tree versions and decide what to publish."""
    main = read_project(root)
    probe = read_project(root, "oauth-probe")
    if main["name"] != MAIN_DIST or probe["name"] != PROBE_DIST:
        raise ReleaseError(
            f"unexpected project names: {main['name']!r}, {probe['name']!r} "
            f"(expected {MAIN_DIST!r}, {PROBE_DIST!r})"
        )
    main_version, probe_version = main["version"], probe["version"]
    requirement = probe_requirement(main)
    if not _specifier_contains(requirement, probe_version):
        raise ReleaseError(
            f"testmcpy requires {PROBE_DIST}{requirement}, which excludes the in-tree "
            f"probe version {probe_version}; the release would be uninstallable"
        )

    main_match, probe_match = MAIN_TAG_RE.match(tag), PROBE_TAG_RE.match(tag)
    if main_match:
        kind, tag_version, package_version, package = (
            "testmcpy",
            main_match[1],
            main_version,
            MAIN_DIST,
        )
    elif probe_match:
        kind, tag_version, package_version, package = (
            "probe",
            probe_match[1],
            probe_version,
            PROBE_DIST,
        )
    else:
        raise ReleaseError(
            f"tag {tag!r} does not match 'vX.Y.Z' (testmcpy) or 'oauth-probe-vX.Y.Z' (probe)"
        )
    if tag_version != package_version:
        raise ReleaseError(
            f"tag {tag!r} says {package} {tag_version}, but the tagged tree declares "
            f"{package} {package_version}. Refusing to release a mismatched artifact."
        )

    probe_on_pypi = pypi_has_version(PROBE_DIST, probe_version, index=index)
    if kind == "probe":
        if probe_on_pypi:
            raise ReleaseError(f"{PROBE_DIST} {probe_version} is already on PyPI; bump its version")
        distributions = [{"name": PROBE_DIST, "version": probe_version, "dir": "probe"}]
    else:
        if pypi_has_version(MAIN_DIST, main_version, index=index):
            raise ReleaseError(
                f"{MAIN_DIST} {main_version} is already on PyPI; versions are immutable, bump it"
            )
        distributions = []
        if not probe_on_pypi:
            distributions.append({"name": PROBE_DIST, "version": probe_version, "dir": "probe"})
        distributions.append({"name": MAIN_DIST, "version": main_version, "dir": "testmcpy"})

    return {
        "tag": tag,
        "kind": kind,
        "probe_version": probe_version,
        "probe_requirement": requirement,
        "distributions": distributions,
    }


def _wheel_metadata_version(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as wheel:
        names = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ReleaseError(f"{path.name}: expected exactly one METADATA file, found {names}")
        return _parse_metadata(wheel.read(names[0]).decode("utf-8"), path.name)


def _sdist_metadata_version(path: Path) -> tuple[str, str]:
    with tarfile.open(path, "r:gz") as sdist:
        members = [
            m for m in sdist.getmembers() if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")
        ]
        if len(members) != 1:
            raise ReleaseError(f"{path.name}: expected exactly one top-level PKG-INFO")
        handle = sdist.extractfile(members[0])
        assert handle is not None
        return _parse_metadata(handle.read().decode("utf-8"), path.name)


def _parse_metadata(text: str, label: str) -> tuple[str, str]:
    fields: dict[str, str] = {}
    for line in text.split("\n\n", 1)[0].splitlines():
        key, _, value = line.partition(":")
        fields.setdefault(key.strip().lower(), value.strip())
    try:
        return fields["name"], fields["version"]
    except KeyError:
        raise ReleaseError(f"{label}: metadata has no Name/Version") from None


def build_dists(plan: dict[str, Any], release_dir: Path, root: Path = REPO_ROOT) -> None:
    """Build exactly the planned distributions into ``release_dir/<dir>``."""
    for dist in plan["distributions"]:
        source = root / "oauth-probe" if dist["dir"] == "probe" else root
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    str(source),
                    "--outdir",
                    str(release_dir / dist["dir"]),
                ],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ReleaseError(f"building {dist['name']} failed (exit {exc.returncode})") from exc


def verify_dists(plan: dict[str, Any], release_dir: Path) -> None:
    """Every planned distribution has exactly one wheel + sdist at the planned version.

    Also fails on anything *unplanned* (stale ``testmcpy`` files in a probe-only
    release, a second version of a dist, stray files) so nothing rides along.
    """
    if not plan["distributions"]:
        raise ReleaseError("release plan contains no distributions")
    expected_dirs = {d["dir"] for d in plan["distributions"]}
    present_dirs = {p.name for p in release_dir.iterdir() if p.is_dir()}
    if present_dirs != expected_dirs:
        raise ReleaseError(
            f"artifact directories {sorted(present_dirs)} do not match plan {sorted(expected_dirs)}"
        )
    for dist in plan["distributions"]:
        directory = release_dir / dist["dir"]
        stem = f"{_file_stem(dist['name'])}-{dist['version']}"
        wheels = sorted(directory.glob("*.whl"))
        sdists = sorted(directory.glob("*.tar.gz"))
        others = sorted(set(directory.iterdir()) - set(wheels) - set(sdists))
        if len(wheels) != 1 or len(sdists) != 1 or others:
            raise ReleaseError(
                f"{directory}: expected exactly one wheel and one sdist, found "
                f"{[p.name for p in directory.iterdir()]}"
            )
        if not wheels[0].name.startswith(f"{stem}-") or sdists[0].name != f"{stem}.tar.gz":
            raise ReleaseError(
                f"{directory}: filenames {wheels[0].name}, {sdists[0].name} are not {dist['name']} "
                f"{dist['version']}"
            )
        for label, (name, version) in (
            (wheels[0].name, _wheel_metadata_version(wheels[0])),
            (sdists[0].name, _sdist_metadata_version(sdists[0])),
        ):
            if _canonical(name) != _canonical(dist["name"]) or version != dist["version"]:
                raise ReleaseError(
                    f"{label} metadata says {name} {version}; expected {dist['name']} {dist['version']}"
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="validate a tag and print the release plan as JSON")
    plan_cmd.add_argument("--tag", required=True)
    plan_cmd.add_argument("--output", type=Path, help="also write the plan here")
    plan_cmd.add_argument("--index", default=PYPI_URL, help=argparse.SUPPRESS)

    build_cmd = sub.add_parser("build", help="build the distributions listed in a plan")
    build_cmd.add_argument("--plan", type=Path, required=True)
    build_cmd.add_argument("--release-dir", type=Path, required=True)

    verify_cmd = sub.add_parser("verify-dists", help="check built artifacts against a plan")
    verify_cmd.add_argument("--plan", type=Path, required=True)
    verify_cmd.add_argument("--release-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan = build_plan(args.root, args.tag, index=args.index)
            text = json.dumps(plan, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text + "\n", encoding="utf-8")
            print(text)
        elif args.command == "build":
            build_dists(
                json.loads(args.plan.read_text(encoding="utf-8")), args.release_dir, args.root
            )
        else:
            verify_dists(json.loads(args.plan.read_text(encoding="utf-8")), args.release_dir)
            print("artifacts match the release plan")
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
