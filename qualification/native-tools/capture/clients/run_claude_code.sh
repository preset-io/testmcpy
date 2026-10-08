#!/usr/bin/env bash
# Drive a real Claude Code CLI against a LOCAL qualification fixture server.
#
#   usage: run_claude_code.sh <mcp-config.json> <out.jsonl> <prompt> [extra claude args...]
#
# Isolation: a fresh CLAUDE_CONFIG_DIR (no user memory, plugins or hooks), --strict-mcp-config
# (only the fixture), project-only settings. Model traffic goes to whatever endpoint the
# environment configures; the runs recorded in this repo used OpenRouter's Anthropic-compatible
# endpoint with OPENROUTER_API_KEY (never written to disk) because no first-party Anthropic key
# or login exists in the qualification environment. That is a route, not first-party behaviour.
# Start fixtures first:  python -m testmcpy.qualification serve --surface generic --port 8801
set -uo pipefail
cfg=$1; out=$2; prompt=$3; shift 3
work=${QUAL_WORK:-/tmp/qual}
mkdir -p "$work/work" "$work/cc-home"
cd "$work/work"
export CLAUDE_CONFIG_DIR="$work/cc-home"
export ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-https://openrouter.ai/api}
export ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN:-${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY or ANTHROPIC_AUTH_TOKEN}}
unset ANTHROPIC_API_KEY
export DISABLE_TELEMETRY=1 DISABLE_AUTOUPDATER=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
timeout 300 claude -p "$prompt" --mcp-config "$cfg" --strict-mcp-config --setting-sources project \
  --disable-slash-commands --no-session-persistence --model "${CC_MODEL:-anthropic/claude-haiku-4.5}" \
  --max-budget-usd 1.5 --output-format stream-json --verbose "$@" < /dev/null > "$out" 2> "$out.err"
echo "rc=$?"
