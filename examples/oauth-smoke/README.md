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

The independently installable `oauth-probe/` distribution exposes the same
core as `testmcpy-oauth` while avoiding the UI and LLM dependency stack.
Its versioned result schema is available with
`testmcpy-oauth schema --kind report`.
