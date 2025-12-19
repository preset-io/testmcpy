# Changelog

All notable changes to testmcpy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (Features and capabilities added in upcoming release)

### Changed
- (Changes to existing functionality)

### Deprecated
- (Features that will be removed in future releases)

### Removed
- (Features removed in this release)

### Fixed
- (Bug fixes)

### Security
- (Security vulnerability fixes or improvements)

---

## [0.2.14] - 2025-12-18

### Fixed
- Fixed `create_llm_provider` passing unsupported kwargs (like `auth`) to providers that don't accept them

---

## [0.2.13] - 2025-12-18

### Added
- Environment variable substitution in `.llm_providers.yaml` using `${VAR}` and `${VAR:-default}` syntax
- Comprehensive unit test suite (428 tests) covering config, evaluators, formatters, profiles, smoke tests, and YAML parsing

### Fixed
- Python 3.10 compatibility with Typer by using `Optional[X]` instead of `X | None` syntax
- CI workflow now correctly runs tests from `unit_tests/` directory

### Changed
- Removed MCP Tests workflow (tests folder is gitignored for runtime-generated tests)

---

## [0.1.1] - 2025-01-16

### Added
- **Multi-layer configuration system** with clear priority ordering:
  1. Command-line options (highest)
  2. `.env` in current directory
  3. `~/.testmcpy` user config file
  4. Environment variables
  5. Built-in defaults (lowest)

- **Dynamic JWT token generation** for MCP services:
  - Configure `MCP_AUTH_API_URL`, `MCP_AUTH_API_TOKEN`, `MCP_AUTH_API_SECRET`
  - Automatically fetches and caches JWT tokens for 50 minutes
  - Eliminates need to manually manage short-lived JWT tokens

- **`testmcpy config-cmd` command** to view current configuration:
  - Shows all config values with their sources
  - Masks sensitive values (API keys, tokens)
  - Displays config file locations and existence

- **`.testmcpy.example`** - Comprehensive example configuration file with detailed comments

### Changed
- **Removed default provider/model** assumptions:
  - No longer defaults to Ollama (which requires local setup)
  - CLI now defaults to Anthropic if not configured
  - Users must explicitly configure their preferred provider in `~/.testmcpy`

- **Updated README** with:
  - Detailed configuration documentation
  - Provider setup instructions (Anthropic, Ollama, OpenAI)
  - Authentication options (static token vs dynamic JWT)
  - Clear recommendations for each provider

- **Integrated config system** into:
  - `testmcpy.cli` - All commands now use Config class
  - `testmcpy.src.mcp_client` - MCPClient uses config for URL and auth

### Fixed
- Config priority now correctly handles generic keys (ANTHROPIC_API_KEY) vs testmcpy-specific keys
- Environment variables properly fall back for generic keys while being overridden for testmcpy keys

## [0.1.0] - 2025-01-15

### Added
- Initial release of testmcpy as installable Python package
- CLI with 6 commands: `research`, `run`, `tools`, `report`, `chat`, `init`
- Support for multiple LLM providers: Anthropic, Ollama, OpenAI, Claude SDK
- MCP client with FastMCP integration
- Test runner with YAML/JSON test definitions
- Rich terminal output with beautiful formatting
- PyPI and Homebrew distribution support
