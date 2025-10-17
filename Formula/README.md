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

Once testmcpy is published to PyPI, update the formula with the correct SHA256:

```bash
# Download the package from PyPI
wget https://files.pythonhosted.org/packages/source/t/testmcpy/testmcpy-0.1.0.tar.gz

# Calculate SHA256
shasum -a 256 testmcpy-0.1.0.tar.gz

# Update the sha256 in testmcpy.rb with the calculated value
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
