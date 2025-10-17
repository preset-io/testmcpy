# Publishing Scripts

## Manual Publishing

Use the `publish.sh` script to publish a new version:

```bash
# 1. Update version in pyproject.toml
# 2. Commit your changes
# 3. Run the publish script
./scripts/publish.sh
```

The script will:
- ✅ Check you're on main branch with no uncommitted changes
- ✅ Build the package
- ✅ Upload to PyPI (prompts for credentials)
- ✅ Download from PyPI and calculate SHA256
- ✅ Update Homebrew formula automatically
- ✅ Create and push git tag
- ✅ Push everything to GitHub

## Automated Publishing (GitHub Actions)

For automated publishing on tag push:

### Setup (One Time):

1. **Get PyPI API Token**:
   - Go to https://pypi.org/manage/account/token/
   - Create a token (scope: entire account or project-specific after first publish)
   - Copy the token (starts with `pypi-...`)

2. **Add to GitHub Secrets**:
   - Go to your repo: Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: paste your PyPI token
   - Click "Add secret"

### Usage:

```bash
# 1. Update version in pyproject.toml
vim pyproject.toml  # Change version = "0.1.0" to "0.2.0"

# 2. Commit and push
git add pyproject.toml
git commit -m "Bump version to 0.2.0"
git push

# 3. Create and push tag
git tag v0.2.0
git push origin v0.2.0
```

GitHub Actions will automatically:
- Build the package
- Publish to PyPI
- Update Homebrew formula with SHA256
- Commit and push the formula update

## Which Method to Use?

- **Manual script** (`./scripts/publish.sh`): 
  - Good for first-time setup
  - Runs locally, you see everything
  - Prompts for confirmation

- **GitHub Actions** (push tag):
  - Fully automated
  - Runs in CI/CD
  - Just push a tag and it handles everything
  - Recommended for regular releases

## First Time Publishing

For your first publish, use the manual script:

```bash
./scripts/publish.sh
```

After that, you can use either method!
