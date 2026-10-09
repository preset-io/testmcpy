# Baseline report: generic compatibility surface vs native tools (SC-125472, phase 1)

Story: https://app.shortcut.com/preset/story/125472

This is the harness and baseline phase. It is **not** the go/no-go: the producer
(https://app.shortcut.com/preset/story/125470) and gateway
(https://app.shortcut.com/preset/story/125471) code do not exist yet, so the native
surfaces here are modelled on a local fixture server. Every number is labelled:

- **measured**: observed against local fixtures or a real local Superset app by this harness
- **observed (client)**: observed in a real client binary driven against the fixtures
- **simulated**: computed from an explicit policy or cost model, never claimed as client behaviour
- **BLOCKED**: not run; reason recorded; nothing inferred from documentation

All numbers below come from `results/results.json` (run `baseline-1`; regenerate with
`python -m testmcpy.qualification run`). The full tables are in
[`baseline-results.md`](baseline-results.md). Budgets were committed before any
measurement ([`../budgets.yaml`](../budgets.yaml), commit `789a500`); one wording
clarification (A1, no threshold change) was appended afterwards and is recorded there.

## What was built

| Piece | Where |
|---|---|
| Pre-registered budgets (12) with justification | `budgets.yaml` |
| Real Superset MCP catalog (79 tools) and the shipped generic surface (4 tools), captured from `apache/superset` master `100f51240b` (2026-10-08) in memory, metadata only | `fixtures/`, `capture/capture_superset_catalog.py` |
| Real `search_tools` responses for every task query (20) from Superset's own BM25 transform | `fixtures/*.search-responses.json` |
| Gateway generic tool definitions (`list_workspaces`, `search_workspace_tools`, `call_tool(workspace_id, ...)`, ...) | `fixtures/gateway-generic-tools.json` |
| Deterministic 150-tool scale catalog (79 real + 71 derived clones) | `testmcpy/qualification/catalog.py` |
| Fixture MCP server (stateless streamable HTTP, roles, grants, Knowledge flag, producer age, write ledger) serving three surfaces | `testmcpy/qualification/server.py`, `world.py` |
| 12-task suite, identical across surfaces | `tasks.yaml` |
| Scripted reference agent, budget evaluation, report | `runner.py`, `evaluate.py`, `report.py` |
| Real Superset dispatcher fidelity probe (9 probes, native vs `call_tool`) | `capture/probe_superset_fidelity.py`, `traffic/superset-real-fidelity.*` |
| Raw JSON-RPC traffic per task and surface | `traffic/fixture/` |
| Real-client spot runs (Claude Code 2.1.280, codex-cli 0.147.0), sanitised | `traffic/clients/`, `capture/clients/` |
| Client matrix with BLOCKED entries | `client_matrix.yaml` |

No live workspace was contacted, nothing was written outside the in-memory fixture world,
and nothing was deployed, merged or submitted.

## Headline numbers (catalog `actual`, tokenizer o200k_base)

| | generic (search/call) | native eager | native deferred (simulated) |
|---|---|---|---|
| Initial context tokens (B01), measured | 472 | 47,834 | 346 |
| Cumulative tokens per task, median / p90 (B03), measured | 4,373 / 5,990 | 47,949 / 50,367 | 5,343 / 6,530 |
| Discovery round trips per task, median / max (B05) | 1 / 3 | 0 / 0 | 1 / 3 (simulated) |
| Scripted task accuracy (B06), 12 tasks | 12/12 | 12/12 | 12/12 |
| Missing-tool rate (B07), argument-failure rate (B08) | 0 / 0 | 0 / 0 | 0 / 0 |
| Approval prompts per read-only task / per write op (B09, `honours_annotations`), simulated | 2.7 / 3 | 0.1 / 1 | 0.1 / 1 |

Catalog `scale` (150 tools, 152 with the two fixture Knowledge tools): initial 472 / 92,319 / 346;
task median 6,441 / 92,434 / 7,318; discovery median 2 / 0 / 2.

Deltas against the generic baseline (actual catalog): native eager adds **+47,362** initial
tokens and **+43,576** median task tokens (10.97x) and removes 1 discovery round trip;
native deferred (simulated) removes 126 initial tokens, adds 970 median task tokens (1.22x)
and keeps the discovery round trips.

Real Claude Code 2.1.280 (provider tokenizer, first-turn prompt tokens, observed (client)):

| | generic | native eager | scale eager |
|---|---|---|---|
| default environment on the OpenRouter route (no deferral) | 29,755 | 88,463 | 143,282 |
| `ENABLE_TOOL_SEARCH=auto` (client deferral on) | 29,891 | 23,922 | 24,812 |

The offline estimate under-counts this provider's tokens by about 24% (native minus generic: 58,708
measured vs 47,362 estimated); no verdict changes. Codex (`openai/gpt-5-mini`, OpenRouter route):
first request 12,873 generic, 46,941 native, 79,050 scale.

## Budget verdicts (gating; both catalogs give the same pass/fail)

| Budget | generic | native eager | native deferred (sim) |
|---|---|---|---|
| B01 initial context <= 10,000 | pass | **FAIL** (47,834) | pass |
| B02 schema size per tool (median 400 / p95 1,200 / max 2,500) | n/a | **FAIL** (519 / 1,556 / 2,373) | **FAIL** (same definitions) |
| B03 cumulative per task (median 15,000, p90 30,000; <= 1.25x generic) | pass | **FAIL** (47,949 / 50,367; 10.97x) | pass (1.22x) |
| B04 latency (informational) | would pass | would pass | would pass |
| B05 discovery round trips (median 1, max 2) | **FAIL** (max 3) | pass | **FAIL** (max 3) |
| B06 scripted accuracy 100% | pass | pass | pass |
| B07 missing-tool rate 0 | pass | pass | pass |
| B08 argument failure <= 5% | pass | pass | pass |
| B09 approvals (reads 0, writes 1 per op) | **FAIL** | **FAIL** (0.1, see below) | **FAIL** (same) |
| B10 listing completeness 100% | n/a | pass | pass |
| B11 isolation 0 leaks | pass (0 of 19 probes) | pass | pass |
| B12 result/error fidelity 100% | **FAIL** (8 of 9 probes, real app) | pass (reference) | pass (reference) |

## Findings

1. **Eager exposure of the whole real catalog is far over budget.** 79 tools cost 47,675 tokens
   (median 519, p95 1,556). The heaviest are `manage_native_filters` (2,373), `generate_chart`
   (2,232), `list_datasets` (1,683) and `list_charts` (1,556). B01 fails 4.8x, and a real client
   confirms it: 88k vs 30k first-turn prompt tokens in Claude Code. Separately, `outputSchema`
   payloads would add about 70k tokens if a client forwards them (not measured as forwarded) and the
   server `instructions` add 6,645 tokens on every surface.
2. **Schema weight is a producer problem, not a delivery-mode problem.** B02 fails on the
   definitions themselves, so deferring them does not fix it; it only hides the cost until a tool is
   loaded. Trimming the few heaviest definitions is a producer item (SC-125470).
3. **The generic surface is cheap to start and expensive to approve.** 472 initial tokens and
   3 to 6k per task, but the dispatcher and `search_tools` carry no annotations, so a client
   applying MCP spec defaults treats every read as destructive. Observed: Claude Code denied the
   unannotated `search_tools` in headless mode; Codex cancelled it ("user cancelled MCP tool call")
   until the server was pre-approved.
4. **Annotations are not a client-independent fix.** Observed (client): Claude Code denied
   `list_charts` despite `readOnlyHint=true`, and also denied the read-only pinned
   `get_instance_info` and `health_check`; allow-listing the server was what made reads run. Codex
   `exec` ran `list_charts` without a prompt and cancelled the unannotated dispatcher. So
   annotation-driven approval depends on the client and must be recorded per client, never assumed.
   The simulated B09 verdict (`honours_annotations`) therefore describes one of the behaviours seen,
   not a guarantee; under `prompts_on_everything` native tools cost 1.6 prompts per read task.
5. **B09 native FAIL is one task.** `sql-query` counts as read-only but `execute_sql` is
   annotated `readOnlyHint=false` (arbitrary SQL can write), so it prompts even on native tools.
   The pre-registered threshold is kept; the owner should decide whether SQL belongs in the
   "read" class for approval purposes.
6. **Discovery is noisy, not just extra.** The real BM25 `search_tools` returned `find_users` and
   `delete_dataset_metric` in the top five for "list charts", and five unrelated `list_*` tools for a
   Knowledge query. Median response is 2,450 tokens (about five full definitions) and
   `structuredContent` repeats the same data. B05 fails only through the `restricted-role` task
   (three searches while correctly failing to find `execute_sql`); positive tasks cost at most two.
7. **The real generic dispatcher is nearly faithful.** 8 of 9 probes against the real Superset app were
   identical native vs `call_tool` (error flags, structured keys, text). The exception is an unknown
   tool name, which is reported as "Error calling tool 'call_tool': Unknown tool ...", hiding which tool
   was wrong. Domain errors are in-band (`isError=false` with an `error` field) on both surfaces, so
   evaluators must read payloads, not only `isError`.
8. **Listing is complete.** `tools/list` returned every permitted tool at page sizes 1, 7, 25, 50 and
   unpaged on both catalogs (no duplicates). Today's server returns one page; a client that reads only
   the first page of a 7-per-page list would see 8.6% of the tools.
9. **Required tasks behave as specified on the fixtures.** Old producer: native surfaces return the
   typed `UNSUPPORTED_PRODUCER` error, the generic surface keeps working. Revoked access: typed
   `ACCESS_REVOKED` (HTTP 403 on a single-workspace connection) while the other workspace still
   reads. Restricted role: the read-only role's list has 48 of the 79 real tools (plus the 2 fixture Knowledge tools), with no SQL or write tool,
   and a direct call is denied. Knowledge disabled: the tools are absent from a single-workspace
   list and `FEATURE_DISABLED` is returned from the generic path. Writes landed only in the
   in-memory ledger.
10. **Malformed arguments are rejected before any write on both surfaces**, but only native tools
    expose the operation's typed schema in `tools/list`; the generic dispatcher exposes
    `arguments: object`, so a client cannot validate before sending. Observed (Codex, gpt-5-mini):
    `call_tool` was sent without `name` and with a guessed tool name; 0 of 5 generic chart-find runs
    were correct versus 8 of 8 native (tiny n, one cheap model; an observation, not an accuracy).
11. **Client-side deferral exists and works, conditionally.** Claude Code deferred MCP definitions and
    used its ToolSearch only when `ENABLE_TOOL_SEARCH` was `auto` or `true` on this non-first-party
    route; first-turn tokens fell from 88,463 to 23,922 (actual) and 143,282 to 24,812 (scale), and the
    chart-find task cost 76k cumulative vs 177k eager. Whether first-party sessions defer by default
    was not observed. Codex showed no deferral on its fallback-metadata route.

## Calibration notes (no verdict changed, recorded for the owner)

- The B01/B02 headroom assumed a +-20% tokenizer difference; Claude measured +24%. The verdicts have
  4.8x and 1.3x margins, so none flips.
- B04 is fixture protocol overhead (tens of milliseconds in-process); it says nothing about network or
  model time and stays informational until a staging endpoint is measured.
- The deferred figures are a cost model; only the Claude Code run is an observation.

## Remaining compatibility gaps (this phase)

- Native-first default for the full catalog needs either a curated default-visible core within B01 or
  client/provider deferral, plus slimmer definitions (B02). That is a decision for the owner after the
  producer lands, not a result of this phase.
- Older clients and providers without deferral stay on the documented compatibility mode.
- Per-client approval behaviour must be written down per client; two clients disagree already.

## Limits of this baseline

- Fixture server, not the real producer or gateway; the real Superset app was used only for the
  catalog, the search responses and the dispatcher-fidelity probes.
- The Superset source is master as of 2026-10-08; it is not the deployed build. Deployed pins are
  still to be established (see `../rollout-plan.md`).
- The generic search on the scale catalog and for non-admin principals uses a stand-in BM25 or the
  recorded real response restricted to the permitted tools; neither is Superset's ranker.
- The gateway native shape (required `workspace_id` on every tool) and the Knowledge tools are
  assumptions (see `../waits-on-125470-125471.md`).
- Client runs used an OpenRouter route with one inexpensive model per client and n between 1 and 5, because
  no first-party key or login exists here. They are observations of that route, not of Claude.ai,
  ChatGPT or first-party sessions, and they are **not** B06 values.
