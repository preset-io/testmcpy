# Headless OAuth/MCP interoperability probe

testmcpy includes an additive, typed probe for black-box OAuth authorization
and authenticated MCP interoperability. It is intentionally vendor-neutral and
does **not** claim formal standards certification. Use the official MCP
conformance suite (`testmcpy conformance`) beside this probe for the protocol
vectors owned upstream.

## Architecture

The independently packaged `testmcpy_oauth_probe` module contains strict
manifest/result models, destination safety, RFC 9728 and RFC 8414 discovery,
optional OIDC discovery, noninteractive token paths, raw stage-visible MCP
requests, mandatory redaction, and reporters. The main distribution re-exports
the API as `testmcpy.oauth_probe` and adds the `testmcpy auth` Typer adapter.

Raw Streamable HTTP is deliberate here: the report must retain exact status,
JSON/SSE framing, JSON-RPC correlation, session propagation, and the stage at
which a deployed server failed. Existing interactive UI OAuth, FastMCP client,
encrypted PKCE/DCR cache, and official conformance wrapper remain compatible;
they are not duplicated or silently replaced by this first headless release.

Public adapter API:

```python
from testmcpy.oauth_probe import ProbeRunner, load_manifest

manifest = load_manifest("auth-smoke.yaml")
report = await ProbeRunner().run_manifest(
    manifest,
    target_ids=["staging-us"],
    run_id="build-123",
)
assert report.exit_code == 0
```

Minimal-package consumers can import the same symbols from
`testmcpy_oauth_probe`. Both packages expose the manifest and report schemas as
`manifest_json_schema()` and `report_json_schema()`.

Adapters may inject an `HttpTransport`, which lets the UI stream the same
typed check records without importing CLI code and lets tests use deterministic
fixtures.

## Safe CI usage

Install either the main immutable artifact or the minimal subproject artifact:

```bash
# From an immutable source checkout/tag:
python -m pip install ./oauth-probe

testmcpy-oauth validate --config auth-smoke.yaml
testmcpy-oauth check --config auth-smoke.yaml --profile canary \
  --format json --output auth.json --junit auth.xml \
  --revision "$GIT_COMMIT" --region "$REGION" --run-id "$CI_RUN_ID"
```

The minimal wheel has only HTTPX and PyYAML as dependencies. Its version can be
pinned independently; config and report schemas are also versioned separately.
The main CLI offers equivalent `testmcpy auth validate|check|schema` commands.
Use `testmcpy-oauth schema --kind report` (or the equivalent main CLI command)
to materialize the report contract.

The package CI job builds from the checked-out PR commit and uploads an artifact
named `testmcpy-oauth-probe-<full Git SHA>`. Its `SHA256SUMS` covers both the
wheel and source archive and is verified before the clean-install smoke. CI
consumers should pin the full commit/artifact name and run
`sha256sum --check SHA256SUMS` before installing; the mutable branch name is not
a provenance boundary.

Credentials are accepted only through named environment references in the
manifest. The probe never accepts credential values on argv, never writes
tokens/codes/verifiers/client secrets/session IDs to files, and sanitizes at
event and serialization boundaries. Use masked, least-privilege CI variables.
Token acquisition, refresh, and authenticated MCP requests are never retried;
deterministic 4xx, HTTP 500, and protocol failures are reported once. Only
explicitly classified transient discovery GETs may retry.

Exit codes are `0` for expectations met, `1` for target assertion failures,
and `2` for configuration, infrastructure, or indeterminate errors. A parseable
manifest produces a report even when a target errors.

## What is checked

- exact unauthorized status and structured Bearer challenge hints;
- RFC 9728 path/root discovery, JSON contract, exact resource identity,
  authorization-server selection, and scope policy;
- RFC 8414 path issuers, exact issuer identity, endpoint URL policy,
  response/grant/scope/auth-method advertisement, optional protected-resource
  cross-check, and DCR advertisement policy;
- optional OIDC discovery with exact issuer identity;
- supplied bearer, refresh token, client credentials, and pre-obtained
  authorization-code + PKCE exchanges;
- public clients plus `client_secret_basic`, `client_secret_post`, and
  `client_secret_jwt` confidential authentication;
- a safe unsupported-grant OAuth error probe, token media/type/cache/scope
contracts, refresh rotation policy, and optional unverified JWT routing-claim
diagnostics (opaque access tokens remain valid unless a claim policy is
explicitly configured);
- authenticated `initialize`, `notifications/initialized`, and paginated
  `tools/list` using JSON or SSE, exact HTTP statuses, JSON-RPC ID correlation,
  negotiated protocol, session propagation, and a page safety bound.

Use `required`, `supported`, `forbidden`, or `ignore` per optional capability.
An absent `supported` feature is skipped; a required feature fails; optional
RFC features are never made mandatory merely because another provider has it.
An `ignore` metadata capability is not requested at all. The
`client_credentials` grant is rejected at configuration time unless a
confidential client-authentication method is configured.
`expectations.issuers` constrains RFC 8414/OIDC metadata, while
`expectations.token_issuers` and `expectations.audiences` explicitly opt into
unverified JWT routing-claim diagnostics. This separation keeps an opaque
access token valid when only metadata issuer identity is being asserted; the
authenticated MCP response remains the authoritative audience/resource check.

## Compatibility and dual-run migration

This release is additive. Existing `smoke-test`, `tools`, Auth Debugger UI,
profiles, OAuth cache, and reports keep their behavior. The new result is a
separate `testmcpy.io/oauth-smoke-report/v1` contract, so existing report
consumers do not receive a silent schema change.

Suggested consumer adoption:

1. Pin the minimal wheel or full testmcpy artifact by immutable version/commit.
2. Translate deployment output into the generic manifest: URL, target, region,
   revision/deployment ID, secret environment names, and explicit expectations.
3. Run the existing product smoke and testmcpy probe in parallel, nonblocking,
   on the same deployed revision. Compare stage/status evidence, not text.
4. Make discovery, token, and authenticated MCP check IDs blocking once parity
   is demonstrated. Keep product-owned provisioning/control-plane checks in
   their home repository.
5. Retire copied OAuth/MCP protocol code only after multiple green releases;
   retain a temporary reverse dual-run so rollback is immediate.

## First-release boundaries

The core validates introspection/revocation/DCR endpoint policies but does not
actively introspect, revoke, or register clients. It also does not yet execute
`private_key_jwt`, mTLS client auth, CIMD, device authorization, browser login,
or a horizontally scaled callback coordinator. The existing interactive
PKCE/DCR UI remains available. These deeper/destructive packs should land only
with isolated credentials and explicit opt-in semantics.
