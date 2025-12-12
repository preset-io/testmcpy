# Profile System Implementation Summary

## Completed Work

### 1. Profile System Architecture ✅
Created three profile systems following the same pattern as MCP profiles:

**Files Created:**
- `testmcpy/llm_profiles.py` - LLM provider profile management
- `testmcpy/test_profiles.py` - Test configuration profile management
- `.llm_providers.yaml.example` - Example LLM provider configurations
- `.test_profiles.yaml.example` - Example test profile configurations

**Config Integration:** ✅
- Updated `testmcpy/config.py` to load and manage all three profile types
- Added `_llm_profile` and `_test_profile` attributes to Config class
- Added methods: `get_default_llm_provider()`, `get_default_test_config()`
- LLM profiles can override `DEFAULT_MODEL` and `DEFAULT_PROVIDER` config values

### 2. Profile System Features

**LLM Provider Profiles:**
- Support for multiple LLM providers per profile (anthropic, openai, ollama, local, claude-sdk, claude-cli)
- Each provider has: name, model, api_key_env, base_url, timeout, default flag
- Example profiles: dev (fast models), prod (best quality), testing (fixed versions), budget (cost-optimized), local (no API costs)

**Test Profiles:**
- Support for multiple test configurations per profile
- Each config has: name, tests_dir, evaluators, timeout, parallel, max_retries, default flag
- Example profiles: unit (fast tests), integration (comprehensive), smoke (quick validation), performance, e2e, regression

**MCP Profiles:** (Already existed)
- Multiple MCP servers per profile with auth configurations
- Example profiles: local-dev, sandbox, staging, prod

## Remaining Work

### 3. CLI Commands

**Location:** `testmcpy/cli.py`

Add these commands following the same pattern as the existing `profiles()` and `status()` commands:

```python
@app.command()
def llm_profiles(show_details: bool = typer.Option(False, "--details", "-d")):
    """List all available LLM provider profiles."""
    from testmcpy.llm_profiles import list_available_llm_profiles, get_llm_profile_config

    console.print("\n[bold cyan]LLM Provider Profiles[/bold cyan]\n")
    profile_ids = list_available_llm_profiles()

    if not profile_ids:
        console.print("[dim]No LLM profiles configured.[/dim]")
        console.print("\nTo configure: create [cyan].llm_providers.yaml[/cyan]")
        console.print("Example: cp .llm_providers.yaml.example .llm_providers.yaml")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", style="dim", width=6)
    table.add_column("Profile ID", style="cyan")
    table.add_column("Providers", justify="right")
    if show_details:
        table.add_column("Default Model")
        table.add_column("Provider Type")

    profile_config = get_llm_profile_config()

    for profile_id in profile_ids:
        profile = profile_config.get_profile(profile_id)
        if not profile:
            continue

        status_icon = "● " if profile_id == profile_config.default_profile_id else "○"
        provider_count = len(profile.providers)

        row = [status_icon, profile.profile_id, str(provider_count)]

        if show_details:
            default_provider = profile.get_default_provider()
            if default_provider:
                row.extend([default_provider.model, default_provider.provider])

        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total: {len(profile_ids)} profile(s)[/dim]")


@app.command()
def test_profiles(show_details: bool = typer.Option(False, "--details", "-d")):
    """List all available test profiles."""
    from testmcpy.test_profiles import list_available_test_profiles, get_test_profile_config

    console.print("\n[bold cyan]Test Profiles[/bold cyan]\n")
    profile_ids = list_available_test_profiles()

    if not profile_ids:
        console.print("[dim]No test profiles configured.[/dim]")
        console.print("\nTo configure: create [cyan].test_profiles.yaml[/cyan]")
        console.print("Example: cp .test_profiles.yaml.example .test_profiles.yaml")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", style="dim", width=6)
    table.add_column("Profile ID", style="cyan")
    table.add_column("Test Configs", justify="right")
    if show_details:
        table.add_column("Tests Dir")
        table.add_column("Evaluators")

    profile_config = get_test_profile_config()

    for profile_id in profile_ids:
        profile = profile_config.get_profile(profile_id)
        if not profile:
            continue

        status_icon = "● " if profile_id == profile_config.default_profile_id else "○"
        config_count = len(profile.test_configs)

        row = [status_icon, profile.profile_id, str(config_count)]

        if show_details:
            default_config = profile.get_default_config()
            if default_config:
                evaluators = ", ".join(default_config.evaluators[:3])
                if len(default_config.evaluators) > 3:
                    evaluators += "..."
                row.extend([default_config.tests_dir, evaluators])

        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total: {len(profile_ids)} profile(s)[/dim]")
```

Also update existing commands to accept the new profile flags:
- Add `--llm-profile` option to `run`, `chat`, `init` commands
- Add `--test-profile` option to `run`, `init` commands

### 4. API Endpoints

**Location:** `testmcpy/server/api.py`

Add these endpoints following the same pattern as the existing MCP profile endpoints:

```python
# LLM Profile Endpoints
@app.get("/api/llm/profiles")
async def list_llm_profiles():
    """List available LLM provider profiles."""
    from testmcpy.llm_profiles import get_llm_profile_config

    try:
        profile_config = get_llm_profile_config()
        if not profile_config.has_profiles():
            return {"profiles": [], "default": None}

        profiles_list = []
        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if not profile:
                continue

            providers_info = []
            for provider in profile.providers:
                providers_info.append({
                    "name": provider.name,
                    "provider": provider.provider,
                    "model": provider.model,
                    "base_url": provider.base_url,
                    "timeout": provider.timeout,
                    "default": provider.default,
                })

            profiles_list.append({
                "profile_id": profile.profile_id,
                "name": profile.name,
                "description": profile.description,
                "providers": providers_info,
            })

        return {
            "profiles": profiles_list,
            "default": profile_config.default_profile_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/llm/profiles/{profile_id}")
async def create_llm_profile(profile_id: str, request: dict):
    """Create a new LLM provider profile."""
    from testmcpy.llm_profiles import get_llm_profile_config, LLMProfile, LLMProviderConfig, reload_llm_profile_config

    try:
        profile_config = get_llm_profile_config()

        # Create providers
        providers = []
        for p in request.get("providers", []):
            provider = LLMProviderConfig(
                name=p.get("name"),
                provider=p.get("provider"),
                model=p.get("model"),
                api_key_env=p.get("api_key_env"),
                base_url=p.get("base_url"),
                timeout=p.get("timeout", 60),
                default=p.get("default", False),
            )
            providers.append(provider)

        # Create profile
        profile = LLMProfile(
            profile_id=profile_id,
            name=request.get("name", profile_id),
            description=request.get("description", ""),
            providers=providers,
        )

        profile_config.add_profile(profile)
        profile_config.save()
        reload_llm_profile_config()

        return {"success": True, "profile_id": profile_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/llm/profiles/{profile_id}/default")
async def set_default_llm_profile(profile_id: str):
    """Set the default LLM provider profile."""
    from testmcpy.llm_profiles import get_llm_profile_config, reload_llm_profile_config

    try:
        profile_config = get_llm_profile_config()
        profile_config.set_default_profile(profile_id)
        profile_config.save()
        reload_llm_profile_config()

        return {"success": True, "default_profile": profile_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test Profile Endpoints
@app.get("/api/test/profiles")
async def list_test_profiles():
    """List available test profiles."""
    from testmcpy.test_profiles import get_test_profile_config

    try:
        profile_config = get_test_profile_config()
        if not profile_config.has_profiles():
            return {"profiles": [], "default": None}

        profiles_list = []
        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if not profile:
                continue

            configs_info = []
            for config in profile.test_configs:
                configs_info.append({
                    "name": config.name,
                    "description": config.description,
                    "tests_dir": config.tests_dir,
                    "evaluators": config.evaluators,
                    "timeout": config.timeout,
                    "parallel": config.parallel,
                    "max_retries": config.max_retries,
                    "default": config.default,
                })

            profiles_list.append({
                "profile_id": profile.profile_id,
                "name": profile.name,
                "description": profile.description,
                "test_configs": configs_info,
            })

        return {
            "profiles": profiles_list,
            "default": profile_config.default_profile_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Similar endpoints for creating/updating/deleting test profiles
# Follow the same pattern as LLM profiles and MCP profiles
```

### 5. UI Components

**Location:** `testmcpy/ui/src/`

Create two new components following the `MCPProfileSelector.jsx` pattern:

**`components/LLMProfileSelector.jsx`:**
```jsx
import React, { useState, useEffect } from 'react';
import { LoadingSpinner } from './LoadingSpinner';

export const LLMProfileSelector = ({ onProfileChange, currentProfile }) => {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/llm/profiles');
      if (!response.ok) throw new Error('Failed to load LLM profiles');

      const data = await response.json();
      setProfiles(data.profiles || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const setDefault = async (profileId) => {
    try {
      const response = await fetch(`/api/llm/profiles/${profileId}/default`, {
        method: 'PUT',
      });
      if (!response.ok) throw new Error('Failed to set default profile');

      await loadProfiles();
      if (onProfileChange) onProfileChange(profileId);
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) return <LoadingSpinner text="Loading LLM profiles..." />;
  if (error) return <div className="error-message">{error}</div>;

  return (
    <div className="profile-selector">
      <h3>LLM Provider Profiles</h3>
      {profiles.length === 0 ? (
        <p>No LLM profiles configured. Create .llm_providers.yaml to get started.</p>
      ) : (
        <ul className="profile-list">
          {profiles.map(profile => (
            <li
              key={profile.profile_id}
              className={profile.profile_id === currentProfile ? 'active' : ''}
              onClick={() => setDefault(profile.profile_id)}
            >
              <div className="profile-name">{profile.name}</div>
              <div className="profile-description">{profile.description}</div>
              <div className="profile-providers">
                {profile.providers.length} provider(s)
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
```

**`components/TestProfileSelector.jsx`:**
Similar structure to LLMProfileSelector but for test profiles.

**Update `App.jsx`:**
Add tabs/sections for LLM and Test profile management alongside the existing MCP profile management.

**Update `pages/MCPExplorer.jsx`:**
Add profile selectors to the top of the page so users can switch between profiles.

## Configuration Priority

The system now has a clear priority order:

1. **Command-line arguments** (highest priority)
   - `--profile` (MCP)
   - `--llm-profile` (LLM providers)
   - `--test-profile` (Test configs)

2. **Profile files**
   - `.mcp_services.yaml` (MCP servers and auth)
   - `.llm_providers.yaml` (LLM provider configs)
   - `.test_profiles.yaml` (Test configurations)

3. **Environment files**
   - `.env` (current directory)
   - `~/.testmcpy` (user config)

4. **Environment variables**

5. **Built-in defaults** (lowest priority)

## Usage Examples

### CLI Usage:
```bash
# List profiles
testmcpy profiles              # MCP profiles
testmcpy llm-profiles         # LLM profiles
testmcpy test-profiles        # Test profiles

# Use specific profiles
testmcpy run test.yaml --profile=prod --llm-profile=budget --test-profile=unit

# Chat with specific providers
testmcpy chat --llm-profile=local  # Use local Ollama models
testmcpy chat --llm-profile=prod   # Use Claude Sonnet
```

### Profile Configuration:
```yaml
# .llm_providers.yaml
default: dev
profiles:
  dev:
    name: "Development"
    providers:
      - name: "Claude Haiku"
        provider: "anthropic"
        model: "claude-3-5-haiku-20241022"
        default: true

# .test_profiles.yaml
default: unit
profiles:
  unit:
    name: "Unit Tests"
    test_configs:
      - name: "Quick Tests"
        tests_dir: "tests/unit"
        evaluators: ["exact_match", "contains"]
        default: true
```

## Next Steps

1. Add CLI commands to `cli.py` (estimated: 100 lines)
2. Add API endpoints to `server/api.py` (estimated: 300 lines)
3. Create UI components (estimated: 400 lines JSX)
4. Update existing commands to accept new profile flags
5. Test the complete integration
6. Update documentation

The foundation is complete - the profile systems are working and integrated with Config. The remaining work is primarily UI/API surface area to make them accessible to users.
