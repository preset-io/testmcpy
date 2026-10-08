#!/bin/bash
# Prepare a release: validate versions, run checks, build and verify the
# distributions locally, create the release tag, and (after an explicit
# confirmation) push it.
#
# This script NEVER uploads to PyPI. Pushing the tag starts
# .github/workflows/publish.yml, which builds in an unprivileged job and then
# publishes via PyPI Trusted Publishing after a reviewer approves the `pypi`
# environment. See RELEASING.md.
#
# Usage: scripts/publish.sh [--dry-run] [--skip-tests]
#
#   --dry-run      run every check and build, but do not create or push a tag
#   --skip-tests   skip ruff + the unit suite (CI already ran them on main)
#
# The only release tag is vX.Y.Z (the GitHub `pypi` environment admits `v*` tags
# only). The probe is released first, in the same run, when its in-tree version
# is not on PyPI yet; there is no probe-only release.
#
# Environment:
#   PYTHON                    interpreter to use (default: python)
#   RELEASE_SKIP_ENV_CHECK=1  push even if the `pypi` environment's reviewer or
#                             tag-policy protection cannot be verified via `gh`
#                             (use only when you have confirmed it in the GitHub UI)
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PYTHON="${PYTHON:-python}"
DRY_RUN=false
SKIP_TESTS=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --skip-tests) SKIP_TESTS=true ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        --probe-only) echo -e "${RED}--probe-only was removed: v* is the only release tag the 'pypi' environment accepts. See RELEASING.md.${NC}" >&2; exit 2 ;;
        *) echo -e "${RED}Unknown argument: ${arg}${NC}" >&2; exit 2 ;;
    esac
done

die() { echo -e "\n${RED}❌ $*${NC}" >&2; exit 1; }

echo -e "${YELLOW}📦 testmcpy release preparation${NC}"
echo "================================"

# Releases are cut from an up-to-date, clean main: the workflow refuses tags
# whose commit is not on main, so catch that here rather than after the push.
if ! git diff-index --quiet HEAD --; then
    die "You have uncommitted changes. Commit or stash them first."
fi
BRANCH=$(git rev-parse --abbrev-ref HEAD)
[ "$BRANCH" = "main" ] || die "Releases are cut from main (currently on '${BRANCH}')."
git fetch --quiet origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] \
    || die "Local main is not at origin/main. Pull (or push) so the tag lands on the merged commit."

# Versions are bumped through a normal reviewed PR before this script runs.
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
PROBE_VERSION=$(grep '^version = ' oauth-probe/pyproject.toml | sed 's/version = "\(.*\)"/\1/')
TAG="v${VERSION}"
echo -e "testmcpy:             ${VERSION}"
echo -e "testmcpy-oauth-probe: ${PROBE_VERSION}"
echo -e "${YELLOW}Release tag:          ${TAG}${NC}"

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    die "Tag ${TAG} already exists locally."
fi
if git ls-remote --exit-code --tags origin "refs/tags/${TAG}" >/dev/null 2>&1; then
    die "Tag ${TAG} already exists on origin."
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Validates tag == package version, the probe pin, and that these versions are
# not already on PyPI; reports which distributions the tag would publish.
echo -e "\n${GREEN}🔎 Validating the release plan...${NC}"
"$PYTHON" scripts/release_check.py plan --tag "$TAG" --output "$WORK/release/plan.json" \
    || die "Release plan validation failed."

if [ "$SKIP_TESTS" != "true" ]; then
    echo -e "\n${GREEN}🧪 Running lint and unit tests...${NC}"
    "$PYTHON" -m ruff check testmcpy oauth-probe/testmcpy_oauth_probe unit_tests integration_tests scripts
    "$PYTHON" -m ruff format --check testmcpy oauth-probe/testmcpy_oauth_probe unit_tests integration_tests scripts
    "$PYTHON" -m pytest unit_tests/ -q
fi

echo -e "\n${GREEN}🔨 Building and checking the planned distributions...${NC}"
"$PYTHON" scripts/release_check.py build --plan "$WORK/release/plan.json" --release-dir "$WORK/release"
"$PYTHON" -m twine check --strict "$WORK"/release/*/*
"$PYTHON" scripts/release_check.py verify-dists --plan "$WORK/release/plan.json" --release-dir "$WORK/release"

# GitHub creates a missing environment on first use, unprotected, which would
# publish without any approval. Check the gate exists (required reviewers, and a
# tag deployment policy covering this tag) before offering the push.
ENV_OK=false
ENV_MSG=""
if command -v gh >/dev/null 2>&1 && SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null); then
    if REVIEWERS=$(gh api "repos/${SLUG}/environments/pypi" \
        --jq '[.protection_rules[]? | select(.type == "required_reviewers")] | length' 2>&1); then
        if [ "$REVIEWERS" -gt 0 ] 2>/dev/null; then
            if TAG_POLICIES=$(gh api "repos/${SLUG}/environments/pypi/deployment-branch-policies" \
                --jq '.branch_policies[]? | select(.type == "tag") | .name' 2>&1); then
                while IFS= read -r PATTERN; do
                    # shellcheck disable=SC2053  # the policy name is a glob on purpose
                    if [ -n "$PATTERN" ] && [[ "$TAG" == $PATTERN ]]; then
                        ENV_OK=true
                    fi
                done <<< "$TAG_POLICIES"
                if [ "$ENV_OK" != "true" ]; then
                    ENV_MSG="GitHub environment 'pypi' has no tag deployment policy covering ${TAG}."
                fi
            else
                ENV_MSG="Could not read the 'pypi' deployment policies via gh (${TAG_POLICIES})."
            fi
        else
            ENV_MSG="GitHub environment 'pypi' has no required reviewers."
        fi
    elif echo "$REVIEWERS" | grep -qi "not found\|404"; then
        ENV_MSG="GitHub environment 'pypi' does not exist yet."
    else
        ENV_MSG="Could not read the 'pypi' environment via gh (${REVIEWERS})."
    fi
else
    ENV_MSG="gh is unavailable or not authenticated, so the 'pypi' environment cannot be checked."
fi

if [ "$DRY_RUN" = "true" ]; then
    echo -e "\n${GREEN}✅ Dry run complete: checks passed and artifacts build for ${TAG}.${NC}"
    if [ "$ENV_OK" != "true" ]; then
        echo -e "${YELLOW}⚠️  ${ENV_MSG} A real run would refuse to push the tag.${NC}"
    fi
    echo "No tag was created or pushed."
    exit 0
fi

if [ "$ENV_OK" != "true" ] && [ "${RELEASE_SKIP_ENV_CHECK:-}" != "1" ]; then
    die "${ENV_MSG} Pushing ${TAG} could publish without approval. Fix the environment (see RELEASING.md), or set RELEASE_SKIP_ENV_CHECK=1 if you verified it in the GitHub UI."
fi

echo -e "\n${GREEN}🏷️  Creating local tag ${TAG}...${NC}"
git tag -a "${TAG}" -m "Release ${TAG}"

echo -e "\n${YELLOW}Pushing ${TAG} starts the publish workflow. It uploads to PyPI only"
echo -e "after a reviewer approves the 'pypi' environment in GitHub.${NC}"
read -r -p "Push tag ${TAG} to origin now? (y/N): " -n 1 REPLY || REPLY=""
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Not pushed. The tag exists locally; push it later with:${NC}"
    echo "  git push origin refs/tags/${TAG}"
    echo "or remove it with:  git tag -d ${TAG}"
    exit 0
fi

git push origin "refs/tags/${TAG}"

echo -e "\n${GREEN}✅ Tag pushed.${NC} Approve the run in the 'pypi' environment:"
echo "  https://github.com/preset-io/testmcpy/actions/workflows/publish.yml"
