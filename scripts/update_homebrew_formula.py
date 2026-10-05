#!/usr/bin/env python3
"""Point Formula/testmcpy.rb at a released testmcpy sdist on PyPI.

The formula's ``url`` and ``sha256`` describe the same file and must move
together. Both are derived from the *real* artifact:

1. PyPI's JSON API names the sdist for ``VERSION`` (its exact URL, not a guess).
2. The file is downloaded; any non-2xx response, empty body, or non-gzip body fails.
3. The sha256 is computed from the downloaded bytes and must equal the digest
   PyPI itself reports for that file.
4. The tarball must be a ``testmcpy`` sdist for exactly ``VERSION``
   (top-level ``testmcpy-VERSION/PKG-INFO`` with matching Name/Version).
5. Only then is the formula rewritten -- one ``url`` line and one ``sha256``
   line, each substituted exactly once -- and read back to confirm.

The script never reports success unless the formula on disk matches the verified
artifact. PyPI's index can lag an upload by a minute or two, so a missing release
is retried; every other failure is immediate.

Standard library only (runs on a bare CI runner).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FORMULA = REPO_ROOT / "Formula" / "testmcpy.rb"
PYPI_URL = "https://pypi.org"
DIST = "testmcpy"

_URL_LINE = re.compile(r'^(\s*url\s+)"[^"]*"\s*$', re.MULTILINE)
_SHA_LINE = re.compile(r'^(\s*sha256\s+)"[^"]*"\s*$', re.MULTILINE)


class FormulaError(Exception):
    pass


def _get(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            if response.status != 200:
                raise FormulaError(f"GET {url} returned HTTP {response.status}")
            return bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise FormulaError(f"GET {url} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FormulaError(f"GET {url} failed: {exc.reason}") from exc


def _is_not_found(exc: FormulaError) -> bool:
    return "HTTP 404" in str(exc)


def fetch_sdist(version: str, *, index: str, attempts: int, delay: float) -> tuple[str, str, bytes]:
    """Return ``(url, sha256, bytes)`` for the verified sdist of ``version``."""
    metadata_url = f"{index}/pypi/{DIST}/{version}/json"
    metadata = None
    for attempt in range(1, attempts + 1):
        try:
            metadata = json.loads(_get(metadata_url))
            break
        except FormulaError as exc:
            if not _is_not_found(exc) or attempt == attempts:
                raise
            print(f"{DIST} {version} not on PyPI yet (attempt {attempt}/{attempts})")
            time.sleep(delay)
    assert metadata is not None

    sdists = [f for f in metadata.get("urls", []) if f.get("packagetype") == "sdist"]
    if len(sdists) != 1:
        raise FormulaError(f"expected exactly one sdist for {DIST} {version}, found {len(sdists)}")
    url = sdists[0]["url"]
    reported = sdists[0].get("digests", {}).get("sha256", "")

    payload = _get(url)
    if not payload:
        raise FormulaError(f"{url} downloaded as an empty file")
    computed = hashlib.sha256(payload).hexdigest()
    if computed != reported:
        raise FormulaError(
            f"sha256 of the downloaded file ({computed}) does not match the digest PyPI "
            f"reports ({reported or 'none'}); refusing to write it to the formula"
        )
    _verify_sdist_contents(payload, version)
    return url, computed, payload


def _verify_sdist_contents(payload: bytes, version: str) -> None:
    prefix = f"{DIST}-{version}"
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as sdist:
            handle = sdist.extractfile(f"{prefix}/PKG-INFO")
            if handle is None:
                raise FormulaError(f"sdist has no {prefix}/PKG-INFO")
            header = handle.read().decode("utf-8").split("\n\n", 1)[0]
    except (tarfile.TarError, KeyError, OSError, EOFError) as exc:
        raise FormulaError(f"downloaded file is not a valid {DIST} {version} sdist: {exc}") from exc
    fields = {}
    for line in header.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    if fields.get("name", "").lower() != DIST or fields.get("version") != version:
        raise FormulaError(
            f"sdist metadata says {fields.get('name')} {fields.get('version')}, expected {DIST} {version}"
        )


def rewrite_formula(text: str, url: str, sha256: str) -> str:
    for label, pattern in (("url", _URL_LINE), ("sha256", _SHA_LINE)):
        if len(pattern.findall(text)) != 1:
            raise FormulaError(f"formula must contain exactly one top-level `{label}` line")
    text = _URL_LINE.sub(lambda m: f'{m.group(1)}"{url}"', text)
    return _SHA_LINE.sub(lambda m: f'{m.group(1)}"{sha256}"', text)


def update_formula(
    formula: Path, version: str, *, index: str = PYPI_URL, attempts: int = 10, delay: float = 15.0
) -> bool:
    """Returns True if the formula changed, False if it was already current."""
    url, sha256, _ = fetch_sdist(version, index=index, attempts=attempts, delay=delay)
    original = formula.read_text(encoding="utf-8")
    updated = rewrite_formula(original, url, sha256)
    if updated != original:
        formula.write_text(updated, encoding="utf-8")
    # Read back: success means the file on disk carries the verified values.
    final = formula.read_text(encoding="utf-8")
    if f'"{url}"' not in final or f'"{sha256}"' not in final:
        raise FormulaError("formula does not contain the verified url/sha256 after writing")
    return updated != original


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("version", help="released testmcpy version, e.g. 0.11.22")
    parser.add_argument("--formula", type=Path, default=DEFAULT_FORMULA)
    parser.add_argument("--index", default=PYPI_URL, help=argparse.SUPPRESS)
    parser.add_argument("--attempts", type=int, default=10, help=argparse.SUPPRESS)
    parser.add_argument("--delay", type=float, default=15.0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        changed = update_formula(
            args.formula, args.version, index=args.index, attempts=args.attempts, delay=args.delay
        )
    except FormulaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{args.formula} {'updated' if changed else 'already current'} for {DIST} {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
