# OAuth/MCP probe examples

`auth-smoke.example.yaml` is a vendor-neutral CI manifest. Credentials are
named environment references; never replace a `{env: ...}` object with a
secret value. `fixtures.yaml` documents the deterministic `.test` scenarios
implemented in `unit_tests/test_oauth_probe.py`, including both wrong-routing
and authenticated-500 incident classes plus malformed challenge, metadata,
redirect, token, and JSON-RPC responses.

```bash
export MCP_REFRESH_TOKEN=...   # inject through the CI secret store
export MCP_CLIENT_ID=...
export MCP_CLIENT_SECRET=...
export REVISION="$GIT_COMMIT"

testmcpy auth validate --config examples/oauth-smoke/auth-smoke.example.yaml
testmcpy auth check --config examples/oauth-smoke/auth-smoke.example.yaml \
  --profile canary --format json --output auth-report.json \
  --junit auth-report.xml --run-id "$CI_RUN_ID"
```

In a release pipeline, install the probe on its own instead — `pip install
"testmcpy-oauth-probe==0.1.0"` pulls HTTPX and PyYAML rather than testmcpy's UI
and LLM stack, and provides the same `testmcpy-oauth` command. Its versioned
result schema is available with `testmcpy-oauth schema --kind report`.

Every string in the manifest, including array elements, expands `${NAME}` and
`${NAME:-default}`, so one static manifest can target an ephemeral stack:

```yaml
    mcp_url: ${SMOKE_MCP_URL}
    expectations:
      issuers: [ "${SMOKE_ORIGIN}" ]
```

Credentials are the exception: they stay as `{env: NAME}` references and are
resolved at run time, never interpolated into the document.
