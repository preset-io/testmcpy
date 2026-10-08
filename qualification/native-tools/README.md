# Native-tool qualification (SC-125472)

Harness, pre-registered budgets, fixtures, raw traffic and reports for qualifying the
move from the generic `search_tools` / `call_tool` compatibility surface to native named
MCP tools. Story: https://app.shortcut.com/preset/story/125472. Producer:
https://app.shortcut.com/preset/story/125470. Gateway:
https://app.shortcut.com/preset/story/125471.

Phase 1 (this directory) is the harness and the baseline. It is **not** the go/no-go: that
needs the producer and gateway code (see `waits-on-125470-125471.md`).

## Read first

| File | What it is |
|---|---|
| `reports/baseline-summary.md` | findings, deltas, verdicts, limits |
| `reports/baseline-results.md` | every table, generated |
| `budgets.yaml` | 12 budgets, committed before any measurement; append-only `amendments` |
| `client_matrix.yaml` | versioned client matrix; BLOCKED rows state why |
| `rollout-plan.md` | staged rollout draft (staging, sandbox, production), pins to establish |
| `waits-on-125470-125471.md` | what cannot finish before the producer and gateway PRs |

## Evidence classes

Every number is `measured` (local fixtures or a real local Superset app), `observed (client)`
(a real client binary driven against the fixtures), `simulated` (an explicit policy or cost model)
or `BLOCKED` (not run; reason recorded). Nothing is inferred from vendor documentation, and
annotations are never assumed to override a client's approval policy.

## Layout

- `tasks.yaml`: the 12-task suite, identical across surfaces.
- `fixtures/`: the real Superset catalog (tools, output schemas and real search responses split to stay
  reviewable) and the gateway generic tool definitions.
- `capture/`: scripts that produced the fixtures and real-app probes
  (`capture_superset_catalog.py`, `probe_superset_fidelity.py`, `clients/`).
- `traffic/`: raw JSON-RPC per task and surface (`fixture/`), real-app fidelity probes, and sanitised real-client
  runs (`clients/`). `tools/list` bodies are stored as name, annotations and a schema digest that is checked
  against the catalog fixture.
- `results/results.json`: machine-readable results of the last run.

## Run

```bash
pip install -e ".[dev,server]"
python -m testmcpy.qualification run                 # all surfaces, both catalogs; writes results + reports
python -m testmcpy.qualification serve --surface native_eager --port 8802   # a fixture for a real client
pytest unit_tests/test_qualification_harness.py
```

The fixture server authenticates with `Authorization: Bearer fixture:<principal>[:<workspace>]`
(principals `alice` admin, `bob` read-only, `carol` revoked from `ws-b`, `dave` writer). It never contacts a
network service; writes go to an in-memory ledger.

## Refresh the real catalog

Inside a Superset checkout with its virtualenv and an initialised metadata DB:

```bash
SUPERSET_CONFIG_PATH=... PYTHONPATH=. python capture/capture_superset_catalog.py \
  --superset-sha <sha> --tasks tasks.yaml --out fixtures/<...>.json \
  --out-output-schemas fixtures/<...>.output-schemas.json --out-search-responses fixtures/<...>.search-responses.json
```

It talks to the in-memory FastMCP app only (metadata and read-only searches).

## Real clients

`capture/clients/run_claude_code.sh` and `run_codex.sh` drive the real CLIs against a local fixture with
isolated config, using `OPENROUTER_API_KEY` from the environment (never stored). Without a first-party
key or login these runs describe the OpenRouter route, not first-party behaviour. Never point them at a
production workspace.
