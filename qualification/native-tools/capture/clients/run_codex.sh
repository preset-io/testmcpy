#!/usr/bin/env bash
# Drive a real Codex CLI (`codex exec`) against a LOCAL qualification fixture server.
#
#   usage: run_codex.sh <port> <fixture-bearer-token> <out.jsonl> <prompt> [model]
#   env:   APPROVE=',default_tools_approval_mode="approve"'  pre-approves the fixture's tools
#
# Isolation: an empty CODEX_HOME (the stored interactive login is never read), read-only
# sandbox, no repository. Model traffic goes through OpenRouter's Responses API with
# OPENROUTER_API_KEY (never written to disk); Codex has no model metadata for that route's
# model ids and falls back, so tool-search behaviour here is NOT what a ChatGPT-login Codex
# session would show.
set -uo pipefail
port=$1; tok=$2; out=$3; prompt=$4; model=${5:-openai/gpt-5-mini}
work=${QUAL_WORK:-/tmp/qual}
mkdir -p "$work/codex-work" "$work/codex-home"
cd "$work/codex-work"
export CODEX_HOME="$work/codex-home" FIXTURE_TOKEN="$tok"
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
timeout 300 codex exec --json --skip-git-repo-check --ephemeral --sandbox read-only -m "$model" \
  -c 'model_provider="openrouter"' \
  -c 'model_providers.openrouter={name="OpenRouter",base_url="https://openrouter.ai/api/v1",env_key="OPENROUTER_API_KEY",wire_api="responses"}' \
  -c "mcp_servers.fixture={url=\"http://127.0.0.1:$port/mcp\",bearer_token_env_var=\"FIXTURE_TOKEN\"${APPROVE:-}}" \
  "$prompt" < /dev/null > "$out" 2> "$out.err"
echo "rc=$?"
