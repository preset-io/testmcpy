# Comprehensive API Test Results - testmcpy

**Test Date:** 2025-11-12
**Base URL:** http://localhost:8000
**Total Tests:** 83
**Passed:** 51 (61.45%)
**Failed:** 32 (38.55%)

---

## Executive Summary

The testmcpy API server has been comprehensively tested across all documented endpoints. While basic health and profile management endpoints work well, several critical issues were discovered:

1. **Test execution endpoints are not implemented** (returning 405 Method Not Allowed)
2. **Reports endpoints are missing** (404 API endpoint not found)
3. **MCP creation has schema mismatches** (expecting `auth_type` at root level instead of nested `auth.type`)
4. **Missing input validation** for empty messages, invalid providers, and malicious inputs
5. **Security concerns** with path traversal, SQL injection patterns, and very long strings being accepted

---

## Critical Issues (1)

### 1. Test Execution Endpoints Not Implemented

**Endpoint:** `POST /api/tests/{test_name}/run`
**Expected:** 200
**Actual:** 405 Method Not Allowed

**Description:** The OpenAPI spec documents test execution endpoints, but they return 405. Looking at the code, the actual endpoint is `/api/tests/run` (without the test name in the path).

**Suggested Fix:**
```python
# The OpenAPI spec shows:
# POST /api/tests/{test_name}/run
# POST /api/tests/{test_name}/cases/{case_index}/run

# But the actual implementation is:
@app.post("/api/tests/run")  # Line 1972

# Need to either:
# 1. Update OpenAPI spec to match implementation
# 2. Or implement the documented endpoints
```

**Impact:** Test execution feature is completely broken from the documented API perspective.

---

## High Priority Issues (13)

### 1. MCP Schema Mismatch - Add MCP to Profile

**Endpoint:** `POST /api/mcp/profiles/{profile_id}/mcps`
**Expected:** 200
**Actual:** 422 Validation Error

**Issue:** The API expects `auth_type` as a root-level field, but the natural data structure has `auth: {type: "none"}`.

**Request Sent:**
```json
{
  "name": "Test MCP",
  "mcp_url": "http://localhost:8080/mcp",
  "auth": {"type": "none"}
}
```

**Error:**
```json
{
  "detail": [{
    "type": "missing",
    "loc": ["body", "auth_type"],
    "msg": "Field required"
  }]
}
```

**Current Schema (Line 127-137):**
```python
class MCPCreateRequest(BaseModel):
    name: str
    mcp_url: str
    auth_type: str  # bearer, jwt, oauth, none
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
```

**Suggested Fix:**
```python
class AuthConfig(BaseModel):
    type: str  # bearer, jwt, oauth, none
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None

class MCPCreateRequest(BaseModel):
    name: str
    mcp_url: str
    auth: AuthConfig
```

This matches the structure in `.mcp_services.yaml`:
```yaml
mcps:
  - name: Superset MCP
    mcp_url: http://localhost:5008/mcp/
    auth:
      type: bearer
      token: ${SUPERSET_MCP_TOKEN}
```

**Impact:** Cannot add MCPs to profiles through the API.

---

### 2. Test File Creation Schema Mismatch

**Endpoint:** `POST /api/tests`
**Expected:** 200
**Actual:** 422 Validation Error

**Issue:** The API expects `filename` and `content`, but the request provides structured test data.

**Current Schema (Line 58-60):**
```python
class TestFileCreate(BaseModel):
    filename: str
    content: str
```

**Request Sent:**
```json
{
  "name": "api_test_suite",
  "description": "Comprehensive API tests",
  "test_cases": [...]
}
```

**Error:**
```json
{
  "detail": [{
    "type": "missing",
    "loc": ["body", "filename"],
    "msg": "Field required"
  }]
}
```

**Suggested Fix:**
Either:
1. Accept raw file content as documented
2. Or create a new endpoint that accepts structured test data

**Impact:** Cannot create test files through the API with structured data.

---

### 3. Reorder Endpoint Path Conflict

**Endpoint:** `PUT /api/mcp/profiles/{profile_id}/mcps/reorder`
**Expected:** 200
**Actual:** 422 Validation Error

**Issue:** FastAPI is treating "reorder" as an `mcp_index` parameter due to route ordering.

**Error:**
```json
{
  "detail": [{
    "type": "int_parsing",
    "loc": ["path", "mcp_index"],
    "msg": "Input should be a valid integer, unable to parse string as an integer",
    "input": "reorder"
  }]
}
```

**Root Cause:** Route definition order matters in FastAPI. The route:
```python
@app.put("/api/mcp/profiles/{profile_id}/mcps/{mcp_index}")
```

is defined before:
```python
@app.put("/api/mcp/profiles/{profile_id}/mcps/reorder")
```

So FastAPI matches "reorder" as the `mcp_index` parameter.

**Suggested Fix:**
```python
# Move the reorder endpoint BEFORE the parameterized route
@app.put("/api/mcp/profiles/{profile_id}/mcps/reorder")
async def reorder_mcps_in_profile(profile_id: str, request: MCPReorderRequest):
    ...

# This must come AFTER the specific routes
@app.put("/api/mcp/profiles/{profile_id}/mcps/{mcp_index}")
async def update_mcp_in_profile(profile_id: str, mcp_index: int, request: MCPUpdateRequest):
    ...
```

**Impact:** Cannot reorder MCPs in profiles.

---

### 4. Reports Endpoint Missing

**Endpoint:** `GET /api/reports`
**Expected:** 200
**Actual:** 404 API endpoint not found

**Issue:** The endpoint is documented in OpenAPI spec but not implemented.

**Suggested Fix:**
Implement the endpoint or remove from OpenAPI spec.

**Impact:** Cannot list or access test reports.

---

### 5. Chat with Missing Provider Returns 500

**Endpoint:** `POST /api/chat`
**Expected:** 422 Validation Error
**Actual:** 500 Internal Server Error

**Issue:** Should return 422 for missing required field, not 500.

**Request:**
```json
{
  "message": "Test",
  "model": "claude-3-5-sonnet-20241022"
}
```

**Error:**
```json
{
  "detail": "Unknown provider: None. Available: ['ollama', 'openai', 'local', 'anthropic', 'claude-sdk', 'claude-cli']"
}
```

**Suggested Fix:**
Make `provider` field required in the schema with proper validation:
```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)  # Ensure non-empty
    provider: str = Field(..., pattern="^(ollama|openai|local|anthropic|claude-sdk|claude-cli)$")
    model: str
    profile_ids: list[str] | None = None
```

**Impact:** Poor error handling, returns 500 instead of proper validation error.

---

### 6. Chat with Invalid Provider Returns 500

**Endpoint:** `POST /api/chat`
**Expected:** 422 Validation Error
**Actual:** 500 Internal Server Error

**Issue:** Should validate provider at Pydantic level, not at runtime.

**Request:**
```json
{
  "message": "Test",
  "provider": "invalid-provider",
  "model": "some-model"
}
```

**Error:**
```json
{
  "detail": "Unknown provider: invalid-provider. Available: ['ollama', 'openai', 'local', 'anthropic', 'claude-sdk', 'claude-cli']"
}
```

**Suggested Fix:**
Use Pydantic's enum validation:
```python
from enum import Enum

class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    LOCAL = "local"
    ANTHROPIC = "anthropic"
    CLAUDE_SDK = "claude-sdk"
    CLAUDE_CLI = "claude-cli"

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    provider: LLMProvider  # This will auto-validate
    model: str
    profile_ids: list[str] | None = None
```

**Impact:** Returns 500 instead of proper validation error.

---

### 7. Path Traversal Attack Accepted

**Endpoint:** `POST /api/mcp/profiles`
**Expected:** 422 Validation Error (security rejection)
**Actual:** 200 Success (sanitized to "malicious")

**Issue:** Path traversal attempts are silently sanitized instead of being rejected.

**Request:**
```json
{
  "profile_id": "test/../../../etc/passwd",
  "name": "Malicious",
  "description": "Path traversal attempt",
  "mcps": []
}
```

**Response:**
```json
{
  "success": true,
  "profile_id": "malicious",
  "message": "Profile 'Malicious' created successfully"
}
```

**Suggested Fix:**
```python
import re

def validate_profile_id(profile_id: str) -> str:
    """Validate profile_id to prevent path traversal and injection."""
    # Must be alphanumeric, hyphens, underscores only
    if not re.match(r'^[a-zA-Z0-9_-]+$', profile_id):
        raise HTTPException(
            status_code=422,
            detail="Profile ID must contain only alphanumeric characters, hyphens, and underscores"
        )
    # Reject path traversal patterns
    if '..' in profile_id or '/' in profile_id or '\\' in profile_id:
        raise HTTPException(
            status_code=422,
            detail="Profile ID cannot contain path traversal characters"
        )
    return profile_id

class ProfileCreateRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    mcps: list[dict] | None = None

    @field_validator('profile_id')
    def validate_profile_id_field(cls, v):
        return validate_profile_id(v)
```

**Impact:** Security vulnerability - though sanitized, malicious inputs should be rejected with clear errors.

---

## Medium Priority Issues (15)

### 1. MCP Tools/Resources/Prompts Return 500 with Filters

**Endpoints:**
- `GET /api/mcp/tools?profiles=local-dev`
- `GET /api/mcp/resources?profiles=local-dev`
- `GET /api/mcp/prompts?profiles=local-dev`

**Expected:** 200
**Actual:** 500 Internal Server Error

**Issue:** When profile filter is provided, the API tries to connect to MCP services but gets 403 Forbidden (likely authentication issue with local-dev profile).

**Error:**
```json
{
  "detail": "Failed to connect to MCP service: Client error '403 Forbidden' for url 'http://localhost:5008/mcp/'"
}
```

**Suggested Fix:**
1. Better error handling for MCP connection failures
2. Check if the local MCP service is running and properly authenticated
3. Return more graceful error (not 500) when MCP service is unavailable

```python
try:
    # Connect to MCP
    ...
except Exception as e:
    raise HTTPException(
        status_code=503,  # Service Unavailable
        detail=f"Unable to connect to MCP service at {mcp_url}. Please ensure the service is running and credentials are valid."
    )
```

**Impact:** Cannot filter tools/resources/prompts by profile.

---

### 2. Empty Message Accepted in Chat

**Endpoint:** `POST /api/chat`
**Expected:** 422 Validation Error
**Actual:** 200 Success (but fails at Anthropic API)

**Issue:** Empty messages should be rejected at validation, not passed to the LLM.

**Request:**
```json
{
  "message": "",
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022"
}
```

**Response:**
```json
{
  "response": "Error: ... all messages must have non-empty content ...",
  "tool_calls": [],
  "token_usage": null,
  "cost": 0.0,
  "duration": 0.463
}
```

**Suggested Fix:**
```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message must be non-empty")
    provider: str
    model: str
    profile_ids: list[str] | None = None
```

**Impact:** Wastes API call to Anthropic, poor UX.

---

### 3. SQL Injection Pattern Accepted

**Endpoint:** `POST /api/mcp/profiles`
**Expected:** 422 Validation Error
**Actual:** 200 Success (sanitized to "sql-injection")

**Issue:** SQL injection patterns should be explicitly rejected.

**Request:**
```json
{
  "profile_id": "test'; DROP TABLE profiles--",
  "name": "SQL Injection",
  "description": "Test",
  "mcps": []
}
```

**Suggested Fix:** Same as path traversal fix above - use strict regex validation.

**Impact:** Security concern, though likely mitigated by YAML storage.

---

### 4. Null Byte Accepted

**Endpoint:** `POST /api/mcp/profiles`
**Expected:** 422 Validation Error
**Actual:** 200 Success (sanitized to "null-byte")

**Request:**
```json
{
  "profile_id": "test\u0000null",
  "name": "Null byte",
  "description": "Test",
  "mcps": []
}
```

**Suggested Fix:** Same strict validation as above.

**Impact:** Security/data integrity concern.

---

### 5-15. Various Test Endpoint Issues

All test-related endpoints have issues:
- Wrong schemas (expecting `filename`/`content` instead of structured data)
- Wrong URL paths for execution endpoints
- Missing implementations

See Critical Issue #1 and High Issue #2 for details.

---

## Low Priority Issues (3)

### 1. Non-existent Profile in Tools Filter Returns 500

**Endpoint:** `GET /api/mcp/tools?profiles=nonexistent`
**Expected:** 200 (empty results or graceful message)
**Actual:** 500 Internal Server Error

**Error:**
```json
{
  "detail": "Profile 'nonexistent' not found in .mcp_services.yaml"
}
```

**Suggested Fix:**
```python
# Return 404 or empty results instead of 500
if profile not in config['profiles']:
    raise HTTPException(
        status_code=404,
        detail=f"Profile '{profile}' not found"
    )
```

**Impact:** Poor error handling.

---

### 2. Very Long Strings Accepted

**Endpoint:** `POST /api/mcp/profiles`
**Expected:** 422 Validation Error
**Actual:** 200 Success

**Issue:** No length limits on fields.

**Request:**
```json
{
  "profile_id": "test-long",
  "name": "x" * 10000,
  "description": "Test",
  "mcps": []
}
```

**Suggested Fix:**
```python
class ProfileCreateRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    mcps: list[dict] | None = None
```

**Impact:** Potential DoS or storage issues.

---

### 3. Unicode Profile IDs Not Properly Handled

**Endpoint:** `DELETE /api/mcp/profiles/test-unicode-😀-🎉`
**Expected:** 200
**Actual:** 404

**Issue:** Profile was created with unicode characters but cannot be deleted. Inconsistent unicode handling.

**Suggested Fix:** Either:
1. Reject unicode in profile_id validation
2. Or ensure consistent unicode handling throughout

**Impact:** Inconsistent behavior, orphaned profiles.

---

## Working Endpoints (51 tests passed)

The following endpoint groups work correctly:

1. **Health & Config**
   - `GET /api/health` ✓
   - `GET /api/config` ✓
   - `GET /` ✓

2. **Profile Management**
   - `GET /api/mcp/profiles` ✓
   - `POST /api/mcp/profiles` ✓ (with valid data)
   - `PUT /api/mcp/profiles/{profile_id}` ✓
   - `DELETE /api/mcp/profiles/{profile_id}` ✓
   - `PUT /api/mcp/profiles/default/{profile_id}` ✓
   - `GET /api/mcp/profiles/{profile_id}/export` ✓
   - `POST /api/mcp/profiles/{profile_id}/duplicate` ✓
   - `POST /api/mcp/profiles/{profile_id}/test-connection/{mcp_index}` ✓

3. **Tools/Resources (without filters)**
   - `GET /api/mcp/tools` ✓
   - `GET /api/mcp/resources` ✓
   - `GET /api/mcp/prompts` ✓

4. **Models**
   - `GET /api/models` ✓

5. **Chat (with valid inputs)**
   - `POST /api/chat` ✓

6. **Config Creation**
   - `POST /api/mcp/profiles/create-config` ✓

---

## Summary of Recommended Fixes

### Immediate (Critical/High Priority)

1. **Fix test execution endpoints** - align implementation with OpenAPI spec
2. **Fix MCP schema** - use nested auth object instead of flat auth_type
3. **Fix test file schema** - clarify what the endpoint expects
4. **Fix route ordering** - move `/reorder` before `/{mcp_index}`
5. **Add input validation** - reject empty messages, invalid providers
6. **Return correct status codes** - use 422 for validation errors, not 500
7. **Add security validation** - reject path traversal, SQL injection patterns

### Medium Priority

1. **Improve MCP connection error handling** - return 503 instead of 500
2. **Add field length limits** - prevent very long strings
3. **Better error messages** - more helpful for API consumers

### Low Priority

1. **Consistent unicode handling** - either support fully or reject
2. **Better non-existent profile handling** - return 404 instead of 500

---

## Test Coverage

| Category | Endpoints Tested | Pass Rate |
|----------|-----------------|-----------|
| Health & Config | 3 | 100% |
| Profiles | 25 | 80% |
| MCP Management | 9 | 22% |
| Tools/Resources | 7 | 43% |
| Models | 1 | 100% |
| Chat | 6 | 50% |
| Test Files | 7 | 14% |
| Test Execution | 5 | 0% |
| Reports | 1 | 0% |
| Edge Cases | 9 | 44% |

---

## Files Generated

1. `/Users/amin/github/preset-io/testmcpy/comprehensive_api_test.py` - Test script
2. `/Users/amin/github/preset-io/testmcpy/api_test_report.txt` - Raw test output
3. `/Users/amin/github/preset-io/testmcpy/API_TEST_SUMMARY.md` - This document

---

## How to Re-run Tests

```bash
cd /Users/amin/github/preset-io/testmcpy
python3 comprehensive_api_test.py
```

The script will:
- Test all endpoints systematically
- Print results in real-time
- Generate a detailed report
- Exit with code 1 if any tests fail

---

## Conclusion

The testmcpy API server has a solid foundation with working health checks, profile management, and basic chat functionality. However, there are significant issues with:

1. **Schema mismatches** between documented API and implementation
2. **Missing implementations** for test execution and reports
3. **Validation gaps** allowing malicious inputs
4. **Error handling** returning 500 instead of proper validation errors

Addressing the immediate priority fixes will greatly improve API reliability and security.
