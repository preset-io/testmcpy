# Staged rollout plan (DRAFT): native-first MCP tools

Story: https://app.shortcut.com/preset/story/125472. Producer:
https://app.shortcut.com/preset/story/125470. Gateway:
https://app.shortcut.com/preset/story/125471.

**Status: draft for owner review. Nothing here is approved, scheduled or executed.**
There is no automatic default flip and no production deploy in this story. Each stage
below needs its own explicit approval from Amin, and progress is tied to verified
adoption, deployment and acceptance (the checks below), not to a merge.

## Principles

1. **Additive first.** Named tools are added next to the generic `search_tools`/`call_tool`
   surface. The generic surface stays on and unchanged until the last stage, so older
   clients and the documented compatibility mode keep working.
2. **Same endpoint, same grants.** The MCP endpoint URL, OAuth client registration, scopes
   and workspace grants do not change, so existing client connections and consents survive.
   Only the tool list changes.
3. **One flag, one rollback.** The surface is selected by a single server-side setting per
   environment (the producer story defines it). Rolling back is flipping it, with no data
   migration and no client reconfiguration.
4. **Measure with the harness at every gate.** The task suite and budgets in this directory
   are re-run against that environment's catalog; the verdicts, not the merge, open the gate.

## Pins to establish before stage 1 (all TO ESTABLISH; none were queried here)

The harness baseline used `apache/superset` master `100f51240b` (2026-10-08). That is not a
deployed build. Record, per environment, with evidence (the command or page used):

| Pin | staging | sandbox | production | How to establish (read-only) |
|---|---|---|---|---|
| Superset core version/commit serving MCP | TO ESTABLISH | TO ESTABLISH | TO ESTABLISH | deployed image tag and git SHA; `get_instance_info` is read-only |
| Shell (private Superset distribution) version | TO ESTABLISH | TO ESTABLISH | TO ESTABLISH | release tag in the deploy manifests |
| MCP gateway version | TO ESTABLISH | TO ESTABLISH | TO ESTABLISH | deployed image tag |
| `fastmcp` / `mcp` library versions in the image | TO ESTABLISH | TO ESTABLISH | TO ESTABLISH | image dependency listing; the baseline captured fastmcp 3.4.8 |
| Producer tool surface in use (generic / native) | TO ESTABLISH | TO ESTABLISH | TO ESTABLISH | one `tools/list` per environment by an approved account |
| Workspaces still on an old producer (no named tools) | TO ESTABLISH | TO ESTABLISH | TO ESTABLISH | fleet version inventory from the release owners |

Support matrix to publish once the pins are known: producer version x gateway version x client
(Codex, Claude Code, Claude.ai, ChatGPT/OpenAI) x surface (generic, native eager, native
deferred) with the evidence class (measured/observed/simulated/BLOCKED) in each cell.
`client_matrix.yaml` is the starting point; its BLOCKED rows are the open work.

## Stages

### Stage 0: prerequisites (no environment change)

- SC-125470 and SC-125471 merged, and their PRs reviewed against `waits-on-125470-125471.md`.
- Harness re-pointed from the fixture server to the real producer/gateway test builds
  (`FixtureServer` replaced by a transport to a local build; tasks and budgets unchanged).
- Budget owner decision on the default-visible set: full catalog is 47,834 tokens against a
  10,000 limit, so either a curated core under the limit, deferral, or trimmed definitions.
- Pins above recorded for staging at minimum.

### Stage 1: staging

- Enable named tools alongside the generic surface for a staging workspace set that includes:
  an admin, a read-only role, a revoked grant, a Knowledge-disabled workspace, and one workspace
  on an old producer.
- Entry: stage 0 complete; approval from Amin.
- Checks (the 12-task suite, run against staging with a test account; reads only, writes only
  against a disposable staging workspace with a cleanup ledger):
  B01-B03 within hard limits on the staging catalog; B07, B08 zero; B10 100%; B11 zero leaks;
  B12 100% for native; typed errors for old producer, revoked access and disabled Knowledge.
- Client canaries: Claude Code and Codex first-party runs, both with and without client-side
  deferral, recording prompt tokens and approval behaviour per the matrix. Claude.ai and
  ChatGPT only if Amin provides test accounts.
- Exit: all gating verdicts pass or each failure has an accepted, written waiver; client rows
  upgraded from BLOCKED where a run was possible.
- Rollback: set the surface flag back to generic-only (no client action).

### Stage 2: sandbox

- Same flag on the sandbox environment; preserve existing grants and client connections
  (verify an already-connected client lists the new tools without re-consent).
- Canary: a small set of internal users/workspaces first; watch error rate by typed code
  (`UNSUPPORTED_PRODUCER`, `ACCESS_REVOKED`, `PERMISSION_DENIED`, `FEATURE_DISABLED`),
  `tools/list` size and latency, and the generic-surface call volume (it should fall as clients
  adopt named tools, but must not break).
- Entry: stage 1 exit; approval from Amin.
- Exit: one full week (owner may adjust) with no regression against the stage 1 baselines and
  no isolation finding.
- Rollback: flag flip; confirm clients return to the generic list on their next `tools/list`.

### Stage 3: production

- Entry: stage 2 exit; written approval from Amin for the specific date and scope; marketplace
  evidence and skills updates (SC-125027, SC-119747, SC-105410) ready, with nothing submitted
  without Amin.
- Rollout by workspace cohort, smallest first, generic surface still on.
- Canary checks per cohort before widening: the read-only tasks from the suite using a
  read-only account only (no production writes from this story), budgets B01, B03, B05, B07,
  B10, B11, B12 re-measured, support-ticket and error-code review.
- Rollback: flag flip per cohort or globally; documented in the runbook before the first cohort.
- Default flip (native-first) and any retirement of the generic surface are separate decisions
  after sustained adoption evidence and are **not** part of this story.

## Preserving grants and client connections

- Do not change the endpoint URL, OAuth client IDs, redirect URIs, scopes or workspace grants.
- Clients that pin tool names in allow-lists (for example Claude Code `mcp__server__call_tool`)
  will need the named tools added; ship the updated allow-list guidance with the release notes.
- Walkthroughs and skills that call `search_tools`/`call_tool` must move to named calls
  (SC-125027); keep compatibility-mode instructions for older clients.

## Open items for the owner

- Which environments and cohorts exist, and who can approve each stage.
- Whether SQL execution should count as a read for approval purposes (see baseline finding 5).
- The default-visible core: which operations are always listed.
