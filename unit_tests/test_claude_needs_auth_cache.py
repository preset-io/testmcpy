"""Tests for ClaudeSDKProvider's eviction of the Claude CLI's per-server
needs-auth cache.

Regression: the CLI caches a "needs OAuth authorization" flag keyed by MCP
server name. Once our fixed name ``mcp-service`` lands in it, the CLI skips
connecting to the server on every run — ignoring the Authorization header we
pass — so zero MCP tools load and every tool-based test fails until the cache
is cleared. The provider drops just its own entry before each run.
"""

import json

from testmcpy.src.llm_integration import ClaudeSDKProvider

NAME = ClaudeSDKProvider._MCP_SERVER_NAME


def _write_cache(path, data):
    path.write_text(json.dumps(data))


def test_evicts_only_our_entry(tmp_path):
    cache = tmp_path / "mcp-needs-auth-cache.json"
    _write_cache(
        cache,
        {
            NAME: {"timestamp": 123},
            "claude.ai preset stg": {"timestamp": 456, "id": "mcpsrv_x"},
        },
    )
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}

    removed = ClaudeSDKProvider._evict_needs_auth_cache_entry(env)

    assert removed is True
    remaining = json.loads(cache.read_text())
    assert NAME not in remaining
    # Other servers' state is preserved untouched.
    assert remaining == {"claude.ai preset stg": {"timestamp": 456, "id": "mcpsrv_x"}}


def test_noop_when_our_entry_absent(tmp_path):
    cache = tmp_path / "mcp-needs-auth-cache.json"
    _write_cache(cache, {"claude.ai preset stg": {"timestamp": 456}})
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}

    removed = ClaudeSDKProvider._evict_needs_auth_cache_entry(env)

    assert removed is False
    # File is left exactly as-is.
    assert json.loads(cache.read_text()) == {"claude.ai preset stg": {"timestamp": 456}}


def test_missing_file_is_safe(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}  # no cache file present
    assert ClaudeSDKProvider._evict_needs_auth_cache_entry(env) is False


def test_corrupt_cache_is_safe(tmp_path):
    cache = tmp_path / "mcp-needs-auth-cache.json"
    cache.write_text("{not valid json")
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}

    # Must not raise on a malformed cache — just report nothing removed.
    assert ClaudeSDKProvider._evict_needs_auth_cache_entry(env) is False


def test_path_honors_config_dir_override(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}
    assert ClaudeSDKProvider._needs_auth_cache_path(env) == (tmp_path / "mcp-needs-auth-cache.json")


def test_path_defaults_to_home_claude(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    p = ClaudeSDKProvider._needs_auth_cache_path({})
    assert p.name == "mcp-needs-auth-cache.json"
    assert p.parent.name == ".claude"
