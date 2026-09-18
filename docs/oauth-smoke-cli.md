# Headless OAuth/MCP interoperability probe

testmcpy includes an additive, typed probe for black-box OAuth authorization
and authenticated MCP interoperability. It is intentionally vendor-neutral and
does **not** claim formal standards certification. Use the official MCP
conformance suite (`testmcpy conformance`) beside this probe for the protocol
vectors owned upstream.

## Architecture

`testmcpy_oauth_probe` is published as its own distribution,
**`testmcpy-oauth-probe`**, whose only dependencies are HTTPX and PyYAML. It
contains strict manifest/result models, destination safety, RFC 9728 and RFC
8414 discovery, optional OIDC discovery, noninteractive token paths, raw
stage-visible MCP requests, mandatory redaction, and reporters, and it owns the
`testmcpy-oauth` console script.

The main `testmcpy` distribution **depends** on it — it does not bundle a copy —
and adds the `testmcpy.oauth_probe` re-export plus the `testmcpy auth` Typer
adapter. Installing both is safe; the import package ships from one place.

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
    target_ids=["example-us"],
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

Install the probe on its own. Do **not** install `testmcpy` for this — that
resolves the UI/LLM/agent stack (anthropic, fastmcp, sqlalchemy, textual,
uvicorn, …) and will conflict with any pipeline that pins those itself:

```bash
# Pin exactly; this is release-pipeline infrastructure.
python -m pip install "testmcpy-oauth-probe==0.1.0"

# Or, from an immutable source checkout/tag:
python -m pip install ./oauth-probe

testmcpy-oauth validate --config auth-smoke.yaml
testmcpy-oauth check --config auth-smoke.yaml --profile canary \
  --format json --output auth.json --junit auth.xml \
  --revision "$GIT_COMMIT" --region "$REGION" --run-id "$CI_RUN_ID"
```

The resulting environment is HTTPX, PyYAML and their transitive closure —
roughly nine distributions. `testmcpy-oauth-probe` is versioned independently
of `testmcpy`, so its version moves only when the probe changes; the manifest
and report schemas are versioned separately again, in their own contract
strings. `--config` and `--manifest` are the same option; pick whichever reads
better in your pipeline.

The main CLI offers equivalent `testmcpy auth validate|check|schema` commands
for environments that already have testmcpy. Use `testmcpy-oauth schema --kind
report` (or the equivalent main CLI command) to materialize the report
contract.

### Correlation flags are labels, not assertions

`--service`, `--region`, `--revision` and `--deployment-id` are recorded
verbatim in the report's `correlation` block so a downstream consumer can join
the report to a build. **The probe never fetches or compares the deployed
revision** — passing `--revision "$GIT_COMMIT"` does not verify that the target
is running that commit, and a target advertising a different revision will not
fail the run. If you need a deployed-revision gate, keep it in the pipeline
that owns the deployment.

The package CI job explicitly checks out the PR head (rather than GitHub's
synthetic merge ref) and uploads an artifact named
`testmcpy-oauth-probe-<full Git SHA>`. `SOURCE_COMMIT` records that same SHA;
`SHA256SUMS` covers it, the wheel, and the source archive and is verified before
the clean-install smoke. CI consumers should pin the full commit/artifact name,
then run `sha256sum --check SHA256SUMS` before installing; the mutable branch
name is not a provenance boundary.

Every string in the manifest — scalars and string-array elements alike —
supports `${NAME}` and `${NAME:-default}` expansion, so a single static
manifest can target an ephemeral stack through injected environment variables:

```yaml
targets:
  ephemeral:
    mcp_url: ${SMOKE_MCP_URL}
    expectations:
      issuers: [ "${SMOKE_ORIGIN}" ]
      scopes:  [ "${SMOKE_SCOPE:-mcp.read}" ]
```

An unset reference with no default is a configuration error rather than a
literal comparison. Array duplicates are detected after expansion.

Credentials are accepted only through named environment references in the
manifest (the `{env: NAME}` form), never through `${...}` interpolation. The probe never accepts credential values on argv, never writes
tokens/codes/verifiers/client secrets/session IDs to files, and sanitizes at
event and serialization boundaries. Use masked, least-privilege CI variables.
All target, challenge-supplied metadata, discovery, redirect, and token endpoint
destinations must resolve exclusively to public addresses by default. Local
fixtures must explicitly set `allow_http_loopback: true`; access to any other
private network requires the broader `allow_private_network: true` opt-in.
Token acquisition, refresh, and authenticated MCP requests are never retried;
deterministic 4xx, HTTP 500, and protocol failures are reported once. Only
explicitly classified transient discovery GETs may retry.

Exit codes are `0` for expectations met, `1` for target assertion failures,
and `2` for configuration, infrastructure, or indeterminate errors. A parseable
manifest produces a report even when a target errors.

## What is checked

The manifest accepts only the implemented authorization profiles:
`mcp-2025-03-26`, `mcp-2025-06-18`, and `mcp-2025-11-25`. The selected profile
changes discovery requirements; arbitrary future version strings are rejected
instead of being tested with incorrect rules.

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
- a safe unsupported-grant OAuth error probe (`oauth.token.error_contract`),
  token media/type/cache/scope contracts, refresh rotation policy, and optional
  unverified JWT routing-claim diagnostics (opaque access tokens remain valid
  unless a claim policy is explicitly configured);
- authenticated `initialize`, `notifications/initialized`, and paginated
  `tools/list` using JSON or SSE, exact HTTP statuses, JSON-RPC ID correlation,
  negotiated protocol, session propagation, and a page safety bound.

Use `required`, `supported`, `forbidden`, or `ignore` per optional capability.
An absent `supported` feature is skipped; a required feature fails; optional
RFC features are never made mandatory merely because another provider has it.
An `ignore` metadata capability is not requested at all. The
`client_credentials` grant is rejected at configuration time unless a
confidential client-authentication method is configured.

`oauth.token.error_contract` is resolved for **every** flow, including `bearer`
and `none`, because the probe needs no credentials of its own to send one
unsupported-grant request. When it cannot run it still emits a record saying
why — no token endpoint was discovered, the discovered endpoint carries
forbidden query/fragment/userinfo, or `refresh_token_disposable` is unset and
the target is therefore never contacted. Set `error_probe: false` to opt out;
that is the only configuration in which the check is absent from the report.
The response must carry one of the six RFC 6749 §5.2 codes
(`invalid_request`, `invalid_client`, `invalid_grant`, `unauthorized_client`,
`unsupported_grant_type`, `invalid_scope`) — an unregistered code fails,
because a conforming client cannot branch on free text. `testmcpy-oauth
discover` sets `error_probe: false` so it stays read-only.
`expectations.issuers` constrains RFC 8414/OIDC metadata, while
`expectations.token_issuers` and `expectations.audiences` explicitly opt into
unverified JWT routing-claim diagnostics. This separation keeps an opaque
access token valid when only metadata issuer identity is being asserted; the
authenticated MCP response remains the authoritative audience/resource check.

## Compatibility and dual-run migration

The **Auth Smoke** web page is validation-only. It validates the canonical
YAML/JSON manifest, but deliberately does not execute `ProbeRunner` or resolve
credential references in the web process. This boundary prevents the page from
becoming a credentialed network-request channel. Save the validated manifest
and run `testmcpy auth check --config <path>` in the CLI environment that holds
its referenced credentials; the CLI emits the typed stage results.

This release is additive. Existing `smoke-test`, `tools`, Auth Debugger UI,
profiles, OAuth cache, and reports keep their behavior. The new result is a
separate `testmcpy.io/oauth-smoke-report/v1` contract, so existing report
consumers do not receive a silent schema change.

Suggested consumer adoption:

1. Pin `testmcpy-oauth-probe` by exact version (or the subproject by immutable
   commit). Do not pull `testmcpy` into a release pipeline for this.
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
