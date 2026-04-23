# testmcpy × Agor Integration Plan

**Date:** 2026-04-23  
**Worktree:** testmcpy-agor-integration  
**Goal:** Make testmcpy a first-class citizen on the Agor board alongside superset-shell, manager, and apache/superset.

---

## Codebase Summary

testmcpy is a Python CLI + React web UI for testing MCP server tool-calling quality. Key facts for integration:

- **Install:** `pip install 'testmcpy[server]'` (FastAPI + React frontend)
- **Web UI:** `testmcpy serve --host 0.0.0.0 --port 8000 --no-browser` → port 8000
- **Dockerfile:** Already exists — multi-stage Node (frontend) + Python 3.11-slim. Exposes 8000, health at `/health`, volume `/app/.testmcpy`
- **MCP config:** `.mcp_services.yaml` in working dir, supports `${ENV_VAR}` substitution, `auth.type: none` works for unauthenticated local servers
- **LLM config:** `.llm_providers.yaml` — needs `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- **No docker-compose.yml exists yet** — needs to be created
- **DB:** SQLite at `TESTMCPY_DB_PATH=/app/.testmcpy/storage.db`, persisted via Docker volume

---

## a) Agor Environment Config for testmcpy

### Port Assignment

Agor port conventions already in use:
- superset-shell worktrees: `5100 + worktree.unique_id`
- apache/superset (`with-mcp`): `9200 + worktree.unique_id`

**Proposed for testmcpy:** `7100 + worktree.unique_id`

This gives port 7100 for the first testmcpy worktree, 7101 for a second, etc. No overlap with other services.

### Environment Config (to register in Agor via `agor_execute_tool`)

```json
{
  "start": "PORT={{add 7100 worktree.unique_id}} MCP_SERVER_URL=${MCP_SERVER_URL} docker compose up -d --build",
  "stop": "docker compose down",
  "health": "curl -sf http://localhost:{{add 7100 worktree.unique_id}}/health",
  "logs": "docker compose logs -f"
}
```

The `MCP_SERVER_URL` env var is the only required runtime secret — it points at whichever Superset MCP endpoint is under test. See section (b) for how to set it.

### Required Env Vars at Start Time

| Variable | Example Value | Purpose |
|---|---|---|
| `MCP_SERVER_URL` | `http://10.0.0.1:5100/api/mcp/` | Target Superset MCP endpoint |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | LLM for test evaluation |
| `PORT` | `7100` | testmcpy web UI port (set by Agor via template) |

Optional:
| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | If using GPT models instead of Claude |
| `TESTMCPY_DB_PATH` | `/app/.testmcpy/storage.db` | Override DB location |

---

## b) Workflow Integration

### Deployment Model: One Persistent testmcpy Worktree

**Recommendation:** A single persistent testmcpy worktree on the board. Developers point it at different MCP targets by profile — either by editing `MCP_SERVER_URL` before restarting, or by selecting a profile in the web UI's `/mcp-profiles` page.

**Why not per-test-run?** The web UI's `/reports`, `/metrics`, and baseline tracking are most valuable when results accumulate over time in one place. Ephemeral containers lose history.

### Typical Developer Workflow

```
1. Developer is working on a superset-shell worktree (e.g. unique_id=2 → MCP port 5102)
2. In Agor terminal or via the board, set:
     export MCP_SERVER_URL=http://localhost:5102/api/mcp/
3. Restart testmcpy (or just select the "local-agor" profile in web UI if pre-configured)
4. Open testmcpy UI at http://board-host:7100
5. Run tests/explore tools/chat against that MCP server
6. Check /reports for pass/fail, /metrics for latency
```

### Multi-Profile Approach (longer-term)

The `.mcp_services.yaml` baked into the image can define named profiles for all known MCP targets:

```yaml
default: local

profiles:
  local:
    name: Local Agor MCP
    mcps:
      - name: Local MCP
        mcp_url: ${MCP_SERVER_URL}
        auth:
          type: none

  sandbox:
    name: Preset Sandbox
    mcps:
      - name: Preset Sandbox
        mcp_url: https://your-workspace.us1a.app-sdx.preset.io/mcp
        auth:
          type: jwt
          api_url: https://api.app-sdx.preset.io/v1/auth/
          api_token: ${SANDBOX_API_TOKEN}
          api_secret: ${SANDBOX_API_SECRET}

  staging:
    name: Preset Staging
    mcps:
      - name: Preset Staging
        mcp_url: https://your-workspace.us1a.app-stg.preset.io/mcp
        auth:
          type: jwt
          api_url: https://api.app-stg.preset.io/v1/auth/
          api_token: ${STAGING_API_TOKEN}
          api_secret: ${STAGING_API_SECRET}
```

Developers select profile via `--profile local` CLI flag or in web UI.

### Targeting superset-shell vs apache/superset Worktrees

| Worktree type | MCP port formula | Example MCP_SERVER_URL |
|---|---|---|
| superset-shell (unique_id=N) | `5100 + N` | `http://HOST_IP:5100/api/mcp/` |
| apache/superset with-mcp (unique_id=N) | `9200 + N` | `http://HOST_IP:9200/api/mcp/` |

The `HOST_IP` is the server's internal IP (accessible to all worktrees on the same host). Since testmcpy runs in Docker, use the actual host IP (not `localhost` which would resolve inside the container).

**Tip:** Use Docker's `--add-host=host.docker.internal:host-gateway` in docker-compose.yml so the container can reach other services via `host.docker.internal:<port>`.

---

## c) docker-compose.yml (Missing — Must Be Created)

The Dockerfile exists but no compose file. Create `docker-compose.yml` in the repo root:

```yaml
# docker-compose.yml
services:
  testmcpy:
    build: .
    image: testmcpy:latest
    ports:
      - "${PORT:-7100}:8000"
    extra_hosts:
      - "host.docker.internal:host-gateway"   # reach other Agor worktrees
    volumes:
      - testmcpy-data:/app/.testmcpy
      - ./mcp_services.yaml:/app/.mcp_services.yaml:ro     # mount config
      - ./llm_providers.yaml:/app/.llm_providers.yaml:ro   # mount config
    environment:
      - TESTMCPY_DB_PATH=/app/.testmcpy/storage.db
      - MCP_SERVER_URL=${MCP_SERVER_URL:-http://host.docker.internal:5100/api/mcp/}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - SANDBOX_API_TOKEN=${SANDBOX_API_TOKEN:-}
      - SANDBOX_API_SECRET=${SANDBOX_API_SECRET:-}
      - STAGING_API_TOKEN=${STAGING_API_TOKEN:-}
      - STAGING_API_SECRET=${STAGING_API_SECRET:-}
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      start_period: 15s
      retries: 3
    restart: unless-stopped

volumes:
  testmcpy-data:
```

Key design choices:
- `extra_hosts: host.docker.internal` — lets the container reach other Agor worktrees at `host.docker.internal:<port>`
- Config files (`mcp_services.yaml`, `llm_providers.yaml`) are mounted from the worktree, not baked into image — easy to edit without rebuild
- `PORT` env var controls the host-side port via the Agor `{{add 7100 worktree.unique_id}}` template

The `.mcp_services.yaml` and `.llm_providers.yaml` shipped in the repo (not the `.example` files, but real defaults) will serve as the mounted configs, with all secrets coming from env vars.

### Config Files to Add to Repo

**`mcp_services.yaml`** (committed, safe — no secrets, uses `${VAR}` references):
```yaml
default: local

profiles:
  local:
    name: Local Agor MCP
    mcps:
      - name: Local Agor MCP Server
        mcp_url: ${MCP_SERVER_URL}
        auth:
          type: none

  sandbox:
    name: Preset Sandbox
    mcps:
      - name: Preset Sandbox
        mcp_url: https://your-workspace.us1a.app-sdx.preset.io/mcp
        auth:
          type: jwt
          api_url: https://api.app-sdx.preset.io/v1/auth/
          api_token: ${SANDBOX_API_TOKEN}
          api_secret: ${SANDBOX_API_SECRET}

  staging:
    name: Preset Staging
    mcps:
      - name: Preset Staging
        mcp_url: https://your-workspace.us1a.app-stg.preset.io/mcp
        auth:
          type: jwt
          api_url: https://api.app-stg.preset.io/v1/auth/
          api_token: ${STAGING_API_TOKEN}
          api_secret: ${STAGING_API_SECRET}

global:
  timeout: 30
  rate_limit:
    requests_per_minute: 60
```

**`llm_providers.yaml`** (committed, safe — API key from env var):
```yaml
default: default

profiles:
  default:
    name: Default
    providers:
      - name: Claude Sonnet
        provider: anthropic
        model: claude-sonnet-4-6
        api_key_env: ANTHROPIC_API_KEY
        timeout: 60
        default: true
      - name: Claude Haiku
        provider: anthropic
        model: claude-haiku-4-5
        api_key_env: ANTHROPIC_API_KEY
        timeout: 30
```

---

## d) preset-dev Plugin Integration

### Assessment: Extend `/preset-dev:evals`, Don't Replace It

The existing `/preset-dev:evals` runs the full 284-test MCP + Chatbot eval suite against a staging workspace (cloud Preset). testmcpy is complementary — it tests local Agor worktrees or specific Preset environments interactively.

**Proposed changes to the `preset-dev` plugin:**

#### Option 1 (Recommended): Add `/preset-dev:testmcpy` command

A new command `commands/testmcpy.md` that:
1. Detects the current superset-shell or apache/superset worktree's MCP port
2. Opens the testmcpy web UI URL in the description
3. Provides a quick `testmcpy run` invocation pattern for CLI-based CI use

```markdown
---
description: Run testmcpy MCP tests against the current worktree's MCP server
argument-hint: "[--profile local|sandbox|staging] [tests/path]"
---

# /preset-dev:testmcpy

Points testmcpy at the current worktree's MCP server and runs tests.

...
```

#### Option 2: Document it in `/preset-dev:evals`

Add a section to the existing `commands/evals.md` noting that testmcpy is available for local/interactive MCP testing, pointing at the testmcpy worktree URL on the board.

Option 1 is cleaner — separate command, separate purpose.

---

## e) Concrete Next Steps

### Step 1 — Create `docker-compose.yml` (Small)
**File:** `docker-compose.yml` (new)  
Create the compose file as specified in section (c). This is the most critical blocker — Agor's environment system needs a compose file to start/stop the service.

### Step 2 — Add default config files (Small)
**Files:** `mcp_services.yaml`, `llm_providers.yaml` (new, committed)  
Create the non-secret config files as shown in section (c). These are safe to commit because all credentials use `${VAR}` substitution.

Update `.gitignore` to ensure `.env` stays excluded but `mcp_services.yaml` and `llm_providers.yaml` are tracked.

### Step 3 — Register testmcpy in Agor (Small — Agor config, not code)
Via `agor_execute_tool` → `agor_worktrees_create` or `agor_worktrees_update`:
- Repo: `preset-io/testmcpy`
- Board: Amin's board
- Environment config:
  ```json
  {
    "start": "PORT={{add 7100 worktree.unique_id}} MCP_SERVER_URL=${MCP_SERVER_URL:-http://host.docker.internal:5100/api/mcp/} docker compose up -d --build",
    "stop": "docker compose down",
    "health": "curl -sf http://localhost:{{add 7100 worktree.unique_id}}/health",
    "logs": "docker compose logs -f"
  }
  ```
- Required env vars to configure in Agor: `ANTHROPIC_API_KEY`, `MCP_SERVER_URL`

### Step 4 — Verify Docker build works in Agor environment (Small)
Manually run `docker compose up --build` in the testmcpy worktree, confirm:
- Build succeeds
- `http://localhost:7100/health` returns 200
- Web UI loads at `http://localhost:7100`
- `/mcp-profiles` page shows "Local Agor MCP" profile
- Tools are discoverable when `MCP_SERVER_URL` points at a running superset-shell worktree

### Step 5 — Add `/preset-dev:testmcpy` command to preset-claude (Medium)
**File:** `/home/agorpg/.agor/repos/preset-claude/plugins/preset-dev/commands/testmcpy.md` (new)

The command should:
1. Detect current branch's worktree type (superset-shell → port 5100+id, apache/superset → port 9200+id)
2. Show how to point testmcpy at it
3. Provide a `testmcpy run` invocation for CLI-based smoke testing
4. Link to the testmcpy board URL

### Step 6 — (Optional) Add test suites for superset-shell MCP (Medium)
Create `tests/` directory in the testmcpy repo with YAML test suites covering:
- Core Superset MCP tools (`list_datasets`, `execute_sql`, `list_dashboards`, etc.)
- Auth flow validation
- Latency thresholds

These become the standard "does this MCP server work?" test suite run as part of deploy validation.

---

## Summary Table

| Step | File(s) | Scope | Blocker? |
|---|---|---|---|
| 1. docker-compose.yml | `docker-compose.yml` | Small | Yes — needed for Agor env |
| 2. Default config files | `mcp_services.yaml`, `llm_providers.yaml` | Small | Yes — needed for Docker mount |
| 3. Register in Agor | Agor API call | Small | No code changes |
| 4. Verify Docker build | Manual test | Small | Gates step 3 |
| 5. preset-dev command | `commands/testmcpy.md` | Medium | No — nice to have |
| 6. Test suites | `tests/*.yaml` | Medium | No — enhances value |

**Minimum viable integration:** Steps 1–4. Steps 5–6 add workflow polish.
