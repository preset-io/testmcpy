# Changelog

All notable changes to testmcpy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.8] - 2026-07-07

### Security
- **CI secret-scanning guardrail**: new `.github/workflows/security.yml` runs
  `gitleaks` (pinned by Docker digest) on every PR diff and push, plus a
  manually-dispatchable full-history scan for auditing older commits. This is
  the CI-side counterpart to the v0.11.7 runtime scrubber — it would have
  caught the original incident commit before merge. Also adds a fast
  `git ls-files` check that fails the build if any file under
  `tests/.results/`, `tests/.smoke_reports/`, or `tests/.generation_logs/` is
  ever tracked, and an advisory (non-blocking) `bandit` pass over `testmcpy/`.
  A `.gitleaks.toml` allowlists known-safe test fixtures and doc examples
  (never the result/report directories above).
- **trufflehog verification pass**: added alongside gitleaks (also pinned by
  Docker digest) on the same PR-diff/push scope. trufflehog calls each
  provider's API to confirm whether a matched credential is actually live,
  so the job only fails the build on a **verified** secret — the fake
  `user:pass@host`-style fixtures already allowlisted for gitleaks just show
  up as informational "unverified" findings instead of blocking every PR. A
  matching `trufflehog-full-history` manual job answers, for the known
  pre-v0.11.7 leak, whether that specific credential is still live.

## [0.11.7] - 2026-07-06

### Security
- **Credential scrubbing before any result persistence**: everything written to
  disk — SQLite question results, `.results/*.json` sidecars, checkpoint files,
  `--report` outputs, smoke reports, generation logs — now passes through a
  scrubber (`testmcpy/scrubber.py`) first. Three tiers: (1) exact known values
  (CLI/profile auth secrets registered at MCPClient/SDK-provider construction,
  plus values of env vars whose names look credential-ish — `*_API_KEY`,
  `*_TOKEN`, `*_SECRET`, ...), (2) high-precision credential patterns
  (Anthropic/GitHub/AWS/Slack tokens, `Bearer` headers, DD-API-KEY headers,
  private-key blocks), and (3) well-known credential field names
  (`auth_token`, `jwt_secret`, ...) masked to their first 8 chars. Bare
  32/40-char hex is deliberately not matched so git SHAs and UUIDs in tool
  output survive. Motivated by a real incident: a `.results` file captured
  live Datadog keys from an `echo $DD_API_KEY` tool call and later surfaced
  in a public fork.

## [0.11.6] - 2026-06-28

### Added
- **Run benchmarks from the app**: a "Benchmark" button in Test Manager and on
  the Performance page (next to the "single runs are noise" warning) opens a
  matrix builder — models × providers × MCP profiles × repeat, with a combo
  preview. It runs natively over the websocket (live per-test + per-combo
  progress), so no shell script is needed. Connection/auth is supplied as
  fields (with a "paste run-args" parser) since it works without a saved
  profile; the block is remembered in localStorage. Each combo is saved as its
  own run under a shared `session_id` and shows up in `/performance`.
- New websocket `run_benchmark` command and shared `testmcpy/benchmarks.py`
  combo builder (used by both the `bench` CLI and the websocket runner).

### Fixed
- **Assistant/chatbot cost is now accurate**: the provider tracked tokens but
  hardcoded `cost = 0`. It now prices its token usage by the (overridden)
  model via the registry. When the model is `default` (the backend picks it
  server-side) it stays unpriceable and the `/performance` leaderboard shows
  "— not tracked" instead of a misleading `$0.00`.
- The websocket run path can now connect ad-hoc from a URL + JWT (no saved
  profile) and honors an explicitly chosen model over a suite `model: default`.

## [0.11.5] - 2026-06-28

### Added
- **Transparent score breakdown**: every test result now carries a structured
  `score_breakdown` (base evaluator mean × false-positive penalty = final score),
  surfaced in the `/reports` test detail as a "Why this score" panel with a
  verdict banner (Prompt → Answer → Why-this-score), and in `/performance`
  (avg-score + false-positive-rate columns, a relative cost-per-run/-per-pass bar
  for comparing models at a glance, and per-run false-positive markers).

### Fixed
- **`--model` override is no longer swallowed by a suite `model: default`**: chatbot
  suites declare `model: default` ("let the provider pick"), and the old
  `effective_model = suite_model or model` let that sentinel mask an explicit
  `--model claude-opus-4-7`, so the override never reached the provider or the
  saved run (it showed as `assistant/default` in /performance and /reports). An
  explicit `--model` now wins; a real suite-level `model:` pin is still honoured;
  and the `default` sentinel is preserved when no override is passed. `--dry-run`
  now prints the resolved provider/model.

### Changed
- **Scoring is now a single source of truth** (`testmcpy/scoring.py`) shared by
  the runner, storage, and the read APIs. Fixes: multiple expected/"primary"
  tools are all honoured (was: only the first, wrongly penalising multi-tool
  tests); the false-positive penalty is applied in the runner so the live score
  matches the stored report (was: penalty only at save time); manually marking a
  result as a false positive now actually lowers its score and recomputes on
  toggle (was: an inert tag); and the coarse `unnecessary_tool_calls` skip no
  longer cancels the false-positive penalty (the two target disjoint problems).

## [0.11.4] - 2026-06-27

### Fixed
- **ClaudeSDK subprocess no longer inherits global MCP plugins**: the subprocess
  was loading MCP servers from `~/.claude/settings.json` (e.g. a Playwright
  browser plugin) despite `setting_sources=[]` being set. Root cause: the SDK
  only passes `--setting-sources` to the CLI when the list is truthy — an empty
  list is silently ignored, leaving the CLI to load all default config. The fix
  passes `--strict-mcp-config` via `extra_args`, which tells the Claude CLI to
  honour only the MCP server explicitly provided for the test run and ignore all
  others. This prevents the model from reaching for leaked tools (e.g.
  `browser_navigate` to read a tool-result file) and producing spurious
  tool-call errors in eval results.

## [0.11.3] - 2026-06-27

### Fixed
- **Temp-dir leak in ClaudeSDKProvider**: `tempfile.mkdtemp()` was never removed after
  each `_run_agent` call, leaking hundreds of `/tmp/testmcpy_sdk_*` directories in
  long-running servers. Added `shutil.rmtree(_sdk_tmpdir, ignore_errors=True)` in a
  `finally` block so cleanup happens on all paths (normal, timeout, exception).
- **DRY evaluator error-detection**: `ToolCallQuality.evaluate` duplicated the
  error-collection loop from `NoToolCallErrors.evaluate`. Factored it into a shared
  `NoToolCallErrors._collect_errors(tool_results)` classmethod so both classes use the
  same logic and cannot drift independently.

### Tests
- Added `TestToolCallQuality` unit tests: all-success → 1.0, partial errors → fractional
  score, all errors → 0.0/passed, empty results → 1.0, factory registration.

## [0.11.2] - 2026-06-27

### Changed
- Removed all references to MCP service-specific tool names (`health_check`,
  `get_instance_info`, `list_dashboards`, `get_chart_info`, `list_datasets`,
  `generate_explore_link`, etc.) from source code, system prompts, comments,
  and unit test fixtures. testmcpy is MCP-server-agnostic — no tool names
  specific to any particular server should appear in the framework itself.
- Generalized the ClaudeSDK, Codex, and Gemini provider system prompts so they
  describe the gateway pattern (`call_tool`) without naming Preset-specific tools.
- Updated unit test fixtures in `test_unnecessary_tool_calls` and
  `test_assistant_sse_multi_turn` to use generic tool names (`fetch_status`,
  `list_items`, `get_details`, `build_url`).

## [0.11.1] - 2026-06-27

### Added
- **`tool_call_quality` evaluator**: soft alternative to `no_tool_call_errors`.
  Scores tool-calling quality as `1 − (error_calls / total_calls)` — always
  passes so the test result is driven by other evaluators, but pulls the
  aggregate score down proportionally to how many tool calls errored before the
  model found the right argument format. Use this instead of `no_tool_call_errors`
  for tests where first-try validation failures (e.g. the model discovering the
  `request` wrapper via retry) are expected and should reduce quality score
  rather than hard-failing the test.

## [0.11.0] - 2026-06-26

### Added
- **Enter the Claude Agent SDK auth token through the UI**: the LLM Profiles
  editor (and wizard) now exposes an optional "Auth token" field for the
  `claude-sdk` / `claude-code` providers. Paste a Claude subscription token
  (`claude setup-token`, starts with `sk-ant-oat`) or an Anthropic API key
  instead of relying on env vars / a host `claude` login. The token is
  auto-routed by prefix to `CLAUDE_CODE_OAUTH_TOKEN` (subscription) or
  `ANTHROPIC_API_KEY` (API key) in the Agent SDK subprocess env via the new
  `claude_cli_auth_env()` helper. Wired through chat, Test Manager runs, and
  the Test Execution Agent (`/api/agent/run` + `testmcpy agent --llm-profile`
  / `--cli-token`). Leaving the field blank preserves the previous behavior
  (host `claude` login).
- **UI token honored on every Claude SDK code path (no gaps)**: added
  `resolve_claude_cli_token()` so any path that builds a `ClaudeSDKProvider`
  picks up a UI-entered token from the LLM profile — including the AI
  test-generation and doc-optimizer/eval endpoints (now accept an
  `llm_profile`), and the programmatic paths (CLI chat, docs optimizer,
  runner tools, websocket chat) via a default-profile fallback. The three
  generation modals now send the globally selected LLM profile.
- **Model field is now a combobox**: the Edit/Add Provider modal and the
  provider wizard list the registry models for the chosen provider as
  suggestions AND accept any custom model name typed in (previously a closed
  dropdown limited to a couple of entries).

### Fixed
- **Claude SDK chat/agent no longer dies as root with
  `--dangerously-skip-permissions cannot be used with root/sudo`**: the
  streaming chat ("interact") path and the Test Execution Agent built their
  SDK subprocess env without `IS_SANDBOX=1`, which the Claude CLI requires to
  honor `--dangerously-skip-permissions` (from
  `permission_mode="bypassPermissions"`) when running as root in a container.
  The chat path and the orchestrator now both reuse
  `ClaudeSDKProvider._build_clean_env` (single source of truth) — which also
  blanks `ANTHROPIC_API_KEY` in the no-token case so the agent uses the host
  subscription login like chat does, instead of silently billing API credits.
  The chat fix also injects the UI/profile token consistently.
- **Editing an MCP server no longer wipes its token/secret**: the profiles
  list endpoint masks secrets (`***` / `<first8>...`), and saving an edit
  used to write that mask back, destroying the real value. The update handler
  now preserves the stored secret when the incoming value is the masked form,
  while still allowing a new value or an explicit clear.

## [0.10.3] - 2026-06-12

### Changed
- **docs-site: bump Next.js 14.2.35 → 15.5.19** (security backports).
  Dependabot proposed 16.2.9, but Nextra 3 is incompatible with Next 16 —
  its search plugin calls `init()` on `next/dist/compiled/webpack/webpack.js`,
  which Next 16 no longer exports (`TypeError: pkg.init is not a function`
  while loading `next.config.mjs`). Next 15.5.x is the newest line that
  carries the security fixes and still works with Nextra 3 / Pages Router /
  React 18; Next 16 needs a Nextra 4 + App Router migration

## [0.10.2] - 2026-06-12

### Fixed
- **Reports deep link didn't scroll the run into view**: opening
  `/reports?run=<run_id>` loaded the run's details in the right panel but
  left the runs list at the top, so the highlighted run could be far
  off-screen. The deep-linked run's list item (tests and smoke tabs) is now
  scrolled into view once it renders

## [0.10.1] - 2026-06-12

### Fixed
- **Add MCP wizard "Test Connection" 405**: the wizard posted to
  `POST /api/mcp/test-connection`, which didn't exist on the backend (only
  the per-profile `POST /api/mcp/profiles/{id}/test-connection/{idx}` did),
  so the SPA catch-all route answered with 405 Method Not Allowed. Added the
  standalone endpoint, which tests an inline MCP config (sse/http or stdio,
  with none/bearer/jwt/oauth auth) before it is saved to any profile
- **CLI `add-mcp` wizard test step always crashed**: it constructed
  `MCPClient` with keyword arguments that don't exist (`mcp_url=`,
  `timeout=`, `transport=`, `command=`, `args=`) and called `list_tools()`
  without `initialize()`. It now uses `StdioMCPClient` for stdio and
  `MCPClient(url, auth=...)` for sse, initializes/closes the client, passes
  the full collected auth config (bearer token / JWT / OAuth details were
  previously dropped), and catches `MCPError` so connection failures show
  the friendly message instead of crashing the wizard
- **`POST /api/tools/compare` and `POST /api/tools/{tool}/debug` were
  broken**: both called `MCPClient(mcp_url=...)` (the parameter is
  `base_url`), `mcp_config.get_mcp_url()` (no such method on `MCPServer`),
  passed an `AuthConfig` object where a dict is expected, and called
  `call_tool` with `(name=, arguments=)` instead of an `MCPToolCall`;
  compare also called nonexistent `client.cleanup()`. Every comparison
  iteration / debug call failed as a result. Tool errors are now also
  surfaced (`is_error` results previously counted as successes), and
  results are serialized JSON-safe

## [0.10.0] - 2026-06-12

### Added
- **Hosted documentation site** at https://preset-io.github.io/testmcpy —
  Nextra 3 static site in `docs-site/` with a full CLI reference (all 38
  commands from live `--help` output), per-page Web UI docs with
  screenshots, concepts, guides, and a FAQ. Deployed to GitHub Pages via
  `deploy-docs.yml`; PRs touching `docs-site/` are build-checked by
  `docs-pr-check.yml`. Includes `llms.txt`, sitemap, and robots.txt
- **5 new UI screenshots**: Performance matrix, Leaderboard, Server
  health, Schema Compat matrix, and Security Dashboard

### Fixed
- **Schema Compat (Servers page) never worked**: `MCPProfileSelector`
  read `profile_id` from `/api/mcp/profiles`, which returns `id` — server
  selection produced `undefined:<name>` IDs, so the compatibility matrix
  reported every tool as Missing and tool auto-discovery returned nothing

### Changed
- **README refresh**: docs badge + hosted-docs links, corrected Web UI
  route table (`/performance` and `/servers` are canonical; `/metrics`,
  `/compare`, `/mcp-health`, `/compatibility` are redirects), expanded
  command highlights, and a larger screenshot gallery
- **All 9 existing screenshots recaptured** at 1600x1000 in dark theme
  against a live demo MCP server with populated data

## [0.9.2] - 2026-06-11

### Fixed
- **Reports tab 500 on older DB files**: `GET /api/results/run/{id}` failed
  with `no such column: question_results.manual_false_positive` for DBs
  created before that column existed. The SQLite column auto-migration now
  derives missing columns from the ORM model metadata instead of a
  hand-maintained list that had drifted from the models

## [0.9.1] - 2026-06-11

### Fixed
- **Chat uses the selected MCP profile's auth**: `/api/chat` and
  `/api/chat/stream` now pass the selected profile's `mcp_url`/`auth` to
  the LLM provider. Previously SDK providers fell back to the *default*
  profile, so chatting with any other profile failed with "No usable
  cached OAuth token for <default-profile-url>" even when the selected
  profile was authenticated

### Added
- **Interactive OAuth login during chat** (`TESTMCPY_CHAT_OAUTH_LOGIN`,
  default on): when the selected profile uses OAuth auto-discovery and no
  cached token exists, chat triggers the browser OAuth flow and retries
  instead of erroring; the stream shows "Waiting for OAuth login in
  browser...". Set `TESTMCPY_CHAT_OAUTH_LOGIN=false` to disable

## [0.9.0] - 2026-06-11

Crash-safe UI test runs: the results DB is now the source of truth for
in-flight runs, and the client survives disconnects instead of declaring
live runs dead.

### Added
- **Incremental result persistence**: UI-triggered runs write their
  `test_runs` row at start and one `question_results` row per completed
  test (`testmcpy/server/run_persistence.py`) — a crash mid-suite keeps
  every finished test instead of losing the whole run
- **Run heartbeats**: new `test_runs.heartbeat_at` column (alembic
  `c3d4e5f6a7b8`, SQLite auto-migrated) stamped every 30s per live run;
  crashed runs flip to `interrupted` within ~4 minutes via a background
  sweeper instead of waiting for the next server restart
- **Concurrency cap with visible queue**: `TESTMCPY_MAX_CONCURRENT_RUNS`
  (default 2); excess runs show `status=queued` in `/api/runs` and the
  background-runs indicator, and can be stopped while queued
- **History fallback**: WebSocket `attach` and `GET /api/runs/{id}`
  resolve runs from the results DB when the in-memory registry no longer
  has them — runs that died mid-flight replay as `interrupted` with
  their partial results
- **Client reconnect**: a dropped run socket reconnects with exponential
  backoff (5 attempts), then offers a manual Reattach banner; resume on
  page load is server-authoritative (`GET /api/runs`) instead of a
  5-minute localStorage TTL

### Fixed
- Token usage was stored as 0 for every UI-triggered run (the mapping
  read `input`/`output` but providers emit `prompt`/`completion`);
  history rows now also record the effective model/provider when a
  suite-level override is set
- Reattaching no longer duplicates the buffered log backlog

## [0.8.0] - 2026-06-11

The platform release: CI gating, per-config performance analytics,
quality scoring, security scanning, and a UI overhaul.

### Added
- **CI gate**: `testmcpy run --gate / --gate-config / --min-pass-rate`
  exits non-zero when thresholds fail; unified `.testmcpy-gate.yaml`
  with `evals` / `conformance` / `usability` / `security` sections
  (legacy flat keys still work; example in `examples/testmcpy-gate.yaml`)
- **JUnit XML output**: `--junit-xml PATH` or `--report foo.xml`;
  markdown report auto-appended to `$GITHUB_STEP_SUMMARY` inside
  GitHub Actions
- **Performance analytics**: per-test × per-config matrix with
  flakiness detection and day-bucketed trends — `/performance` UI
  page, `/api/analytics/*` endpoints, and CLI parity via
  `testmcpy matrix | leaderboard | flaky`
- **`testmcpy bench`**: run a suite across models × profiles ×
  repeats (one session) to feed the matrix
- **`testmcpy conformance`**: wraps the official
  `@modelcontextprotocol/conformance` suite with testmcpy reporting
  and exit codes
- **`testmcpy score`**: LLM-usability grade (0-100, A-F) for a
  server's tool surface — descriptions, schemas, naming, token
  economy, parameter clarity
- **`testmcpy scan`**: static security scanner — tool-poisoning
  heuristics (TMS001-007), rug-pull detection vs saved baselines
  (TMS100-103), SARIF 2.1.0 output for GitHub code scanning
- **Security evaluators**: `no_injection_echo` canary detection,
  `auth_rejects_missing_token` / `auth_rejects_invalid_token` /
  `auth_token_not_echoed` probes; `security` and `auth-security`
  evaluator packs
- **`testmcpy badge`**: shields.io endpoint JSON for pass-rate /
  usability / conformance badges
- **Reusable GitHub Action** rewritten: uvx install, real gate exit
  codes, JUnit, sticky PR comment, structured outputs
- `TESTMCPY_DB_URL` (full SQLAlchemy URL, e.g. Postgres) with a new
  `[postgres]` extra; SQLite remains the default
- `python -m testmcpy` entry point

### Changed
- UI consolidation: new Performance page replaces Compare + Metrics
  (routes redirect); MCP Health + Compatibility merged into a tabbed
  Servers page; nav regrouped (Workflow / Analytics / Infrastructure
  / Settings)
- Mobile-web pass: responsive modals, stacking forms, touch-draggable
  panels, phone-tuned Monaco, 44px tap targets, overflow-safe tables
- Run listings now surface `mcp_profile` / `llm_profile` and paginate
  with real totals

### Fixed
- Runs stuck in `running` after a server crash are marked
  `interrupted` on startup
- Profile YAML loader warns when credential fields hold literals
  instead of `${ENV_VAR}` references

## [0.7.26] - 2026-06-09

### Fixed
- **Docker server image can't run Claude Agent SDK (agentic) tests
  out of the box** (follow-up to v0.7.25's CLI-bake work). Two
  coupled issues:

  1. **Missing dependency.** The Dockerfile installs only
     `pip install .[server]`, but `claude-agent-sdk` lived only in
     the `sdk` and `all` extras. The server's test runner
     (`testmcpy/src/test_runner.py`) imports `claude_agent_sdk` for
     any test using the Claude SDK provider, so the published image
     crashed with `ModuleNotFoundError: No module named
     'claude_agent_sdk'` (raised as a `ValueError` from
     `testmcpy/src/llm_integration.py:1421`). The SDK is now part of
     the `server` extra so `pip install testmcpy[server]` (and the
     Docker image) include it. Anyone running the server can run
     agentic tests without a separate install.

  2. **Version conflict between `fastmcp` and `claude-agent-sdk`.**
     `fastmcp 2.12.5` pinned `mcp<1.17.0`, while
     `claude-agent-sdk 0.2.x` requires `mcp>=1.23`. Installing both
     produced a `pip` resolver warning and a fragile environment.
     Bumped `fastmcp>=2.14.5,<3.0.0` (first 2.x line that allows
     `mcp>=1.24`), tightened `claude-agent-sdk>=0.2.0,<1.0.0`. The
     two pins are now co-locked — a clean `pip install` produces a
     conflict-free environment.

  As a bonus, `claude-agent-sdk` 0.2.x's wheel already bundles a
  platform-appropriate `claude` CLI binary at
  `claude_agent_sdk/_bundled/claude` (~250 MB on linux x86_64), and
  the SDK's CLI lookup finds the bundled copy before falling back
  to PATH. So agentic tests run end-to-end on the default image —
  no `INSTALL_CLAUDE_CLI=true` required. The v0.7.25 build-arg
  remains, repositioned as the separate "I want
  `docker exec <container> claude`" / "I want a specific Claude
  Code version that differs from what the SDK bundles" use case.

  CI now runs `pip check`, `import claude_agent_sdk, fastmcp, mcp`,
  AND drives the SDK's own CLI-lookup + a `--version` invocation
  through the located binary, so a future SDK wheel that fails to
  bundle the binary, a resolver conflict, or a binary that can't
  link on `python:3.11-slim`'s libc all fail CI rather than ship.

## [0.7.25] - 2026-06-09

### Added
- **Optional Claude Code CLI in the Docker image (SC-108437).** New
  build ARG `INSTALL_CLAUDE_CLI` (default `false`) when set to `true`
  installs the [Claude Code](https://docs.claude.com/en/docs/claude-code/)
  native binary into the image so `docker exec <container> claude …`
  works without a per-container install that's wiped on every
  `up --build`. Uses the native installer
  (`https://claude.ai/install.sh`) rather than `npm install -g`
  because the slim base has no Node.js — keeps the gated image lean.
  The binary is symlinked to `/usr/local/bin/claude` so it's on the
  default `docker exec` PATH. Layer is placed right after the curl
  apt-get step so it shares the cache and isn't invalidated by source
  changes below.

  docker-compose.yml threads the ARG through from an env var so the
  ergonomic opt-in is:

  ```
  INSTALL_CLAUDE_CLI=true docker compose up -d --build
  docker exec <container> claude --version
  ```

  Default builds (and the published image) stay unchanged.

## [0.7.24] - 2026-06-09

### Fixed
- **Bulk-delete in `/reports` left the page apparently empty until a
  manual reload (SC-108367 #1).** `loadTestRuns` fetches with
  `limit=100`. After bulk-delete the client only filtered the deleted
  IDs out of local state — runs beyond the 100-row window stayed
  hidden until the user reloaded the page. Now re-fetches
  `loadTestRuns()` + `loadFilterOptions()` after a successful delete,
  also adds the missing `res.ok` check + a user-visible error toast on
  failure. Same fix applied to the per-file history bulk-delete in
  TestManager (`loadResultsHistory(testFile)` after success).
- **Reports detail view: cost/tokens read as `$0.00` / `0` for
  chatbot-provider runs (SC-108367 #2).** The chatbot/assistant
  provider's endpoint doesn't surface cost or token counts. Showing
  `$0.00` and a bare `0` icon misled users into reading "free" or
  "broken." Both the run-level header and the per-test row now show
  `— cost` / `— tokens` with a tooltip "Cost/Token counts not reported
  by the chatbot/assistant provider" when `provider == 'assistant' |
  'chatbot'` and the value is zero. Other providers still see the
  literal value.
- **Reports detail view: per-test score number was unlabeled
  (SC-108367 #2).** A bare `0.50` was easy to miss as a score. Now
  reads `score 0.50/1.00` with a tooltip "Aggregate evaluator score
  for this test (0.00–1.00). 1.00 = all evaluators passed at 100%."
- **Reports detail view: assistant response was collapsed by default
  and prompt was missing entirely (SC-108367 #2).** The test's user
  prompt was never saved in `TestResult`, and the LLM response was
  hidden behind a click. For chatbot tests the response IS the test,
  so it's now surfaced at the top of each expanded card alongside the
  prompt, with Tool Calls / Evaluations / Metrics below. Empty
  responses (e.g. guardrail refusals) get an explicit hint —
  "Empty response. The assistant ran N tool calls but never produced
  final text…" — instead of an empty box. Old runs missing the prompt
  show a "(not recorded for this run)" inline hint so users know to
  open the YAML or re-run with v0.7.24+.

### Added
- **`TestResult.prompt`** persisted by `_run_test_with_retry`, so the
  /reports detail view can render the original prompt without
  re-parsing the source YAML (which may have moved or been edited).
  Old saved runs lack this field; the UI shows a graceful fallback.

### Fixed
- **MCP-profile / LLM-providers config saves crashed with 500 on
  read-only single-file bind mounts (SC-108367 #3).** Docker
  deployments mount `mcp_services.yaml` / `llm_providers.yaml` as
  `:ro`. `Path.replace` requires write access to the *target* file
  (not just parent dir), so the atomic-write step raised `EROFS`,
  and the recovery `shutil.copy2(backup, primary)` raised `EROFS`
  again — surfacing as a misleading "Failed to restore backup" 500
  cascade. The previous `~/.testmcpy/` fallback (commit `f19c866`)
  only checked CWD writability and didn't trigger here.
  Saves now detect the single-file read-only case and write to
  `./.testmcpy/<filename>` instead — sharing the named volume already
  used for `storage.db`. Loads prefer that fallback when it exists,
  so UI edits round-trip across container restarts. The backup-
  restore-onto-primary path is skipped when falling back, eliminating
  the "Failed to restore backup" noise. Applied to both duplicate
  `save_mcp_yaml` copies (`server/state.py` now delegates to
  `server/helpers/mcp_config.py`) and to `LLMProfileConfig.save`.
  10 unit tests pin the read-only fallback + writable-primary
  unchanged behavior + load-prefers-fallback round trip.
- **MCP `:ro` follow-up — saved edits invisible at runtime (review
  finding #1 on PR #79).** The PR initially fixed the 500 + the
  silent save-doesn't-stick problem only for the two `save_mcp_yaml`
  call sites, but `MCPProfileConfig._find_config_file` (used by
  `GET /api/mcp/profiles` and runtime `load_profile()`) was still
  reading the read-only primary directly. So a saved MCP edit went
  to `.testmcpy/.mcp_services.yaml` correctly but the profiles list
  + the runner kept using the stale config. Fixed by delegating
  `_find_config_file` to `helpers.get_mcp_config_path()` (which
  prefers the fallback) with a graceful fall-through for CLI
  contexts where the server helpers aren't importable.
- **LLM save/load resolver symmetry (review finding #5).**
  `LLMProfileConfig.save` derived `primary_path` directly rather
  than via the fallback-preferring resolver, so in the unusual
  Docker-then-native transition a fallback existed but save wrote
  to CWD. Now uses `_resolve_llm_providers_path` for both.
- **`.testmcpy/` no longer materialised by read-side path lookups
  (review finding #6).** Split `_persistent_dir` into a pure-path
  read variant and a write-side `_persistent_dir_ensure` so opening
  the Reports / Tests pages doesn't have a write side-effect.

  2 added unit tests:
  - `test_mcp_profile_config_loader_prefers_fallback` — drives the
    full path-disagreement reproduction (read-only primary → save
    via `save_mcp_yaml` → `MCPProfileConfig()` loads the fresh
    profile, not the stale one).
  - `test_load_path_resolution_does_not_create_persistent_dir` —
    pins the no-side-effect-on-reads invariant.

## [0.7.23] - 2026-06-08

### Fixed
- **Stop button vanished + run continued invisibly when a directory
  batch's first file errored (SC-108217).** The directory runner's
  per-file `_run_test_command` emitted `{type: "error", …}` for any
  exception. The UI treats `error` as TERMINAL (sets `running=false`,
  closes the WS). So when file 1's MCP init crashed, the batch kept
  iterating files 2..N server-side but the UI thought the run was
  dead — no Stop button, no logs, no way out other than reload-or-kill.
  Server now distinguishes per-file errors from batch-fatal ones:
  inside a directory batch (`_in_batch=True`), errors emit
  `{type: "file_error"}` which the client appends to logs and marks
  the file as failed in `directoryRunProgress.results`, while the
  batch keeps streaming. Single-file / single-test runs still emit
  the terminal `error` event.
- **Stop button optimistically declared victory.** Old `stopTests`
  sent `stop` then immediately closed the WS and set `running=false`
  without server confirmation. New flow: send `stop`, set transient
  `stopping=true`, DON'T close the WS. The server emits a `stopping`
  ack immediately and a terminal `all_complete{status:"stopped"}`
  once the cancellation finalises — only then does the client close.
  Falls back to `POST /api/runs/{run_id}/stop` if no live WS.
- **Stop button visibility too narrow.** Previously gated on
  `running && !runAllLlmsMode`; now also visible when
  `directoryRunProgress` is set (covers the file-error desync above)
  OR when `stopping=true` (renders as a disabled "Stopping…" button).

### Added
- **Global "In-flight runs" indicator in the sidebar.** New
  `<BackgroundRunsIndicator />` polls `GET /api/runs?active_only=true`
  every 5s and shows a pill with the count + a popover listing each
  run with Open / Kill buttons. Works from any page — pre-fix, runs
  started on /tests were completely invisible from /reports etc.
- **`GET /api/runs`** lists in-flight (or all) registry handles,
  with a serialised view of `meta` so the UI can label them
  meaningfully (folder name for batches, file path for singles).
  **`GET /api/runs/{run_id}`** returns one. **`POST
  /api/runs/{run_id}/stop`** fires the cancellation without needing
  a WebSocket.
- **`stopping` WebSocket event** ack'd immediately on `stop` receipt.
- **Terminal `all_complete{status:"stopped"}`** emitted when the
  registry finalises a cancelled run, so the client transitions out
  of its "stopping…" transient.
- 8 unit tests in `test_runs_router.py` (list/get/stop endpoints,
  active-only filter, finished-noop, 404s, cancel-actually-cancels-
  the-task). 2 new in `test_websocket_attach.py`
  (`file_error` vs `error` gating; stop-emits-`stopping`-then-
  terminal-`all_complete{stopped}`).

## [0.7.22] - 2026-06-08

### Added
- **New `no_tool_call_errors` evaluator (SC-108214)** catches false-negative
  passes where `execution_successful` was happy because `is_error=False`,
  yet the tool result's `content` block carried error text the model then
  silently recovered from (51 such silent passes observed on workspace
  `bcff9fe0`).

  The MCP transport flag (`result.is_error`) only catches transport-level
  failures. When a Preset MCP server rejects an argument shape (e.g.
  pydantic validation), the response comes back with `is_error=False` and
  a text block like `Error: 1 validation error for call[list_charts] …`.
  The model usually recovers by retrying with different arguments — the
  test passes, but the first attempt was a silent error.

  `no_tool_call_errors` normalises the `content` payload (dict / list of
  text blocks / plain string / None) and scans for known error patterns:
  `"Error: "`, `"validation error for call["`, `"Unknown tool:"`,
  `"Unknown tool '"`, `"error_type"`, `"ASCIIError"`. Strictly stronger
  than `execution_successful`: `is_error=True` is still a fail.
  Composable: "no tools made" passes (pair with `was_mcp_tool_called`
  to also assert a tool fired).

  Registered in the factory as `"no_tool_call_errors"`. 7 unit tests
  pin clean-pass, `is_error=True`-fails, validation-error-with-
  `is_error=False`-fails, unknown-tool pattern, list-content
  normalisation, empty results, and factory registration.

## [0.7.21] - 2026-06-08

### Added
- **Directory "Run All" streams logs end-to-end (SC-108184).** Previously
  `runAllInDirectory` issued sequential HTTP `POST /api/tests/run`
  requests with no streaming — the Logs tab was gated on
  `running || streamingLogs.length` and never opened for batch runs.
  The directory flow now goes through a new server-side
  `{type: "run_directory"}` WebSocket command that runs the batch under
  ONE registry run_id and surfaces per-file boundaries as `file_start` /
  `file_complete` events. The Logs tab opens the moment a batch starts.
- **Browser reload survives in-flight runs (SC-108184).** The WS handler
  used to run `_watch_for_stop` alongside the test task with
  `asyncio.wait(FIRST_COMPLETED)`; on `WebSocketDisconnect` the watcher
  returned and `run_task.cancel()` fired — runs died on reload. A new
  in-memory `run_registry` module now owns the asyncio task plus a
  bounded log buffer (`deque(maxlen=20_000)`) and a list of structured
  events. WebSocket connections become *attachments* rather than owners:
  disconnect drops the attachment only; the task keeps writing to the
  buffer. The client persists `currentRunId` to localStorage and, on
  mount-with-recent-run-still-active, sends `{type: "attach", run_id}`
  to reattach. The dispatcher replays buffered logs as `log_replay`
  events, then live-streams from the registry queue. Users see a
  `🔁 Reattached to run …` banner.
- New top-level WebSocket messages:
  - `run_directory` (client → server) — start a batch under one run_id.
  - `attach` (client → server) — reattach to an in-flight or
    recently-finished run.
  - `run_started` (server → client) — sent immediately on a new run
    OR on a successful reattach (with `reattached: true`).
  - `log_replay`, `file_start`, `file_complete`, `superseded` (server →
    client) — backlog replay marker, directory per-file boundaries,
    and a marker the prior attachment receives when another client
    supersedes it.

### Changed
- **`save_test_run_to_file`** honors a caller-supplied `run_id` so the
  WebSocket runner's registry id matches the saved history record. For
  single-file runs the live "Reattached" banner and the `/reports` row
  now show the same id. Directory sub-saves still mint their own per-file
  ids — each YAML keeps its own `/reports` row.
- **`TestRunContext`** centralises WS event handling in a single
  `_handleServerMessage` helper (was three duplicated switch
  statements). Adds `runDirectory` and `attachToRun` actions plus
  `currentRunId` and `directoryRunProgress` state, all persisted to
  localStorage.
- **`TestManager`** `runAllInDirectory` delegates to
  `contextRunDirectory` and drops the trailing `alert()` summary in
  favour of the live Logs tab + Results tab updating in place. The
  `directoryRunProgress` state lives in the context now so a reload
  during a batch still renders the per-folder progress strip.

### Notes
- Runs are held in memory only — runs are lost on server restart. Finished
  runs are retained for 30 min so a slow reload can still pick up the
  final state, then GC'd lazily on the next `create_run` call.
- Only one attachment per run at a time; a second client attaching
  receives the backlog and the first attachment gets a `superseded`
  marker. Avoids fan-out complexity.

## [0.7.20] - 2026-06-07

### Fixed
- **Multi-turn loop terminated on `got_final` even when the same turn
  also produced new tool_results**: the Preset chatbot backend emits
  the `final` event in the SAME SSE stream as the tool_call /
  tool_result events for some flows (observed in
  `test_C02_1_explore_not_generate`: 4 tools including
  `generate_explore_link` ran, then `final` arrived, but the actual
  synthesized answer — the explore URL — was on a follow-up POST that
  never happened). `got_final` was treated as unconditional "stop",
  collapsing the response to the transitional opener
  (`"Sure! I'll use Vehicle Sales."`).

  Reordered the stop conditions so `got_error` is unconditional but
  `got_final` only terminates when no new tool_results arrived this
  turn — otherwise the loop keeps going so the backend can produce
  the synthesized answer in a follow-up POST. The
  text-grew + no-new-tool-results stop still wins for cases where the
  backend doesn't emit `final` at all.

### Added
- 3 unit tests in `test_assistant_sse_multi_turn.py`:
  - `test_followup_post_when_final_arrives_alongside_new_tool_results`
    — pins the C02_1 regression.
  - `test_got_final_alone_still_stops_when_no_new_tool_results` —
    backwards-compat for the clean-text-with-final path.
  - `test_got_error_terminates_immediately_even_with_new_tool_results`
    — confirms `got_error` stays unconditional.

### Changed
- **`AssistantProvider.MAX_COMPLETION_TURNS` raised from 3 → 8**
  (SC-108183). After the `got_final` fix above, C02_1 still failed —
  log showed `turns=3/3, final=no, 4 tool calls` (all info-gathering:
  `get_instance_info`, `search_tools`, `list_datasets` × 2) and 128
  chars of transitional text. The chatbot legitimately walks through
  several discovery tool calls across multiple turns before invoking
  `generate_explore_link` and synthesising — the 3-turn budget was
  clipping the synthesis turn off. Idle (`SSE_IDLE_ABORT_SECONDS`,
  default 90s) and per-call wall-clock (`PER_CALL_WALL_CLOCK_SECONDS`,
  default 180s) still bound runaway streams independently of this cap.
  The cap-hits test now drives `MAX_COMPLETION_TURNS` batches
  parameterically rather than hard-coding 3 so the assertion follows
  future cap changes.

## [0.7.18] - 2026-06-07

### Fixed
- **Chatbot evals failing intermittently in long suites with empty SSE
  streams (no tool calls, no text, no error)**: `AssistantProvider`
  opened a single conversation in `initialize()` and reused the same
  `conversation_id` across every test in the run. By later tests
  (observed reliably on `test_C01_4_sql_discovery_and_query` once the
  preceding C01 tests had run) the conversation carried the entire
  accumulated history of tool calls and responses, and the Preset
  chatbot backend either hit a context limit or silently returned an
  empty stream — surfacing as `execution_successful: FAIL` with zero
  tool_calls and an empty response. Moved conversation creation out of
  `initialize()` into the start of every `generate_with_tools()` call,
  so each test gets a fresh conversation. The multi-turn follow-up
  POSTs inside a single call still share that one fresh
  conversation_id (the in-call turn threading is preserved). Failure
  to create the conversation now surfaces as an `LLMResult` with
  `response="Error: failed to create conversation: …"` so the test
  runner gets a real result back instead of an exception.

### Added
- 2 unit tests in `test_assistant_sse_multi_turn.py` pin the new
  invariant:
  - `test_fresh_conversation_per_generate_with_tools_call` — three
    successive calls produce three distinct conversation_ids; the
    `_open_conversation` helper fires exactly once per call regardless
    of how many follow-up POSTs the multi-turn loop issues.
  - `test_conversation_creation_failure_returns_error_llmresult` —
    a raising `_open_conversation` surfaces as a clean error
    `LLMResult` (not an exception) and no SSE POST is issued.

### Fixed
- **Chatbot evals always returned an empty response after server-side
  tool execution**: the Preset `/api/v1/copilot/completions` endpoint
  emits `tool_call` + `tool_result` events on the first SSE stream and
  then closes WITHOUT a `final` / `token` event. The generated answer
  arrives only on a SECOND POST that reuses the same `conversation_id`.
  `AssistantProvider.generate_with_tools` only made one POST, so
  `response_includes`-style evaluators couldn't match anything.
  `generate_with_tools` now issues a follow-up POST when the previous
  turn ended with tool_results but no answer text and no
  final/error/abort signal. Capped at `MAX_COMPLETION_TURNS = 3` and
  stops early when a turn produces zero new tool_results (so a backend
  in a steady "no more work" state can't pin the runner). The
  concurrency-limit semaphore is now held across all turns so the cap
  limits parallel logical requests, not parallel POSTs.
- **Multi-turn loop stopped too early on transitional text**
  (regression in C01_2_dashboard_drill_down): the Preset chatbot
  backend streams "thinking aloud" sentences (e.g. `Let me work through
  this step by step.`) ALONGSIDE tool calls in the same SSE turn — no
  `final` event yet. The first stop-condition (`text grew → break`)
  surfaced that fragment as the answer and never issued the follow-up
  that contained the real analysis. Stop conditions reordered:
  `got_final`/`got_error` first (authoritative), then aborts, then
  `text grew AND no new tool_results` (heuristic). Transitional text
  alongside new tool calls now correctly keeps the loop going. 2 added
  tests pin the transitional-text path and the "text without new
  tool_results triggers stop even without a `final` event" path. 8
  total multi-turn tests.

### Added
- **External / symlinked test directory discovery in the UI**:
  - `GET /api/tests` now walks `<cwd>/tests` with `os.walk(followlinks=True)`,
    so a `ln -s /path/to/external/suite tests/suite` shows up in the
    Tests page (Path.rglob in 3.11 silently skipped these).
  - A new `TESTMCPY_EXTRA_TESTS_DIRS` env var (os.pathsep-separated
    absolute paths) registers external test roots that get walked and
    namespaced under their basename so different suites stay
    visually distinct in the file tree.
  - Symlink-cycle guard via `realpath` so `tests/loop -> tests/` (or
    any cross-tree loop between roots) terminates safely.
  - The same `realpath` set now suppresses duplicate listings when the
    same physical dir is reachable BOTH via a symlink under `tests/`
    AND a `TESTMCPY_EXTRA_TESTS_DIRS` entry. The symlink label wins
    (primary scan runs first). When both modes resolve to the same
    suite, prefer the symlink form so the editor + edit endpoints have
    a single canonical local path.
  - `GET /api/tests/{filename}`, `PUT /api/tests/{filename}`, and
    `DELETE /api/tests/{filename}` now resolve via a shared
    `_resolve_test_file` helper that searches `<cwd>/tests` AND each
    `TESTMCPY_EXTRA_TESTS_DIRS` root. Externally-discovered files are
    now viewable + savable + deletable from the UI editor (previously
    they 404ed because the endpoints only checked under `<cwd>/tests`).
    Path-traversal guards (`is_relative_to(allowed_root)`) extend to
    every allowed root.
  - The streaming runner's history label now uses the discovered
    relative path under any allowed root (e.g.
    `preset-mcp-tests/chatbot/C01.yaml`) rather than collapsing to a
    bare basename, so two external suites sharing a filename can't
    collide in the history index.
  - Discovery loop catches `Exception` (with a `noqa` rationale) so
    one bad YAML — UnicodeDecodeError, malformed structure, etc. —
    doesn't 500 the entire Tests page.
  - All discovered files carry absolute `path` values so
    `run-single` / the streaming runner can open them regardless of
    discovery method.
  - 17 unit tests cover symlinked subdirs, cycle guard, single + multi
    extra-root, stale env-var entries, dedup, broken-YAML resilience,
    view/edit-extra-root resolution, path-traversal block, and baseline
    no-regression paths.

> If a suite is reachable both via a `tests/<sym>` symlink AND a
> `TESTMCPY_EXTRA_TESTS_DIRS` entry, the symlink label wins — pick one
> mechanism per suite to keep the UI grouping predictable.

## [0.7.16] - 2026-06-06

### Fixed
- **Test runner logs panel rendered each test as two collapsible groups**: both
  the websocket (`🧪 Running test 1/N: name` + `📝 Prompt: …` + `⏱️ Timeout: …s`)
  AND `TestRunner.run_test` (`Running test: name` + full `Prompt: …` +
  `Provider: …, Model: …` + `Available tools: N` + `MCP URL: …`) emitted
  test-start headers. The `StreamingLogViewer` parser greedily grouped on
  every `Running test:` line, producing two cards per test — first a
  near-empty card with the truncated prompt, then the real card with all
  the actual entries. Added a `quiet_test_announcement` flag to `TestRunner`
  that the websocket sets, suppressing the duplicate header / prompt /
  provider / MCP-URL / chatbot-API lines inside the runner.
- **Truncated prompt in streamed logs**: websocket no longer trims
  `tc.prompt` to 100 chars — it sends the full prompt as the in-group
  `📝 Prompt: …` entry.
- **Sticky group header looked doubled / ghosted when multiple tests were
  expanded**: replaced the translucent `bg-*/20 backdrop-blur-sm` sticky
  header with a solid `bg-surface-elevated` + colored left-border accent.
  Sticky headers no longer bleed through one another at the top of the
  scroll container.
- **CLI banner + MCP init ignored suite-level `provider:` declaration**:
  `testmcpy run` printed `Provider: <CLI default>` in the startup banner
  and always tried to initialize the local MCP client even when the YAML
  declared `provider: assistant` at the top level (which means tools are
  resolved server-side and no local MCP is needed). We now peek the file
  for a top-level `provider:` / `model:` before printing the banner and
  before computing `skip_mcp_init`, so chatbot YAML files no longer trigger
  spurious OAuth flows or banner mismatches.
- **UI "Using:" badge ignored suite-level overrides**: when a YAML test
  file declared `provider:` / `model:` at the top level, the Tests-page
  badge still showed whatever the LLM-profile default was. Added a
  `parseSuiteOverride()` helper that scans the open file's leading
  top-level keys; the badge now displays the effective model/provider
  with a "suite override" pill, and `getLlmConfig()` (used for both
  single-test and run-all flows) sends the override-aware values to the
  websocket.
- **Chatbot YAMLs crashed in the UI with `AssistantProvider requires
  workspace_hash AND domain`**: the websocket never folded
  `.llm_providers.yaml` credentials into the runner's `provider_config`
  the way `POST /tests/run-single` already does. UI now sends the
  selected `llm_profile` over the WebSocket; server-side, when the
  effective provider is `assistant`/`chatbot`, the websocket loads the
  profile and merges `workspace_hash` / `domain` / `api_token` /
  `api_secret` / `api_url` / `conversations_path` / `completions_path`
  into `provider_config` (suite-level YAML keys still win). Chatbot
  YAMLs now launch from the Tests page without the
  `--workspace-hash`/`--domain` CLI flags.
- **MCP-profile fallback for chatbot credentials**: most users'
  `.llm_providers.yaml` only lists Claude/OpenAI providers — they have
  no `assistant` entry to merge from. The websocket now derives
  `workspace_hash` + `domain` from the selected MCP profile's URL
  (`https://<workspace_hash>.<domain>/mcp`) and pulls `api_url` /
  `api_token` / `api_secret` from the MCP profile's JWT auth block. A
  `🔑 Derived from MCP profile …` log line names exactly which fields
  were filled, so users can see what to add to `.llm_providers.yaml`
  if they want explicit control. Suite YAML and LLM profile values
  still win — this is the last resort, not a default.

### Changed
- **`getLlmConfig` UI fallback model**: `claude-sonnet-4-20250514` is
  retired; default fallback is now `claude-sonnet-4-6` (matches the
  Python defaults already updated in earlier releases).
- **"Using:" badge handles the `model: default` sentinel**: chatbot
  YAMLs declare `model: default` to mean "let the chatbot endpoint
  pick"; the badge now renders this as italic "provider default"
  with a tooltip explaining the sentinel, instead of looking like a
  buggy literal "default" string.

## [0.7.15] - 2026-06-06

### Changed
- **`AssistantProvider` endpoints are now configurable — no hardcodes**:
  `_DEFAULT_CONVERSATIONS_PATH` and `_DEFAULT_COMPLETIONS_PATH` class constants
  are removed. Both paths must now be supplied via `.llm_providers.yaml` or the
  `--assistant-conversations-path` / `--assistant-completions-path` CLI flags;
  `AssistantProvider.__init__` raises `ValueError` with a clear message if
  either is missing.
- **Auth no longer falls back to MCP config**: `api_token`, `api_secret`, and
  `api_url` are no longer read from the default MCP server config. Values must
  come from `.llm_providers.yaml` or the `--jwt-*` / `--assistant-api-*` CLI
  flags. This removes the cross-concern coupling between MCP and chatbot auth.
- **`.llm_providers.yaml` now accepts assistant fields**: `LLMProviderConfig`
  gains `workspace_hash`, `domain`, `api_token`, `api_secret`, `api_url`,
  `conversations_path`, `completions_path`. The YAML loader reads these from
  either the top-level provider block or a nested `auth:` sub-block.
- **Server `run-single` endpoint** passes `provider_config` to `TestRunner`
  and folds LLM-profile assistant fields into it when an `llm_profile` is
  provided.

## [0.7.14] - 2026-06-06

### Fixed
- **Blank tool name in AssistantProvider verbose output**: `_handle_sse_event`
  now tries multiple field name conventions for the `tool_call` event
  (`tool_name`, `name`, `function_name`, `function.name`) and for `tool_result`
  (`tool_name`, `name`, `function_name`), then falls back to matching the
  stored `tool_calls` by `id`. Same multi-field fallback applied to
  `arguments`/`input`/`parameters` and `tool_call_id`/`id`.
- **Misleading "Available tools: 0" and "MCP URL: ..." for assistant provider**:
  the runner verbose block now skips those lines for `assistant`/`chatbot`
  providers and instead shows the chatbot completions endpoint URL and a note
  that tools are managed server-side. `AssistantProvider` gains a
  `completions_url` property for this purpose.

## [0.7.13] - 2026-06-06

### Fixed
- **ClaudeSDK verbose log noise**: `Message #N: AssistantMessage` / `UserMessage`
  header lines are now suppressed for types that already log their own content
  (text, tool calls, tool results). Only `RateLimitEvent` and `ResultMessage` —
  which have no content block logged below them — keep the header line.
- **Thinking preview**: `Thinking (N chars)` is now
  `Thinking: "first 100 chars..." (N chars)` so the model's reasoning is
  visible at a glance without expanding anything.

## [0.7.12] - 2026-06-06

### Fixed
- **`OperationalError: table question_results has no column named tool_call_counts`**:
  `TestStorage.__init__()` now calls `_apply_column_migrations()` after
  `create_all()`. This method inspects `PRAGMA table_info` for each table and
  issues `ALTER TABLE … ADD COLUMN` for any column that is missing, making the
  migration automatic and idempotent. Covers `tool_call_counts`, `false_positive_rate`
  (added in v0.7.10), and `total_cost` (added in v0.7.7) for existing DB files
  that predate those releases.

## [0.7.11] - 2026-06-06

### Added
- **Mass delete for test results**: the `/reports` left panel now has a
  "Select" button that enters multi-select mode. Each run gets a checkbox;
  a sticky toolbar shows a "Select all" checkbox, the count of selected items,
  and a red "Delete N" button. Confirming sends a single
  `POST /api/results/runs/bulk-delete` request. Cancelling exits select mode
  without touching data. The single per-row trash icon is hidden while in
  select mode to avoid accidental single deletes.

## [0.7.10] - 2026-06-06

### Added
- **Tool call breakdown + false positive rate** per question result: `tool_call_counts`
  (`{tool_name: count}`) and `false_positive_rate` (0–1) are now computed in
  `save_question_result()`, stored in two new `question_results` columns
  (Alembic migration included), returned by the API, and displayed in the
  `TestResultPanel` UI after the tool-calls list.
- **Score penalty** for unnecessary extra calls: score is multiplied by
  `max(0.5, 1 - false_positive_rate)` unless the `unnecessary_tool_calls`
  evaluator already penalised the result.

### Fixed
- **`MarkupError` crash** when LLM response contains URL-like brackets (e.g.
  `/superset/dashboard/preset-prod/`): `run.py` now imports `escape` from
  `rich.markup` and wraps `result.reason`, `result.error`, and
  `result.error_message` before passing them to `console.print` /
  `table.add_row`.

## [0.7.9] - 2026-06-06

### Fixed
- **`/reports` page shows `$0.00` for all runs**: `GET /api/results/run/{run_id}`
  in `results.py` had two hardcoded `0.0` literals — one for `metadata.total_cost`
  and one for each per-result `cost`. Both now read from the DB values:
  `run["summary"]["total_cost_usd"]` and `qr["cost_usd"]` respectively.

## [0.7.8] - 2026-06-06

### Added
- **Exponential back-off for unavailable MCP servers**: when a connection or
  `list_tools()` call fails, the server now waits before retrying — 5 s, 10 s,
  20 s, 40 s … capped at 5 minutes. Previously the UI's polling caused a fresh
  (expensive) connection attempt on every request, flooding the logs and
  hammering a dead server. Back-off state is tracked per
  `{profile_id}:{mcp_name}` key; a successful connection resets it. Client
  evictions (after use-time errors) also trigger back-off so reconnects are
  throttled in that path too.

## [0.7.7] - 2026-06-06

### Fixed
- **OAuth generator lock crash** (`RuntimeError: The current task is not holding
  this lock`): `MCPClient.list_tools()` now uses `asyncio.timeout` on Python
  3.11+ instead of `asyncio.wait_for`. The new form runs the coroutine in the
  current task so `CancelledError` unwinds the FastMCP auth generator's
  `async with lock:` block in the correct task context, preventing the anyio
  lock from being released by a GC finaliser task that doesn't own it. A custom
  event-loop exception handler suppresses the residual noise on Python 3.10.
- **Broken cached client not evicted**: `list_mcp_tools()` now evicts the cached
  `MCPClient` on *any* error, not only connection errors. Previously a failed
  `list_tools()` call left the broken client in the in-memory cache, causing
  every subsequent request to the same profile to 500.
- **`is_connection_error` too narrow**: extended to match
  `"failed to connect"`, `"failed to initialize"`, and `"timed out"` substrings
  so MCPConnectionError and MCPTimeoutError messages correctly surface as 503.
- **Cost always `$0.00` in UI**: `storage.complete_run()` now sums
  `question_results.cost_usd` into `test_runs.total_cost` alongside the
  existing `total_tokens` rollup. Per-question costs were already stored
  correctly; they just were never aggregated to the run level.

## [0.7.6] - 2026-06-06

### Added
- **Sidecar JSON after every `testmcpy run`**: results are now also written to
  `tests/.results/<run_id>.json` in addition to the SQLite DB. The file is
  created atomically (write to `.tmp` then rename) and the directory is
  created if it doesn't exist. Structure: `run_id`, `test_file`, `provider`,
  `model`, `mcp_profile`, `summary` (total/passed/failed/score), `results`.

## [0.7.5] - 2026-05-28

### Fixed
- **`ClaudeSDKProvider` system prompt**: removed "search/discover tools if
  needed" guidance that caused `claude-sonnet-4-6` to call `search_tools`
  before every tool execution. On PROD the gateway returns a 107k-char
  response that exhausts the session context. System prompt now explicitly
  bans `search_tools` and any `authenticate` tool call. Fixes the chronic
  file-14 NOT COMPLETED, ghost-authenticate on file-07 (sc-106500), and
  widespread `was_tool_called` failures seen in eval cycles c39/c40.
- **Default model** updated from retired `claude-sonnet-4-20250514` to
  `claude-sonnet-4-6` in `MCPClientRunner`, `AnthropicDirectRunner`, and
  `LLMJudge`. The old model ID is retained in the registry but marked
  `is_deprecated=True`.

## [0.7.4] - 2026-05-21

### Added
- **Progressive checkpoint saves** in `testmcpy run`. After every
  test completes, partial results are written to
  `tests/.results/.checkpoints/<session_id>.json` (atomic
  write-then-replace). If the run is killed mid-stream (OOM, ctrl-C,
  parent harness timeout), the harness can still recover what
  finished without rerunning the suite. Surfaced in eval cycle c33
  (SC-107284) where long suites died mid-run with no recoverable
  state.
- **`.done` sentinel file** written immediately after the run summary
  prints, before optional post-processing (DB save, report
  generation). The sentinel lets a parent harness treat the run as
  finished even if a later step hangs or fails. Sentinel path:
  `tests/.results/.checkpoints/<session_id>.done`.

### Changed
- `MCPClient._expand_gateway_tools()` now caps total chars collected
  across all `search_tools` discovery queries at 200k. Prevents
  memory / context blowup against MCP servers that inline very large
  tool schemas in their gateway responses. Truncation is
  per-response and the loop short-circuits once the cap is reached.

## [0.7.3] - 2026-05-08

### Added
- **Per-call wall-clock guard** in `AssistantProvider.generate_with_tools()`.
  `PER_CALL_WALL_CLOCK_SECONDS` (default 180s) is a hard ceiling on
  the SSE consumption — it fires even when bytes ARE flowing, just
  slowly. Distinct from the existing idle-abort: idle = "no progress
  at all", wall-clock = "any progress, but too slow overall". Time
  spent waiting for the concurrency-limit semaphore (see below) is
  NOT counted against this budget. The agor parallel-cycle harness
  was hitting this case across c28-c32 (SC-106138) where bytes kept
  flowing but the call took 5+ minutes. Wall-clock-aborted calls
  surface a clean error string in `LLMResult.response` and tag the
  Done log with `[SSE wall-clock aborted]`.
- **SSE heartbeat log lines** every `HEARTBEAT_SECONDS` (default 10s)
  while the stream is open: `[Assistant] still streaming … 30s
  elapsed, 12 events, 5s since last event`. Lets a parent harness
  distinguish a slow-but-progressing child from a wedged one without
  parsing every SSE event.
- **`--max-concurrent-streams` CLI flag** on `testmcpy run` for the
  assistant/chatbot provider. Class-level `asyncio.Semaphore` capped
  at the configured limit; held for the entire SSE consumption so
  the cap really does limit parallel streams. Lazy-allocated inside
  the running event loop on first use (so the semaphore binds
  correctly under pytest-asyncio and other multi-loop setups). Use
  this when a parent harness fans out many testmcpy children at
  once and the chatbot endpoint stalls under load.
- Unit tests in `unit_tests/test_assistant_sse_concurrency_and_walls.py`:
  per-call wall-clock fires against a chatty stream, heartbeats appear,
  semaphore serialises concurrent streams, semaphore is unbounded
  when unset, configure idempotency.

### Changed
- `AssistantProvider.generate_with_tools()` now distinguishes
  "request start" (`start_time`, used for `LLMResult.duration`) from
  "stream consumption start" (`stream_start_time`, used for the
  per-call wall-clock budget). When a semaphore wait happens, only
  the request start moves earlier — the stream budget is preserved.

## [0.7.2] - 2026-05-06

### Added
- **SSE idle-abort defense** in `AssistantProvider.generate_with_tools()`.
  If the chatbot SSE stream emits no recognized event for
  `SSE_IDLE_ABORT_SECONDS` (default 90s) the provider closes the
  connection and returns an explanatory error in `LLMResult.response`.
  This complements the v0.7.1 per-test wall-clock timeout: the
  wall-clock fires *between* tests, but a stalled SSE stream that
  keeps the TCP connection open (httpx's per-event read timeout never
  fires because no event has been received *yet*) could hang inside a
  single test indefinitely. Observed in eval cycle c29 (SC-105915)
  where C00_9, C01_9, and C02_7 hung against the chatbot backend
  despite v0.7.1 being deployed. The threshold is a class attribute
  so subclasses / tests can override it.
- Unit test in `unit_tests/test_assistant_sse_idle_abort.py` exercising
  the idle-abort path with a fake SSE stream that opens, sends one
  event, then goes silent.

## [0.7.1] - 2026-05-06

### Added
- **Per-test wall-clock timeout** in `TestRunner._run_test_with_retry`.
  Each test is now wrapped in `asyncio.wait_for(...)` with a budget of
  `test_case.timeout + WALL_CLOCK_SLACK_SECONDS` (60s default; CLI
  providers also get the existing 120s floor on the per-call timeout).
  Without this, providers that stream events — notably the
  `AssistantProvider` chatbot endpoint — could keep a test alive
  indefinitely because the per-event httpx timeout resets on every
  received chunk. Observed in eval cycle c28 (SC-105726): the chatbot
  hung 15+ minutes on `add_chart_to_existing_dashboard` against a
  nonexistent chart, never closing the SSE stream. The wall-clock
  guard breaks out of these.
- **Per-tool-call retry budget** in `ClaudeSDKProvider`. Tracks each
  `(tool_name, args, error_text_prefix)` signature; if the same call
  produces the same error 3× in a row the query aborts with a clear
  diagnostic in the response (and a `[retry budget aborted]` marker in
  the logs). Observed in c28: the model kept calling `execute_sql` with
  `query=...` instead of `sql=...`, hitting the same 3 validation
  errors each turn until the runner was killed externally.
- 3 new unit tests in `unit_tests/test_runner_wall_clock_timeout.py`:
  hung-test abort, happy-path passthrough, CLI 120s floor.

### Changed
- `WALL_CLOCK_SLACK_SECONDS` is a class-level attribute on `TestRunner`
  (default 60.0s) so it can be overridden in tests or via subclassing.

## [0.7.0] - 2026-05-05

### Changed
- `AssistantProvider` is now a vendor-neutral chatbot client. The class
  docstring documents the protocol contract it expects (JWT auth →
  conversation create → SSE completions stream with `token` /
  `tool_call` / `tool_result` / `usage` / `final` / `error` events).
  No vendor-specific class names, paths, or branding live in the
  source. To target a vendor that diverges from the contract, subclass
  and override one of the hooks: `_authenticate`, `_open_conversation`,
  `_build_headers`, `_build_completions_payload`, `_handle_sse_event`.
- The SSE-loop's mutable state is factored into a `_SSEStreamState`
  dataclass so subclasses can replace event handling without
  re-implementing the loop.

### Added
- CLI flags `--assistant-conversations-path` and
  `--assistant-completions-path` so users can override the endpoint
  paths without subclassing (e.g., to target a different chatbot
  backend). Both are optional; if omitted, the provider's
  `_DEFAULT_CONVERSATIONS_PATH` / `_DEFAULT_COMPLETIONS_PATH` are
  used.
- `TestRunner.initialize()` and per-test loops skip MCP client init
  + `list_tools()` for the `assistant` / `chatbot` providers — the
  chatbot endpoint owns its tool registry server-side. (Folds in the
  fix from PR #51.)

### Fixed
- Internal session-token attribute renamed `_jwt_token` → `_session_token`
  for consistency with the vendor-neutral framing. Callers that poked
  at the old name need to be updated (caught one in
  `unit_tests/test_assistant_provider.py`).

## [0.6.2] - 2026-05-05

### Fixed
- `testmcpy run --provider assistant` (or `chatbot`) no longer
  initializes a local MCP client. The assistant endpoint talks to
  MCP server-side, so the local runner shouldn't be opening an MCP
  connection — doing so was triggering an unwanted OAuth flow against
  the workspace's MCP URL and loading auth from `.mcp_services.yaml`
  that the user hadn't asked for. Patched in three places:
  the CLI (`run.py`), `TestRunner.initialize()`, and the inner
  per-test loops that previously called `mcp_client.list_tools()`.
  For the assistant/chatbot providers, no local tool discovery is
  performed — the chatbot endpoint owns the tool registry server-side.
- `AssistantProvider` now returns `tool_results` as a list of
  `MCPToolResult` objects (matching `ClaudeSDKProvider`), instead of
  raw dicts. The previous shape caused evaluators to fail with
  `'dict' object has no attribute 'is_error'` on every test.

## [0.6.1] - 2026-05-05

### Added
- Dedicated `--assistant-api-url` / `--assistant-api-token` /
  `--assistant-api-secret` CLI flags so MCP and the assistant
  endpoint can use different JWT credentials in the same command.
  The MCP `--jwt-*` flags are still accepted as a fallback for
  shared-cred setups.
- `assistant` and `chatbot` are now valid values for `--provider`
  (added to the `ModelProvider` enum so typer accepts them).
- `OPENROUTER_API_KEY`, `XAI_API_KEY`, `GOOGLE_API_KEY`, and
  `GEMINI_API_KEY` are now recognized in `~/.testmcpy` and `./.env`
  (added to `Config.GENERIC_KEYS`).

### Fixed
- `AssistantProvider.initialize()` validation error messages now
  point users at the new CLI flags / config files instead of the
  removed `ASSISTANT_*` env vars.

## [0.6.0] - 2026-05-05

### Changed (BREAKING)
- testmcpy code no longer reads environment variables directly. Credentials
  and provider configuration must come from CLI flags, the YAML config
  files (`.mcp_services.yaml` / `.llm_providers.yaml`, which support
  `${VAR}` substitution at load time), or the env-format config files
  (`~/.testmcpy` / `./.env`). Specifically:
  - `AssistantProvider` no longer reads `ASSISTANT_WORKSPACE_HASH`,
    `ASSISTANT_DOMAIN`, `ASSISTANT_ENVIRONMENT`, `ASSISTANT_API_TOKEN`,
    `ASSISTANT_API_SECRET`, `ASSISTANT_API_URL` from the environment.
    Pass them via CLI flags (`--workspace-hash`, `--domain`,
    `--environment`, `--jwt-url`, `--jwt-token`, `--jwt-secret`) or
    via `provider_config` on the Python API.
  - `OpenRouterProvider` and `XAIProvider` no longer fall back to
    `OPENROUTER_API_KEY` / `XAI_API_KEY` env vars. Configure via
    `.llm_providers.yaml` `${VAR}` substitution.
  - `AnthropicRunnerTool` no longer falls back to `ANTHROPIC_API_KEY`.
  - `LLMAsJudgeEvaluator` no longer reads `ANTHROPIC_API_KEY`,
    `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY` directly.
  - `Config._load_config` no longer reads `GENERIC_KEYS` /
    `TESTMCPY_KEYS` from the environment. The `~/.testmcpy` and `./.env`
    file paths are still loaded as before.
  - The `envvar=` kwargs were removed from CLI flags `--auth-token`,
    `--jwt-url`, `--jwt-token`, `--jwt-secret` so they no longer pick up
    `MCP_AUTH_TOKEN` / `MCP_JWT_*` from the environment.

### Added
- CLI flags `--workspace-hash`, `--domain`, `--environment`,
  `--assistant-api-url`, `--assistant-api-token`,
  `--assistant-api-secret` on `testmcpy run` to configure the
  assistant/chatbot provider without env vars. The MCP `--jwt-*`
  flags are also accepted as a fallback when MCP and assistant share
  the same JWT credentials.
- `assistant` and `chatbot` are now valid values for `--provider`
  (added to the `ModelProvider` enum).
- `OPENROUTER_API_KEY`, `XAI_API_KEY`, `GOOGLE_API_KEY`, and
  `GEMINI_API_KEY` are now recognized in the `~/.testmcpy` and
  `./.env` env-format config files (added to `Config.GENERIC_KEYS`).
- CLI flag values for `assistant` / `chatbot` providers are folded into
  `provider_config` and reach `AssistantProvider.__init__` via
  `create_llm_provider`'s kwarg filtering.

## [0.5.1] - 2026-05-04

### Changed
- `ExecutionSuccessful` evaluator now ignores SDK-internal recovery errors that
  the model triggers when a tool result exceeds the SDK token limit and is
  saved to a file. Specifically: errors matching `Server "file-system" not
  found` / `Server "file" not found` are skipped, and `ReadMcpResourceTool`
  is treated as a blocked tool (its failures don't count against the test).
- `MCPToolResult` now carries the `tool_name` so evaluators can match against
  the tool name directly instead of inferring from the `tool_call_id`.

## [0.5.0]

### Added
- Docker Compose configuration for containerized deployment
- MCP service profiles (`mcp_services.yaml`) with local profile
- LLM provider profiles (`llm_providers.yaml`) with Claude and GPT-4o defaults
- Pre-commit hook to prevent Preset infrastructure URLs from leaking into the repo

### Changed
- Renamed `PresetOAuth` to `MCPOAuth` (back-compat alias preserved)
- Genericized `.mcp_services.yaml.example` with `example.com` placeholder URLs
- `AssistantProvider` domain mappings are now empty by default (set via env vars)

### Removed
- Preset infrastructure URLs from code and config (`preset.io`, `preset.zone`)
- `PRESET_*` environment variable fallbacks from `AssistantProvider`
- Preset sandbox/staging profiles from committed `mcp_services.yaml`
- `SANDBOX_API_*`/`STAGING_API_*` env vars from `docker-compose.yml`

---

## [0.2.17] - 2025-12-19

### Added
- Verbose progress output for `testmcpy run` CLI command showing test-by-test progress
- Real-time PASS/FAIL status, score, and duration for each test as it completes
- Spinner animation while tests are executing

---

## [0.2.16] - 2025-12-19

### Fixed
- Skip hidden directories (`.results/`, `.smoke_reports/`) when recursively discovering test files
- Only load files with valid test structure (`prompt` or `tests` key) to avoid loading result files

---

## [0.2.15] - 2025-12-18

### Fixed
- Fixed `testmcpy run <directory>` to recursively find test files in subdirectories using `rglob`
- Added support for `.yml` extension and `.json` files in directory test discovery
- Handle single test case files (without `tests` key) when loading from directories

---

## [0.2.14] - 2025-12-18

### Fixed
- Fixed `create_llm_provider` passing unsupported kwargs (like `auth`) to providers that don't accept them

---

## [0.2.13] - 2025-12-18

### Added
- Environment variable substitution in `.llm_providers.yaml` using `${VAR}` and `${VAR:-default}` syntax
- Comprehensive unit test suite (428 tests) covering config, evaluators, formatters, profiles, smoke tests, and YAML parsing

### Fixed
- Python 3.10 compatibility with Typer by using `Optional[X]` instead of `X | None` syntax
- CI workflow now correctly runs tests from `unit_tests/` directory

### Changed
- Removed MCP Tests workflow (tests folder is gitignored for runtime-generated tests)

---

## [0.1.1] - 2025-01-16

### Added
- **Multi-layer configuration system** with clear priority ordering:
  1. Command-line options (highest)
  2. `.env` in current directory
  3. `~/.testmcpy` user config file
  4. Environment variables
  5. Built-in defaults (lowest)

- **Dynamic JWT token generation** for MCP services:
  - Configure `MCP_AUTH_API_URL`, `MCP_AUTH_API_TOKEN`, `MCP_AUTH_API_SECRET`
  - Automatically fetches and caches JWT tokens for 50 minutes
  - Eliminates need to manually manage short-lived JWT tokens

- **`testmcpy config-cmd` command** to view current configuration:
  - Shows all config values with their sources
  - Masks sensitive values (API keys, tokens)
  - Displays config file locations and existence

- **`.testmcpy.example`** - Comprehensive example configuration file with detailed comments

### Changed
- **Removed default provider/model** assumptions:
  - No longer defaults to Ollama (which requires local setup)
  - CLI now defaults to Anthropic if not configured
  - Users must explicitly configure their preferred provider in `~/.testmcpy`

- **Updated README** with:
  - Detailed configuration documentation
  - Provider setup instructions (Anthropic, Ollama, OpenAI)
  - Authentication options (static token vs dynamic JWT)
  - Clear recommendations for each provider

- **Integrated config system** into:
  - `testmcpy.cli` - All commands now use Config class
  - `testmcpy.src.mcp_client` - MCPClient uses config for URL and auth

### Fixed
- Config priority now correctly handles generic keys (ANTHROPIC_API_KEY) vs testmcpy-specific keys
- Environment variables properly fall back for generic keys while being overridden for testmcpy keys

## [0.1.0] - 2025-01-15

### Added
- Initial release of testmcpy as installable Python package
- CLI with 6 commands: `research`, `run`, `tools`, `report`, `chat`, `init`
- Support for multiple LLM providers: Anthropic, Ollama, OpenAI, Claude SDK
- MCP client with FastMCP integration
- Test runner with YAML/JSON test definitions
- Rich terminal output with beautiful formatting
- PyPI and Homebrew distribution support
