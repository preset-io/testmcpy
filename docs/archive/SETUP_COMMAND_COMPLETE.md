# Setup Command Implementation - Complete

## Summary

Successfully rewrote the `testmcpy setup` command to create YAML-based configuration files instead of using `.env` or `~/.testmcpy` files. The setup wizard now creates `.llm_providers.yaml` and `.mcp_services.yaml` in the current directory with all API keys stored directly in the files.

## Changes Made

### 1. Rewrote `testmcpy setup` Command (cli.py:935-1246)

**Key Features:**
- Creates `.llm_providers.yaml` and `.mcp_services.yaml` in current directory
- Detects API keys from environment (ANTHROPIC_API_KEY, OPENAI_API_KEY) and offers to save them
- Interactive prompts for LLM provider (Claude, OpenAI, Ollama)
- Interactive prompts for MCP service URL and authentication
- Idempotent - safe to run multiple times
- `--force` flag to overwrite existing files
- No longer uses `~/.testmcpy` for API keys (as explicitly requested by user)

**Configuration Flow:**

1. **LLM Provider Configuration**
   - Detects API keys from environment and displays them
   - Asks user which provider to use (Anthropic/OpenAI/Ollama)
   - Asks which model to use with that provider
   - Saves API key directly to `.llm_providers.yaml`

2. **MCP Service Configuration**
   - Detects current MCP URL from existing config
   - Asks for new MCP URL or uses existing
   - Asks for authentication method (JWT/Bearer/None)
   - Saves auth credentials to `.mcp_services.yaml`

### 2. Updated Documentation

**README.md (lines 215-272):**
- Rewrote "Configuration" section to focus on `testmcpy setup` command
- Added examples showing API keys stored directly in `.llm_providers.yaml`
- Documented idempotent behavior and `--force` flag
- Updated configuration priority chain

**INSTALLATION.md (lines 60-141):**
- Added "Quick Setup (Recommended)" section highlighting `testmcpy setup`
- Detailed explanation of what setup creates
- Configuration priority documentation
- Examples showing `api_key: "your-key-here"` format (not `api_key_env`)

### 3. Previous Related Changes (from earlier in conversation)

**CLI (cli.py):**
- Fixed all `config.mcp_url` → `config.get_mcp_url()` references (lines 86, 139, 306, 450, 753, 986, 1301, 1618, 1806, 2452)
- Updated DEFAULT_MODEL/DEFAULT_PROVIDER to use LLM profile (lines 82-92)

**Example Files:**
- `.llm_providers.yaml.example` - Changed from `api_key_env` to `api_key` with direct keys
- `.test_profiles.yaml.example` - Rewrote with MCP-focused test scenarios (basic, validation, auth, workflows, edge_cases)
- `.env.example` - Simplified to be minimal with notes about YAML files

**UI Components:**
- `App.jsx` - Added LLM profile modal, removed /profiles route
- `ChatInterface.jsx` - Removed model/provider dropdowns, uses LLM profile from sidebar
- `TestManager.jsx` - Added 3 profile selectors (MCP, LLM, Test)

## Verification

```bash
# Verify CLI imports
python3 -c "from testmcpy.cli import app; print('CLI imports successfully')"
# Output: CLI imports successfully

# Check setup help
testmcpy setup --help
# Shows: Interactive setup wizard for testmcpy configuration
#        Creates .llm_providers.yaml and .mcp_services.yaml

# Verify serve starts
testmcpy serve --no-browser
# Output: Server starting at http://127.0.0.1:8000

# Check config
testmcpy config-cmd
# Shows: DEFAULT_MODEL: claude-sonnet-4-5 (Source: LLM Profile)
#        DEFAULT_PROVIDER: anthropic (Source: LLM Profile)
```

## User Requirements Met

✅ API keys stored in `.llm_providers.yaml` (NOT in `~/.testmcpy`)
✅ Setup command creates both `.llm_providers.yaml` and `.mcp_services.yaml`
✅ Setup detects environment variables and suggests them to user
✅ Setup is idempotent (safe to run multiple times)
✅ Setup doesn't use environment variables in actual code - only YAML profiles
✅ MCP profiles can be configured via setup
✅ Test profiles don't need interactive setup (can be edited manually)
✅ All documentation updated to reflect new approach
✅ Fixed `config.mcp_url` AttributeError

## Configuration Priority Chain

The final configuration loading order is:

1. CLI options (e.g., `--model claude-opus-4-1`)
2. LLM Profile (`.llm_providers.yaml`)
3. MCP Profile (`.mcp_services.yaml`)
4. Environment variables (`.env` or system)

This ensures maximum flexibility while following the user's preference for YAML-based configuration.

## Next Steps (Optional)

The profile system is now complete and fully functional. Potential future enhancements:

1. Add `testmcpy profiles edit` command to open YAML files in editor
2. Add `testmcpy profiles validate` to check YAML syntax
3. Add profile templates for common setups (e.g., `testmcpy setup --template anthropic-prod`)
4. Add profile switching in the TUI dashboard
5. Add profile management to the web UI (already has profile selectors, could add CRUD)

## Files Modified

- `testmcpy/cli.py` - Rewrote setup command, fixed config references
- `README.md` - Updated configuration section
- `INSTALLATION.md` - Added setup wizard documentation
- `.llm_providers.yaml.example` - Changed to use direct API keys
- `.test_profiles.yaml.example` - Rewrote with MCP-focused profiles
- `.env.example` - Simplified to minimal

## Files Created

- `SETUP_COMMAND_COMPLETE.md` - This summary document
