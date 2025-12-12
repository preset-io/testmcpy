# testmcpy - OAuth/Auth Debugging & Testing Framework

## Vision: Complete Auth Observability for MCP Development

Make testmcpy the **only tool needed** for developing, testing, debugging, and inspecting MCP servers with authentication. Combine Inspector's OAuth debugging visibility with testmcpy's testing/eval capabilities for a complete auth development experience.

---

## 🎯 Current State vs. Vision

### ✅ What We Have (Implementation)
- **OAuth Client Credentials Flow**: Fetch tokens from OAuth providers
- **JWT Dynamic Authentication**: Fetch JWT tokens from custom APIs
- **Bearer Token Auth**: Static token authentication
- **Profile-based Auth**: Store auth configs in MCP profiles
- **Basic Testing**: Auth works or fails (binary)

### ❌ What We're Missing (Gaps vs. Inspector)
1. **OAuth Flow Visibility**: No step-by-step handshake inspection
2. **Auth Debugging**: Limited error messages, no request/response inspection
3. **Auth Testing/Evals**: No evaluators for auth scenarios
4. **Token Management**: No refresh, expiration, or validation testing
5. **Interactive Debugging**: No TUI/CLI for live auth troubleshooting

---

## 🚀 Phase 1: OAuth/Auth Debugging (Inspector Parity)

### Goal: "View every step of the OAuth handshake in detail, with guided explanations"

### 1.1 Rich Auth Logging & Inspection

**New Module: `testmcpy/auth_debugger.py`**

```python
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich.syntax import Syntax
import json

class AuthDebugger:
    """Debug authentication flows with detailed logging."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.console = Console()
        self.steps = []

    def log_step(self, step_name: str, data: dict, success: bool = True):
        """Log a step in the auth flow."""
        if not self.enabled:
            return

        self.steps.append({
            "step": step_name,
            "data": data,
            "success": success
        })

        # Pretty print the step
        color = "green" if success else "red"
        icon = "✓" if success else "✗"

        self.console.print(f"\n[{color}]{icon} {step_name}[/{color}]")
        self.console.print(Panel(
            Syntax(json.dumps(data, indent=2), "json"),
            title=f"{step_name} Details",
            border_style=color
        ))

    def log_oauth_flow(self, flow_type: str, steps: dict):
        """Log complete OAuth flow with tree visualization."""
        tree = Tree(f"[cyan]OAuth {flow_type} Flow[/cyan]")

        for step_name, step_data in steps.items():
            branch = tree.add(f"[green]{step_name}[/green]")
            for key, value in step_data.items():
                branch.add(f"{key}: {value}")

        self.console.print(tree)

    def summarize(self):
        """Print summary of all auth steps."""
        if not self.enabled or not self.steps:
            return

        self.console.print("\n[cyan]Authentication Flow Summary[/cyan]")
        for i, step in enumerate(self.steps, 1):
            icon = "✓" if step["success"] else "✗"
            color = "green" if step["success"] else "red"
            self.console.print(f"  [{color}]{i}. {icon} {step['step']}[/{color}]")
```

### 1.2 Enhanced OAuth Client with Debugging

**Update: `testmcpy/src/mcp_client.py`**

Add debugging to `_fetch_oauth_token()`:

```python
async def _fetch_oauth_token(
    self,
    client_id: str,
    client_secret: str,
    token_url: str,
    scopes: list[str] | None = None,
    debug: bool = False
) -> str:
    """Fetch OAuth access token with optional debugging."""

    debugger = AuthDebugger(enabled=debug)

    # Step 1: Prepare request
    request_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": "***" if not debug else client_secret[:8] + "...",
        "scope": " ".join(scopes) if scopes else "",
    }
    debugger.log_step("1. OAuth Request Prepared", request_data)

    try:
        async with httpx.AsyncClient() as client:
            # Step 2: Send request
            debugger.log_step("2. Sending POST to Token Endpoint", {
                "url": token_url,
                "headers": {"Content-Type": "application/x-www-form-urlencoded"}
            })

            response = await client.post(token_url, data=request_data, ...)

            # Step 3: Response received
            debugger.log_step("3. Response Received", {
                "status_code": response.status_code,
                "headers": dict(response.headers)
            })

            response.raise_for_status()
            data = response.json()

            # Step 4: Token extracted
            token = data["access_token"]
            debugger.log_step("4. Token Extracted", {
                "token_length": len(token),
                "token_preview": token[:20] + "...",
                "expires_in": data.get("expires_in", "unknown"),
                "scope": data.get("scope", "unknown")
            }, success=True)

            debugger.summarize()
            return token

    except httpx.HTTPError as e:
        debugger.log_step("ERROR: HTTP Request Failed", {
            "error": str(e),
            "status_code": getattr(e.response, "status_code", "N/A"),
            "response_body": getattr(e.response, "text", "N/A")
        }, success=False)
        debugger.summarize()
        raise MCPError(f"OAuth token fetch failed: {e}")
```

### 1.3 CLI Commands for Auth Debugging

**New: `testmcpy debug-auth` command**

```bash
# Debug OAuth flow for a profile
testmcpy debug-auth --profile production --verbose

# Debug specific auth type
testmcpy debug-auth --type oauth --client-id xxx --client-secret yyy --token-url https://...

# Save debug trace to file
testmcpy debug-auth --profile prod --output auth-trace.json

# Interactive auth debugger (TUI)
testmcpy debug-auth --interactive
```

**Output:**
```
  ▀█▀ █▀▀ █▀ ▀█▀ █▀▄▀█ █▀▀ █▀█ █▄█
   █  ██▄ ▄█  █  █ ▀ █ █▄▄ █▀▀  █

  🔐 Auth Debugger - OAuth Client Credentials

✓ 1. OAuth Request Prepared
┌─ OAuth Request Prepared Details ─────────────────┐
│ {                                                 │
│   "grant_type": "client_credentials",            │
│   "client_id": "my-client-123",                  │
│   "client_secret": "abc12345...",                │
│   "scope": "read write"                          │
│ }                                                 │
└───────────────────────────────────────────────────┘

✓ 2. Sending POST to Token Endpoint
┌─ Sending POST to Token Endpoint Details ─────────┐
│ {                                                 │
│   "url": "https://auth.example.com/oauth/token", │
│   "headers": {                                    │
│     "Content-Type": "application/x-www-form..."  │
│   }                                               │
│ }                                                 │
└───────────────────────────────────────────────────┘

✓ 3. Response Received
┌─ Response Received Details ──────────────────────┐
│ {                                                 │
│   "status_code": 200,                            │
│   "headers": {                                    │
│     "content-type": "application/json",          │
│     "cache-control": "no-store"                  │
│   }                                               │
│ }                                                 │
└───────────────────────────────────────────────────┘

✓ 4. Token Extracted
┌─ Token Extracted Details ────────────────────────┐
│ {                                                 │
│   "token_length": 1243,                          │
│   "token_preview": "eyJhbGciOiJSUzI1NiIs...",   │
│   "expires_in": 3600,                            │
│   "scope": "read write"                          │
│ }                                                 │
└───────────────────────────────────────────────────┘

Authentication Flow Summary
  1. ✓ OAuth Request Prepared
  2. ✓ Sending POST to Token Endpoint
  3. ✓ Response Received
  4. ✓ Token Extracted

🎉 OAuth authentication successful!
```

---

## 🧪 Phase 2: Auth Testing & Evaluators

### Goal: Test authentication flows like any other MCP capability

### 2.1 New Auth Evaluators

**New: `testmcpy/evals/auth_evaluators.py`**

```python
from testmcpy.evals.base_evaluators import BaseEvaluator

class AuthSuccessfulEvaluator(BaseEvaluator):
    """Evaluate if authentication was successful."""

    def evaluate(self, test_result) -> bool:
        return test_result.auth_success and not test_result.auth_error

class TokenValidEvaluator(BaseEvaluator):
    """Evaluate if OAuth/JWT token is valid and not expired."""

    def evaluate(self, test_result) -> bool:
        # Check token is present
        if not test_result.auth_token:
            return False

        # Check token format (JWT)
        if self.args.get("format") == "jwt":
            import jwt
            try:
                jwt.decode(test_result.auth_token, options={"verify_signature": False})
                return True
            except:
                return False

        # Check token length
        min_length = self.args.get("min_length", 10)
        return len(test_result.auth_token) >= min_length

class TokenRefreshEvaluator(BaseEvaluator):
    """Evaluate if token refresh works correctly."""

    def evaluate(self, test_result) -> bool:
        # Check if refresh was attempted
        if not test_result.refresh_attempted:
            return False

        # Check if new token was obtained
        return (
            test_result.refresh_success and
            test_result.new_token != test_result.old_token
        )

class OAuth2FlowEvaluator(BaseEvaluator):
    """Evaluate OAuth2 flow completion."""

    def evaluate(self, test_result) -> bool:
        required_steps = [
            "request_prepared",
            "token_endpoint_called",
            "response_received",
            "token_extracted"
        ]

        return all(
            step in test_result.auth_flow_steps
            for step in required_steps
        )

class AuthErrorHandlingEvaluator(BaseEvaluator):
    """Evaluate proper error handling for auth failures."""

    def evaluate(self, test_result) -> bool:
        # Should have clear error message
        if not test_result.auth_error:
            return False

        # Check error message quality
        error_msg = test_result.auth_error_message
        required_info = self.args.get("required_info", [])

        return all(
            info.lower() in error_msg.lower()
            for info in required_info
        )
```

### 2.2 Auth Test Suite Definition

**Example: `tests/auth_tests.yaml`**

```yaml
version: "1.0"
name: "OAuth Authentication Test Suite"

tests:
  - name: "test_oauth_success"
    description: "Verify OAuth client credentials flow succeeds"
    auth:
      type: oauth
      client_id: ${OAUTH_CLIENT_ID}
      client_secret: ${OAUTH_CLIENT_SECRET}
      token_url: "https://auth.example.com/oauth/token"
      scopes: ["read", "write"]
    evaluators:
      - name: "auth_successful"
      - name: "token_valid"
        args:
          format: "jwt"
          min_length: 100
      - name: "oauth2_flow_complete"

  - name: "test_jwt_dynamic_fetch"
    description: "Verify dynamic JWT token fetch"
    auth:
      type: jwt
      api_url: "https://api.example.com/auth/token"
      api_token: ${JWT_API_TOKEN}
      api_secret: ${JWT_API_SECRET}
    evaluators:
      - name: "auth_successful"
      - name: "token_valid"
        args:
          format: "jwt"

  - name: "test_invalid_credentials"
    description: "Verify proper error handling for invalid credentials"
    auth:
      type: oauth
      client_id: "invalid-client"
      client_secret: "invalid-secret"
      token_url: "https://auth.example.com/oauth/token"
    expect_failure: true
    evaluators:
      - name: "auth_error_handling"
        args:
          required_info: ["invalid_client", "unauthorized"]

  - name: "test_token_refresh"
    description: "Verify token refresh mechanism"
    auth:
      type: oauth
      client_id: ${OAUTH_CLIENT_ID}
      client_secret: ${OAUTH_CLIENT_SECRET}
      token_url: "https://auth.example.com/oauth/token"
      refresh_enabled: true
    actions:
      - wait: 3600  # Wait for token to expire
      - refresh_token: true
    evaluators:
      - name: "token_refresh_successful"

  - name: "test_mcp_with_auth"
    description: "Verify MCP tool calling with OAuth works"
    auth:
      type: oauth
      client_id: ${OAUTH_CLIENT_ID}
      client_secret: ${OAUTH_CLIENT_SECRET}
      token_url: "https://auth.example.com/oauth/token"
    prompt: "List all available datasets"
    evaluators:
      - name: "auth_successful"
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"
      - name: "execution_successful"
```

**Run auth tests:**
```bash
testmcpy run tests/auth_tests.yaml --debug-auth

# Run only auth evaluators
testmcpy run tests/ --filter auth

# Generate auth test report
testmcpy report --auth-only
```

---

## 🎨 Phase 3: Interactive Auth Debugging (TUI)

### Goal: Beautiful CLI interface for auth troubleshooting

### 3.1 Auth Debug Screen

**New: `testmcpy dash --auth-debug`**

```
╔═══════════════════════════════════════════════════════════════════════════╗
║ Auth Debugger - OAuth Client Credentials                 [h] Home [?] Help║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Configuration                       │ Flow Steps                           ║
╟─────────────────────────────────────┼──────────────────────────────────────╢
║ Auth Type       OAuth 2.0           │ ✓ 1. Request Prepared                ║
║ Client ID       my-client-123       │ ✓ 2. Token Endpoint Called           ║
║ Token URL       auth.example.com... │ ✓ 3. Response Received (200 OK)      ║
║ Scopes          read, write         │ ✓ 4. Token Extracted                 ║
║                                     │                                      ║
║ [e] Edit Config                     │ Duration: 234ms                      ║
║ [r] Retry Auth                      │                                      ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Request Details                                                             ║
╟─────────────────────────────────────────────────────────────────────────────╢
║ POST https://auth.example.com/oauth/token                                  ║
║                                                                             ║
║ Headers:                                                                    ║
║   Content-Type: application/x-www-form-urlencoded                          ║
║                                                                             ║
║ Body:                                                                       ║
║   grant_type=client_credentials                                            ║
║   client_id=my-client-123                                                  ║
║   client_secret=***                                                        ║
║   scope=read+write                                                         ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Response Details                                                            ║
╟─────────────────────────────────────────────────────────────────────────────╢
║ Status: 200 OK                                                             ║
║                                                                             ║
║ Headers:                                                                    ║
║   content-type: application/json                                           ║
║   cache-control: no-store                                                  ║
║                                                                             ║
║ Body:                                                                       ║
║   {                                                                         ║
║     "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",            ║
║     "token_type": "Bearer",                                                ║
║     "expires_in": 3600,                                                    ║
║     "scope": "read write"                                                  ║
║   }                                                                         ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Token Details                                                               ║
╟─────────────────────────────────────────────────────────────────────────────╢
║ Type          Bearer                                                        ║
║ Length        1243 characters                                              ║
║ Format        JWT                                                           ║
║ Expires       2025-11-11 15:23:45 (59m 32s remaining)                      ║
║                                                                             ║
║ JWT Claims:                                                                 ║
║   iss: auth.example.com                                                    ║
║   sub: my-client-123                                                       ║
║   aud: api.example.com                                                     ║
║   exp: 1731341025                                                          ║
║   iat: 1731337425                                                          ║
║   scope: read write                                                        ║
║                                                                             ║
║ [v] Verify Token  [c] Copy Token  [t] Test with MCP                        ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### 3.2 Auth Inspector Integration

**New: `testmcpy inspect` command**

Combine Inspector's OAuth debugging with testmcpy's testing:

```bash
# Inspect auth flow and generate test
testmcpy inspect --profile prod --generate-test

# Live auth monitoring
testmcpy inspect --watch --profile prod

# Compare auth across environments
testmcpy inspect --compare dev,staging,prod
```

---

## 📊 Phase 4: Auth Analytics & Reporting

### Goal: Track auth performance, reliability, and issues

### 4.1 Auth Metrics Dashboard

**New: `testmcpy dash --auth-metrics`**

```
╔═══════════════════════════════════════════════════════════════════════════╗
║ Auth Metrics Dashboard - Last 30 Days                                      ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Success Rate                        │ Token Fetch Times                    ║
╟─────────────────────────────────────┼──────────────────────────────────────╢
║ OAuth      ███████████████░ 98.5%   │ Avg: 245ms    P95: 450ms            ║
║ JWT        ████████████████ 99.2%   │ Min: 120ms    P99: 890ms            ║
║ Bearer     ████████████████ 100%    │ Max: 1.2s                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Recent Failures (2)                                                         ║
╟─────────────────────────────────────────────────────────────────────────────╢
║ 2025-11-10 14:32  OAuth  invalid_client  prod                              ║
║ 2025-11-09 09:15  JWT    timeout         staging                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Token Lifecycle                                                             ║
╟─────────────────────────────────────────────────────────────────────────────╢
║ Active Tokens       12                                                      ║
║ Expiring Soon       3 (within 5 minutes)                                   ║
║ Avg Token TTL       3600s (1 hour)                                         ║
║ Refresh Success     100% (45/45)                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### 4.2 Auth Test Reports

**New report format:**

```bash
testmcpy report --auth-summary

# Output:
Auth Test Summary - Run #42 (2025-11-11 14:23:45)
═══════════════════════════════════════════════════

Profiles Tested: 3 (prod, staging, dev)
Total Auth Tests: 15
Passed: 14 (93.3%)
Failed: 1 (6.7%)

By Auth Type:
  OAuth         6/6 ✓
  JWT           5/6 ✗ (1 failure: test_jwt_dynamic_fetch on staging)
  Bearer        3/3 ✓

Performance:
  Avg Auth Time:  234ms
  P95 Auth Time:  450ms
  Max Auth Time:  1.2s (staging JWT)

Failures:
  1. test_jwt_dynamic_fetch (staging)
     Error: Connection timeout to https://staging-api.example.com/auth/token
     Duration: 10.0s (timeout)
     Recommendation: Check staging API availability
```

---

## 🎯 Success Metrics

### Developer Experience
- ✅ Debug OAuth flows without external tools (no Inspector needed)
- ✅ Test auth scenarios like any other MCP feature
- ✅ Catch auth regressions in CI/CD
- ✅ Monitor auth reliability across environments

### Feature Completeness
- ✅ **Debugging**: Step-by-step OAuth/JWT/Bearer flow inspection
- ✅ **Testing**: Auth-specific evaluators and test suites
- ✅ **Inspection**: Live auth monitoring and troubleshooting
- ✅ **Analytics**: Auth metrics, reporting, and alerting

### Parity with Inspector
- ✅ OAuth flow visualization (CLI + TUI)
- ✅ Request/response inspection
- ✅ Guided explanations for each step
- ✅ **PLUS**: Testing, evals, CI/CD integration, multi-environment comparison

---

## 🗓️ Implementation Roadmap

### Phase 1: OAuth/Auth Debugging (2 weeks)
- Week 1: `AuthDebugger` class, enhanced logging, CLI commands
- Week 2: TUI auth debug screen, request/response inspection

### Phase 2: Auth Testing & Evaluators (2 weeks)
- Week 1: Auth evaluators implementation
- Week 2: Auth test suite format, integration with test runner

### Phase 3: Interactive Auth Debugging (1 week)
- TUI screens for live auth monitoring
- Interactive auth troubleshooting

### Phase 4: Auth Analytics & Reporting (1 week)
- Metrics collection and dashboard
- Auth-specific reports and alerts

**Total: 6 weeks to complete auth observability**

---

## 💡 Why This Makes testmcpy Complete

### What Inspector Does
- Shows OAuth handshake details
- Visual OAuth flow
- Guided explanations

### What testmcpy Will Do (After This)
✅ Everything Inspector does (OAuth debugging)
✅ **PLUS** testing with evaluators
✅ **PLUS** CI/CD integration
✅ **PLUS** multi-environment comparison
✅ **PLUS** auth analytics and metrics
✅ **PLUS** token lifecycle management
✅ **PLUS** all in beautiful CLI/TUI

**Result: testmcpy becomes the ONE tool for MCP development** - inspect, debug, test, and monitor all auth scenarios without ever leaving the terminal.

---

## 🔗 Related Documentation
- [Current PROJECT.md](PROJECT.md) - TUI dashboard vision
- [MCP Profiles](testmcpy/mcp_profiles.py) - Profile-based auth
- [Auth Examples](examples/auth_examples.py) - Current auth usage
- [Evaluator Reference](docs/EVALUATOR_REFERENCE.md) - Existing evaluators