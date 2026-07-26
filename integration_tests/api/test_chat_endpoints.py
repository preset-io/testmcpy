"""Integration tests for /api/chat and /api/chat/stream.

Covers the selected-profile auth routing (the LLM provider must receive the
SELECTED MCP profile's mcp_url/auth, not the default profile's) and the
TESTMCPY_CHAT_OAUTH_LOGIN-gated interactive OAuth re-login path.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from testmcpy.src.mcp_client import MCPToolResult

OAUTH_ERROR = ValueError(
    "No usable cached OAuth token for http://mock-mcp:3000/mcp. Authenticate the MCP profile first."
)


def make_fake_provider(init_error: Exception | None = None) -> AsyncMock:
    """Build a fake LLM provider whose generate_with_tools returns a plain result."""
    provider = AsyncMock()
    if init_error is not None:
        provider.initialize.side_effect = init_error
    provider.generate_with_tools.return_value = SimpleNamespace(
        response="hello",
        tool_calls=[],
        tool_results=[],
        thinking=None,
        token_usage={"prompt": 1, "completion": 1, "total": 2},
        cost=0.0,
        duration=0.1,
    )
    return provider


CHAT_BODY = {
    "message": "hey",
    "model": "claude-sonnet-4-6",
    "provider": "anthropic",
    "profiles": ["test:Test MCP"],
}


class TestChatSelectedProfileAuth:
    """The provider factory must receive the selected profile's mcp_url/auth."""

    def test_chat_passes_selected_profile_mcp_url_and_auth(self, client, mock_mcp_client):
        mock_mcp_client.auth_config = {"type": "oauth", "oauth_auto_discover": True}
        with patch(
            "testmcpy.server.api.create_llm_provider", return_value=make_fake_provider()
        ) as factory:
            res = client.post("/api/chat", json=CHAT_BODY)
        assert res.status_code == 200
        assert res.json()["response"] == "hello"
        kwargs = factory.call_args.kwargs
        assert kwargs["mcp_url"] == mock_mcp_client.base_url
        assert kwargs["auth"] == {"type": "oauth", "oauth_auto_discover": True}

    def test_chat_and_generic_stream_forward_saved_history(self, client):
        history = [
            {"role": "system", "content": "Answer concisely."},
            {"role": "user", "content": "My project is Atlas."},
            {"role": "assistant", "content": "Understood."},
        ]
        body = {**CHAT_BODY, "history": history, "message": "What is my project?"}

        regular_provider = make_fake_provider()
        with patch("testmcpy.server.api.create_llm_provider", return_value=regular_provider):
            regular_response = client.post("/api/chat", json=body)

        stream_provider = make_fake_provider()
        with patch("testmcpy.server.api.create_llm_provider", return_value=stream_provider):
            stream_response = client.post("/api/chat/stream", json=body)

        assert regular_response.status_code == 200
        assert stream_response.status_code == 200
        assert regular_provider.generate_with_tools.await_args.kwargs["messages"] == history
        assert stream_provider.generate_with_tools.await_args.kwargs["messages"] == history

    def test_chat_provider_failures_are_errors_not_successful_assistant_turns(self, client):
        regular_provider = make_fake_provider()
        regular_provider.generate_with_tools.return_value.error = "provider unavailable"
        stream_provider = make_fake_provider()
        stream_provider.generate_with_tools.return_value.error = "provider unavailable"

        with patch(
            "testmcpy.server.api.create_llm_provider",
            side_effect=[regular_provider, stream_provider],
        ):
            regular_response = client.post("/api/chat", json=CHAT_BODY)
            stream_response = client.post("/api/chat/stream", json=CHAT_BODY)

        assert regular_response.status_code == 500
        assert regular_response.json()["detail"] == "provider unavailable"
        events = [
            json.loads(line.removeprefix("data: "))
            for line in stream_response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert {event["type"] for event in events} >= {"status", "error"}
        assert [event["data"] for event in events if event["type"] == "error"] == [
            "provider unavailable"
        ]
        assert not any(event["type"] == "complete" for event in events)

    def test_chat_stream_errors_when_tool_loop_exhausts_without_final_answer(
        self, client, mock_mcp_client
    ):
        provider = make_fake_provider()
        provider.generate_with_tools.return_value = SimpleNamespace(
            response="",
            tool_calls=[{"name": "health_check", "arguments": {}, "id": "repeat-call"}],
            tool_results=[],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
            error=None,
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert provider.generate_with_tools.await_count == 10
        assert mock_mcp_client.call_tool.await_count == 10
        assert [event["data"] for event in events if event["type"] == "error"] == [
            "Stopped after 10 tool turns before the model produced a final answer."
        ]
        assert not any(event["type"] == "complete" for event in events)

    def test_chat_stream_budgets_outbound_history_but_reports_what_stays_saved(self, client):
        provider = make_fake_provider()
        oversized_answer = "x" * 300_000
        history = [
            {"role": "system", "content": "Keep project facts."},
            {"role": "user", "content": "Old question"},
            {"role": "assistant", "content": oversized_answer},
            {"role": "user", "content": "My project is Atlas."},
            {"role": "assistant", "content": "Understood."},
        ]
        body = {
            **CHAT_BODY,
            "model": "gpt-4o",
            "provider": "openai",
            "history": history,
            "message": "What is my project?",
        }

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat/stream", json=body)

        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        notices = [event["data"] for event in events if event["type"] == "context_trimmed"]
        assert notices == [
            {
                "omitted_messages": 1,
                "original_messages": 5,
                "sent_messages": 4,
                "context_window": 128000,
                "model": "gpt-4o",
                "system_truncated": False,
            }
        ]
        sent_history = provider.generate_with_tools.await_args.kwargs["messages"]
        assert {message["content"] for message in sent_history} == {
            "Keep project facts.",
            "Old question",
            "My project is Atlas.",
            "Understood.",
        }
        assert oversized_answer not in {message["content"] for message in sent_history}
        assert any(event["type"] == "complete" for event in events)

    def test_chat_response_reports_budgeted_history(self, client):
        provider = make_fake_provider()
        oversized_answer = "x" * 300_000
        body = {
            **CHAT_BODY,
            "model": "gpt-4o",
            "provider": "openai",
            "history": [
                {"role": "system", "content": "Keep project facts."},
                {"role": "user", "content": "Old question"},
                {"role": "assistant", "content": oversized_answer},
                {"role": "user", "content": "My project is Atlas."},
                {"role": "assistant", "content": "Understood."},
            ],
            "message": "What is my project?",
        }

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat", json=body)

        assert response.status_code == 200
        assert response.json()["context_trimmed"] == {
            "omitted_messages": 1,
            "original_messages": 5,
            "sent_messages": 4,
            "context_window": 128000,
            "model": "gpt-4o",
            "system_truncated": False,
        }
        assert oversized_answer not in {
            message["content"]
            for message in provider.generate_with_tools.await_args.kwargs["messages"]
        }

    def test_chat_uses_native_results_without_replaying_tool_calls(self, client, mock_mcp_client):
        native_provider = make_fake_provider()
        native_provider.generate_with_tools.return_value = SimpleNamespace(
            response="created once",
            tool_calls=[{"name": "health_check", "arguments": {"mutate": True}, "id": "native-1"}],
            tool_results=[
                {
                    "tool_call_id": "native-1",
                    "content": "already executed by provider",
                    "is_error": False,
                }
            ],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=native_provider):
            native_response = client.post("/api/chat", json=CHAT_BODY)

        assert native_response.status_code == 200
        assert native_response.json()["tool_calls"][0]["result"] == ("already executed by provider")
        mock_mcp_client.call_tool.assert_not_awaited()

        non_native_provider = make_fake_provider()
        non_native_provider.generate_with_tools.return_value = SimpleNamespace(
            response="execute through MCP",
            tool_calls=[{"name": "health_check", "arguments": {}, "id": "mcp-1"}],
            tool_results=[],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=non_native_provider):
            non_native_response = client.post("/api/chat", json=CHAT_BODY)

        assert non_native_response.status_code == 200
        assert non_native_response.json()["tool_calls"][0]["result"] == "OK"
        mock_mcp_client.call_tool.assert_awaited_once()

    def test_chat_pairs_sparse_native_results_by_tool_call_id(self, client, mock_mcp_client):
        provider = make_fake_provider()
        provider.generate_with_tools.return_value = SimpleNamespace(
            response="partial native execution",
            tool_calls=[
                {"name": "health_check", "arguments": {}, "id": "native-1"},
                {"name": "get_data", "arguments": {"id": "42"}, "id": "native-2"},
            ],
            tool_results=[
                MCPToolResult(tool_call_id="native-2", content="second result"),
            ],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat", json=CHAT_BODY)

        assert response.status_code == 200
        tool_calls = response.json()["tool_calls"]
        assert tool_calls[0]["result"] is None
        assert tool_calls[0]["error"] == "Provider did not return a result for this tool call"
        assert tool_calls[1]["result"] == "second result"
        mock_mcp_client.call_tool.assert_not_awaited()

    def test_chat_pairs_reordered_native_results_by_tool_call_id(self, client, mock_mcp_client):
        provider = make_fake_provider()
        provider.generate_with_tools.return_value = SimpleNamespace(
            response="reordered native execution",
            tool_calls=[
                {"name": "health_check", "arguments": {}, "id": "native-1"},
                {"name": "get_data", "arguments": {"id": "42"}, "id": "native-2"},
            ],
            tool_results=[
                {"tool_call_id": "native-2", "content": "second result"},
                {"tool_call_id": "native-1", "content": "first result"},
            ],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat", json=CHAT_BODY)

        assert response.status_code == 200
        assert [call["result"] for call in response.json()["tool_calls"]] == [
            "first result",
            "second result",
        ]
        mock_mcp_client.call_tool.assert_not_awaited()

    def test_chat_uses_positional_native_results_only_when_complete(self, client, mock_mcp_client):
        provider = make_fake_provider()
        provider.generate_with_tools.return_value = SimpleNamespace(
            response="idless native execution",
            tool_calls=[
                {"name": "health_check", "arguments": {}, "id": "native-1"},
                {"name": "get_data", "arguments": {"id": "42"}, "id": "native-2"},
            ],
            tool_results=[{"content": "first result"}, {"content": "second result"}],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            complete = client.post("/api/chat", json=CHAT_BODY)

        assert [call["result"] for call in complete.json()["tool_calls"]] == [
            "first result",
            "second result",
        ]

        provider.generate_with_tools.return_value.tool_results = [{"content": "ambiguous result"}]
        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            partial = client.post("/api/chat", json=CHAT_BODY)

        assert partial.status_code == 200
        assert [call["result"] for call in partial.json()["tool_calls"]] == [None, None]
        assert all(call["is_error"] for call in partial.json()["tool_calls"])
        mock_mcp_client.call_tool.assert_not_awaited()

    def test_chat_stream_does_not_replay_non_claude_sdk_tool_calls(self, client, mock_mcp_client):
        from testmcpy.src.llm_integration import CodexSDKProvider

        provider = CodexSDKProvider(model="codex-o3", openai_api_key="sk-test")
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.generate_with_tools = AsyncMock(
            return_value=SimpleNamespace(
                response="native SDK response",
                tool_calls=[
                    {"name": "health_check", "arguments": {}, "id": "native-1"},
                    {"name": "get_data", "arguments": {"id": "42"}, "id": "native-2"},
                ],
                tool_results=[
                    MCPToolResult(tool_call_id="native-2", content="second result"),
                ],
                thinking=None,
                token_usage=None,
                cost=0.0,
                duration=0.1,
            )
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        assert response.status_code == 200
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        tool_results = [event["data"] for event in events if event["type"] == "tool_result"]
        assert tool_results[0]["result"] is None
        assert tool_results[1]["result"] == "second result"
        provider.generate_with_tools.assert_awaited_once()
        mock_mcp_client.call_tool.assert_not_awaited()

    def test_chat_accepts_gemini_native_results_with_matching_ids(self, client, mock_mcp_client):
        from testmcpy.src.llm_integration import GeminiSDKProvider

        provider = GeminiSDKProvider(model="gemini-sdk-flash", api_key="AIza-test")
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.generate_with_tools = AsyncMock(
            return_value=SimpleNamespace(
                response="native Gemini response",
                tool_calls=[
                    {"name": "health_check", "arguments": {}, "id": "gemini-call-1"},
                ],
                tool_results=[
                    MCPToolResult(
                        tool_call_id="gemini-call-1",
                        content={"status": "healthy"},
                    ),
                ],
                thinking=None,
                token_usage=None,
                cost=0.0,
                duration=0.1,
            )
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat", json=CHAT_BODY)

        assert response.status_code == 200
        assert response.json()["tool_calls"][0]["result"] == {"status": "healthy"}
        mock_mcp_client.call_tool.assert_not_awaited()

    def test_chat_sdk_missing_native_results_fails_closed(self, client, mock_mcp_client):
        from testmcpy.src.llm_integration import CodexSDKProvider

        provider = CodexSDKProvider(model="codex-o3", openai_api_key="sk-test")
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.generate_with_tools = AsyncMock(
            return_value=SimpleNamespace(
                response="SDK contract violation",
                tool_calls=[
                    {"name": "health_check", "arguments": {}, "id": "native-1"},
                ],
                tool_results=[],
                thinking=None,
                token_usage=None,
                cost=0.0,
                duration=0.1,
            )
        )

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat", json=CHAT_BODY)

        assert response.status_code == 200
        tool_call = response.json()["tool_calls"][0]
        assert tool_call["result"] is None
        assert tool_call["is_error"] is True
        assert tool_call["error"] == "Provider did not return a result for this tool call"
        mock_mcp_client.call_tool.assert_not_awaited()

    def test_chat_rejects_explicit_missing_llm_profile(self, client):
        response = client.post(
            "/api/chat",
            json={
                "message": "hey",
                "llm_profile": "missing",
                "profiles": ["test:Test MCP"],
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "LLM profile 'missing' was not found"

    def test_chat_treats_blank_llm_profile_as_unselected(self, client):
        body = {**CHAT_BODY, "llm_profile": ""}
        with patch("testmcpy.server.api.create_llm_provider", return_value=make_fake_provider()):
            response = client.post("/api/chat", json=body)

        assert response.status_code == 200

    def test_chat_reports_malformed_profile_config_as_conflict(self, client):
        Path(".llm_providers.yaml").write_text("profiles: [not-a-mapping]\n")

        response = client.post(
            "/api/chat",
            json={"message": "hey", "llm_profile": "missing"},
        )

        assert response.status_code == 409
        assert "Invalid LLM profile configuration" in response.json()["detail"]

    def test_chat_stream_reports_malformed_profile_config_detail(self, client):
        Path(".llm_providers.yaml").write_text("profiles: [not-a-mapping]\n")

        response = client.post(
            "/api/chat/stream",
            json={"message": "hey", "profiles": ["test:Test MCP"]},
        )

        assert response.status_code == 200
        assert "Invalid LLM profile configuration" in response.text
        assert "Internal error" not in response.text

    def test_chat_stream_passes_selected_profile_mcp_url_and_auth(self, client, mock_mcp_client):
        mock_mcp_client.auth_config = {"type": "oauth", "oauth_auto_discover": True}
        with patch(
            "testmcpy.server.api.create_llm_provider", return_value=make_fake_provider()
        ) as factory:
            res = client.post("/api/chat/stream", json=CHAT_BODY)
        assert res.status_code == 200
        assert '"type": "complete"' in res.text or '"complete"' in res.text
        kwargs = factory.call_args.kwargs
        assert kwargs["mcp_url"] == mock_mcp_client.base_url
        assert kwargs["auth"] == {"type": "oauth", "oauth_auto_discover": True}

    def test_chat_stream_replays_history_in_dedicated_claude_sdk_prompt(self, client):
        from testmcpy.src.llm_integration import ClaudeSDKProvider

        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url="https://mock-mcp:3000/mcp",
            auth={"type": "none"},
        )
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.start_insecure_mcp_proxy = AsyncMock(return_value=None)
        provider.build_agent_options = MagicMock(return_value=SimpleNamespace())
        captured = {}

        async def fake_sdk_query(*, prompt, options):
            captured["prompt"] = prompt
            captured["options"] = options
            if False:
                yield None

        body = {
            **CHAT_BODY,
            "history": [
                {"role": "system", "content": "Answer concisely."},
                {"role": "user", "content": "My project is Atlas."},
                {"role": "assistant", "content": "Understood."},
            ],
            "message": "What is my project?",
        }
        with (
            patch("claude_agent_sdk.query", new=fake_sdk_query),
            patch("testmcpy.server.api.create_llm_provider", return_value=provider),
        ):
            response = client.post("/api/chat/stream", json=body)

        assert response.status_code == 200
        assert '"type": "complete"' in response.text
        instruction, encoded_transcript = captured["prompt"].split("\n\n", 1)
        assert "answer only current_user" in instruction
        assert json.loads(encoded_transcript) == {
            "system": None,
            "messages": [
                {"role": "user", "content": "My project is Atlas."},
                {"role": "assistant", "content": "Understood."},
            ],
            "current_user": "What is my project?",
        }
        assert provider.build_agent_options.call_args.kwargs["saved_system_prompt"] == (
            "Answer concisely."
        )
        provider.start_insecure_mcp_proxy.assert_awaited_once()
        provider.close.assert_awaited_once()

    def test_sdk_turn_start_omits_max_turns(self, client):
        # The SDK path's sdk_turn counts streamed tool-result batches, not a hard
        # cap, so its turn_start events must NOT carry a denominator — the UI
        # renders a bare "Turn n". Regression guard for the PR #118 fix.
        from testmcpy.src.llm_integration import ClaudeSDKProvider

        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url="https://mock-mcp:3000/mcp",
            auth={"type": "none"},
        )
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.start_insecure_mcp_proxy = AsyncMock(return_value=None)
        provider.build_agent_options = MagicMock(return_value=SimpleNamespace())

        async def fake_sdk_query(*, prompt, options):
            if False:
                yield None

        with (
            patch("claude_agent_sdk.query", new=fake_sdk_query),
            patch("testmcpy.server.api.create_llm_provider", return_value=provider),
        ):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        turn_starts = [e["data"] for e in events if e["type"] == "turn_start"]
        assert turn_starts, "expected at least one SDK turn_start event"
        assert all("max_turns" not in ts for ts in turn_starts)

    def test_manual_turn_start_includes_max_turns_10(self, client, mock_mcp_client):
        # The non-SDK manual loop DOES hard-stop at 10, so its turn_start events
        # keep max_turns: 10 (the "Turn n/10" the UI still shows for that path).
        provider = make_fake_provider()
        provider.generate_with_tools.return_value = SimpleNamespace(
            response="",
            tool_calls=[{"name": "health_check", "arguments": {}, "id": "c1"}],
            tool_results=[],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
            error=None,
        )
        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        turn_starts = [e["data"] for e in events if e["type"] == "turn_start"]
        assert turn_starts, "expected at least one manual turn_start event"
        assert all(ts.get("max_turns") == 10 for ts in turn_starts)

    def test_chat_stream_does_not_complete_after_claude_sdk_stream_error(self, client):
        from claude_agent_sdk import ClaudeSDKError

        from testmcpy.src.llm_integration import ClaudeSDKProvider

        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url="https://mock-mcp:3000/mcp",
            auth={"type": "none"},
        )
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.start_insecure_mcp_proxy = AsyncMock(return_value=None)
        provider.build_agent_options = MagicMock(return_value=SimpleNamespace())

        async def failing_sdk_query(*, prompt, options):
            del prompt, options
            raise ClaudeSDKError("SDK stream failed")
            yield  # pragma: no cover - makes this an async generator

        with (
            patch("claude_agent_sdk.query", new=failing_sdk_query),
            patch("testmcpy.server.api.create_llm_provider", return_value=provider),
        ):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert [event["data"] for event in events if event["type"] == "error"] == [
            "SDK stream failed"
        ]
        assert not any(event["type"] == "complete" for event in events)
        provider.close.assert_awaited_once()

    def test_chat_stream_treats_claude_error_result_as_terminal_error(self, client):
        from claude_agent_sdk import ResultMessage

        from testmcpy.src.llm_integration import ClaudeSDKProvider

        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url="https://mock-mcp:3000/mcp",
            auth={"type": "none"},
        )
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        provider.start_insecure_mcp_proxy = AsyncMock(return_value=None)
        provider.build_agent_options = MagicMock(return_value=SimpleNamespace())

        async def error_result_sdk_query(*, prompt, options):
            del prompt, options
            yield ResultMessage(
                subtype="error_during_execution",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                result="Request failed",
                errors=["rate limit exceeded"],
            )

        with (
            patch("claude_agent_sdk.query", new=error_result_sdk_query),
            patch("testmcpy.server.api.create_llm_provider", return_value=provider),
        ):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert [event["data"] for event in events if event["type"] == "error"] == [
            "rate limit exceeded"
        ]
        assert not any(event["type"] == "complete" for event in events)
        provider.close.assert_awaited_once()

    def test_chat_stream_isolates_claude_from_unselected_mcp_configs(self, client):
        from testmcpy.src.llm_integration import ClaudeSDKProvider

        # This project server must never leak into the Claude subprocess.
        Path(".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "offline": {
                            "type": "http",
                            "url": "https://localhost/mcp",
                        }
                    }
                }
            )
        )

        selected_server = {
            "type": "http",
            "url": "https://mock-mcp:3000/mcp",
            "headers": {"Authorization": "Bearer selected-token"},
        }
        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url=selected_server["url"],
            auth={"type": "none", "insecure": True},
        )
        provider._mcp_server_config = selected_server
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        captured = {}
        original_start_proxy = provider.start_insecure_mcp_proxy

        async def capture_proxy():
            proxy = await original_start_proxy()
            captured["proxy"] = proxy
            original_close_proxy = proxy.close

            async def close_proxy():
                captured["iterator_closed_before_proxy"] = captured.get("iterator_closed", False)
                await original_close_proxy()

            proxy.close = close_proxy
            return proxy

        provider.start_insecure_mcp_proxy = capture_proxy

        async def fake_sdk_query(*, prompt, options):
            try:
                captured["prompt"] = prompt
                captured["options"] = options
                captured["cwd_exists_during_query"] = Path(options.cwd).is_dir()
                if False:
                    yield None
            finally:
                captured["iterator_closed"] = True

        with (
            patch("claude_agent_sdk.query", new=fake_sdk_query),
            patch("testmcpy.server.api.create_llm_provider", return_value=provider),
        ):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        assert response.status_code == 200
        assert '"type": "complete"' in response.text
        options = captured["options"]
        assert captured["prompt"] == CHAT_BODY["message"]
        selected_config = options.mcp_servers["mcp-service"]
        assert selected_config["url"].startswith("http://127.0.0.1:")
        assert "headers" not in selected_config
        assert options.extra_args == {"strict-mcp-config": None}
        assert options.tools == ["ToolSearch"]
        assert options.disallowed_tools == []
        assert options.system_prompt == provider._MCP_TOOL_SEARCH_SYSTEM_PROMPT
        assert "NODE_TLS_REJECT_UNAUTHORIZED" not in options.env
        assert captured["cwd_exists_during_query"] is True
        assert Path(options.cwd) != Path.cwd()
        assert not Path(options.cwd).exists()
        assert captured["proxy"]._runner is None
        assert captured["proxy"]._session is None
        assert captured["iterator_closed_before_proxy"] is True

    def test_chat_stream_cleans_isolated_cwd_when_option_building_fails(self, client):
        from testmcpy.src.llm_integration import ClaudeSDKProvider

        provider = ClaudeSDKProvider(
            model="claude-sonnet-4-6",
            mcp_url="https://mcp.example.test/mcp",
            auth={"type": "none", "insecure": True},
        )
        provider._mcp_server_config = {
            "type": "http",
            "url": provider.mcp_url,
        }
        provider.initialize = AsyncMock()
        provider.close = AsyncMock()
        captured = {}
        original_start_proxy = provider.start_insecure_mcp_proxy

        async def capture_proxy():
            proxy = await original_start_proxy()
            captured["proxy"] = proxy
            return proxy

        provider.start_insecure_mcp_proxy = capture_proxy

        def fail_build(**kwargs):
            captured["cwd"] = Path(kwargs["cwd"])
            assert captured["cwd"].is_dir()
            raise RuntimeError("SDK options failed")

        provider.build_agent_options = MagicMock(side_effect=fail_build)
        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat/stream", json=CHAT_BODY)

        assert response.status_code == 200
        assert "Internal error: RuntimeError" in response.text
        assert not captured["cwd"].exists()
        assert captured["proxy"]._runner is None
        assert captured["proxy"]._session is None
        provider.close.assert_awaited_once()

    def test_chat_resolves_profile_api_key_env(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "runtime-profile-key")
        Path(".llm_providers.yaml").write_text(
            """
default: env-profile
profiles:
  env-profile:
    name: Environment profile
    providers:
      - name: Claude
        provider: anthropic
        model: claude-test
        api_key_env: ANTHROPIC_API_KEY
        default: true
"""
        )
        body = {
            "message": "hey",
            "llm_profile": "env-profile",
            "profiles": ["test:Test MCP"],
        }

        with patch(
            "testmcpy.server.api.create_llm_provider", return_value=make_fake_provider()
        ) as factory:
            response = client.post("/api/chat", json=body)

        assert response.status_code == 200
        assert factory.call_args.kwargs["api_key"] == "runtime-profile-key"

    def test_chat_openai_profile_missing_bound_env_never_uses_ambient_key(
        self, client, monkeypatch
    ):
        ambient_secret = "ambient-openai-key-must-not-be-used"
        monkeypatch.setenv("OPENAI_API_KEY", ambient_secret)
        monkeypatch.delenv("PROFILE_OPENAI_KEY", raising=False)
        Path(".llm_providers.yaml").write_text(
            """
profiles:
  isolated:
    name: Isolated OpenAI
    providers:
      - name: OpenAI
        provider: openai
        model: gpt-test
        api_key_env: PROFILE_OPENAI_KEY
"""
        )

        with patch("testmcpy.server.api.create_llm_provider") as factory:
            response = client.post(
                "/api/chat",
                json={
                    "message": "hey",
                    "llm_profile": "isolated",
                    "profiles": ["test:Test MCP"],
                },
            )

        assert response.status_code == 409
        assert "configured API key" in response.json()["detail"]
        assert ambient_secret not in response.text
        factory.assert_not_called()

    def test_chat_default_profile_missing_bound_env_never_uses_ambient_key(
        self, client, monkeypatch
    ):
        ambient_secret = "ambient-default-key-must-not-be-used"
        monkeypatch.setenv("OPENAI_API_KEY", ambient_secret)
        monkeypatch.delenv("PROFILE_OPENAI_KEY", raising=False)
        Path(".llm_providers.yaml").write_text(
            """
default: isolated
profiles:
  isolated:
    name: Isolated OpenAI
    providers:
      - name: OpenAI
        provider: openai
        model: gpt-test
        api_key_env: PROFILE_OPENAI_KEY
"""
        )

        with patch("testmcpy.server.api.create_llm_provider") as factory:
            response = client.post(
                "/api/chat",
                json={
                    "message": "hey",
                    "profiles": ["test:Test MCP"],
                },
            )

        assert response.status_code == 409
        assert "configured API key" in response.json()["detail"]
        assert ambient_secret not in response.text
        factory.assert_not_called()

    def test_chat_anthropic_profile_blank_key_expression_never_uses_ambient_key(
        self, client, monkeypatch
    ):
        ambient_secret = "ambient-anthropic-key-must-not-be-used"
        monkeypatch.setenv("ANTHROPIC_API_KEY", ambient_secret)
        monkeypatch.delenv("PROFILE_ANTHROPIC_KEY", raising=False)
        Path(".llm_providers.yaml").write_text(
            """
profiles:
  isolated:
    name: Isolated Anthropic
    providers:
      - name: Anthropic
        provider: anthropic
        model: claude-test
        api_key: ${PROFILE_ANTHROPIC_KEY}
"""
        )

        with patch("testmcpy.server.api.create_llm_provider") as factory:
            response = client.post(
                "/api/chat",
                json={
                    "message": "hey",
                    "llm_profile": "isolated",
                    "profiles": ["test:Test MCP"],
                },
            )

        assert response.status_code == 409
        assert "configured API key" in response.json()["detail"]
        assert ambient_secret not in response.text
        factory.assert_not_called()

    def test_chat_passes_complete_assistant_profile_runtime_config(self, client):
        Path(".llm_providers.yaml").write_text(
            """
default: assistant-profile
profiles:
  assistant-profile:
    name: Assistant profile
    providers:
      - name: Assistant
        provider: assistant
        model: assistant-model
        workspace_hash: workspace-1
        domain: example.test
        api_token: token-1
        api_secret: secret-1
        api_url: https://example.test/auth
        conversations_path: /conversations
        completions_path: /completions
        default: true
"""
        )
        body = {
            "message": "hey",
            "llm_profile": "assistant-profile",
            "profiles": ["test:Test MCP"],
        }

        with patch(
            "testmcpy.server.api.create_llm_provider", return_value=make_fake_provider()
        ) as factory:
            response = client.post("/api/chat", json=body)

        assert response.status_code == 200
        kwargs = factory.call_args.kwargs
        assert factory.call_args.args == ("assistant", "assistant-model")
        assert kwargs["workspace_hash"] == "workspace-1"
        assert kwargs["domain"] == "example.test"
        assert kwargs["api_token"] == "token-1"
        assert kwargs["api_secret"] == "secret-1"
        assert kwargs["api_url"] == "https://example.test/auth"

    def test_chat_and_stream_scrub_profile_key_echoed_by_provider(self, client):
        secret = "profile-openai-secret-12345"
        Path(".llm_providers.yaml").write_text(
            f"""
default: redaction-profile
profiles:
  redaction-profile:
    name: Redaction profile
    providers:
      - name: OpenAI
        provider: openai
        model: gpt-test
        api_key: {secret}
        default: true
"""
        )
        provider = make_fake_provider()
        provider.generate_with_tools.return_value = SimpleNamespace(
            response=f"Error: upstream echoed Bearer {secret}",
            tool_calls=[],
            thinking=f"debug {secret}",
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )
        body = {
            "message": "hey",
            "llm_profile": "redaction-profile",
            "profiles": ["test:Test MCP"],
        }

        with patch("testmcpy.server.api.create_llm_provider", return_value=provider):
            response = client.post("/api/chat", json=body)
            stream_response = client.post("/api/chat/stream", json=body)

        assert response.status_code == 200
        assert stream_response.status_code == 200
        assert secret not in response.text
        assert secret not in stream_response.text
        assert "***REDACTED***" in response.text
        assert "***REDACTED***" in stream_response.text

    def test_chat_and_stream_close_provider_after_generation_error(self, client):
        regular_provider = make_fake_provider()
        regular_provider.generate_with_tools.side_effect = RuntimeError("generation failed")
        stream_provider = make_fake_provider()
        stream_provider.generate_with_tools.side_effect = RuntimeError("generation failed")

        with patch(
            "testmcpy.server.api.create_llm_provider",
            side_effect=[regular_provider, stream_provider],
        ):
            regular = client.post("/api/chat", json=CHAT_BODY)
            streamed = client.post("/api/chat/stream", json=CHAT_BODY)

        assert regular.status_code == 500
        assert streamed.status_code == 200
        regular_provider.close.assert_awaited_once()
        stream_provider.close.assert_awaited_once()


class TestChatOAuthLoginFlag:
    """TESTMCPY_CHAT_OAUTH_LOGIN gates the interactive OAuth re-login retry."""

    def test_flag_off_oauth_error_surfaces(self, client, monkeypatch):
        monkeypatch.setenv("TESTMCPY_CHAT_OAUTH_LOGIN", "false")
        relogin_client = AsyncMock()
        with (
            patch(
                "testmcpy.server.api.create_llm_provider",
                return_value=make_fake_provider(init_error=OAUTH_ERROR),
            ),
            patch("testmcpy.server.api.get_mcp_client_for_server", relogin_client),
        ):
            res = client.post("/api/chat", json=CHAT_BODY)
        assert res.status_code == 500
        assert "No usable cached OAuth token" in res.json()["detail"]
        # Awaited once by the endpoint's normal client resolution — no re-login.
        assert relogin_client.await_count == 1

    def test_flag_off_stream_emits_error_event(self, client, monkeypatch):
        monkeypatch.setenv("TESTMCPY_CHAT_OAUTH_LOGIN", "0")
        with patch(
            "testmcpy.server.api.create_llm_provider",
            return_value=make_fake_provider(init_error=OAUTH_ERROR),
        ):
            res = client.post("/api/chat/stream", json=CHAT_BODY)
        assert res.status_code == 200
        assert '"error"' in res.text
        assert "No usable cached OAuth token" in res.text

    def test_flag_on_chat_retries_after_relogin(self, client, monkeypatch):
        monkeypatch.delenv("TESTMCPY_CHAT_OAUTH_LOGIN", raising=False)  # default ON
        failing = make_fake_provider(init_error=OAUTH_ERROR)
        working = make_fake_provider()
        relogin_client = AsyncMock()
        with (
            patch(
                "testmcpy.server.api.create_llm_provider",
                side_effect=[failing, working],
            ),
            patch("testmcpy.server.api.get_mcp_client_for_server", relogin_client),
        ):
            res = client.post("/api/chat", json=CHAT_BODY)
        assert res.status_code == 200
        assert res.json()["response"] == "hello"
        # Resolution + re-login.
        assert relogin_client.await_count == 2
        assert relogin_client.await_args.args == ("test", "Test MCP")

    def test_flag_on_stream_emits_oauth_status_and_completes(self, client, monkeypatch):
        monkeypatch.delenv("TESTMCPY_CHAT_OAUTH_LOGIN", raising=False)  # default ON
        failing = make_fake_provider(init_error=OAUTH_ERROR)
        working = make_fake_provider()
        relogin_client = AsyncMock()
        with (
            patch(
                "testmcpy.server.api.create_llm_provider",
                side_effect=[failing, working],
            ),
            patch("testmcpy.server.api.get_mcp_client_for_server", relogin_client),
        ):
            res = client.post("/api/chat/stream", json=CHAT_BODY)
        assert res.status_code == 200
        assert "Waiting for OAuth login in browser..." in res.text
        # Resolution + re-login.
        assert relogin_client.await_count == 2
        assert relogin_client.await_args.args == ("test", "Test MCP")

    def test_flag_on_non_oauth_value_error_not_retried(self, client, monkeypatch):
        monkeypatch.delenv("TESTMCPY_CHAT_OAUTH_LOGIN", raising=False)
        relogin_client = AsyncMock()
        with (
            patch(
                "testmcpy.server.api.create_llm_provider",
                return_value=make_fake_provider(init_error=ValueError("API key missing")),
            ),
            patch("testmcpy.server.api.get_mcp_client_for_server", relogin_client),
        ):
            res = client.post("/api/chat", json=CHAT_BODY)
        assert res.status_code == 500
        assert "API key missing" in res.json()["detail"]
        # Awaited once by the endpoint's normal client resolution — no re-login.
        assert relogin_client.await_count == 1

    def test_flag_on_tool_execution_uses_refreshed_client(self, client, monkeypatch):
        """After re-login the old clients are closed; tools must run on the new ones."""
        monkeypatch.delenv("TESTMCPY_CHAT_OAUTH_LOGIN", raising=False)  # default ON

        tool = MagicMock()
        tool.name = "health_check"
        tool.description = "Check health"
        tool.input_schema = {"type": "object", "properties": {}}

        tool_result = MagicMock()
        tool_result.content = "OK"
        tool_result.is_error = False
        tool_result.error_message = None

        old_client = AsyncMock()
        old_client.base_url = "http://mock-mcp:3000/mcp"
        old_client.auth_config = {"type": "oauth", "oauth_auto_discover": True}
        old_client.list_tools.return_value = [tool]
        new_client = AsyncMock()
        new_client.base_url = "http://mock-mcp:3000/mcp"
        new_client.auth_config = {"type": "oauth", "oauth_auto_discover": True}
        new_client.call_tool.return_value = tool_result

        failing = make_fake_provider(init_error=OAUTH_ERROR)
        working = make_fake_provider()
        working.generate_with_tools.return_value = SimpleNamespace(
            response="done",
            tool_calls=[{"name": "health_check", "arguments": {}, "id": "tc1"}],
            thinking=None,
            token_usage=None,
            cost=0.0,
            duration=0.1,
        )
        with (
            patch(
                "testmcpy.server.api.create_llm_provider",
                side_effect=[failing, working],
            ),
            patch(
                "testmcpy.server.api.get_mcp_client_for_server",
                AsyncMock(side_effect=[old_client, new_client]),
            ),
        ):
            res = client.post("/api/chat", json=CHAT_BODY)
        assert res.status_code == 200
        new_client.call_tool.assert_awaited_once()
        old_client.call_tool.assert_not_awaited()


class TestReloginBackoffInterplay:
    """_relogin_oauth_servers must clear back-off so the reconnect is immediate."""

    def test_relogin_clears_backoff(self, client):
        import asyncio

        from testmcpy.server import api as api_module

        api_module._record_failure("p:m")
        assert api_module._backoff_remaining("p:m") > 0
        with patch("testmcpy.server.api.get_mcp_client_for_server", AsyncMock()):
            asyncio.run(api_module._relogin_oauth_servers(["p:m"]))
        assert api_module._backoff_remaining("p:m") == 0.0

    def test_clear_cached_client_default_still_records_backoff(self, client, mock_mcp_client):
        import asyncio

        from testmcpy.server import api as api_module

        api_module._connection_backoff.pop("test:Test MCP", None)
        assert asyncio.run(api_module.clear_cached_client("test:Test MCP")) is True
        assert api_module._backoff_remaining("test:Test MCP") > 0
        api_module._connection_backoff.pop("test:Test MCP", None)
