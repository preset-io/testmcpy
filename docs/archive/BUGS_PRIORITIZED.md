# Prioritized Bug List - testmcpy API

## CRITICAL (1 bug)

### BUG-001: Test Execution Endpoints Not Implemented
- **Severity:** CRITICAL
- **Endpoint:** `POST /api/tests/{test_name}/run`, `POST /api/tests/{test_name}/cases/{case_index}/run`
- **Status Code:** 405 Method Not Allowed (expected 200)
- **Description:** OpenAPI spec documents these endpoints but they return 405. Actual implementation is at `/api/tests/run` without test name in path.
- **Impact:** Test execution feature completely broken
- **Fix:** Align implementation with OpenAPI spec or update spec to match implementation

---

## HIGH (13 bugs)

### BUG-002: MCP Creation Schema Mismatch
- **Severity:** HIGH
- **Endpoint:** `POST /api/mcp/profiles/{profile_id}/mcps`
- **Status Code:** 422 (expected 200)
- **Description:** API expects flat `auth_type` field but natural structure is nested `auth: {type: "none"}`
- **Impact:** Cannot add MCPs to profiles
- **Fix:** Change schema to use nested AuthConfig object
- **File:** `/Users/amin/github/preset-io/testmcpy/testmcpy/server/api.py` line 127-137

### BUG-003: Update MCP Returns 404 (No MCPs Exist)
- **Severity:** HIGH
- **Endpoint:** `PUT /api/mcp/profiles/{profile_id}/mcps/{mcp_index}`
- **Status Code:** 404 (expected 200)
- **Description:** Cannot update MCP at index 0 because no MCPs could be added (see BUG-002)
- **Impact:** Cannot modify MCPs
- **Fix:** Fix BUG-002 first

### BUG-004: Delete MCP Returns 404
- **Severity:** HIGH
- **Endpoint:** `DELETE /api/mcp/profiles/{profile_id}/mcps/{mcp_index}`
- **Status Code:** 404 (expected 200)
- **Description:** Cannot delete MCP because no MCPs could be added (see BUG-002)
- **Impact:** Cannot remove MCPs
- **Fix:** Fix BUG-002 first

### BUG-005: Test File Creation Schema Mismatch
- **Severity:** HIGH
- **Endpoint:** `POST /api/tests`
- **Status Code:** 422 (expected 200)
- **Description:** API expects `filename` and `content` but test sends structured test data with `name`, `description`, `test_cases`
- **Impact:** Cannot create test files with structured data
- **Fix:** Either accept structured data or document that raw YAML content is expected
- **File:** `/Users/amin/github/preset-io/testmcpy/testmcpy/server/api.py` line 58-60

### BUG-006: Update Test File Schema Mismatch
- **Severity:** HIGH
- **Endpoint:** `PUT /api/tests/{filename}`
- **Status Code:** 422 (expected 200)
- **Description:** Same as BUG-005
- **Impact:** Cannot update test files
- **Fix:** Same as BUG-005

### BUG-007: Get Test File Returns 404
- **Severity:** HIGH
- **Endpoint:** `GET /api/tests/{filename}`
- **Status Code:** 404 (expected 200)
- **Description:** Cannot get test file because it was never created (see BUG-005)
- **Impact:** Cannot retrieve test files
- **Fix:** Fix BUG-005 first

### BUG-008: Delete Test File Returns 404
- **Severity:** HIGH
- **Endpoint:** `DELETE /api/tests/{filename}`
- **Status Code:** 404 (expected 200)
- **Description:** Cannot delete test file because it was never created (see BUG-005)
- **Impact:** Cannot delete test files
- **Fix:** Fix BUG-005 first

### BUG-009: Run Specific Test Case Returns 405
- **Severity:** HIGH
- **Endpoint:** `POST /api/tests/{test_name}/cases/{case_index}/run`
- **Status Code:** 405 (expected 200)
- **Description:** Same as BUG-001
- **Impact:** Cannot run individual test cases
- **Fix:** Implement endpoint

### BUG-010: Reports Endpoint Missing
- **Severity:** HIGH
- **Endpoint:** `GET /api/reports`
- **Status Code:** 404 API endpoint not found (expected 200)
- **Description:** Endpoint documented in OpenAPI but not implemented
- **Impact:** Cannot list reports
- **Fix:** Implement endpoint or remove from OpenAPI spec

### BUG-011: Path Traversal Accepted
- **Severity:** HIGH (Security)
- **Endpoint:** `POST /api/mcp/profiles`
- **Status Code:** 200 (expected 422)
- **Description:** Input `test/../../../etc/passwd` is sanitized to `malicious` instead of rejected
- **Impact:** Security vulnerability - malicious inputs should be rejected with clear errors
- **Fix:** Add strict validation rejecting path traversal patterns
- **Example:**
```python
@field_validator('profile_id')
def validate_profile_id(cls, v):
    if not re.match(r'^[a-zA-Z0-9_-]+$', v):
        raise ValueError("Profile ID must contain only alphanumeric, hyphens, underscores")
    if '..' in v or '/' in v or '\\' in v:
        raise ValueError("Profile ID cannot contain path traversal characters")
    return v
```

### BUG-012: Chat Missing Provider Returns 500
- **Severity:** HIGH
- **Endpoint:** `POST /api/chat`
- **Status Code:** 500 (expected 422)
- **Description:** Missing required `provider` field causes 500 instead of validation error
- **Impact:** Poor error handling
- **Fix:** Make provider required with proper Pydantic validation

### BUG-013: Chat Invalid Provider Returns 500
- **Severity:** HIGH
- **Endpoint:** `POST /api/chat`
- **Status Code:** 500 (expected 422)
- **Description:** Invalid provider causes 500 instead of validation error
- **Impact:** Poor error handling
- **Fix:** Use Pydantic Enum for provider validation
```python
class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    LOCAL = "local"
    ANTHROPIC = "anthropic"
    CLAUDE_SDK = "claude-sdk"
    CLAUDE_CLI = "claude-cli"

class ChatRequest(BaseModel):
    provider: LLMProvider  # Auto-validates
```

### BUG-014: Reorder MCPs Route Conflict
- **Severity:** HIGH
- **Endpoint:** `PUT /api/mcp/profiles/{profile_id}/mcps/reorder`
- **Status Code:** 422 (expected 200)
- **Description:** FastAPI matches "reorder" as mcp_index parameter due to route ordering
- **Impact:** Cannot reorder MCPs
- **Fix:** Move reorder route BEFORE the `/{mcp_index}` route
- **File:** `/Users/amin/github/preset-io/testmcpy/testmcpy/server/api.py` line 1345

---

## MEDIUM (15 bugs)

### BUG-015: Add MCP to Non-existent Profile Wrong Error
- **Severity:** MEDIUM
- **Endpoint:** `POST /api/mcp/profiles/nonexistent/mcps`
- **Status Code:** 422 (expected 404)
- **Description:** Returns validation error instead of not found
- **Impact:** Confusing error message
- **Fix:** Check profile exists before validation

### BUG-016: Tools Filter Returns 500
- **Severity:** MEDIUM
- **Endpoint:** `GET /api/mcp/tools?profiles=local-dev`
- **Status Code:** 500 (expected 200)
- **Description:** MCP connection fails with 403 Forbidden
- **Impact:** Cannot filter tools by profile
- **Fix:** Return 503 (Service Unavailable) with helpful message, not 500

### BUG-017: Tools Multiple Profiles Filter Returns 500
- **Severity:** MEDIUM
- **Endpoint:** `GET /api/mcp/tools?profiles=local-dev&profiles=sandbox`
- **Status Code:** 500 (expected 200)
- **Description:** Same as BUG-016
- **Impact:** Cannot filter tools by multiple profiles
- **Fix:** Same as BUG-016

### BUG-018: Resources Filter Returns 500
- **Severity:** MEDIUM
- **Endpoint:** `GET /api/mcp/resources?profiles=local-dev`
- **Status Code:** 500 (expected 200)
- **Description:** Same as BUG-016
- **Impact:** Cannot filter resources by profile
- **Fix:** Same as BUG-016

### BUG-019: Prompts Filter Returns 500
- **Severity:** MEDIUM
- **Endpoint:** `GET /api/mcp/prompts?profiles=local-dev`
- **Status Code:** 500 (expected 200)
- **Description:** Same as BUG-016
- **Impact:** Cannot filter prompts by profile
- **Fix:** Same as BUG-016

### BUG-020: Empty Message Accepted
- **Severity:** MEDIUM
- **Endpoint:** `POST /api/chat`
- **Status Code:** 200 (expected 422)
- **Description:** Empty message "" is accepted but fails at Anthropic API
- **Impact:** Wastes API call, poor UX
- **Fix:** Add min_length=1 validation
```python
message: str = Field(..., min_length=1)
```

### BUG-021: Update Non-existent Test Wrong Error
- **Severity:** MEDIUM
- **Endpoint:** `PUT /api/tests/nonexistent`
- **Status Code:** 422 (expected 404)
- **Description:** Returns validation error instead of not found
- **Impact:** Confusing error message
- **Fix:** Check file exists before validation

### BUG-022: Run Non-existent Test Returns 405
- **Severity:** MEDIUM
- **Endpoint:** `POST /api/tests/nonexistent/run`
- **Status Code:** 405 (expected 404)
- **Description:** Wrong method, not wrong resource
- **Impact:** Confusing error
- **Fix:** Implement endpoint (see BUG-001)

### BUG-023: Run Test Missing Config Returns 405
- **Severity:** MEDIUM
- **Endpoint:** `POST /api/tests/{test_name}/run`
- **Status Code:** 405 (expected 422)
- **Description:** Wrong method, not validation error
- **Impact:** Confusing error
- **Fix:** Implement endpoint (see BUG-001)

### BUG-024: Run Test Case Invalid Index Returns 405
- **Severity:** MEDIUM
- **Endpoint:** `POST /api/tests/{test_name}/cases/999/run`
- **Status Code:** 405 (expected 404)
- **Description:** Wrong method, not wrong resource
- **Impact:** Confusing error
- **Fix:** Implement endpoint (see BUG-001)

### BUG-025: Reorder MCPs Invalid Length Wrong Route
- **Severity:** MEDIUM
- **Endpoint:** `PUT /api/mcp/profiles/{profile_id}/mcps/reorder`
- **Status Code:** 422 (expected varies based on BUG-014 fix)
- **Description:** Related to BUG-014
- **Impact:** Cannot test reorder validation
- **Fix:** Fix BUG-014 first

### BUG-026: Reorder MCPs Out of Bounds Wrong Route
- **Severity:** MEDIUM
- **Endpoint:** `PUT /api/mcp/profiles/{profile_id}/mcps/reorder`
- **Status Code:** 422 (expected varies based on BUG-014 fix)
- **Description:** Related to BUG-014
- **Impact:** Cannot test reorder validation
- **Fix:** Fix BUG-014 first

### BUG-027: SQL Injection Pattern Accepted
- **Severity:** MEDIUM (Security)
- **Endpoint:** `POST /api/mcp/profiles`
- **Status Code:** 200 (expected 422)
- **Description:** Input `test'; DROP TABLE profiles--` sanitized instead of rejected
- **Impact:** Security concern
- **Fix:** Same strict validation as BUG-011

### BUG-028: Null Byte Accepted
- **Severity:** MEDIUM (Security)
- **Endpoint:** `POST /api/mcp/profiles`
- **Status Code:** 200 (expected 422)
- **Description:** Input `test\x00null` sanitized instead of rejected
- **Impact:** Data integrity concern
- **Fix:** Same strict validation as BUG-011

### BUG-029: Add Second MCP Schema Mismatch
- **Severity:** MEDIUM
- **Endpoint:** `POST /api/mcp/profiles/{profile_id}/mcps`
- **Status Code:** 422 (expected 200)
- **Description:** Same as BUG-002
- **Impact:** Cannot add multiple MCPs
- **Fix:** Same as BUG-002

---

## LOW (3 bugs)

### BUG-030: Non-existent Profile Filter Returns 500
- **Severity:** LOW
- **Endpoint:** `GET /api/mcp/tools?profiles=nonexistent`
- **Status Code:** 500 (expected 200 or 404)
- **Description:** Should return empty results or 404, not 500
- **Impact:** Poor error handling
- **Fix:** Return 404 with helpful message

### BUG-031: Very Long Name Accepted
- **Severity:** LOW
- **Endpoint:** `POST /api/mcp/profiles`
- **Status Code:** 200 (expected 422)
- **Description:** 10,000 character name accepted without validation
- **Impact:** Potential DoS or storage issues
- **Fix:** Add max_length constraints
```python
name: str = Field(..., min_length=1, max_length=255)
```

### BUG-032: Unicode Profile ID Inconsistent
- **Severity:** LOW
- **Endpoint:** `DELETE /api/mcp/profiles/test-unicode-😀-🎉`
- **Status Code:** 404 (expected 200)
- **Description:** Profile created with unicode but cannot be deleted
- **Impact:** Orphaned profiles
- **Fix:** Either reject unicode in validation or ensure consistent handling

---

## Quick Stats

- **Total Bugs:** 32
- **Critical:** 1 (3%)
- **High:** 13 (41%)
- **Medium:** 15 (47%)
- **Low:** 3 (9%)

## Root Causes

1. **Schema Mismatches (9 bugs):** API implementation doesn't match documented schemas
2. **Missing Implementations (5 bugs):** Endpoints documented but not implemented
3. **Route Ordering Issues (3 bugs):** FastAPI route conflicts
4. **Validation Gaps (8 bugs):** Missing or incorrect input validation
5. **Error Handling (7 bugs):** Wrong HTTP status codes returned

## Fix Order Recommendation

1. Fix BUG-002 (MCP schema) - unblocks BUG-003, BUG-004, BUG-029
2. Fix BUG-005 (Test file schema) - unblocks BUG-006, BUG-007, BUG-008
3. Fix BUG-001 (Test execution) - unblocks BUG-009, BUG-022, BUG-023, BUG-024
4. Fix BUG-014 (Reorder route) - unblocks BUG-025, BUG-026
5. Fix BUG-011 (Input validation) - improves security for BUG-027, BUG-028, BUG-031
6. Fix BUG-012, BUG-013 (Chat validation) - improves BUG-020
7. Fix remaining bugs in order of severity

Fixing these 6 key bugs will resolve or unblock 24 of the 32 total bugs (75%).
