# Gateway smoke lane

A compact, read-only, deterministic smoke check for an MCP gateway, powered by
testmcpy. It makes **no LLM calls** and has **no write path**. One run does
exactly three things against one named environment and one named workspace:

1. **Protocol and auth.** An unauthenticated `initialize` must be challenged
   (HTTP 401, `WWW-Authenticate: Bearer`, RFC 9728 protected-resource metadata).
   The configured credential then obtains a token and `initialize` must
   negotiate the requested protocol version and advertise the required
   capabilities.
2. **Bounded tool discovery.** `tools/list` under a hard page cap and byte
   budget. Required tool names (and, optionally, required input properties) must
   be present, within a tool-count and size budget.
3. **One approved fixture read.** A single `tools/call` of a read-only tool
   against the workspace named in the config, with deterministic assertions on
   fields of the result.

It is a smoke check. See [What this does not prove](#what-this-does-not-prove).

## Reuse

The lane is built on what the repository already has rather than beside it:

| Piece | Source | Used for |
| --- | --- | --- |
| Destination-safe HTTP transport (HTTPS only, no redirects, private-network block) | `testmcpy_oauth_probe.transport` | Every request |
| RFC 9728 / RFC 8414 discovery and the 401 challenge check | `testmcpy_oauth_probe.discovery` | Step 1 |
| Non-interactive `client_credentials` / existing-bearer token acquisition | `testmcpy_oauth_probe.oauth` | Step 1 |
| Secret registry, structural redaction, `safe_url` | `testmcpy_oauth_probe.secrets` | All output |
| JSON-RPC / SSE framing | `testmcpy_oauth_probe.mcp._rpc_messages` | Steps 1-3 |
| Generic gateway tool catalogue (`list_workspaces`, `list_workspace_services`, `get_workspace_catalog`, `search_workspace_tools`, `call_tool`) | `qualification/native-tools/fixtures/gateway-generic-tools.json` (native-tool qualification harness) | The fake gateway's tool list |

Not reused, deliberately:

- The gateway-aware evaluators in `testmcpy/evals/` score LLM tool-call traces.
  The lane has no model and no trace, so there is nothing for them to evaluate.
- The probe's own `probe_mcp` discards the tool catalogue and the session and has
  no byte budget or `tools/call`, so the lane has a small bounded session client
  (`testmcpy/gateway_smoke/client.py`) instead.
- The qualification harness is a fixture baseline with pre-registered budgets. Its
  numbers are not a live result and the lane does not reuse or extend them.

The lane lives in the `testmcpy` distribution, not in `testmcpy-oauth-probe`,
because the probe is released separately and pinned; this adds no probe change and
no new dependency (it needs HTTPX and PyYAML, which `testmcpy` already requires).

## Run it

```bash
export GATEWAY_SMOKE_CLIENT_ID=...        # named in the config; from the secret store
export GATEWAY_SMOKE_CLIENT_SECRET=...

testmcpy gateway-smoke validate --config gateway-smoke.yaml          # offline
testmcpy gateway-smoke run --config gateway-smoke.yaml \
    --format json --output gateway-smoke.json --junit gateway-smoke.xml \
    --expect-environment <label> --expect-workspace-id <id>
```

`python -m testmcpy.gateway_smoke ...` is the same program without the Typer app.
There is no flag that takes a token, secret or password.

### Dry run against the local fake

```bash
python examples/gateway-smoke/fake_gateway.py --port 18765 &   # synthetic gateway
export FAKE_GATEWAY_CLIENT_SECRET=dry-run-secret-0000
python -m testmcpy.gateway_smoke run --config /path/to/fake-config.yaml
```

where the config points `mcp_url` at `http://127.0.0.1:18765/mcp` with
`allow_http_loopback: true`, client id `fake-client` and
`client_secret: {env: FAKE_GATEWAY_CLIENT_SECRET}`. The unit tests in
`unit_tests/test_gateway_smoke.py` drive the same fake through every PASS, FAIL,
BLOCKED and ERROR path.

## Configuration

Start from `examples/gateway-smoke/gateway-smoke.example.yaml`. Every value in it is
a placeholder; running it unedited is refused (BLOCKED) before any request, and the
lane never opens a socket to a placeholder or reserved documentation host.

| Key | Meaning |
| --- | --- |
| `environment` | Label recorded in every result. The lane contacts only `mcp_url`. |
| `mcp_url` | The one gateway endpoint. Redirects are not followed and no other host is tried. |
| `workspace.id`, `workspace.name` | The fixture workspace. Recorded in every result. |
| `auth.mode` | `client_credentials` (machine OAuth) or `bearer` (an existing gateway token already in an env var). |
| `auth.client_id`, `auth.client_secret`, `auth.access_token` | Credentials are `{env: NAME}` references; a literal secret is a config error. |
| `auth.expected_audiences`, `auth.expected_token_issuers` | Optional JWT claim guards, useful against supplying the wrong kind of token. |
| `challenge.*` | Expected unauthenticated status, whether metadata is required, expected resource/issuer. |
| `limits.*` | Hard limits (below). |
| `discovery.*` | Page cap, tool-count and byte budgets, required tools and input shapes. |
| `fixture.*` | The single read: `tool`, `arguments`, `read_only: true`, optional `workspace_argument`, optional `inner_tool_argument`, and `expect` assertions. |
| `allow_http_loopback`, `allow_private_network` | For local fixtures only. Both default to `false`. |

Fixture assertions are deterministic checks on the tool result (`structuredContent`,
else the first JSON text block). Paths are dotted with numeric list indexes
(`services.0.id`). Exactly one operator per assertion: `equals`, `exists`, `type`,
`contains`, `min_length`. At least one is required.

Fixture guards:

- `read_only: true` must be written out; the lane only performs approved reads.
- `tool` (and the dispatched tool named by `inner_tool_argument`, for a wrapper
  like `call_tool`) is refused at config load if its name contains a write-like word
  (`create`, `update`, `delete`, `execute`, `generate`, ...). This is a denylist: it
  catches a mis-pointed fixture, it does not prove a tool is read-only.
- If `workspace_argument` is set, `arguments[workspace_argument]` must equal
  `workspace.id`, so the call cannot target a different workspace.
- At run time a directly named tool that advertises `destructiveHint: true` or
  `readOnlyHint: false` is refused (BLOCKED) and not called.
- The lane never calls `list_workspaces` or any other enumeration: the workspace is
  named, not discovered.

## Statuses and exit codes

| Status | Exit | Meaning |
| --- | --- | --- |
| `PASS` | 0 | All three steps ran and every check passed. |
| `FAIL` | 1 | The gateway answered and an assertion did not hold (wrong status, missing tool, budget exceeded, wrong fixture value). |
| `ERROR` | 2 | The lane could not trust what it saw: malformed response, transport failure, a hard limit or timeout hit, unexpected exception. |
| `BLOCKED` | 3 | The lane could not run the check: placeholder or unusable config, no fixture, credential env var unset, machine OAuth unavailable, identity expectation mismatch, a fixture the lane refuses to call. **Never PASS.** |

Precedence is ERROR > FAIL > BLOCKED > PASS. A step that did not run is `SKIPPED`
with a reason, and a run with a skipped step is never a PASS. BLOCKED conditions
that can be decided offline (placeholders, missing env vars, missing fixture) are
decided before any request is made, so a blocked run makes zero calls.

"Machine OAuth unavailable" means the token endpoint rejected the configured grant
(for example `invalid_client`), answered with a non-200 status, was unreachable, or
could not be discovered. It is BLOCKED rather than FAIL because the credential, not
the gateway's behaviour, is what is missing. A token endpoint that answers 200 with
a malformed body is ERROR.

In JUnit XML, BLOCKED is written as an `<error type="BLOCKED">`, so a CI consumer
cannot read it as green. Steps that were not run are `<skipped>`.

## Hard limits

All limits are in `limits:` / `discovery:` and are enforced, not advisory:

| Limit | Default | On breach |
| --- | --- | --- |
| `total_timeout_seconds` | 60 | ERROR, partial results kept |
| `per_call_timeout_seconds` | 15 | ERROR |
| `max_calls` (every HTTP request, metadata and token included) | 16 | the next request is refused before it is sent; ERROR |
| `max_response_bytes` (per response) | 262144 | ERROR |
| `max_total_bytes` (whole run) | 1048576 | ERROR |
| `discovery.max_pages` | 3 | FAIL if the catalogue is not exhausted; no further page is fetched |
| `discovery.max_tools`, `discovery.max_bytes` | 50, 65536 | FAIL (budget) |

The lane never retries a request.

## Output

- `--format json` (also the default machine form): `testmcpy.io/gateway-smoke-report/v1`
  with `status`, `exit_code`, `reason`, `environment`, `workspace {id, name}`,
  `target {mcp_url, spec_profile}`, per-step `checks`, the configured `limits`, a
  `usage` block (calls, bytes, elapsed) and a `calls` log (phase, method, URL path
  with no query string, status, bytes, duration). It also states
  `lane: {llm_calls: 0, writes: 0, read_only: true}`.
- `--junit PATH`: JUnit XML, one test case per check, with `environment`,
  `workspace_id`, `workspace_name`, `status` and `run_id` as suite properties.
- `--format human`: the same content for a terminal.

Every result carries the environment and workspace, including BLOCKED results from
a config that could not be loaded (identity is read best-effort from the file).

### Redaction

Tokens, client secrets, session ids, authorization headers and cookies are never
emitted: values are registered when read and scrubbed from every string and
evidence field, sensitive keys are masked structurally, URL query strings and
fragments are stripped from every URL in the report, and the report is checked for
registered secrets before it is written (the run fails instead of emitting a leak).
Request headers are never recorded. On a fixture assertion failure the report shows
a short, scrubbed snippet of the offending value; point the fixture at a canary
workspace so that snippet is harmless.

Secrets are read only from the environment variables named in the config. Do not
reuse a Manager API JWT as a gateway OAuth credential: it is a different credential
for a different audience. Use `auth.expected_audiences` to catch that mistake.

## Proposed daily schedule (DISABLED: proposal only)

> **Not created, not enabled, in any scheduler.** This is a proposal. It should not
> be turned on until a manual run has produced a PASS against the approved
> environment and fixture, and the environment, fixture and time below have been
> confirmed by the owner.

```yaml
# PROPOSAL - DISABLED
name: gateway-smoke-daily
enabled: false
cron: "17 21 * * *"          # placeholder time (UTC); to be confirmed
environment: <approved environment label>   # to be confirmed
command: >
  testmcpy gateway-smoke run
  --config /etc/gateway-smoke/<environment>.yaml
  --format json --output gateway-smoke.json --junit gateway-smoke.xml
  --expect-environment <environment label>
  --expect-workspace-id <canary workspace id>
env_from_secret_store:
  - GATEWAY_SMOKE_CLIENT_ID
  - GATEWAY_SMOKE_CLIENT_SECRET
on_status:
  PASS: record
  FAIL: alert
  ERROR: alert
  BLOCKED: alert   # a blocked lane is not a healthy lane
```

Treat BLOCKED as an alert, not a pass: a daily check that is silently blocked is
indistinguishable from no check.

## Live status

The checked-in config is placeholders only. No approved canary workspace or fixture
is documented in this repository, so no live run was made from it. The known live
blocker is that machine (client-credentials) OAuth for the intended gateway
environment is currently unavailable: an administrator must check the client
credentials in its OAuth settings, and browser sign-in cannot repair it. Until that
is fixed a live run is expected to report `BLOCKED` at `oauth.token.acquire`, not
PASS.

## What this does not prove

- **Not live qualification.** A PASS against the local fake says the lane's logic
  works. A PASS against a real gateway says that one environment answered those
  three steps on that run.
- **Not a comprehensive evaluation.** One read-only call on one fixture says nothing
  about other tools, other workspaces, other roles, write paths, throughput or
  correctness of results beyond the asserted fields.
- **Not the native-tool go/no-go.** The native-tool qualification harness
  (`qualification/native-tools/`) is a fixture baseline with pre-registered budgets,
  and this lane neither reuses nor replaces its budgets. Nothing here measures
  native-tool token cost or task success.
- **Not an OAuth or MCP compliance certification.** It checks the observable
  behaviours listed above, not the full specifications.
- **Not proof a tool is read-only.** The write guard is a name denylist plus the
  tool's own annotations; the safety of the call rests on the approved fixture.
- **Not an authorization test.** It does not check that a different caller is denied
  the fixture.
