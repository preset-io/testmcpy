#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}📦 testmcpy Publishing Script${NC}"
echo "================================"

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}❌ Error: You have uncommitted changes${NC}"
    echo "Please commit or stash your changes first"
    exit 1
fi

# Show current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo -e "\n${YELLOW}Current branch: ${BRANCH}${NC}"

# Get current version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
# Two distributions ship from this repo. testmcpy declares a hard dependency on
# testmcpy-oauth-probe, so publishing testmcpy alone leaves a release on PyPI
# that cannot be installed at all.
PROBE_VERSION=$(grep '^version = ' oauth-probe/pyproject.toml | sed 's/version = "\(.*\)"/\1/')
PROBE_REQUIREMENT=$(grep -o 'testmcpy-oauth-probe[^"]*' pyproject.toml | head -1)
echo -e "${YELLOW}Current version: ${VERSION}${NC}"
echo -e "${YELLOW}Probe version:   ${PROBE_VERSION}  (testmcpy requires: ${PROBE_REQUIREMENT})${NC}"

# Confirm publication
echo -e "\n${YELLOW}This will:${NC}"
echo "1. Clean previous builds"
echo "2. Build testmcpy-oauth-probe ${PROBE_VERSION} and testmcpy ${VERSION}"
echo "3. Upload testmcpy-oauth-probe to PyPI, then testmcpy"
echo "4. Create git tag v${VERSION}"
echo "5. Update Homebrew formula with SHA256"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Aborted${NC}"
    exit 0
fi

# Clean previous builds
echo -e "\n${GREEN}🧹 Cleaning previous builds...${NC}"
rm -rf dist/ build/ *.egg-info testmcpy.egg-info
rm -rf oauth-probe/dist/ oauth-probe/build/ oauth-probe/*.egg-info

# Build packages
echo -e "\n${GREEN}🔨 Building testmcpy-oauth-probe...${NC}"
python -m build oauth-probe --outdir oauth-probe/dist

echo -e "\n${GREEN}🔨 Building testmcpy...${NC}"
python -m build

# Check if PyPI credentials are configured
if [ ! -f ~/.pypirc ]; then
    echo -e "\n${YELLOW}⚠️  No ~/.pypirc found${NC}"
    echo "You'll need to enter your PyPI credentials"
    echo "Username: __token__"
    echo "Password: <your-pypi-token>"
fi

# Upload to PyPI. Order matters: testmcpy depends on testmcpy-oauth-probe, so
# uploading testmcpy first publishes a release that pip cannot resolve.
# --skip-existing makes the probe upload a no-op when its version is unchanged,
# which is the normal case (the two are versioned independently).
echo -e "\n${GREEN}📤 Uploading testmcpy-oauth-probe to PyPI...${NC}"
if ! python -m twine upload --skip-existing oauth-probe/dist/*; then
    echo -e "\n${RED}❌ Probe upload failed${NC}"
    echo -e "${YELLOW}If this is the first ever upload of testmcpy-oauth-probe, a"
    echo -e "project-scoped PyPI token cannot create it. Use an account-scoped"
    echo -e "token once, then scope a new token to the project.${NC}"
    exit 1
fi

# Guard the ordering above rather than trusting it: refuse to publish testmcpy
# against a probe version that is not installable from PyPI.
echo -e "\n${GREEN}🔎 Verifying ${PROBE_REQUIREMENT} is installable from PyPI...${NC}"
PROBE_AVAILABLE=false
for attempt in 1 2 3 4 5; do
    if python -m pip download --no-deps --dest /tmp/probe-publish-check "${PROBE_REQUIREMENT}" >/dev/null 2>&1; then
        PROBE_AVAILABLE=true
        break
    fi
    echo "  not on PyPI yet; retrying in 15s (attempt ${attempt}/5)"
    sleep 15
done
rm -rf /tmp/probe-publish-check
if [ "$PROBE_AVAILABLE" != "true" ]; then
    echo -e "\n${RED}❌ ${PROBE_REQUIREMENT} is not installable from PyPI${NC}"
    echo -e "${RED}Refusing to publish testmcpy ${VERSION} against it — the release"
    echo -e "would be unresolvable for every consumer.${NC}"
    exit 1
fi

echo -e "\n${GREEN}📤 Uploading testmcpy to PyPI...${NC}"
python -m twine upload dist/*

if [ $? -ne 0 ]; then
    echo -e "\n${RED}❌ Upload failed${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ Successfully published to PyPI!${NC}"

# Wait a moment for PyPI to process
echo -e "\n${YELLOW}⏳ Waiting for PyPI to process...${NC}"
sleep 5

# Download from PyPI and calculate SHA256
echo -e "\n${GREEN}📥 Downloading from PyPI to calculate SHA256...${NC}"
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"
curl -sL -o "testmcpy-${VERSION}.tar.gz" "https://files.pythonhosted.org/packages/source/t/testmcpy/testmcpy-${VERSION}.tar.gz"

if [ ! -f "testmcpy-${VERSION}.tar.gz" ] || [ ! -s "testmcpy-${VERSION}.tar.gz" ]; then
    echo -e "${YELLOW}⚠️  Could not download from PyPI yet. Try again in a few minutes.${NC}"
    echo "Manual steps:"
    echo "1. curl -sL -o testmcpy-${VERSION}.tar.gz https://files.pythonhosted.org/packages/source/t/testmcpy/testmcpy-${VERSION}.tar.gz"
    echo "2. shasum -a 256 testmcpy-${VERSION}.tar.gz"
    echo "3. Update Formula/testmcpy.rb with the SHA256"
    cd -
    rm -rf "$TEMP_DIR"
else
    SHA256=$(shasum -a 256 "testmcpy-${VERSION}.tar.gz" | awk '{print $1}')
    cd -
    rm -rf "$TEMP_DIR"

    echo -e "\n${GREEN}🔐 SHA256: ${SHA256}${NC}"

    # Update Homebrew formula (URL + SHA256 must stay in sync)
    echo -e "\n${GREEN}📝 Updating Homebrew formula...${NC}"
    sed -i '' "s|testmcpy-[0-9.]*\.tar\.gz|testmcpy-${VERSION}.tar.gz|" Formula/testmcpy.rb
    sed -i '' "s/sha256 \".*\"/sha256 \"${SHA256}\"/" Formula/testmcpy.rb

    # Commit the formula update
    git add Formula/testmcpy.rb
    git commit -m "Update Homebrew formula for v${VERSION}"
    
    echo -e "${GREEN}✅ Homebrew formula updated${NC}"
fi

# Create git tag
echo -e "\n${GREEN}🏷️  Creating git tag v${VERSION}...${NC}"
git tag -a "v${VERSION}" -m "Release v${VERSION}"

# Push everything
echo -e "\n${GREEN}⬆️  Pushing to GitHub...${NC}"
git push origin ${BRANCH}
git push origin "v${VERSION}"

echo -e "\n${GREEN}✅ Publishing complete!${NC}"
echo -e "\n${YELLOW}Users can now install with:${NC}"
echo "  pip install testmcpy"
echo "  brew tap preset-io/testmcpy && brew install testmcpy"
echo ""
echo -e "${YELLOW}View on PyPI:${NC}"
echo "  https://pypi.org/project/testmcpy/${VERSION}/"
