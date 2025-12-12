# Homebrew Tap Setup - Quick Guide

This repo is now configured as both a source repository AND a Homebrew tap!

## For Users

Once testmcpy is published to PyPI, users can install via Homebrew:

```bash
# Tap this repository
brew tap preset-io/testmcpy

# Install testmcpy
brew install testmcpy

# Use it
testmcpy --help
testmcpy tools
```

## For Maintainers - Enabling Homebrew Installation

### Step 1: Publish to PyPI (REQUIRED FIRST)

```bash
# Build the package
python -m build

# Upload to PyPI (requires PyPI account and API token)
python -m twine upload dist/*
```

### Step 2: Update the Formula with SHA256

Once published to PyPI, get the SHA256:

```bash
# Download the package from PyPI
wget https://files.pythonhosted.org/packages/source/t/testmcpy/testmcpy-0.1.0.tar.gz

# Calculate SHA256
shasum -a 256 testmcpy-0.1.0.tar.gz
```

Update `Formula/testmcpy.rb` line 7 with the actual SHA256.

### Step 3: Commit and Push

```bash
git add Formula/testmcpy.rb
git commit -m "Update Homebrew formula with PyPI SHA256"
git push
```

### Step 4: Done!

Users can now install with:
```bash
brew tap preset-io/testmcpy
brew install testmcpy
```

## How It Works

- Homebrew looks for a `Formula/` directory in tapped repos
- When users run `brew tap preset-io/testmcpy`, Homebrew adds this repo as a tap
- The formula downloads testmcpy from PyPI and installs it in a Homebrew-managed virtualenv
- The `testmcpy` command becomes available in `/usr/local/bin/`

## Current Status

✅ Formula created and committed
✅ Tap structure ready
⏳ Waiting for PyPI publication
⏳ Waiting for SHA256 update

Once PyPI is published and SHA256 is updated, Homebrew installation will work!
