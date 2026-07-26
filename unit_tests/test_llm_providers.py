"""
Integration tests for the LLM provider factory and tool call parsing.

Tests cover:
- Provider factory (create_llm_provider) — instantiation without API calls
- LLMResult dataclass creation and field access
- Evaluator factory (create_evaluator) — instantiation and evaluation
- Tool name matching (_match_tool_name)
- New evaluators: response_not_includes, no_leaked_data, url_is_valid,
  success_rate_above, latency_percentile, response_matches_pattern
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testmcpy.evals.base_evaluators import _match_tool_name, create_evaluator
from testmcpy.src.llm_integration import (
    AnthropicProvider,
    AssistantProvider,
    ClaudeSDKProvider,
    CodexSDKProvider,
    GeminiProvider,
    GeminiSDKProvider,
    LLMResult,
    OpenAIProvider,
    OpenRouterProvider,
    _InsecureMCPProxy,
    _SSEStreamState,
    create_llm_provider,
)

# ---------------------------------------------------------------------------
# Provider Factory Tests
# ---------------------------------------------------------------------------


class TestProviderFactory:
    def test_create_anthropic_provider(self):
        provider = create_llm_provider("anthropic", "claude-haiku-4-5", api_key="test")
        assert isinstance(provider, AnthropicProvider)

    def test_create_openai_provider(self):
        provider = create_llm_provider("openai", "gpt-4o", api_key="test")
        assert isinstance(provider, OpenAIProvider)

    def test_create_assistant_provider(self):
        provider = create_llm_provider(
            "assistant",
            "default",
            workspace_hash="test",
            domain="test.com",
            conversations_path="/api/v1/copilot/conversations",
            completions_path="/api/v1/copilot/completions",
        )
        assert isinstance(provider, AssistantProvider)

    def test_create_openrouter_provider(self):
        provider = create_llm_provider("openrouter", "anthropic/claude-haiku-4-5", api_key="test")
        assert isinstance(provider, OpenRouterProvider)

    def test_create_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            create_llm_provider("nonexistent", "model")

    def test_provider_aliases(self):
        # claude-cli, claude-code should map to ClaudeSDKProvider
        p1 = create_llm_provider("claude-cli", "claude-sonnet-4-20250514")
        p2 = create_llm_provider("claude-code", "claude-sonnet-4-20250514")
        assert type(p1).__name__ == "ClaudeSDKProvider"
        assert type(p2).__name__ == "ClaudeSDKProvider"

    def test_claude_sdk_receives_mcp_url_and_auth(self):
        auth = {"type": "bearer", "token": "t"}
        provider = create_llm_provider(
            "claude-sdk", "claude-sonnet-4-6", mcp_url="http://u/mcp", auth=auth
        )
        assert provider.mcp_url == "http://u/mcp"
        assert provider.auth_config == auth

    def test_anthropic_receives_mcp_url_and_auth(self):
        auth = {"type": "bearer", "token": "t"}
        provider = create_llm_provider(
            "anthropic", "claude-haiku-4-5", api_key="test", mcp_url="http://u/mcp", auth=auth
        )
        assert provider.tool_discovery.mcp_url == "http://u/mcp"

    def test_unsupported_mcp_kwargs_filtered(self):
        # Providers that don't accept mcp_url/auth must not blow up — the
        # factory filters kwargs by each provider's __init__ signature.
        provider = create_llm_provider(
            "openai", "gpt-4o", api_key="test", mcp_url="http://u/mcp", auth={"type": "none"}
        )
        assert isinstance(provider, OpenAIProvider)


# ---------------------------------------------------------------------------
# ClaudeSDKProvider OAuth Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_claude_sdk_module(monkeypatch):
    """Stub claude_agent_sdk so .initialize() doesn't require the real package."""
    import sys
    import types

    # Provide just enough surface for ClaudeSDKProvider.initialize().
    fake_pkg = types.ModuleType("claude_agent_sdk")
    fake_pkg.CLINotFoundError = type("CLINotFoundError", (Exception,), {})
    fake_types = types.ModuleType("claude_agent_sdk.types")
    fake_types.McpHttpServerConfig = dict  # used as a type alias only
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_pkg)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_types)
    return fake_pkg


class TestClaudeSDKProviderOAuth:
    """Cover the OAuth branches in ClaudeSDKProvider.initialize().

    These exist because the SDK's MCP transport will silently fall back to
    its own claude.ai/oauth flow if no Authorization header is set, which
    masks misconfiguration. The provider must either supply a Bearer token
    or fail loudly.
    """

    @pytest.mark.asyncio
    async def test_oauth_auto_discover_uses_cached_token(self, fake_claude_sdk_module):
        """When oauth_auto_discover is set, the cached fastmcp token is used as Bearer."""
        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-5",
            mcp_url="https://mcp.example.com/mcp",
            auth={"type": "oauth", "oauth_auto_discover": True},
        )
        with patch.object(
            ClaudeSDKProvider,
            "_read_cached_oauth_token",
            new=AsyncMock(return_value="cached-access-token-abc"),
        ) as read_cached:
            await provider.initialize()
            read_cached.assert_awaited_once()
        headers = provider._mcp_server_config.get("headers", {})
        assert headers.get("Authorization") == "Bearer cached-access-token-abc"

    @pytest.mark.asyncio
    async def test_oauth_auto_discover_missing_token_fails_fast(self, fake_claude_sdk_module):
        """No cached token must raise so the SDK can't bounce to claude.ai/oauth."""
        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-5",
            mcp_url="https://mcp.example.com/mcp",
            auth={"type": "oauth", "oauth_auto_discover": True},
        )
        with patch.object(
            ClaudeSDKProvider, "_read_cached_oauth_token", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(ValueError, match="No usable cached OAuth token"):
                await provider.initialize()

    @pytest.mark.asyncio
    async def test_oauth_client_credentials_path_unchanged(self, fake_claude_sdk_module):
        """Profiles without oauth_auto_discover still use the client_credentials grant."""
        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-5",
            mcp_url="https://mcp.example.com/mcp",
            auth={
                "type": "oauth",
                "client_id": "id",
                "client_secret": "secret",
                "token_url": "https://auth.example.com/token",
            },
        )
        with (
            patch.object(
                ClaudeSDKProvider,
                "_fetch_oauth_token",
                new=AsyncMock(return_value="cc-token-xyz"),
            ) as fetch_cc,
            patch.object(
                ClaudeSDKProvider, "_read_cached_oauth_token", new=AsyncMock()
            ) as read_cached,
        ):
            await provider.initialize()
            fetch_cc.assert_awaited_once()
            read_cached.assert_not_awaited()
        headers = provider._mcp_server_config.get("headers", {})
        assert headers.get("Authorization") == "Bearer cc-token-xyz"


# ---------------------------------------------------------------------------
# ClaudeSDKProvider env construction tests
# ---------------------------------------------------------------------------


class TestClaudeSDKBuildCleanEnv:
    """Cover the subprocess env handed to the Claude CLI.

    The IS_SANDBOX=1 entry is load-bearing: recent Claude CLI versions
    refuse --dangerously-skip-permissions (driven by permission_mode=
    "bypassPermissions") under root/sudo unless IS_SANDBOX=1 is set, which
    breaks testmcpy 100% inside our root Docker container.
    """

    def test_is_sandbox_set(self):
        env = ClaudeSDKProvider._build_clean_env({})
        assert env["IS_SANDBOX"] == "1"

    def test_anthropic_api_key_cleared(self):
        env = ClaudeSDKProvider._build_clean_env({"ANTHROPIC_API_KEY": "sk-real-key"})
        assert env["ANTHROPIC_API_KEY"] == ""

    def test_claude_code_session_vars_stripped(self):
        source = {
            "CLAUDECODE": "1",
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            "CLAUDE_CODE_SOMETHING": "x",
            "PATH": "/usr/bin",
        }
        env = ClaudeSDKProvider._build_clean_env(source)
        assert "CLAUDECODE" not in env
        assert not any(k.startswith("CLAUDE_CODE") for k in env)
        # Unrelated vars are passed through.
        assert env["PATH"] == "/usr/bin"

    def test_unrelated_env_preserved(self):
        env = ClaudeSDKProvider._build_clean_env({"HOME": "/root", "FOO": "bar"})
        assert env["HOME"] == "/root"
        assert env["FOO"] == "bar"

    def test_default_reads_os_environ(self, monkeypatch):
        # Without an explicit source_env, _build_clean_env should read os.environ
        # — and still apply IS_SANDBOX=1 regardless of whether the caller is root.
        monkeypatch.delenv("IS_SANDBOX", raising=False)
        env = ClaudeSDKProvider._build_clean_env()
        assert env["IS_SANDBOX"] == "1"

    def test_does_not_inherit_process_wide_node_tls_opt_out(self):
        env = ClaudeSDKProvider._build_clean_env({"NODE_TLS_REJECT_UNAUTHORIZED": "0"})

        assert "NODE_TLS_REJECT_UNAUTHORIZED" not in env

    def test_loopback_bypasses_inherited_proxy_settings(self):
        env = ClaudeSDKProvider._build_clean_env(
            {
                "HTTPS_PROXY": "http://proxy.example.test:8080",
                "NO_PROXY": "internal.example.test",
                "no_proxy": "metadata.example.test",
            }
        )

        assert env["HTTPS_PROXY"] == "http://proxy.example.test:8080"
        for key in ("NO_PROXY", "no_proxy"):
            entries = set(env[key].split(","))
            assert {
                "internal.example.test",
                "metadata.example.test",
                "127.0.0.1",
                "localhost",
            }.issubset(entries)

    @pytest.mark.asyncio
    async def test_agent_temp_dir_is_removed_when_option_building_fails(self, tmp_path):
        sdk_tmpdir = tmp_path / "sdk-cwd"
        sdk_tmpdir.mkdir()
        provider = ClaudeSDKProvider(model="claude-sonnet-4-6")
        proxy = AsyncMock()
        proxy.url = "http://127.0.0.1:54321/mcp-secret"

        with (
            patch(
                "testmcpy.src.llm_integration.tempfile.mkdtemp",
                return_value=str(sdk_tmpdir),
            ),
            patch.object(
                provider,
                "build_agent_options",
                side_effect=ValueError("invalid SDK options"),
            ),
            patch.object(
                provider,
                "start_insecure_mcp_proxy",
                new=AsyncMock(return_value=proxy),
            ),
        ):
            result = await provider._run_agent("hello", timeout=1.0, messages=None)

        assert "invalid SDK options" in result.response_text
        assert not sdk_tmpdir.exists()
        proxy.close.assert_awaited_once()


class TestClaudeMCPProxy:
    @pytest.mark.asyncio
    async def test_self_signed_tls_is_bypassed_only_through_loopback_proxy(self, tmp_path):
        import asyncio
        import datetime as dt
        import ipaddress
        import socket
        import ssl

        import httpx
        from aiohttp import web
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from multidict import CIMultiDict

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(hours=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert_path, key_path)

        captured = {}

        async def upstream_handler(request):
            if request.headers.get("X-Test-Redirect"):
                return web.Response(
                    status=307,
                    headers={"Location": f"https://127.0.0.1:{port}/canonical-mcp"},
                )
            captured["authorization"] = request.headers.get("Authorization")
            captured["origin"] = request.headers.get("Origin")
            captured["content_length"] = request.headers.get("Content-Length")
            captured["transfer_encoding"] = request.headers.get("Transfer-Encoding")
            captured["dynamic_hop_header"] = request.headers.get("X-Hop")
            captured["body"] = await request.read()
            return web.Response(
                body=b'{"jsonrpc":"2.0","result":{}}',
                content_type="application/json",
                headers=CIMultiDict(
                    [
                        ("Mcp-Session-Id", "session-123"),
                        ("WWW-Authenticate", 'Bearer realm="first"'),
                        ("WWW-Authenticate", 'Bearer realm="second"'),
                        ("Connection", "X-Internal"),
                        ("X-Internal", "must-not-leak"),
                        ("Set-Cookie", "proxy_cookie=must-not-replay"),
                    ]
                ),
            )

        async def upstream_stream(request):
            captured["last_event_id"] = request.headers.get("Last-Event-ID")
            captured["cookie"] = request.headers.get("Cookie")
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            await response.write(b"data: first\n\n")
            await asyncio.sleep(0.01)
            await response.write(b"data: second\n\n")
            await response.write_eof()
            return response

        async def upstream_delete(request):
            captured["deleted_session"] = request.headers.get("Mcp-Session-Id")
            return web.Response(status=204)

        app = web.Application()
        app.router.add_post("/mcp", upstream_handler)
        app.router.add_get("/mcp", upstream_stream)
        app.router.add_delete("/mcp", upstream_delete)
        runner = web.AppRunner(app)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        sock.setblocking(False)
        port = sock.getsockname()[1]
        await runner.setup()
        site = web.SockSite(runner, sock, ssl_context=tls)
        await site.start()

        proxy = _InsecureMCPProxy(
            f"https://127.0.0.1:{port}/mcp",
            upstream_headers={"Authorization": "Bearer selected-token"},
        )
        try:
            await proxy.start()
            proxy_origin = proxy.url.rsplit("/", 1)[0]
            payload = b'{"jsonrpc":"2.0","method":"initialize"}'
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    proxy.url,
                    headers={
                        "Origin": proxy_origin,
                        "Connection": "X-Hop",
                        "X-Hop": "must-not-leak",
                    },
                    content=payload,
                )
                async with client.stream(
                    "GET",
                    proxy.url,
                    headers={"Last-Event-ID": "event-42"},
                ) as stream_response:
                    streamed_body = b"".join(
                        [chunk async for chunk in stream_response.aiter_bytes()]
                    )
                deleted = await client.delete(
                    proxy.url,
                    headers={"Mcp-Session-Id": "session-123"},
                )
                redirected = await client.post(
                    proxy.url,
                    headers={"X-Test-Redirect": "1"},
                )
                unsupported = await client.put(proxy.url)
                invalid_host = await client.post(
                    proxy.url,
                    headers={"Host": "attacker.example"},
                )
                invalid_origin = await client.post(
                    proxy.url,
                    headers={"Origin": "https://attacker.example"},
                )
                unknown_path = await client.post(f"{proxy_origin}/not-the-secret-path")

            assert response.status_code == 200
            assert response.headers["Mcp-Session-Id"] == "session-123"
            assert response.headers.get_list("WWW-Authenticate") == [
                'Bearer realm="first"',
                'Bearer realm="second"',
            ]
            assert "X-Internal" not in response.headers
            assert "Set-Cookie" not in response.headers
            assert stream_response.headers["Content-Type"] == "text/event-stream"
            assert streamed_body == b"data: first\n\ndata: second\n\n"
            assert deleted.status_code == 204
            assert redirected.status_code == 502
            assert "canonical MCP URL" in redirected.text
            assert unsupported.status_code == 405
            assert invalid_host.status_code == 421
            assert invalid_origin.status_code == 403
            assert unknown_path.status_code == 404
            assert captured == {
                "authorization": "Bearer selected-token",
                "origin": f"https://127.0.0.1:{port}",
                "content_length": str(len(payload)),
                "transfer_encoding": None,
                "dynamic_hop_header": None,
                "body": payload,
                "last_event_id": "event-42",
                "cookie": None,
                "deleted_session": "session-123",
            }
        finally:
            await proxy.close()
            await runner.cleanup()

        with pytest.raises(RuntimeError, match="has not been started"):
            _ = proxy.url

    @pytest.mark.asyncio
    async def test_provider_overrides_only_mcp_url_and_never_node_tls(self):
        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url="https://mcp.example.test/mcp",
            auth={"type": "none", "insecure": True},
        )
        provider._mcp_server_config = {
            "type": "http",
            "url": provider.mcp_url,
            "headers": {"Authorization": "Bearer selected-token"},
        }
        proxy = await provider.start_insecure_mcp_proxy()
        assert proxy is not None
        try:
            options = provider.build_agent_options(
                cwd="/tmp",
                mcp_url_override=proxy.url,
            )
        finally:
            await proxy.close()

        config = options.mcp_servers["mcp-service"]
        assert config["url"].startswith("http://127.0.0.1:")
        assert "headers" not in config
        assert options.tools == []
        assert options.disallowed_tools == []
        assert "NODE_TLS_REJECT_UNAUTHORIZED" not in options.env


# ---------------------------------------------------------------------------
# ClaudeSDK verbose log format tests
# ---------------------------------------------------------------------------


class TestClaudeSDKVerboseLogs:
    """Assert that the new log-suppression and thinking-preview logic works."""

    @pytest.mark.asyncio
    async def test_assistant_message_header_suppressed(self, monkeypatch):
        """Message #N: AssistantMessage must NOT appear in logs (content lines replace it)."""
        import sys
        import types

        # Build minimal fake claude_agent_sdk with the types the code imports.
        fake_pkg = types.ModuleType("claude_agent_sdk")
        fake_types_mod = types.ModuleType("claude_agent_sdk.types")

        # Name classes without underscores so type().__name__ matches what the
        # production code logs (e.g. "AssistantMessage", not "_AssistantMessage").
        TextBlock = type(
            "TextBlock", (), {"__init__": lambda s, text: setattr(s, "text", text) or None}
        )
        ThinkingBlock = type(
            "ThinkingBlock", (), {"__init__": lambda s, t: setattr(s, "thinking", t) or None}
        )
        AssistantMessage = type(
            "AssistantMessage", (), {"__init__": lambda s, c: setattr(s, "content", c) or None}
        )
        UserMessage = type("UserMessage", (), {})
        SystemMessage = type(
            "SystemMessage",
            (),
            {
                "__init__": lambda s: (
                    (setattr(s, "subtype", "info"), setattr(s, "data", {})) and None
                )
            },
        )

        rl_info = type("RLInfo", (), {"status": "allowed", "utilization": None})()
        RateLimitEvent = type(
            "RateLimitEvent",
            (),
            {"__init__": lambda s: setattr(s, "rate_limit_info", rl_info) or None},
        )
        ResultMessage = type(
            "ResultMessage",
            (),
            {
                "__init__": lambda s: (
                    (
                        setattr(s, "usage", {}),
                        setattr(s, "total_cost_usd", 0.001),
                        setattr(s, "duration_ms", 100),
                        setattr(s, "num_turns", 1),
                    )
                    and None
                )
            },
        )
        ToolResultBlock = type("ToolResultBlock", (), {})

        # Populate fake package
        for name, cls in [
            ("AssistantMessage", AssistantMessage),
            ("UserMessage", UserMessage),
            ("SystemMessage", SystemMessage),
            ("RateLimitEvent", RateLimitEvent),
            ("ResultMessage", ResultMessage),
            ("TextBlock", TextBlock),
            ("ThinkingBlock", ThinkingBlock),
            ("ToolUseBlock", type("ToolUseBlock", (), {})),
            ("ClaudeAgentOptions", dict),
            ("ClaudeSDKError", Exception),
            ("CLIConnectionError", Exception),
            ("CLINotFoundError", Exception),
            ("ProcessError", Exception),
        ]:
            setattr(fake_pkg, name, cls)

        fake_types_mod.ToolResultBlock = ToolResultBlock

        # 120-char thinking string so truncation fires and ellipsis appears
        long_thinking = 'I need to call "get_dashboard_info" to answer this. ' * 3

        async def fake_query(prompt, options):
            yield AssistantMessage(
                [
                    TextBlock("I'll look into that."),
                    ThinkingBlock(long_thinking),
                ]
            )
            yield RateLimitEvent()
            yield ResultMessage()

        fake_pkg.query = fake_query

        monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_pkg)
        monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_types_mod)

        provider = ClaudeSDKProvider(model="claude-sonnet-4-5")
        provider._initialized = True
        provider._mcp_server_config = {}
        provider.verbose = True

        result = await provider.generate_with_tools("Hello", tools=[])

        log_text = "\n".join(result.logs)

        # Generic class-name headers must be suppressed for content-bearing types
        assert "Message #1: AssistantMessage" not in log_text
        assert "Message #1: UserMessage" not in log_text

        # RateLimitEvent MUST keep its header (no dedicated content line)
        assert "Message #2: RateLimitEvent" in log_text

        # ResultMessage MUST keep its header
        assert "Message #3: ResultMessage" in log_text

        # Text content line must be present
        assert "[ClaudeSDK] Text:" in log_text

        # Thinking preview must appear with repr() and ellipsis
        assert "[ClaudeSDK] Thinking:" in log_text
        assert "chars)" in log_text
        # The preview should use repr() — so quotes are present
        thinking_lines = [line for line in result.logs if "Thinking:" in line]
        assert len(thinking_lines) == 1
        assert "..." in thinking_lines[0]  # ellipsis because text > 100 chars


# ---------------------------------------------------------------------------
# CodexSDKProvider Tests
# ---------------------------------------------------------------------------


class TestCodexSDKProvider:
    """Cover CodexSDKProvider construction, auth resolution, and factory aliases."""

    def test_factory_alias_codex_sdk(self) -> None:
        p = create_llm_provider("codex-sdk", "codex-o3", openai_api_key="sk-test")
        assert isinstance(p, CodexSDKProvider)

    def test_factory_maps_profile_api_key(self) -> None:
        p = create_llm_provider("codex-sdk", "codex-o3", api_key="profile-key")

        assert isinstance(p, CodexSDKProvider)
        assert p.openai_api_key == "profile-key"

    def test_factory_alias_codex_cli(self) -> None:
        p = create_llm_provider("codex-cli", "codex-o3", openai_api_key="sk-test")
        assert isinstance(p, CodexSDKProvider)

    def test_factory_alias_codex(self) -> None:
        p = create_llm_provider("codex", "codex-o3", openai_api_key="sk-test")
        assert isinstance(p, CodexSDKProvider)

    def test_model_id_remapped(self) -> None:
        p = CodexSDKProvider(model="codex-o3", openai_api_key="sk-test")
        assert p.model == "o3"

    def test_model_id_remapped_o4mini(self) -> None:
        p = CodexSDKProvider(model="codex-o4-mini", openai_api_key="sk-test")
        assert p.model == "o4-mini"

    def test_model_id_passthrough_for_unknown(self) -> None:
        # If user passes a raw OpenAI model ID, it is passed through unchanged.
        p = CodexSDKProvider(model="gpt-4o-mini", openai_api_key="sk-test")
        assert p.model == "gpt-4o-mini"

    def test_api_key_from_constructor(self) -> None:
        p = CodexSDKProvider(model="codex-o3", openai_api_key="sk-explicit")
        assert p.openai_api_key == "sk-explicit"

    def test_no_api_key_defaults_empty(self) -> None:
        # Key comes from the LLM profile (resolved in .llm_providers.yaml),
        # not from the environment — constructor with no key yields empty string.
        p = CodexSDKProvider(model="codex-o3")
        assert p.openai_api_key == ""

    def test_read_cached_codex_token_present(self, tmp_path, monkeypatch) -> None:
        auth_file = tmp_path / ".codex" / "auth.json"
        auth_file.parent.mkdir(parents=True)
        # Real Codex CLI schema: OPENAI_API_KEY at top level, OAuth tokens nested
        auth_file.write_text(
            '{"OPENAI_API_KEY": "sk-stored-key", "tokens": {"access_token": "oauth-only"}}'
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        p = CodexSDKProvider(model="codex-o3")
        assert p._read_cached_codex_token() == "sk-stored-key"

    def test_read_cached_codex_token_oauth_only_returns_none(self, tmp_path, monkeypatch) -> None:
        # OAuth-only login: OPENAI_API_KEY is null — ChatGPT token can't hit Platform API
        auth_file = tmp_path / ".codex" / "auth.json"
        auth_file.parent.mkdir(parents=True)
        auth_file.write_text('{"OPENAI_API_KEY": null, "tokens": {"access_token": "chatgpt-tok"}}')
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        p = CodexSDKProvider(model="codex-o3")
        assert p._read_cached_codex_token() is None

    def test_read_cached_codex_token_missing_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        p = CodexSDKProvider(model="codex-o3")
        assert p._read_cached_codex_token() is None

    def test_read_cached_codex_token_invalid_json(self, tmp_path, monkeypatch) -> None:
        auth_file = tmp_path / ".codex" / "auth.json"
        auth_file.parent.mkdir(parents=True)
        auth_file.write_text("not-json{{")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        p = CodexSDKProvider(model="codex-o3")
        assert p._read_cached_codex_token() is None

    @pytest.mark.asyncio
    async def test_initialize_missing_package_raises(self, monkeypatch) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "agents", None)
        p = CodexSDKProvider(model="codex-o3", openai_api_key="sk-test")
        with pytest.raises(ValueError, match="openai-agents"):
            await p.initialize()

    @pytest.mark.asyncio
    async def test_initialize_no_key_raises(self, monkeypatch, tmp_path) -> None:
        """No constructor key and no ~/.codex/auth.json must raise ValueError."""
        import sys
        import types

        fake_agents = types.ModuleType("agents")
        fake_agents.Agent = object
        fake_agents.Runner = object
        monkeypatch.setitem(sys.modules, "agents", fake_agents)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        p = CodexSDKProvider(model="codex-o3")  # no openai_api_key
        with pytest.raises(ValueError, match="api_key"):
            await p.initialize()

    def test_tool_call_extraction_from_raw_item(self) -> None:
        """tool_calls must be populated from ToolCallItem.raw_item, not .arguments."""
        pytest.importorskip("agents", reason="openai-agents not installed")
        from agents.items import ToolCallItem

        # RunItemBase stores a weakref to agent; a plain class instance supports it.
        class _FakeAgent:
            pass

        raw = {"name": "list_dashboards", "arguments": '{"page": 1}', "call_id": "c1"}
        item = ToolCallItem(raw_item=raw, agent=_FakeAgent())  # type: ignore[arg-type]

        assert item.tool_name == "list_dashboards"
        # Confirm .arguments does NOT exist on ToolCallItem (the bug this guards).
        assert not hasattr(item, "arguments")
        # Arguments live on raw_item — our extraction code reads them correctly.
        assert raw.get("arguments") == '{"page": 1}'

    @pytest.mark.asyncio
    async def test_initialize_bearer_auth_sets_mcp_header(self, monkeypatch) -> None:
        """Bearer auth type must set Authorization header on MCP requests."""
        import sys
        import types

        fake_agents = types.ModuleType("agents")
        fake_agents.Agent = object
        fake_agents.Runner = object
        monkeypatch.setitem(sys.modules, "agents", fake_agents)

        p = CodexSDKProvider(
            model="codex-o3",
            mcp_url="https://mcp.example.com/mcp",
            auth={"type": "bearer", "token": "bearer-tok-789"},
            openai_api_key="sk-test",
        )
        await p.initialize()
        assert p._mcp_headers == {"Authorization": "Bearer bearer-tok-789"}


# ---------------------------------------------------------------------------
# GeminiProvider env-var fix tests
# ---------------------------------------------------------------------------


class TestGeminiProviderNoEnvRead:
    """GeminiProvider must no longer read env vars in __init__."""

    def test_no_api_key_defaults_empty(self) -> None:
        p = GeminiProvider(model="gemini-2.5-flash", api_key=None)
        assert p.api_key == ""

    def test_api_key_from_constructor(self) -> None:
        p = GeminiProvider(model="gemini-2.5-flash", api_key="AIza-explicit")
        assert p.api_key == "AIza-explicit"


# ---------------------------------------------------------------------------
# GeminiSDKProvider tests
# ---------------------------------------------------------------------------


class TestGeminiSDKProvider:
    """Cover GeminiSDKProvider construction, auth resolution, and factory alias."""

    def test_factory_alias_gemini_sdk(self) -> None:
        p = create_llm_provider("gemini-sdk", "gemini-sdk-flash", api_key="AIza-test")
        assert isinstance(p, GeminiSDKProvider)

    def test_model_id_remapped_flash(self) -> None:
        p = GeminiSDKProvider(model="gemini-sdk-flash", api_key="AIza-test")
        assert p.model == "gemini-2.5-flash"

    def test_model_id_remapped_pro(self) -> None:
        p = GeminiSDKProvider(model="gemini-sdk-pro", api_key="AIza-test")
        assert p.model == "gemini-2.5-pro"

    def test_model_id_remapped_default_alias(self) -> None:
        p = GeminiSDKProvider(model="gemini-sdk", api_key="AIza-test")
        assert p.model == "gemini-2.5-flash"

    def test_model_id_passthrough_for_unknown(self) -> None:
        p = GeminiSDKProvider(model="gemini-1.5-pro", api_key="AIza-test")
        assert p.model == "gemini-1.5-pro"

    def test_api_key_from_constructor(self) -> None:
        p = GeminiSDKProvider(model="gemini-sdk-flash", api_key="AIza-explicit")
        assert p.api_key == "AIza-explicit"

    def test_no_api_key_defaults_empty(self) -> None:
        p = GeminiSDKProvider(model="gemini-sdk-flash")
        assert p.api_key == ""

    @pytest.mark.asyncio
    async def test_initialize_missing_package_raises(self, monkeypatch) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "google.adk", None)
        p = GeminiSDKProvider(model="gemini-sdk-flash", api_key="AIza-test")
        with pytest.raises(ValueError, match="google-adk"):
            await p.initialize()

    @pytest.mark.asyncio
    async def test_initialize_no_key_raises(self, monkeypatch) -> None:
        """No api_key must raise ValueError immediately."""
        import sys
        import types

        fake_adk = types.ModuleType("google.adk")
        fake_adk.Agent = object
        monkeypatch.setitem(sys.modules, "google.adk", fake_adk)

        p = GeminiSDKProvider(model="gemini-sdk-flash")
        with pytest.raises(ValueError, match="api_key"):
            await p.initialize()

    @pytest.mark.asyncio
    async def test_initialize_bearer_auth_sets_mcp_header(self, monkeypatch) -> None:
        """Bearer auth config must set Authorization header."""
        import sys
        import types

        fake_adk = types.ModuleType("google.adk")
        fake_adk.Agent = object
        monkeypatch.setitem(sys.modules, "google.adk", fake_adk)

        p = GeminiSDKProvider(
            model="gemini-sdk-flash",
            mcp_url="https://mcp.example.com/mcp",
            auth={"type": "bearer", "token": "bearer-gemini-xyz"},
            api_key="AIza-test",
        )
        await p.initialize()
        assert p._mcp_headers == {"Authorization": "Bearer bearer-gemini-xyz"}

    @pytest.mark.asyncio
    async def test_generate_with_tools_fake_events(self) -> None:
        """generate_with_tools must: populate tool_results, sum usage, compute cost,
        not re-execute tools, and close McpToolset on completion."""
        pytest.importorskip("google.adk", reason="google-adk not installed")
        import uuid as _uuid
        from unittest.mock import MagicMock

        # Build fake events using MagicMock — Event is a Pydantic model and does
        # not allow setting arbitrary attributes directly.
        class _FakeUsage:
            prompt_token_count = 10
            candidates_token_count = 20
            total_token_count = 30

        class _FakeFunctionCall:
            name = "list_dashboards"
            args = {"page": 1}
            id = "fc-1"

        class _FakeFunctionResponse:
            name = "list_dashboards"
            id = "fc-1"
            response = {"dashboards": ["d1", "d2"]}

        class _FakeIdlessFunctionCall:
            name = "health_check"
            args = {}

        class _FakeIdlessFunctionResponse:
            name = "health_check"
            response = {"status": "healthy"}

        class _FakePart:
            text = "Found 2 dashboards."

        class _FakeContent:
            parts = [_FakePart()]

        fc_event = MagicMock()
        fc_event.get_function_calls.return_value = [
            _FakeFunctionCall(),
            _FakeIdlessFunctionCall(),
        ]
        fc_event.get_function_responses.return_value = []
        fc_event.is_final_response.return_value = False
        fc_event.content = None
        fc_event.usage_metadata = None

        fr_event = MagicMock()
        fr_event.get_function_calls.return_value = []
        fr_event.get_function_responses.return_value = [
            _FakeFunctionResponse(),
            _FakeIdlessFunctionResponse(),
        ]
        fr_event.is_final_response.return_value = False
        fr_event.content = None
        fr_event.usage_metadata = _FakeUsage()

        final_event = MagicMock()
        final_event.get_function_calls.return_value = []
        final_event.get_function_responses.return_value = []
        final_event.is_final_response.return_value = True
        final_event.content = _FakeContent()
        final_event.usage_metadata = _FakeUsage()

        async def _fake_run_async(**kwargs):
            for ev in [fc_event, fr_event, final_event]:
                yield ev

        closed = []

        class _FakeMcpToolset:
            async def close(self):
                closed.append(True)

        class _FakeSession:
            id = _uuid.uuid4().hex

        class _FakeSessionService:
            async def create_session(self, **kwargs):
                return _FakeSession()

        class _FakeRunner:
            def __init__(self, **kwargs):
                pass

            def run_async(self, **kwargs):
                return _fake_run_async(**kwargs)

        from unittest.mock import patch

        p = GeminiSDKProvider(
            model="gemini-sdk-flash",
            mcp_url="https://mcp.example.com/mcp",
            api_key="AIza-test",
        )
        p._mcp_headers = {}

        # McpToolset etc. are deferred imports inside generate_with_tools, so
        # patch the source modules, not testmcpy.src.llm_integration.*.
        with (
            patch(
                "google.adk.tools.mcp_tool.mcp_toolset.McpToolset",
                return_value=_FakeMcpToolset(),
            ),
            patch(
                "google.adk.sessions.in_memory_session_service.InMemorySessionService",
                return_value=_FakeSessionService(),
            ),
            patch(
                "google.adk.runners.Runner",
                side_effect=lambda **kw: _FakeRunner(**kw),
            ),
            patch("google.adk.tools.mcp_tool.mcp_session_manager.StreamableHTTPConnectionParams"),
            patch("google.adk.agents.llm_agent.LlmAgent"),
            patch("google.adk.models.google_llm.Gemini"),
        ):
            result = await p.generate_with_tools("list dashboards", [], timeout=30.0)

        # tool_calls populated
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0]["name"] == "list_dashboards"
        assert result.tool_calls[0]["id"] == "fc-1"
        assert result.tool_calls[1]["name"] == "health_check"
        assert "id" not in result.tool_calls[1]
        # tool_results populated — no second MCP execution needed
        assert len(result.tool_results) == 2
        assert result.tool_results[0].tool_name == "list_dashboards"
        assert result.tool_results[0].tool_call_id == "fc-1"
        assert result.tool_results[1].tool_name == "health_check"
        assert result.tool_results[1].tool_call_id == ""
        # usage summed across two usage-bearing events
        assert result.token_usage is not None
        assert result.token_usage["prompt"] == 20  # 10 + 10
        assert result.token_usage["completion"] == 40  # 20 + 20
        # cost nonzero (registry has pricing for gemini-sdk-flash)
        assert result.cost > 0
        # response text collected
        assert "dashboards" in result.response.lower()
        # toolset closed
        assert closed == [True]


# ---------------------------------------------------------------------------
# BaseSDKProvider contract tests (Claude / Codex / Gemini)
# ---------------------------------------------------------------------------


class TestSDKProviderContract:
    """Cover the contract :class:`BaseSDKProvider` enforces for every
    SDK-backed provider. These are the drift points that have repeatedly
    produced real eval-harness bugs — assert them once for the base and
    parametrise across the three subclasses.

    Specifically:

    1. ``LLMResult.tool_results`` MUST be populated whenever the vendor SDK
       executes tools natively. If empty when ``tool_calls`` is non-empty,
       ``test_runner.py:598`` re-executes every call against MCP, which is
       catastrophic for state-mutating tools.
    2. ``token_usage`` MUST use ``{"prompt", "completion", "total"}``.
    3. ``cost`` should come out non-zero when token_usage + model registry
       pricing are available.
    """

    def _build_provider(self, provider_cls):
        """Construct each provider with whatever vendor-specific kwarg it
        needs to bypass credential validation. We don't call ``initialize``
        — the test patches ``_run_agent`` directly."""
        from testmcpy.src.llm_integration import (
            ClaudeSDKProvider,
            CodexSDKProvider,
            GeminiSDKProvider,
        )

        if provider_cls is ClaudeSDKProvider:
            return ClaudeSDKProvider(model="claude-sonnet-4-5")
        if provider_cls is CodexSDKProvider:
            # codex-o4-mini → registry entry has pricing → cost should be > 0.
            return CodexSDKProvider(model="codex-o4-mini", openai_api_key="sk-test")
        if provider_cls is GeminiSDKProvider:
            return GeminiSDKProvider(model="gemini-sdk-flash", api_key="AIza-test")
        raise AssertionError(f"unknown provider class {provider_cls}")

    @pytest.mark.parametrize(
        "provider",
        [
            CodexSDKProvider(
                model="codex-o3",
                mcp_url="https://mcp.example.test/mcp",
                auth={"type": "none", "insecure": True},
                openai_api_key="sk-test",
            ),
            GeminiSDKProvider(
                model="gemini-sdk-flash",
                mcp_url="https://mcp.example.test/mcp",
                auth={"type": "none", "insecure": True},
                api_key="AIza-test",
            ),
        ],
        ids=["codex", "gemini"],
    )
    def test_native_mcp_transport_uses_insecure_httpx_factory(self, provider) -> None:
        params = provider._build_mcp_transport_params()

        with patch("testmcpy.src.mcp_client.httpx.AsyncClient") as async_client:
            params["httpx_client_factory"]()

        assert async_client.call_args.kwargs["verify"] is False

    def test_secure_native_mcp_transport_uses_sdk_default_factory(self) -> None:
        provider = CodexSDKProvider(
            model="codex-o3",
            mcp_url="https://mcp.example.test/mcp",
            auth={"type": "none"},
            openai_api_key="sk-test",
        )

        assert "httpx_client_factory" not in provider._build_mcp_transport_params()

    @pytest.mark.parametrize(
        "auth,method_name,response_json,expected_token,expected_verify",
        [
            (
                {
                    "type": "jwt",
                    "api_url": "https://auth.example.test/jwt",
                    "api_token": "user",
                    "api_secret": "secret",
                    "insecure": True,
                },
                "_fetch_jwt_token",
                {"payload": {"access_token": "jwt-token"}},
                "jwt-token",
                False,
            ),
            (
                {
                    "type": "oauth",
                    "token_url": "https://auth.example.test/token",
                    "client_id": "client",
                    "client_secret": "secret",
                    "insecure": True,
                },
                "_fetch_oauth_token",
                {"access_token": "oauth-token"},
                "oauth-token",
                False,
            ),
            (
                {
                    "type": "oauth",
                    "token_url": "https://auth.example.test/token",
                    "client_id": "client",
                    "client_secret": "secret",
                },
                "_fetch_oauth_token",
                {"access_token": "secure-token"},
                "secure-token",
                True,
            ),
        ],
        ids=["insecure-jwt", "insecure-oauth", "secure-oauth"],
    )
    @pytest.mark.asyncio
    async def test_auth_token_fetch_honors_tls_verification_setting(
        self,
        auth,
        method_name,
        response_json,
        expected_token,
        expected_verify,
    ) -> None:
        provider = CodexSDKProvider(
            model="codex-o3",
            mcp_url="https://mcp.example.test/mcp",
            auth=auth,
            openai_api_key="sk-test",
        )
        response = MagicMock()
        response.json.return_value = response_json
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response

        with patch(
            "testmcpy.src.llm_integration.httpx.AsyncClient",
            return_value=client,
        ) as async_client:
            token = await getattr(provider, method_name)()

        assert token == expected_token
        async_client.assert_called_once_with(verify=expected_verify)

    @pytest.mark.parametrize("provider_name", ["claude", "codex", "gemini"])
    @pytest.mark.asyncio
    async def test_tool_results_populated_when_sdk_executes_tools(self, provider_name) -> None:
        """Contract: when ``_run_agent`` returns ``SDKRunResult`` with both
        ``tool_calls`` and ``tool_results`` populated, the resulting
        :class:`LLMResult` must carry both — so ``test_runner.py`` skips
        re-execution. This is the exact drift bug that bit CodexSDKProvider
        in PR #84.
        """
        from unittest.mock import AsyncMock, patch

        from testmcpy.src.llm_integration import (
            ClaudeSDKProvider,
            CodexSDKProvider,
            GeminiSDKProvider,
            MCPToolResult,
            SDKRunResult,
        )

        provider_cls = {
            "claude": ClaudeSDKProvider,
            "codex": CodexSDKProvider,
            "gemini": GeminiSDKProvider,
        }[provider_name]
        provider = self._build_provider(provider_cls)

        fake_run_result = SDKRunResult(
            response_text="ok",
            tool_calls=[{"id": "call-1", "name": "list_dashboards", "arguments": {}}],
            tool_results=[
                MCPToolResult(
                    tool_call_id="call-1",
                    tool_name="list_dashboards",
                    content="[d1, d2]",
                    is_error=False,
                )
            ],
            token_usage={"prompt": 10, "completion": 5, "total": 15},
        )

        with patch.object(
            provider_cls,
            "_run_agent",
            new=AsyncMock(return_value=fake_run_result),
        ):
            result = await provider.generate_with_tools("list dashboards", tools=[], timeout=30.0)

        # Core contract: tool_results MUST be populated and pair with
        # tool_calls so test_runner.py:598 short-circuits re-execution.
        assert len(result.tool_results) == 1, (
            f"{provider_cls.__name__} dropped tool_results — "
            "test_runner will re-execute calls against MCP"
        )
        assert result.tool_results[0].tool_name == "list_dashboards"
        assert len(result.tool_calls) == 1
        # token_usage shape is the repo-standard one.
        assert result.token_usage == {
            "prompt": 10,
            "completion": 5,
            "total": 15,
        }
        assert result.response == "ok"

    @pytest.mark.parametrize("provider_name", ["claude", "codex", "gemini"])
    @pytest.mark.asyncio
    async def test_warns_when_tool_results_missing(self, provider_name, caplog) -> None:
        """When a subclass forgets to populate ``tool_results`` but does
        report ``tool_calls``, :meth:`BaseSDKProvider.generate_with_tools`
        emits a WARNING. This is the only signal a future-drift subclass
        will have before the harness silently doubles MCP execution."""
        import logging
        from unittest.mock import AsyncMock, patch

        from testmcpy.src.llm_integration import (
            ClaudeSDKProvider,
            CodexSDKProvider,
            GeminiSDKProvider,
            SDKRunResult,
        )

        provider_cls = {
            "claude": ClaudeSDKProvider,
            "codex": CodexSDKProvider,
            "gemini": GeminiSDKProvider,
        }[provider_name]
        provider = self._build_provider(provider_cls)

        fake_run_result = SDKRunResult(
            response_text="ok",
            tool_calls=[{"id": "call-1", "name": "list_dashboards", "arguments": {}}],
            tool_results=[],  # subclass forgot to populate
        )

        with caplog.at_level(logging.WARNING):
            with patch.object(
                provider_cls,
                "_run_agent",
                new=AsyncMock(return_value=fake_run_result),
            ):
                await provider.generate_with_tools("list dashboards", tools=[], timeout=30.0)

        joined = " ".join(rec.message for rec in caplog.records)
        assert "Contract violation" in joined, (
            "Expected base class to log a WARNING when tool_calls present but tool_results empty"
        )
        assert "tool_results" in joined

    @pytest.mark.asyncio
    async def test_cost_estimated_from_model_registry(self) -> None:
        """When the SDK does not report cost directly but does report
        ``token_usage`` AND the model registry has pricing for the
        provider's registry id, the base must populate ``LLMResult.cost``
        from registry per-1M pricing."""
        from unittest.mock import AsyncMock, patch

        from testmcpy.src.llm_integration import (
            CodexSDKProvider,
            SDKRunResult,
        )

        provider = CodexSDKProvider(model="codex-o4-mini", openai_api_key="sk-test")

        fake_run_result = SDKRunResult(
            response_text="ok",
            tool_calls=[],
            tool_results=[],
            token_usage={"prompt": 1_000_000, "completion": 500_000, "total": 1_500_000},
            cost=None,  # SDK did not report cost — base must estimate
        )

        with patch.object(
            CodexSDKProvider,
            "_run_agent",
            new=AsyncMock(return_value=fake_run_result),
        ):
            result = await provider.generate_with_tools("ping", tools=[], timeout=30.0)

        # 1M prompt * $1.10 + 500K completion * $4.40 = $1.10 + $2.20 = $3.30
        assert result.cost > 0, "Cost should be estimated from registry pricing"

    @pytest.mark.asyncio
    async def test_programming_errors_propagate_not_swallowed(self) -> None:
        """Unexpected exceptions (programming defects: AttributeError,
        TypeError on wrong vendor kwargs, etc.) MUST propagate from
        :meth:`generate_with_tools` rather than be converted into a silent
        ``LLMResult(response='Error: ...')``. The latter is what caused
        Codex/Gemini PRs to mask broken SDK call sites as 0-score eval
        failures (see PR #82/#84 review comments)."""
        from unittest.mock import AsyncMock, patch

        from testmcpy.src.llm_integration import CodexSDKProvider

        provider = CodexSDKProvider(model="codex-o4-mini", openai_api_key="sk-test")

        with patch.object(
            CodexSDKProvider,
            "_run_agent",
            new=AsyncMock(side_effect=AttributeError("bogus kwarg")),
        ):
            with pytest.raises(AttributeError, match="bogus kwarg"):
                await provider.generate_with_tools("ping", tools=[], timeout=30.0)


# ---------------------------------------------------------------------------
# AssistantProvider SSE tool_call parsing tests
# ---------------------------------------------------------------------------


class TestAssistantSSEToolCallParsing:
    """_handle_sse_event must extract tool name/args across backend field variants."""

    def _make_provider(self):
        p = AssistantProvider.__new__(AssistantProvider)
        p.model = "default"
        p.workspace_hash = "testhash"
        p.domain = "example.com"
        p.base_url = "https://testhash.example.com"
        p.completions_path = "/api/v1/copilot/completions"
        return p

    def _run(self, data: dict) -> tuple[str, dict, str]:
        provider = self._make_provider()
        state = _SSEStreamState()
        logs: list[str] = []
        provider._handle_sse_event("tool_call", data, state, logs.append)
        assert len(state.tool_calls) == 1
        tc = state.tool_calls[0]
        return tc["name"], tc["arguments"], tc["id"]

    def test_canonical_fields(self):
        name, args, tid = self._run(
            {"tool_call_id": "id1", "tool_name": "get_info", "input": {"k": "v"}}
        )
        assert name == "get_info"
        assert args == {"k": "v"}
        assert tid == "id1"

    def test_name_field_fallback(self):
        name, args, _ = self._run({"name": "list_dashboards", "arguments": {"page": 1}})
        assert name == "list_dashboards"
        assert args == {"page": 1}

    def test_function_name_field(self):
        name, args, _ = self._run(
            {"function_name": "create_chart", "parameters": {"title": "Sales"}}
        )
        assert name == "create_chart"
        assert args == {"title": "Sales"}

    def test_nested_function_dict(self):
        name, args, _ = self._run(
            {"function": {"name": "health_check", "arguments": {"verbose": True}}}
        )
        assert name == "health_check"
        assert args == {"verbose": True}

    def test_dotted_function_keys(self):
        name, args, _ = self._run(
            {"function.name": "get_schema", "function.arguments": {"model_type": "chart"}}
        )
        assert name == "get_schema"
        assert args == {"model_type": "chart"}

    def test_json_string_arguments_parsed(self):
        """arguments delivered as a JSON string must be parsed into a dict."""
        import json

        name, args, _ = self._run(
            {"name": "run_query", "arguments": json.dumps({"sql": "SELECT 1"})}
        )
        assert name == "run_query"
        assert args == {"sql": "SELECT 1"}

    def test_json_string_function_arguments_parsed(self):
        """function.arguments as JSON string must also be parsed."""
        import json

        name, args, _ = self._run({"function": {"name": "foo", "arguments": json.dumps({"x": 1})}})
        assert name == "foo"
        assert args == {"x": 1}

    def test_non_dict_function_value_ignored(self):
        """If function is not a dict, fall back to other fields."""
        name, args, _ = self._run({"function": "not_a_dict", "name": "fallback_tool"})
        assert name == "fallback_tool"

    def test_id_field_fallback(self):
        name, _, tid = self._run({"id": "alt-id", "tool_name": "my_tool"})
        assert tid == "alt-id"

    def test_verbose_log_contains_name(self):
        provider = self._make_provider()
        state = _SSEStreamState()
        logs: list[str] = []
        provider._handle_sse_event(
            "tool_call", {"tool_name": "list_charts", "input": {}}, state, logs.append
        )
        assert any("list_charts" in line for line in logs)


# ---------------------------------------------------------------------------
# LLMResult Parsing Tests
# ---------------------------------------------------------------------------


class TestLLMResult:
    def test_llm_result_creation(self):
        result = LLMResult(
            response="Hello",
            tool_calls=[{"name": "health_check", "arguments": {}}],
            tool_results=[],
            token_usage={"total": 100},
            cost=0.01,
            duration=1.5,
        )
        assert result.response == "Hello"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "health_check"
        assert result.cost == 0.01
        assert result.duration == 1.5

    def test_llm_result_empty(self):
        result = LLMResult(
            response="",
            tool_calls=[],
            tool_results=[],
            token_usage={},
            cost=0.0,
            duration=0.0,
        )
        assert result.response == ""
        assert result.tool_calls == []
        assert result.tool_results == []


# ---------------------------------------------------------------------------
# Evaluator Factory Tests
# ---------------------------------------------------------------------------


class TestEvaluatorFactory:
    def test_create_all_evaluators(self):
        """Verify all registered evaluators can be instantiated."""
        simple_evaluators = ["execution_successful", "no_leaked_data", "url_is_valid"]
        for name in simple_evaluators:
            eval_instance = create_evaluator(name)
            assert eval_instance.name is not None

    def test_create_evaluator_with_args(self):
        e = create_evaluator("response_includes", content=["hello"])
        assert "response_includes" in e.name

    def test_create_unknown_evaluator_raises(self):
        with pytest.raises(ValueError):
            create_evaluator("nonexistent_evaluator")


# ---------------------------------------------------------------------------
# Tool Name Matching Tests
# ---------------------------------------------------------------------------


class TestToolNameMatching:
    def test_match_tool_name_exact(self):
        assert _match_tool_name("health_check", "health_check")

    def test_match_tool_name_prefix(self):
        assert _match_tool_name("mcp__myserver__health_check", "health_check")

    def test_match_tool_name_no_match(self):
        assert not _match_tool_name("list_charts", "health_check")


# ---------------------------------------------------------------------------
# New Evaluator Tests
# ---------------------------------------------------------------------------


class TestResponseNotIncludes:
    def test_pass(self):
        e = create_evaluator("response_not_includes", content=["error", "failed"])
        result = e.evaluate({"response": "All dashboards loaded successfully"})
        assert result.passed

    def test_fail(self):
        e = create_evaluator("response_not_includes", content=["error"])
        result = e.evaluate({"response": "An error occurred"})
        assert not result.passed


class TestNoLeakedData:
    def test_pass(self):
        e = create_evaluator("no_leaked_data")
        result = e.evaluate({"response": "Here are your dashboards"})
        assert result.passed

    def test_fail_connection_string(self):
        e = create_evaluator("no_leaked_data")
        result = e.evaluate({"response": "Error connecting to postgresql://user:pass@host/db"})
        assert not result.passed


class TestUrlIsValid:
    def test_pass(self):
        e = create_evaluator("url_is_valid")
        result = e.evaluate({"response": "View at https://example.com/dashboard/1"})
        assert result.passed

    def test_no_urls(self):
        e = create_evaluator("url_is_valid")
        result = e.evaluate({"response": "No URL here"})
        assert not result.passed


class TestSuccessRateAbove:
    def test_pass(self):
        e = create_evaluator("success_rate_above", min_rate=0.8)
        results = [{"success": True}] * 9 + [{"success": False}]
        result = e.evaluate({"load_test_results": results})
        assert result.passed  # 90% > 80%

    def test_fail(self):
        e = create_evaluator("success_rate_above", min_rate=0.9)
        results = [{"success": True}] * 7 + [{"success": False}] * 3
        result = e.evaluate({"load_test_results": results})
        assert not result.passed  # 70% < 90%


class TestLatencyPercentile:
    def test_pass(self):
        e = create_evaluator("latency_percentile", percentile=95, max_seconds=10.0)
        results = [{"duration": i * 0.5} for i in range(20)]  # 0 to 9.5s
        result = e.evaluate({"load_test_results": results})
        assert result.passed


class TestResponseMatchesPattern:
    def test_pass(self):
        e = create_evaluator("response_matches_pattern", pattern=r"dashboard_id:\s*\d+")
        result = e.evaluate({"response": "Created dashboard_id: 42"})
        assert result.passed


class TestCostHelpers:
    """Module-level cost helpers used by the non-SDK providers."""

    def test_known_model_uses_registry_rates(self):
        from testmcpy.src.llm_integration import _estimate_cost_with_fallback
        from testmcpy.src.model_registry import get_model

        info = get_model("gpt-4o")
        cost = _estimate_cost_with_fallback("gpt-4o", 1_000_000, 1_000_000, 30.0, 60.0)
        assert cost == pytest.approx(info.input_price_per_1m + info.output_price_per_1m)

    def test_unknown_model_keeps_caller_fallback(self):
        from testmcpy.src.llm_integration import _estimate_cost_with_fallback

        cost = _estimate_cost_with_fallback("model-not-in-registry", 1_000_000, 0, 30.0, 60.0)
        assert cost == pytest.approx(30.0)

    def test_zero_tokens_zero_cost(self):
        from testmcpy.src.llm_integration import _estimate_cost_with_fallback

        assert _estimate_cost_with_fallback("gpt-4o", 0, 0, 30.0, 60.0) == 0.0


class TestNormalizeBedrockModelId:
    @pytest.mark.parametrize(
        "bedrock_id,expected",
        [
            ("us.anthropic.claude-sonnet-4-20250514-v1:0", "claude-sonnet-4-20250514"),
            ("eu.anthropic.claude-3-5-haiku-20241022-v1:0", "claude-3-5-haiku-20241022"),
            ("apac.anthropic.claude-sonnet-4-20250514-v1:0", "claude-sonnet-4-20250514"),
            ("global.anthropic.claude-sonnet-4-20250514-v1:0", "claude-sonnet-4-20250514"),
            ("jp.anthropic.claude-sonnet-4-20250514-v1:0", "claude-sonnet-4-20250514"),
            ("anthropic.claude-sonnet-4-20250514-v2:1", "claude-sonnet-4-20250514"),
            ("claude-sonnet-4-20250514", "claude-sonnet-4-20250514"),
        ],
    )
    def test_prefix_and_suffix_stripping(self, bedrock_id, expected):
        from testmcpy.src.llm_integration import _normalize_bedrock_model_id

        assert _normalize_bedrock_model_id(bedrock_id) == expected

    def test_normalized_id_resolves_in_registry(self):
        from testmcpy.src.llm_integration import _normalize_bedrock_model_id
        from testmcpy.src.model_registry import get_model

        normalized = _normalize_bedrock_model_id("global.anthropic.claude-sonnet-4-20250514-v1:0")
        assert get_model(normalized) is not None


class TestOpenAIEffortPayload:
    """Effort must reach the outgoing request, not just be stored on the
    provider. Regression guard: reasoning_effort was previously only added in
    the non-o1 branch, so o1 reasoning models silently dropped it."""

    async def _capture_payload(self, model, effort):
        provider = OpenAIProvider(model=model, api_key="test", effort=effort)
        captured = {}

        class _FakeResp:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        async def fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return _FakeResp()

        provider.client.post = fake_post
        await provider.generate_with_tools("hi", tools=[], timeout=5.0)
        return captured["json"]

    @pytest.mark.asyncio
    async def test_effort_sent_for_non_o1(self):
        payload = await self._capture_payload("gpt-5.5", "high")
        assert payload["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_effort_sent_for_o1_reasoning_model(self):
        # o1 takes the tools-less branch (max_completion_tokens); effort must
        # still be present — this is the bug the review caught.
        payload = await self._capture_payload("o1-mini", "medium")
        assert payload["reasoning_effort"] == "medium"
        assert "max_completion_tokens" in payload  # confirm it took the o1 branch

    @pytest.mark.asyncio
    async def test_no_effort_omits_reasoning_effort(self):
        payload = await self._capture_payload("gpt-4o", None)
        assert "reasoning_effort" not in payload


class TestClaudeSDKEffortOption:
    """Effort must reach the outgoing ClaudeAgentOptions, not just self._effort."""

    def test_build_agent_options_sets_effort(self, tmp_path):
        provider = ClaudeSDKProvider(model="claude-opus-4-8", effort="high")
        options = provider.build_agent_options(cwd=str(tmp_path))
        assert options.effort == "high"

    def test_build_agent_options_omits_effort_when_unset(self, tmp_path):
        provider = ClaudeSDKProvider(model="claude-opus-4-8")
        options = provider.build_agent_options(cwd=str(tmp_path))
        assert getattr(options, "effort", None) is None
