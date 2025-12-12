# Authentication Flow Recorder

The Authentication Flow Recorder is a comprehensive system for recording, replaying, and comparing OAuth, JWT, and Bearer authentication flows in testmcpy. This feature helps with debugging, documentation, and tracking authentication changes over time.

## Features

- **Complete Flow Recording**: Capture all HTTP requests, responses, timing, and status
- **Replay Capability**: Load and view saved authentication flows
- **Side-by-Side Comparison**: Compare two flows to identify what changed
- **Diff Tool**: See exact differences between working and broken auth flows
- **Export & Share**: Export flows as JSON (with optional sanitization)
- **CLI Integration**: Full command-line interface for managing recordings
- **Web API**: RESTful API endpoints for programmatic access
- **Automatic Storage**: Flows saved to `~/.testmcpy/auth_flows/`

## Use Cases

1. **Save Successful Auth Flow**: Document working authentication for team reference
2. **Compare Working vs Broken**: Identify exactly what changed when auth breaks
3. **Share with Team**: Export sanitized flows for collaboration
4. **Debug Intermittent Issues**: Record multiple attempts to spot patterns
5. **Test Auth Changes**: Compare before/after when updating auth configuration
6. **Compliance & Auditing**: Keep historical records of authentication flows

## Quick Start

### Recording an Auth Flow

Record authentication while debugging:

```bash
# Record OAuth flow from profile
testmcpy debug-auth --profile production --record --flow-name "prod_oauth_login"

# Record JWT flow with custom name
testmcpy debug-auth --type jwt --api-url https://api.example.com/token \
  --api-token xxx --api-secret yyy --record --flow-name "staging_jwt"

# Record bearer token validation
testmcpy debug-auth --type bearer --token xxx --record
```

### Listing Saved Flows

```bash
# List all saved flows
testmcpy auth-flows

# Filter by type
testmcpy auth-flows --type oauth

# Limit results
testmcpy auth-flows --limit 10
```

### Viewing a Flow

```bash
testmcpy auth-flow-view oauth_prod_oauth_login_20250111_143022.json
```

### Comparing Flows

```bash
testmcpy auth-flow-compare oauth_working_20250110.json oauth_broken_20250111.json
```

### Exporting Flows

```bash
# Export with sanitized data (default)
testmcpy auth-flow-export oauth_login.json -o shared_flow.json

# Export with full data (including secrets - use with caution!)
testmcpy auth-flow-export oauth_login.json -o full_flow.json --no-sanitize
```

### Deleting Flows

```bash
# With confirmation
testmcpy auth-flow-delete oauth_old.json

# Skip confirmation
testmcpy auth-flow-delete oauth_old.json --yes
```

## Web API Usage

### List Recordings

```bash
curl http://localhost:8000/api/auth-flows

# Filter by type
curl "http://localhost:8000/api/auth-flows?auth_type=oauth&limit=10"
```

### Get Specific Recording

```bash
curl http://localhost:8000/api/auth-flows/oauth_login_20250111.json
```

### Compare Two Recordings

```bash
curl -X POST http://localhost:8000/api/auth-flows/compare \
  -H "Content-Type: application/json" \
  -d '{
    "filepath1": "/path/to/flow1.json",
    "filepath2": "/path/to/flow2.json"
  }'
```

### Export Recording (Sanitized)

```bash
curl "http://localhost:8000/api/auth-flows/oauth_login.json/export?sanitize=true"
```

### Delete Recording

```bash
curl -X DELETE http://localhost:8000/api/auth-flows/oauth_old.json
```

### Debug Auth with Recording

```bash
curl -X POST "http://localhost:8000/api/debug-auth?record=true&flow_name=my_test" \
  -H "Content-Type: application/json" \
  -d '{
    "auth_type": "oauth",
    "client_id": "xxx",
    "client_secret": "yyy",
    "token_url": "https://oauth.example.com/token"
  }'
```

## Python API Usage

### Using AuthFlowRecorder Directly

```python
from testmcpy.auth_flow_recorder import AuthFlowRecorder

# Initialize recorder
recorder = AuthFlowRecorder()

# Start recording
recording = recorder.start_recording(
    flow_name="My OAuth Flow",
    auth_type="oauth",
    protocol_version="OAuth 2.0"
)

# Record steps
recorder.record_step(
    step_name="Token Request",
    step_type="request",
    data={"client_id": "xxx", "grant_type": "client_credentials"},
    success=True,
    duration=0.5
)

recorder.record_step(
    step_name="Token Response",
    step_type="response",
    data={"status_code": 200, "token_length": 256},
    success=True,
    duration=0.1
)

# Stop and save
recording = recorder.stop_recording(success=True)
print(f"Saved to: {recording.recording_id}")
```

### Using with AuthDebugger

```python
from testmcpy.auth_debugger import AuthDebugger
from testmcpy.auth_flow_recorder import AuthFlowRecorder

# Create recorder and debugger
recorder = AuthFlowRecorder()
debugger = AuthDebugger(enabled=True, recorder=recorder)

# Start recording
debugger.start_flow_recording(
    flow_name="Production OAuth",
    auth_type="oauth",
    protocol_version="OAuth 2.0"
)

# Debug auth flow (steps are automatically recorded)
token = await debug_oauth_flow(
    client_id="xxx",
    client_secret="yyy",
    token_url="https://oauth.example.com/token",
    debugger=debugger
)

# Save recording
saved_path = debugger.save_flow_recording(success=True)
print(f"Flow saved to: {saved_path}")
```

### Loading and Comparing Recordings

```python
from testmcpy.auth_flow_recorder import AuthFlowRecorder

recorder = AuthFlowRecorder()

# Load recordings
flow1 = recorder.load_recording("oauth_working.json")
flow2 = recorder.load_recording("oauth_broken.json")

# Compare
comparison = recorder.compare_recordings(flow1, flow2)

# Display results
recorder.display_comparison(comparison)

# Check differences
if comparison["differences"]["success_changed"]:
    print("Success status changed!")

for diff in comparison["differences"]["step_differences"]:
    if diff["type"] == "success_changed":
        print(f"Step '{diff['step_name']}' changed from {diff['from']} to {diff['to']}")
```

### Sanitizing Recordings

```python
from testmcpy.auth_flow_recorder import AuthFlowRecorder

recorder = AuthFlowRecorder()
recording = recorder.load_recording("oauth_flow.json")

# Create sanitized copy (safe to share)
sanitized = recorder.sanitize_recording(recording, keep_token_preview=True)

# Export sanitized version
recorder.export_to_json(sanitized, "oauth_flow_sanitized.json")
```

## Recording Data Structure

Each recording is stored as JSON with the following structure:

```json
{
  "recording_id": "my_flow_1704988800",
  "flow_name": "Production OAuth Login",
  "auth_type": "oauth",
  "protocol_version": "OAuth 2.0",
  "metadata": {},
  "start_time": 1704988800.0,
  "end_time": 1704988801.5,
  "duration": 1.5,
  "success": true,
  "error": null,
  "step_count": 4,
  "success_count": 4,
  "failure_count": 0,
  "created_at": "2025-01-11T14:30:00",
  "steps": [
    {
      "step_name": "1. OAuth Request Prepared",
      "step_type": "validation",
      "data": {
        "grant_type": "client_credentials",
        "client_id": "xxx...",
        "scope": "read write"
      },
      "success": true,
      "timestamp": 1704988800.0,
      "duration": 0.0,
      "metadata": {}
    },
    {
      "step_name": "2. Sending POST to Token Endpoint",
      "step_type": "request",
      "data": {
        "url": "https://oauth.example.com/token",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"}
      },
      "success": true,
      "timestamp": 1704988800.1,
      "duration": 0.5,
      "metadata": {}
    },
    {
      "step_name": "3. Response Received",
      "step_type": "response",
      "data": {
        "status_code": 200,
        "headers": {"content-type": "application/json"}
      },
      "success": true,
      "timestamp": 1704988800.6,
      "duration": 0.0,
      "metadata": {}
    },
    {
      "step_name": "4. Token Extracted",
      "step_type": "extraction",
      "data": {
        "token_length": 256,
        "token_preview": "eyJhbGc...",
        "expires_in": 3600,
        "scope": "read write",
        "token_type": "Bearer"
      },
      "success": true,
      "timestamp": 1704988800.6,
      "duration": 0.0,
      "metadata": {}
    }
  ]
}
```

## Step Types

- **request**: HTTP request being sent
- **response**: HTTP response received
- **validation**: Data validation or preparation
- **extraction**: Token or data extraction
- **error**: Error or failure

## Comparison Output

When comparing two flows, you get:

```json
{
  "recording1": {
    "id": "flow1_1704988800",
    "name": "Working Flow",
    "success": true,
    "duration": 1.5,
    "step_count": 4
  },
  "recording2": {
    "id": "flow2_1704989000",
    "name": "Broken Flow",
    "success": false,
    "duration": 2.1,
    "step_count": 3
  },
  "differences": {
    "success_changed": true,
    "step_count_delta": -1,
    "duration_delta": 0.6,
    "step_differences": [
      {
        "index": 2,
        "type": "success_changed",
        "step_name": "3. Response Received",
        "from": true,
        "to": false
      },
      {
        "index": 3,
        "type": "removed",
        "step_name": "4. Token Extracted"
      }
    ]
  }
}
```

## Security Considerations

### Sensitive Data

The recorder automatically sanitizes the following fields in saved recordings:

- `client_secret`
- `api_secret`
- `password`
- `token`
- `access_token`
- `refresh_token`

By default, tokens are truncated to show only the first 8 characters (e.g., `eyJhbGc...`).

### Export Options

- **Sanitized Export** (default): Safe to share, secrets removed
- **Full Export**: Contains all data, use only in secure environments

### Storage Location

Recordings are stored in `~/.testmcpy/auth_flows/` by default. Ensure this directory has appropriate permissions in production environments.

## Best Practices

1. **Name Your Flows**: Use descriptive names like `prod_oauth_working` or `staging_jwt_20250111`
2. **Record Baselines**: Save successful flows as baselines for comparison
3. **Regular Cleanup**: Delete old recordings to save disk space
4. **Sanitize Before Sharing**: Always use `--sanitize` when exporting for others
5. **Version Control**: Consider adding sanitized flows to git for team reference
6. **Compare After Changes**: Always compare before/after when modifying auth config

## Troubleshooting

### No Recordings Found

```bash
# Check storage directory
ls -la ~/.testmcpy/auth_flows/

# Verify recording was enabled
testmcpy debug-auth --profile prod --record --verbose
```

### Recording Not Saved

Ensure you're using the `--record` flag:

```bash
testmcpy debug-auth --profile prod --record
```

### Cannot Load Recording

Check the filename is correct:

```bash
testmcpy auth-flows  # List all available recordings
```

### Comparison Shows No Differences

Both flows may be identical. Try comparing flows from different time periods or configurations.

## Examples

### Example 1: Debug Broken OAuth

```bash
# Record the broken flow
testmcpy debug-auth --profile production --record --flow-name "oauth_broken"

# Compare with working baseline
testmcpy auth-flow-compare oauth_baseline.json oauth_oauth_broken_*.json

# Look for differences in the output
```

### Example 2: Share Flow with Team

```bash
# Record the flow
testmcpy debug-auth --profile staging --record --flow-name "staging_setup"

# Export sanitized version
testmcpy auth-flow-export oauth_staging_setup_*.json -o staging_auth_flow.json

# Share staging_auth_flow.json with team
```

### Example 3: Monitor Auth Health

```bash
# Record daily baseline
testmcpy debug-auth --profile production --record --flow-name "daily_$(date +%Y%m%d)"

# Compare with yesterday
testmcpy auth-flow-compare oauth_daily_20250110.json oauth_daily_20250111.json
```

## Related Commands

- `testmcpy debug-auth`: Debug authentication flows (add `--record` to save)
- `testmcpy profiles list`: List available MCP profiles
- `testmcpy doctor`: Run health checks on your configuration

## API Reference

For detailed API documentation, see:

- `/Users/amin/github/preset-io/testmcpy/testmcpy/auth_flow_recorder.py` - Core recorder implementation
- `/Users/amin/github/preset-io/testmcpy/testmcpy/auth_debugger.py` - Debugger integration
- `/Users/amin/github/preset-io/testmcpy/testmcpy/server/api.py` - Web API endpoints
