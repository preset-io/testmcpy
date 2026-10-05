# Homebrew Formula for testmcpy

This directory contains the Homebrew formula for testmcpy.

## For Users

To install testmcpy via Homebrew:

```bash
# Tap this repository
brew tap preset-io/testmcpy

# Install testmcpy
brew install testmcpy

# Verify installation
testmcpy --help
```

## For Maintainers

### After Publishing to PyPI

The publish workflow updates `url` and `sha256` together after each release, using
`scripts/update_homebrew_formula.py`, which only writes values derived from a
validated download of the sdist PyPI serves. To do it by hand:

```bash
python3 scripts/update_homebrew_formula.py 0.1.0   # then commit Formula/testmcpy.rb
```

### Testing the Formula

```bash
# Install locally to test
brew install --build-from-source Formula/testmcpy.rb

# Or use brew audit
brew audit --strict Formula/testmcpy.rb
```

### How It Works

When someone taps `preset-io/testmcpy`, Homebrew looks for formulas in the `Formula/` directory of this repo. The formula uses `virtualenv_install_with_resources` which automatically:

1. Creates a Python virtual environment
2. Installs testmcpy and all its dependencies from PyPI
3. Creates the `testmcpy` command in `/usr/local/bin/`

This is the simplest approach and requires the package to be published on PyPI first.
