# Releasing testmcpy

Releases are published to PyPI by GitHub Actions using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (GitHub OIDC).
There is no PyPI API token, nothing is uploaded from a laptop, and every upload
waits for a human to approve it in GitHub.

Two distributions ship from this repository and are versioned independently:

| Distribution           | Source           | Version lives in             |
| ---------------------- | ---------------- | ---------------------------- |
| `testmcpy`             | repository root  | `pyproject.toml`             |
| `testmcpy-oauth-probe` | `oauth-probe/`   | `oauth-probe/pyproject.toml` |

`testmcpy` hard-depends on the probe (`testmcpy-oauth-probe>=X,<Y` in
`pyproject.toml`), so the exact in-tree probe version must be available as a
wheel from PyPI before `testmcpy` is uploaded. The workflow enforces that
ordering and refuses a source-only probe: downloading an sdist could execute
its build backend in the OIDC-enabled job.

## Tag convention

The tag is the release request. Its version must equal the version in the
tagged tree's `pyproject.toml`; any mismatch fails the release (there is no
fallback that publishes "whatever was built").

| Tag      | Releases                                                                                |
| -------- | --------------------------------------------------------------------------------------- |
| `vX.Y.Z` | `testmcpy` X.Y.Z. The in-tree probe version is released first if it is not on PyPI yet. |

`vX.Y.Z` is the **only** release tag. The `pypi` environment's deployment policy
admits `v*` tags only, so a tag such as `oauth-probe-vX.Y.Z` would be rejected at
the environment gate; the workflow does not trigger on it and `scripts/publish.sh`
has no probe-only mode.

Pre-releases use `aN`, `bN` or `rcN` suffixes (`v0.12.0rc1`). Anything else
(`v1.2`, `1.2.3`, `v1.2.3-beta`, `release-1.2.3`) is rejected. The tagged commit
must be on `main`.

Pushing a tag is the only trigger. Creating a GitHub Release, running the
workflow by hand, or pushing a branch does nothing.

## Account and repository setup

These are account/repository settings, not code. All of them are in place; the
workflow depends on them staying that way.

1. **PyPI trusted publishers** (done) on both `testmcpy` and
   `testmcpy-oauth-probe`: owner `preset-io`, repository `testmcpy`, workflow
   `publish.yml`, environment `pypi`. Renaming `publish.yml` or the environment
   breaks publishing until both PyPI projects are updated.
2. **GitHub environment `pypi`** (done): it exists with required reviewers
   (self-review permitted) and a deployment policy limited to tags matching
   `v*`. Settings → Environments → `pypi`.

> **Never push a release tag if the `pypi` environment is missing or has no
> required reviewers.** GitHub silently creates a missing environment the first
> time a job references it, with no protection, which would let that run publish
> with no approval. `scripts/publish.sh` checks through `gh` that the environment
> has required reviewers and a tag deployment policy covering the tag, and refuses
> to push the tag otherwise.

The old `PYPI_API_TOKEN` repository secret is no longer read by anything.
Deleting it and revoking the PyPI token is a separate step to do only after the
verification release below has succeeded.

## Cutting a release

1. **Bump versions in a normal PR.** Change `version` in `pyproject.toml`; change
   `oauth-probe/pyproject.toml` only if the probe changed, and keep
   `testmcpy`'s `testmcpy-oauth-probe` pin range containing the probe version.
   Merge to `main`. Pick a version that is not on PyPI yet: check
   `https://pypi.org/pypi/testmcpy/json` and
   `https://pypi.org/pypi/testmcpy-oauth-probe/json` first, because a version can
   exist on PyPI without a matching commit or tag in this repository (testmcpy
   0.11.21 was uploaded from a local, uncommitted bump before Trusted Publishing).
   `scripts/publish.sh --dry-run` also refuses a version that is already published.
   Add the `CHANGELOG.md` entry in the same PR.
2. **Dry run** from an up-to-date `main`:
   ```bash
   scripts/publish.sh --dry-run
   ```
   Validates the tag against both versions and PyPI, runs lint and unit tests,
   builds the web UI (`npm ci && npm run build` in `testmcpy/ui`, so Node.js and
   npm are required), builds the wheel and sdist of each planned distribution,
   runs `twine check`, and checks the `pypi` environment. It never creates a tag
   or touches PyPI.
3. **Tag and push:**
   ```bash
   scripts/publish.sh
   ```
   Runs the same checks, creates the annotated tag locally, then asks before
   pushing it. Answering `n` leaves the local tag in place (it prints the push
   command, and how to delete the tag). `--skip-tests` skips lint and pytest.
4. **Approve** the run: Actions → *Publish to PyPI* → *Review deployments* →
   `pypi`. Nothing is uploaded until a required reviewer approves.

### What the workflow does

| Job        | Permissions                          | Does                                                                                                                                                                                     |
| ---------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build`    | `contents: read`, no OIDC            | Checks the tag is on `main`; validates tag vs. versions and PyPI; runs release/packaging tests; builds the web UI (`testmcpy/ui/dist` is git-ignored but shipped in the `testmcpy` wheel and sdist, and `verify-dists` fails the release if it is missing); builds the planned dists; `twine check --strict`; installs the built wheels into clean venvs (`pip check`, CLI smoke); records checksums; uploads one artifact. |
| `publish`  | `id-token: write`, environment `pypi` | Downloads the artifact and **runs no repository code**: verifies checksums and re-derives tag/version/filenames from the tag itself; uploads the probe (if planned); checks the exact probe version is installable from PyPI; uploads `testmcpy`. |
| `homebrew` | `contents: write`, no OIDC           | After `testmcpy` is published, rewrites `Formula/testmcpy.rb` (see below) and pushes it to `main`.                                                                                        |

All actions are pinned by full commit SHA, with the version in a comment. Bump
them deliberately.

Before publishing, `SHA256SUMS` must cover every artifact file, including
`plan.json`, exactly once (excluding the manifest itself). Omissions, extra
entries, duplicate paths, absolute paths, `..` components and symlinks are
rejected before any listed file is read; then every digest is verified.

### Homebrew formula

`scripts/update_homebrew_formula.py VERSION` asks PyPI's JSON API for the sdist
of that version, downloads it, and refuses to touch the formula unless the
download is HTTP 200, non-empty, a valid gzip tarball whose `PKG-INFO` names
`testmcpy` `VERSION`, and its sha256 equals the digest PyPI reports. It then
rewrites both the `url` and `sha256` lines (they must move together) and reads
the file back. Any failure exits non-zero and fails the job; a failed `git push`
fails the job too. PyPI is already published when this job runs, so if it fails
fix the cause and use **Re-run failed jobs**: the publish job is not repeated.
You can also run the script yourself and commit the result.

### Failure and recovery

- **Tag/version mismatch, malformed tag, version already on PyPI** → the `build`
  job fails before anything is uploaded. Delete the tag
  (`git push origin :refs/tags/TAG`), fix the version in a PR, and tag again.
- **Probe uploaded, `testmcpy` upload failed** → fix the cause and re-run the whole
  workflow. The plan is recomputed: the probe is now on PyPI, so only `testmcpy`
  is built and uploaded. PyPI files are immutable and `skip-existing` is
  deliberately not used, since it would hide an artifact that differs from the one
  on PyPI.
- **`testmcpy` published but Homebrew sync failed** → *Re-run failed jobs* (see above).
  Re-running the whole workflow instead fails at the "already on PyPI" check.
- **Rejected approval** → nothing was uploaded; delete the tag.

## First approved verification release (operational step, not yet performed)

The `pypi` environment exists with required reviewers, so the first real release
doubles as the end-to-end verification. It is a manual operational step and is
not part of the change that introduced this workflow:

1. Confirm the environment still has required reviewers and a `v*` tag policy
   (`gh api repos/preset-io/testmcpy/environments/pypi` and
   `.../environments/pypi/deployment-branch-policies`).
2. Merge a version-bump PR and run `scripts/publish.sh --dry-run`, then
   `scripts/publish.sh`.
3. Confirm the run **pauses** at *Review deployments* and that the upload does not
   start before approval. Approve it.
4. Confirm on PyPI that each new release shows it was published via Trusted
   Publishing from this workflow.
5. In a clean venv, `pip install testmcpy==X.Y.Z` resolves `testmcpy-oauth-probe`
   and `testmcpy --help` runs.
6. Confirm the Homebrew job pushed a formula whose `url` and `sha256` both name
   `X.Y.Z`.
7. Only then delete the `PYPI_API_TOKEN` secret and revoke the PyPI token.

## Known gaps

- **No probe-only release (deferred decision).** Because the environment admits
  `v*` tags only, a change to `oauth-probe/` can only ship together with a new
  `vX.Y.Z` of `testmcpy` (bump the probe version and cut a `testmcpy` release).
  Releasing the probe on its own would need an `oauth-probe-v*` tag policy on the
  `pypi` environment plus restoring that tag path in the workflow,
  `scripts/release_check.py` and `scripts/publish.sh`. Not done here; for the
  repository owner to decide.
- If the probe's code changes but its version is not bumped, the release does not
  notice: the probe's version is already on PyPI, so it is skipped, and `testmcpy`
  ships against the older probe. Bump the probe whenever `oauth-probe/` changes.
- The workflow cannot itself prove the `pypi` environment is protected; only
  `scripts/publish.sh` checks it (reviewers and tag policy, best effort, through
  `gh`).
