# `testmcpy profiles` Command Fixed and Enhanced ✅

## Summary

Fixed the AttributeError in `testmcpy profiles` command and added functionality to get/set the default profile from the CLI, matching the UI functionality.

## Bug Fixed

**Error**:
```
AttributeError: 'str' object has no attribute 'is_default'
```

**Root Cause**:
The `list_available_profiles()` function returns `list[str]` (profile IDs), but the code was trying to access attributes like `profile.is_default` as if they were profile objects.

**Fix**:
Updated the command to:
1. Get profile IDs from `list_available_profiles()`
2. Load each profile object using `load_profile(profile_id)`
3. Access profile attributes correctly

## New Features Added

### 1. List Profiles (Default Behavior)

```bash
testmcpy profiles
```

**Output**:
```
MCP Profiles

┏━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃     ┃ Profile ID ┃ Name                ┃ MCPs ┃
┡━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ ○   │ local-dev  │ Local Development   │    1 │
│ ○   │ sandbox    │ Sandbox Environment │    1 │
│ ○   │ staging    │ Staging Environment │    1 │
│ ●   │ prod       │ Production          │    1 │
└─────┴────────────┴─────────────────────┴──────┘

Total: 4 profile(s)
Default: prod

Commands:
  testmcpy profiles --get-default        # Show default profile
  testmcpy profiles --set-default <name> # Set default profile
  testmcpy dash                         # Interactive management
```

**Features**:
- ● = Default profile (filled circle)
- ○ = Non-default profile (empty circle)
- Shows profile ID, name, and MCP server count
- Displays total count and current default

### 2. Show Detailed Information

```bash
testmcpy profiles --details
```

**Output**:
```
┏━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃     ┃ Profile ID ┃ Name              ┃ MCPs ┃ First MCP URL      ┃ Auth Type ┃
┡━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ ○   │ local-dev  │ Local Development │    1 │ http://localhost:… │ bearer    │
│ ●   │ sandbox    │ Sandbox           │    1 │ https://66d22a6f.… │ jwt       │
│ ○   │ staging    │ Staging           │    1 │ https://a167749f.… │ jwt       │
│ ○   │ prod       │ Production        │    1 │ https://2cad1810.… │ jwt       │
└─────┴────────────┴───────────────────┴──────┴────────────────────┴───────────┘
```

**Additional Columns**:
- First MCP URL (truncated if too long)
- Auth Type (bearer, jwt, oauth, none)

### 3. Get Default Profile

```bash
testmcpy profiles --get-default
```

**Output**:
```
Default MCP Profile: prod
```

Quick way to check which profile is currently set as default.

### 4. Set Default Profile

```bash
testmcpy profiles --set-default sandbox
```

**Output**:
```
✓ Default profile set to: sandbox
Updated: /Users/amin/github/preset-io/testmcpy/.mcp_services.yaml
```

**What It Does**:
1. Validates the profile exists
2. Reads `.mcp_services.yaml`
3. Updates the `default:` field
4. Writes back to the YAML file
5. Shows confirmation

**Error Handling**:
```bash
testmcpy profiles --set-default invalid
```

**Output**:
```
Error: Profile 'invalid' not found

Available profiles:
  • local-dev
  • sandbox
  • staging
  • prod
```

## Implementation Details

**File**: `/Users/amin/github/preset-io/testmcpy/testmcpy/cli.py`

**Updated Function** (lines 2053-2191):

```python
@app.command()
def profiles(
    show_details: bool = typer.Option(False, "--details", "-d"),
    set_default: str = typer.Option(None, "--set-default"),
    get_default: bool = typer.Option(False, "--get-default"),
):
    # Get default profile
    if get_default:
        default = profile_config.default_profile
        console.print(f"Default MCP Profile: {default}")
        return

    # Set default profile
    if set_default:
        # Validate profile exists
        # Update YAML file
        config_data['default'] = set_default
        yaml.dump(config_data, f, default_flow_style=False)
        return

    # List profiles
    for profile_id in profile_ids:
        profile = load_profile(profile_id)  # Load object, not string
        is_default = profile_id == default_profile_id
        status_icon = "●" if is_default else "○"
        # Build table row...
```

## Usage Examples

### Example 1: Check Current Setup
```bash
testmcpy profiles --get-default
# Output: Default MCP Profile: prod
```

### Example 2: Switch to Sandbox
```bash
testmcpy profiles --set-default sandbox
# Output: ✓ Default profile set to: sandbox

testmcpy tools
# Now uses sandbox MCP service
```

### Example 3: Detailed View
```bash
testmcpy profiles --details
# Shows URLs and auth types
```

### Example 4: Quick Status Check
```bash
testmcpy profiles
# See all profiles with default indicator
```

## UI Parity

This CLI command now matches the UI functionality where users can:
- ✅ View all profiles
- ✅ See which is default (● indicator)
- ✅ Change the default profile
- ✅ See profile details

The difference is:
- **UI**: Click to select default profile (stored in localStorage + can write to YAML)
- **CLI**: Use `--set-default` flag to write to YAML file directly

Both methods update the same `.mcp_services.yaml` file!

## Verification

```bash
# Test all features
testmcpy profiles                      # ✅ Lists profiles
testmcpy profiles --details            # ✅ Shows URLs and auth
testmcpy profiles --get-default        # ✅ Shows: prod
testmcpy profiles --set-default sandbox # ✅ Updates YAML
testmcpy profiles --get-default        # ✅ Shows: sandbox
testmcpy profiles --set-default prod   # ✅ Resets to prod

# Error handling
testmcpy profiles --set-default invalid # ✅ Shows error + available profiles
```

All tests passed! ✅
