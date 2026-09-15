# Stage 1: Build React frontend
FROM node:20-slim AS frontend
WORKDIR /app/testmcpy/ui
COPY testmcpy/ui/package*.json ./
RUN npm ci --no-audit --no-fund
COPY testmcpy/ui/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Optionally bake the Claude Code CLI into the image so `docker exec
# <container> claude` works without a per-container install.
#
# Agentic-path overview (read this before changing anything below):
#   - The Python SDK (`claude-agent-sdk` package) is in the `server`
#     extra (pyproject.toml) — so it's ALWAYS installed in this image
#     by the `pip install .[server]` step below.
#   - The SDK's wheel already BUNDLES a platform-appropriate `claude`
#     binary at `claude_agent_sdk/_bundled/claude` (~250 MB on linux
#     x86_64). The SDK's CLI lookup (`SubprocessCLITransport._find_cli`
#     in claude_agent_sdk/_internal/transport/subprocess_cli.py)
#     finds the bundled copy FIRST before falling back to PATH, so
#     agentic tests run end-to-end out of the box — no separate CLI
#     install required.
#   - INSTALL_CLAUDE_CLI=true (this layer, below) is for the SEPARATE
#     use case of `docker exec <container> claude` direct CLI use, or
#     for pinning a specific Claude Code version that differs from
#     whatever the SDK currently bundles. It is NOT required for
#     agentic tests to run.
#
# Opt in with:
#
#     docker compose build --build-arg INSTALL_CLAUDE_CLI=true
#
# Pin a specific version for reproducibility (recommended for shared
# images — install.sh otherwise floats `latest` and the same source
# SHA can produce different binaries weeks apart):
#
#     docker compose build \
#         --build-arg INSTALL_CLAUDE_CLI=true \
#         --build-arg CLAUDE_CLI_VERSION=2.1.170
#
# Trust model: this image pipes the install script from claude.ai
# directly into a shell — `curl … | bash`. There's no upstream
# checksum / signature for the standalone installer to pin against
# today. Acceptable for an opt-in dev image built by the user that
# already runs as root inside the container; not appropriate for a
# zero-trust supply chain. Pin the version above so the surface a
# compromised installer could affect is bounded.
#
# We use the native installer because the slim base has no Node.js;
# `npm install -g @anthropic-ai/claude-code` would pull the entire
# Node toolchain. The installer drops the binary at
# /root/.local/bin/claude which isn't on the default `docker exec`
# PATH — symlink to /usr/local/bin/claude so it's discoverable. Layer
# is placed right after curl so it shares the cache with the apt-get
# step and is NOT invalidated by source changes below.
#
# `SHELL ["/bin/bash", "-o", "pipefail", "-c"]` makes `curl | bash`
# fail the build if curl itself fails (default `/bin/sh -c` uses the
# pipeline tail's exit status; a 5xx from claude.ai would otherwise
# let curl fail silently and the build proceed to a dangling symlink).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG INSTALL_CLAUDE_CLI=false
ARG CLAUDE_CLI_VERSION=""
RUN if [ "$INSTALL_CLAUDE_CLI" = "true" ]; then \
        curl -fsSL https://claude.ai/install.sh | bash && \
        if [ -n "$CLAUDE_CLI_VERSION" ]; then \
            /root/.local/bin/claude install "$CLAUDE_CLI_VERSION"; \
        fi && \
        ln -sf /root/.local/bin/claude /usr/local/bin/claude && \
        claude --version; \
    fi

# Optionally bake the Codex CLI into the image for `codex auth login` and
# direct CLI use inside the container.
#
# CodexSDKProvider (openai-agents Python SDK) does NOT require the Codex CLI
# to be installed — it calls the OpenAI API directly. This layer is only
# needed when you want `codex auth login` OAuth inside the container so that
# ~/.codex/auth.json is available for CodexSDKProvider to pick up.
#
# Requires Node.js (~80 MB extra). Opt in with:
#
#     docker compose build --build-arg INSTALL_CODEX_CLI=true
#
# Pin a specific version for reproducibility:
#
#     docker compose build \
#         --build-arg INSTALL_CODEX_CLI=true \
#         --build-arg CODEX_CLI_VERSION=0.1.2
#
ARG INSTALL_CODEX_CLI=false
ARG CODEX_CLI_VERSION=""
RUN if [ "$INSTALL_CODEX_CLI" = "true" ]; then \
        curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
        apt-get install -y --no-install-recommends nodejs && \
        rm -rf /var/lib/apt/lists/* && \
        if [ -n "$CODEX_CLI_VERSION" ]; then \
            npm install -g "@openai/codex@${CODEX_CLI_VERSION}"; \
        else \
            npm install -g @openai/codex; \
        fi && \
        codex --version; \
    fi

# Install Python dependencies
COPY pyproject.toml .
COPY testmcpy/ testmcpy/
COPY oauth-probe/testmcpy_oauth_probe/ oauth-probe/testmcpy_oauth_probe/
# Copy built frontend before pip install so it's included in package data
COPY --from=frontend /app/testmcpy/ui/dist testmcpy/ui/dist
RUN pip install --no-cache-dir ".[server]"
# Wheel installation gives packaged UI sources fresh mtimes, which can make the
# already-built bundle look stale to the source-checkout guard. Mark the bundle
# as the final build output so the slim runtime never needs Node.js to start.
RUN python -c "import site; from pathlib import Path; roots = [Path('/app/testmcpy'), *(Path(p) / 'testmcpy' for p in site.getsitepackages())]; [f.touch() for root in roots for f in (root / 'ui' / 'dist').rglob('*') if f.is_file()]"

# Create data directory for persistent storage
RUN mkdir -p /app/.testmcpy

# Default environment variables
ENV TESTMCPY_DB_PATH=/app/.testmcpy/storage.db

# Volume for persistent data (database, configs)
VOLUME /app/.testmcpy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["testmcpy", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
