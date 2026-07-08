# Security Remediation: Dec 2025 Datadog Credential Exposure

Status as of 2026-07-07. Findings only — no destructive actions have been taken.
Everything in "Proposed" sections requires Amin's explicit go-ahead before execution.

## 1. Current state (verified)

- **Scrubber fix is on `main`.** `testmcpy/scrubber.py` landed in PR #107 (commit
  `9350cb5`, v0.11.7) and is wired into every persistence sink. Confirmed present
  and current-HEAD on `main`.
- **The leaked file is not in the working tree.** No `tests/.results/*` files
  exist in any checkout of `main`.
- **Correction to the incident brief:** the leaked commit is NOT reachable from
  any current branch or tag — it doesn't show up in a normal
  `git log --all --oneline -- 'tests/.results/a897ba10*'` because this worktree
  (and a fresh clone of `preset-io/testmcpy`) only has 104 commits on `main`,
  and `main`'s second commit jumps straight from a Sept 26, 2025 stub
  ("Initial commit: MCP Testing Framework") to a Feb 4, 2026 squash
  ("feat: testmcpy - MCP Testing Framework for LLMs", commit `8bce894`) that
  re-adds the entire project fresh. **Someone already rewrote `main`'s history
  before this session**, discarding the whole Sept 2025–Feb 2026 commit graph,
  including the Dec 2025 incident commits. This was not done as part of this
  remediation effort and predates it.
- **The secret is still recoverable from GitHub anyway.** The old commit chain
  still physically exists in GitHub's backend and is fetchable directly by SHA
  even though no ref points to it:
  ```
  git fetch origin 49c109608ef00680ab0c6532029fe6c680b45533   # succeeds
  git cat-file -t 49c109608ef00680ab0c6532029fe6c680b45533    # -> commit
  git merge-base --is-ancestor 49c1096... main                # -> not an ancestor
  ```
  That commit (authored 2025-12-18T17:01:10Z, not Dec 17 as originally
  reported — a one-day discrepancy in the incident timeline) has tree entries
  including `tests/.results/a897ba10_20251217_181156.json`, which contains the
  real, now-revoked `DD-API-KEY` (`d8269208...`) and `DD-APPLICATION-KEY`
  (`d79a3129...`) in dozens of curl command strings — confirmed by reading the
  blob directly.
  `gh api repos/preset-io/testmcpy/commits/49c1096...` also returns it (200),
  and so does `gh api repos/mseep-ai/testmcpy/commits/49c1096...` for the
  public fork. **This is exactly the mechanism that let the Jul 6, 2026 fork
  re-scan re-surface the blob**: GitHub's fork network shares object storage,
  so unreachable commits from a pre-rewrite state remain fetchable by SHA
  across the whole network (origin + forks) long after a force-push, until
  GitHub purges them server-side. A `git filter-repo` pass on `main` today
  would not by itself fix this, because `main` already doesn't contain the
  commit — the exposure is in dangling/cached objects, not in `main`'s graph.
- **New finding — the real key values are also hardcoded in a *current* file
  on `main`.** PR #107 itself added `unit_tests/test_scrubber.py`, which uses
  the actual leaked values as regression fixtures reproducing the incident
  (`test_dd_headers`, `test_env_api_key_value_scrubbed`, docstring "The Dec
  2025 reproduction"). The keys are revoked, so this isn't a live-credential
  exposure, but it keeps the literal secret strings in the current tree (not
  just history), which secret scanners will keep flagging and which is bad
  hygiene regardless of revocation. **Recommend swapping these two literal
  values for synthetic look-alikes** (same shape/length, not the real former
  key) — the scrubber tests don't need the real value, just something that
  matches the same regex/shape.

## 2. Proposed history-purge plan (NOT executed — needs your decision)

Because `main`'s reachable graph is already clean, a fresh `filter-repo` pass
on `preset-io/testmcpy` is not the actual fix — the remaining exposure is
GitHub-side cached/dangling objects and the external fork. Three independent
actions, can do any subset:

**a) File a GitHub Support "remove sensitive data" request** for
   `preset-io/testmcpy`, citing commit SHA `49c109608ef00680ab0c6532029fe6c680b45533`
   and blob path `tests/.results/a897ba10_20251217_181156.json`. This is
   GitHub's documented process for purging cached views/dangling objects that
   survive a history rewrite — it's the only way to make the object actually
   stop being fetchable by SHA. Low risk, no coordination needed, doesn't
   touch `main`.

**b) Report the fork.** `mseep-ai/testmcpy` is a public fork; we don't have
   write access to force-push its history. Options: ask GitHub Support to
   include fork-network cache purging in the same request (a), and/or file a
   direct request to GitHub Trust & Safety if the fork's copy needs separate
   handling. We cannot unilaterally rewrite someone else's fork.

**c) Optional extra hygiene: `git filter-repo` on `preset-io/testmcpy` `main`**
   to strip any `tests/.results/*.json` blobs that might still be reachable
   from *other* branches/tags/PR-head refs we haven't checked individually
   (this audit only confirmed `main` is clean). This would be a coordinated,
   disruptive rewrite (new commit SHAs, force-push, everyone re-clones) and
   should only be done if (a) further investigation turns up the secret
   reachable from some other live ref. **Do not run this without checking
   first** — I have not yet enumerated every branch/PR-head ref for the file;
   I only confirmed `main`. Happy to do that enumeration next if useful.

I have not run `filter-repo`, contacted GitHub Support, or contacted the fork
owner. Awaiting your call on (a)/(b)/(c) and on the test-fixture swap above.

## 3. Defense in depth (proposed, not applied)

**`.gitignore` is already correct.** `tests/` is blanket-ignored (`tests/` +
`!tests/.gitkeep`, added Feb 4, 2026 in commit `8bce894`, originally added as
`b0d1b02 chore: gitignore tests folder contents, keep .gitkeep` in the
pre-rewrite history shortly after the incident). This covers
`.results/`, `.smoke_reports/`, and `.generation_logs/` today. It did **not**
cover them at the time of the Dec 17, 2025 leak — the leaked file predates
that gitignore entry, which is consistent with the incident timeline.

Gaps: nothing currently stops a `git add -f` from re-committing a results
file, and there's no secret-scanning CI job (checked `.github/workflows/*.yml`
— `ci.yml`, `deploy-docs.yml`, `docs-pr-check.yml`, `publish.yml`, none scan
for secrets). Proposed additions:

1. **Pre-commit hook** (`.pre-commit-config.yaml`, local hook like the
   existing `no-preset-infra-urls`): reject any staged path under
   `tests/.results/`, `tests/.smoke_reports/`, `tests/.generation_logs/`,
   regardless of `.gitignore` (defends against `-f`).
2. **gitleaks pre-commit hook** (`gitleaks/gitleaks` mirror,
   `id: gitleaks`) for a local secret-scan safety net on every commit.
3. **CI job** in `ci.yml` (or a new workflow) running `gitleaks/gitleaks-action`
   on PR diffs, so a secret slipping past pre-commit (e.g. someone without
   hooks installed) still gets caught before merge.

Not yet applied — say the word and I'll wire these up.

## 4. Full-history secret audit (gitleaks v8.21.2, `--log-opts="--all"`, 632 commits scanned)

30 raw findings / 17 unique (file, line) locations. Full breakdown, each
verified by reading the actual line in context:

| File:Line | Rule | Verdict |
|---|---|---|
| `unit_tests/test_scrubber.py:112,113,148,149` | generic-api-key | **Real** — the already-revoked Dec 2025 DD-API-KEY/DD-APPLICATION-KEY, kept intentionally as regression-test fixtures (see §1 recommendation to swap for synthetic values) |
| `unit_tests/test_scrubber.py:134,170` | generic-api-key | Fake — synthetic `jwt_secret` test value (`a259c6ece3506e98c6be...`), invented for a field-name-masking unit test, unrelated to any real credential |
| `unit_tests/test_scrubber.py:120,156` | private-key | Fake — literal test fixture `"-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nlines\n-----END..."`, placeholder body ("lines"), not a real key |
| `context/archives/AUTH_FLOW_DIAGRAM.md:172,188` | generic-api-key | Fake — doc example, literally truncated (`eyJhbGciOiJIUzI1NiI...12345678`) |
| `context/concepts/authentication.md:205` | generic-api-key | Fake — same doc example, mirrored from the archive |
| `docs-site/pages/concepts/authentication.mdx:214` | generic-api-key | Fake — same doc example, mirrored into the docs site |
| `examples/auth_evaluators_example.py:29` | generic-api-key | Fake — example script, value ends in literal `"..."` |
| `unit_tests/test_advanced_auth.py:536` | generic-api-key | Fake — `TEST_API_KEY_12345` env var name + `"env-secret-key"` placeholder value |
| `unit_tests/test_evaluators_advanced.py:158` | generic-api-key | Fake — `sk-abcdefghijklmnop1234567890`, sequential-alphabet placeholder |
| `unit_tests/test_hardening.py:65` | generic-api-key | Fake — `sk-live-abcdef123456789`, sequential placeholder |
| `integration_tests/e2e/test_thorough.py:403` (historical, deleted from tree; commit `3b9dc98`) | jwt | Fake — the universally-known jwt.io tutorial example token ("John Doe", `sub: 1234567890`) |

**Conclusion: no additional real secrets found in history beyond the two
already-known, already-revoked Datadog keys.** Everything else is
intentionally-fake test/doc fixture data.

## Open questions for Amin

1. Which of §2's (a)/(b)/(c) do you want to pursue, and in what order?
2. OK to swap the real (revoked) key values in `unit_tests/test_scrubber.py`
   for synthetic look-alikes?
3. OK to add the pre-commit hook + gitleaks pre-commit + CI job from §3?
4. Want me to enumerate every branch/PR-head ref (not just `main`) to confirm
   none of them reintroduce `tests/.results/*` before deciding on §2(c)?
