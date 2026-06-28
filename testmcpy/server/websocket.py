"""
WebSocket support for streaming chat responses and test execution.
"""

import asyncio
import contextlib
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from fastapi import WebSocket, WebSocketDisconnect

from testmcpy.config import get_config
from testmcpy.server import run_registry
from testmcpy.server.run_persistence import RunRecord
from testmcpy.server.run_registry import RunHandle
from testmcpy.server.state import get_or_create_mcp_client
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPClient, MCPToolCall
from testmcpy.src.test_runner import TestCase, TestRunner

# How often a live run stamps its DB row's heartbeat_at. Must be much
# smaller than storage.mark_stale_runs_interrupted's cutoff (minutes) so
# a few missed beats never get a live run marked interrupted.
HEARTBEAT_INTERVAL_S = 30


def strip_mcp_prefix(tool_name: str) -> str:
    """Strip MCP namespace prefix from tool name.

    LLM providers may return tool names like 'mcp__testmcpy__list_charts'
    but the MCP server expects just 'list_charts'.
    """
    if "__" in tool_name:
        # Get the last part after the final __
        return tool_name.rsplit("__", 1)[-1]
    return tool_name


def _derive_workspace_and_domain_from_mcp_url(mcp_url: str) -> tuple[str | None, str | None]:
    """Split a Preset MCP URL into (workspace_hash, domain).

    Preset workspaces always live at `https://<workspace_hash>.<domain>/mcp`
    — the workspace hash is the leftmost subdomain. We use this when running
    a chatbot YAML from the UI: the selected MCP profile already encodes
    which workspace the chat tests should target, so we can populate the
    AssistantProvider's `workspace_hash`/`domain` automatically rather than
    forcing the user to duplicate that info in `.llm_providers.yaml`.

    Returns (None, None) if the URL is missing, lacks a host, has only one
    label, or is otherwise unparseable — the caller treats that as "no
    fallback available" and leaves the existing config untouched.
    """
    if not mcp_url:
        return None, None
    try:
        parsed = urlparse(mcp_url)
    except (ValueError, TypeError):
        return None, None
    host = parsed.hostname
    if not host or "." not in host:
        return None, None
    workspace, _, domain = host.partition(".")
    if not workspace or not domain:
        return None, None
    return workspace, domain


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


async def handle_chat_websocket(websocket: WebSocket, mcp_client: MCPClient):
    """
    Handle WebSocket chat connections with streaming responses.

    Message format from client:
    {
        "type": "chat",
        "message": "user message",
        "model": "claude-haiku-4-5",
        "provider": "anthropic"
    }

    Message format to client:
    {
        "type": "start" | "token" | "tool_call" | "tool_result" | "complete" | "error",
        "content": "...",
        "tool_name": "...",  # for tool_call
        "tool_args": {...},  # for tool_call
        "tool_result": {...},  # for tool_result
        "token_usage": {...},  # for complete
        "cost": 0.0,  # for complete
        "duration": 0.0  # for complete
    }
    """
    await manager.connect(websocket)
    config = get_config()

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            if data.get("type") == "chat":
                message = data.get("message", "")
                model = data.get("model") or config.default_model
                provider = data.get("provider") or config.default_provider

                # Send start message
                await manager.send_message(
                    {"type": "start", "content": "Processing your request..."}, websocket
                )

                try:
                    # Get available tools
                    tools = await mcp_client.list_tools()
                    formatted_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.input_schema,
                            },
                        }
                        for tool in tools
                    ]

                    # Initialize LLM provider
                    llm_provider = create_llm_provider(provider, model)
                    await llm_provider.initialize()

                    # Generate response
                    result = await llm_provider.generate_with_tools(
                        prompt=message, tools=formatted_tools, timeout=30.0
                    )

                    # Stream the response text token by token for better UX
                    response_text = result.response
                    chunk_size = 50  # Characters per chunk
                    for i in range(0, len(response_text), chunk_size):
                        chunk = response_text[i : i + chunk_size]
                        await manager.send_message({"type": "token", "content": chunk}, websocket)
                        await asyncio.sleep(0.05)  # Small delay for streaming effect

                    # Execute tool calls if any
                    if result.tool_calls:
                        for tool_call in result.tool_calls:
                            # Send tool call notification
                            await manager.send_message(
                                {
                                    "type": "tool_call",
                                    "tool_name": tool_call["name"],
                                    "tool_args": tool_call.get("arguments", {}),
                                },
                                websocket,
                            )

                            # Execute tool - strip MCP prefix if present
                            actual_tool_name = strip_mcp_prefix(tool_call["name"])
                            mcp_tool_call = MCPToolCall(
                                name=actual_tool_name,
                                arguments=tool_call.get("arguments", {}),
                                id=tool_call.get("id", "unknown"),
                            )
                            tool_result = await mcp_client.call_tool(mcp_tool_call)

                            # Send tool result
                            await manager.send_message(
                                {
                                    "type": "tool_result",
                                    "tool_name": tool_call["name"],
                                    "tool_result": {
                                        "content": tool_result.content,
                                        "is_error": tool_result.is_error,
                                        "error_message": tool_result.error_message,
                                    },
                                },
                                websocket,
                            )

                    # Send completion message
                    await manager.send_message(
                        {
                            "type": "complete",
                            "token_usage": result.token_usage,
                            "cost": result.cost,
                            "duration": result.duration,
                        },
                        websocket,
                    )

                    await llm_provider.close()

                except Exception as e:
                    await manager.send_message({"type": "error", "content": str(e)}, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


def _emit_log(handle: RunHandle, msg: str) -> None:
    """Publish a free-text log line through the registry. The registry
    buffers it AND forwards to whoever (if anyone) is currently attached."""
    run_registry.log(handle, msg)


def _emit_event(handle: RunHandle, event_msg: dict[str, Any]) -> None:
    """Publish a structured event (test_start / test_complete / file_start /
    all_complete / error) through the registry."""
    run_registry.event(handle, event_msg)


def _emit_run_error(
    handle: RunHandle,
    data: dict[str, Any],
    message: str,
    traceback: str | None = None,
) -> None:
    """Emit an error event with the right terminal vs non-terminal semantics.

    - When invoked OUTSIDE a directory batch (no ``_in_batch`` flag in
      ``data``), emit ``{type: "error"}`` — the client treats this as
      terminal (running=false, close WS).
    - When invoked INSIDE a directory batch (``_in_batch=True``), emit
      ``{type: "file_error"}`` — non-terminal: the client appends to logs
      and marks the file as failed in directoryRunProgress, but the batch
      keeps streaming files 2..N (SC-108217).

    Previously every per-file MCP-init crash terminated the whole batch
    on the client and left the server task running invisibly.
    """
    payload: dict[str, Any] = {"message": message}
    if traceback is not None:
        payload["traceback"] = traceback
    if data.get("_in_batch"):
        payload["type"] = "file_error"
        payload["test_path"] = data.get("test_path") or data.get("test_path_resolved")
    else:
        payload["type"] = "error"
    _emit_event(handle, payload)


def _display_test_file_name(test_path: Path) -> str:
    """Relativize ``test_path`` for history grouping: relative to ./tests
    when inside it, ``<extra-root-name>/<rel>`` for configured extra test
    dirs, bare filename otherwise."""
    from testmcpy.server.routers.tests import _extra_tests_dirs

    test_file_name = test_path.name
    tests_dir = Path.cwd() / "tests"
    try:
        resolved = test_path.resolve()
        if resolved.is_relative_to(tests_dir.resolve()):
            test_file_name = str(resolved.relative_to(tests_dir.resolve()))
        else:
            for extra_root in _extra_tests_dirs():
                extra_real = extra_root.resolve()
                if resolved.is_relative_to(extra_real):
                    test_file_name = f"{extra_root.name}/{resolved.relative_to(extra_real)}"
                    break
    except OSError:
        pass
    return test_file_name


def _inline_auth_from_data(data: dict[str, Any]) -> dict[str, Any] | None:
    """Build an MCPClient auth dict from ad-hoc connection fields in a run/
    benchmark message — the websocket equivalent of the CLI's
    ``--auth-type`` / ``--jwt-*`` / ``--auth-token`` flags. Returns ``None``
    when no ``auth_type`` is supplied (unauthenticated MCP server)."""
    auth_type = data.get("auth_type")
    if not auth_type:
        return None
    auth: dict[str, Any] = {"type": auth_type}
    if auth_type == "jwt":
        if data.get("jwt_url"):
            auth["api_url"] = data["jwt_url"]
        if data.get("jwt_token"):
            auth["api_token"] = data["jwt_token"]
        if data.get("jwt_secret"):
            auth["api_secret"] = data["jwt_secret"]
    elif auth_type == "bearer" and data.get("auth_token"):
        auth["token"] = data["auth_token"]
    elif auth_type == "api_key" and data.get("auth_token"):
        auth["api_key"] = data["auth_token"]
    return auth


def _assistant_config_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Assistant ``provider_config`` from ad-hoc connection fields — the
    websocket equivalent of the CLI's assistant flags (``--workspace-hash``,
    ``--domain``, ``--assistant-*``, with ``--jwt-*`` as the auth fallback).
    Only non-empty values are returned so callers can ``setdefault`` them
    without clobbering suite/profile-provided values."""
    fields = {
        "workspace_hash": data.get("workspace_hash"),
        "domain": data.get("domain"),
        "environment": data.get("environment"),
        "api_url": data.get("assistant_api_url") or data.get("jwt_url"),
        "api_token": data.get("assistant_api_token") or data.get("jwt_token"),
        "api_secret": data.get("assistant_api_secret") or data.get("jwt_secret"),
        "conversations_path": data.get("assistant_conversations_path"),
        "completions_path": data.get("assistant_completions_path"),
    }
    return {k: v for k, v in fields.items() if v}


async def _run_test_command(handle: RunHandle, data: dict, config) -> None:
    """Execute a single 'run_test' command tied to ``handle``.

    All output goes through the registry — no direct WebSocket I/O. Whoever
    is currently attached to ``handle`` will see the live stream; clients
    that disconnect mid-run can reattach later and get a replay of the
    buffered log lines + structured events from before they arrived.
    Cooperative cancellation is honored at every `await` point (Stop button).
    """
    test_path = Path(data.get("test_path", ""))
    test_name = data.get("test_name")
    model = data.get("model") or config.default_model
    provider = data.get("provider") or config.default_provider
    profile = data.get("profile")
    llm_profile_id = data.get("llm_profile")

    if not test_path.exists():
        _emit_run_error(handle, data, f"Test file not found: {test_path}")
        return

    _emit_log(handle, f"📁 Loading test file: {test_path}")

    # Incremental history record — begun once the runner is ready, appended
    # per test, finished on every exit path (crash-safe partial results).
    record: RunRecord | None = None
    # An ad-hoc MCP client we build ourselves (vs. a cached profile client) is
    # ours to close — TestRunner won't, since we pass it in already-initialized
    # (so its _owns_mcp_client is False). Closing it per run matters for a
    # benchmark, which opens one client per combo × file.
    adhoc_client = None

    try:
        # Load test cases
        with open(test_path) as f:
            file_data = yaml.safe_load(f)

        test_cases = []
        if "tests" in file_data:
            for test_data in file_data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        else:
            test_cases.append(TestCase.from_dict(file_data))

        # Check for suite-level provider override
        suite_provider = file_data.get("provider")
        suite_provider_config = file_data.get("provider_config", {})
        suite_model = file_data.get("model")

        effective_provider = suite_provider or provider
        # A suite-level `model: default` sentinel must not mask an explicitly
        # chosen model (e.g. a benchmark combo). When ``_force_model`` is set the
        # passed model wins — same precedence the CLI applies for `--model`.
        if data.get("_force_model"):
            effective_model = model
        else:
            effective_model = suite_model or model

        # Build the final provider_config. For assistant/chatbot we fold in
        # the assistant-specific fields (workspace_hash, domain, JWT auth,
        # path overrides) from the selected LLM profile in `.llm_providers.yaml`
        # — without these, AssistantProvider.__init__ raises ValueError. The
        # CLI accepts them as flags; the websocket has no flags so it must
        # pick them up from the profile config the user already maintains.
        # Precedence: explicit suite YAML `provider_config:` > LLM profile.
        effective_provider_config: dict[str, Any] = dict(suite_provider_config or {})
        if effective_provider in ("assistant", "chatbot") and llm_profile_id:
            from testmcpy.llm_profiles import load_llm_profile

            llm_profile = load_llm_profile(llm_profile_id)
            if llm_profile:
                # Prefer the entry in the profile whose `provider` matches the
                # one we're about to run; otherwise fall back to the profile
                # default. This handles the common pattern of an LLM profile
                # bundling several providers (e.g. claude-sdk + assistant) where
                # the suite YAML pins which one to use.
                assistant_entry = (
                    next(
                        (p for p in llm_profile.providers if p.provider == effective_provider),
                        None,
                    )
                    or llm_profile.get_default_provider()
                )
                if assistant_entry:
                    for fname in (
                        "workspace_hash",
                        "domain",
                        "api_token",
                        "api_secret",
                        "api_url",
                        "conversations_path",
                        "completions_path",
                    ):
                        val = getattr(assistant_entry, fname, None)
                        if val and not effective_provider_config.get(fname):
                            effective_provider_config[fname] = val

        # Ad-hoc assistant credentials supplied directly in the message (no saved
        # profile) — how the benchmark dialog passes the user's run-args. Suite
        # YAML / profile values already set above take precedence.
        if effective_provider in ("assistant", "chatbot"):
            for k, v in _assistant_config_from_data(data).items():
                effective_provider_config.setdefault(k, v)

        # Filter to specific test if requested
        if test_name:
            test_cases = [tc for tc in test_cases if tc.name == test_name]
            if not test_cases:
                _emit_run_error(handle, data, f"Test '{test_name}' not found")
                return

        _emit_log(handle, f"📋 Found {len(test_cases)} test(s) to run")
        _emit_log(handle, f"🤖 Provider: {effective_provider}, Model: {effective_model}")
        if suite_provider:
            _emit_log(handle, f"📝 Suite-level provider override: {suite_provider}")

        # Get MCP client. An ad-hoc ``mcp_url`` in the message (how the
        # benchmark dialog passes the user's run-args, with no saved profile)
        # builds a client straight from URL + auth, mirroring the CLI's
        # inline-auth path. Otherwise fall back to the named/default profile.
        mcp_client = None
        effective_profile = profile
        adhoc_mcp_url = data.get("mcp_url")

        if adhoc_mcp_url and not effective_profile:
            from testmcpy.src.mcp_client import MCPClient

            _emit_log(handle, f"🔌 Connecting to MCP (ad-hoc): {adhoc_mcp_url}")
            mcp_client = MCPClient(adhoc_mcp_url, auth=_inline_auth_from_data(data))
            await mcp_client.initialize()
            adhoc_client = mcp_client
        else:
            if not effective_profile:
                # Try to get default profile from config
                from testmcpy.server.helpers.mcp_config import load_mcp_yaml

                mcp_config = load_mcp_yaml()
                effective_profile = mcp_config.get("default")
                if effective_profile:
                    _emit_log(handle, f"🔌 Using default MCP profile: {effective_profile}")

            if effective_profile:
                _emit_log(handle, f"🔌 Loading MCP profile: {effective_profile}")
                mcp_client = await get_or_create_mcp_client(effective_profile)
                if mcp_client is None:
                    _emit_run_error(
                        handle,
                        data,
                        f"MCP profile '{effective_profile}' not found. "
                        f"Check your MCP Profiles configuration.",
                    )
                    return

        # Get MCP URL from the selected profile's client, not the default config
        effective_mcp_url = config.get_mcp_url()
        if mcp_client and hasattr(mcp_client, "base_url") and mcp_client.base_url:
            effective_mcp_url = mcp_client.base_url

        # MCP profile fallback for assistant/chatbot credentials.
        # (See task-fix-fresh-conversation history for the full rationale —
        # condensed comment kept here.)
        if effective_provider in ("assistant", "chatbot") and mcp_client is not None:
            filled_from_mcp: list[str] = []
            ws_hash, domain = _derive_workspace_and_domain_from_mcp_url(effective_mcp_url)
            if ws_hash and not effective_provider_config.get("workspace_hash"):
                effective_provider_config["workspace_hash"] = ws_hash
                filled_from_mcp.append("workspace_hash")
            if domain and not effective_provider_config.get("domain"):
                effective_provider_config["domain"] = domain
                filled_from_mcp.append("domain")
            auth_cfg = getattr(mcp_client, "auth_config", None) or {}
            if isinstance(auth_cfg, dict) and auth_cfg.get("type") == "jwt":
                for src_key, dst_key in (
                    ("api_url", "api_url"),
                    ("api_token", "api_token"),
                    ("api_secret", "api_secret"),
                ):
                    val = auth_cfg.get(src_key)
                    if val and not effective_provider_config.get(dst_key):
                        effective_provider_config[dst_key] = val
                        filled_from_mcp.append(dst_key)
            if filled_from_mcp:
                _emit_log(
                    handle,
                    f"🔑 Derived from MCP profile '{effective_profile}': "
                    f"{', '.join(filled_from_mcp)} "
                    "(add an `assistant` entry to .llm_providers.yaml to override)",
                )

        # Create runner with streaming log callback that goes through the
        # registry. Sync callback — registry.log is non-blocking, so
        # there's no benefit to spawning a fresh task per log line.
        runner = TestRunner(
            model=effective_model,
            provider=effective_provider,
            mcp_url=effective_mcp_url,
            mcp_client=mcp_client,
            verbose=True,
            hide_tool_output=False,
            log_callback=lambda msg: _emit_log(handle, msg),
            provider_config=effective_provider_config,
            # We emit our own per-test "🧪 Running test … / 📝 Prompt / ⏱️ Timeout"
            # block below, so the runner must not also emit its own (would create
            # two collapsible test groups in the UI for every test).
            quiet_test_announcement=True,
        )

        _emit_log(handle, "⚙️ Initializing test runner...")
        await runner.initialize()
        _emit_log(handle, "✅ Test runner ready")

        # For single-file runs, reuse the registry's run_id so the live
        # "Reattached to run …" banner and the /reports entry show the same
        # id. Directory sub-calls mint a fresh per-file id — each YAML keeps
        # its own /reports row.
        record = RunRecord(
            run_id=handle.run_id if not data.get("_in_batch") else None,
            log=lambda msg: _emit_log(handle, msg),
        )
        record.begin(
            test_file=_display_test_file_name(test_path),
            model=effective_model,
            provider=effective_provider,
            mcp_profile=effective_profile,
            llm_profile=llm_profile_id,
            # Shared across a benchmark's combos so /api/results/sessions and a
            # session-scoped /performance view can group them.
            metadata=({"session_id": data["session_id"]} if data.get("session_id") else None),
        )
        handle.db_run_id = record.run_id

        # Run each test one at a time
        all_results = []
        for i, tc in enumerate(test_cases):
            _emit_event(
                handle,
                {
                    "type": "test_start",
                    "test_name": tc.name,
                    "index": i,
                    "total": len(test_cases),
                },
            )

            _emit_log(handle, f"\n{'=' * 50}")
            _emit_log(handle, f"🧪 Running test {i + 1}/{len(test_cases)}: {tc.name}")
            _emit_log(handle, f"📝 Prompt: {tc.prompt}")
            _emit_log(handle, f"⏱️ Timeout: {tc.timeout}s")

            start_time = time.time()
            result = await runner.run_test(tc)
            elapsed = time.time() - start_time

            # Send logs from the result
            if hasattr(result, "logs") and result.logs:
                for log_line in result.logs:
                    _emit_log(handle, log_line)

            # Send test result
            status = "✅ PASSED" if result.passed else "❌ FAILED"
            _emit_log(handle, f"{status} in {elapsed:.2f}s")

            if result.tool_calls:
                _emit_log(handle, f"🔧 Tool calls: {len(result.tool_calls)}")
                for tc_call in result.tool_calls:
                    _emit_log(handle, f"   - {tc_call.get('name', 'unknown')}")

            if result.error:
                _emit_log(handle, f"⚠️ Error: {result.error}")

            result_dict = result.to_dict()
            _emit_event(
                handle,
                {
                    "type": "test_complete",
                    "test_name": tc.name,
                    "result": result_dict,
                },
            )

            all_results.append(result)
            handle.results.append(result_dict)
            # Persist immediately — a crash mid-suite keeps every test
            # completed so far.
            record.append(result_dict)

        # Send final summary
        passed = sum(1 for r in all_results if r.passed)
        failed = len(all_results) - passed
        total_cost = sum(r.cost for r in all_results)

        _emit_log(handle, f"\n{'=' * 50}")
        _emit_log(handle, f"📊 SUMMARY: {passed} passed, {failed} failed")
        if total_cost > 0:
            _emit_log(handle, f"💰 Total cost: ${total_cost:.4f}")

        results_list = [r.to_dict() for r in all_results]
        summary = {
            "total": len(all_results),
            "passed": passed,
            "failed": failed,
            "total_cost": total_cost,
        }
        handle.summary = summary

        # Per-test results were persisted incrementally via record.append();
        # stamp the terminal status + denormalized totals.
        record.finish("completed")
        _emit_log(handle, f"💾 Results saved: {record.run_id}")

        # `all_complete` is a TERMINAL signal on the wire (the UI sets
        # running=false, clears directoryRunProgress, and closes the WS).
        # Suppress it when invoked as a sub-call from `_run_directory_command`
        # — the batch loop emits its own single terminal all_complete after
        # the last file. Driven by an explicit `_in_batch` flag the parent
        # injects into `data`. (Copilot review on PR #76: without this,
        # a directory batch appeared to finish after the FIRST file and
        # the WS got closed mid-batch.)
        if not data.get("_in_batch"):
            _emit_event(
                handle,
                {
                    "type": "all_complete",
                    "summary": summary,
                    "results": results_list,
                },
            )

    except asyncio.CancelledError:
        # Stopped by user — keep the partial results, let the caller emit
        # the user-facing message.
        if record is not None:
            record.finish("stopped")
        raise
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        if record is not None:
            record.finish("error")
        _emit_log(handle, f"❌ Error: {str(e)}")
        _emit_log(handle, f"Traceback:\n{tb}")
        _emit_run_error(handle, data, str(e), traceback=tb)
    finally:
        # Release the ad-hoc client's HTTP session + auth token. Cached profile
        # clients are shared and must NOT be closed here.
        if adhoc_client is not None:
            with contextlib.suppress(Exception):
                await adhoc_client.close()


async def _run_directory_command(handle: RunHandle, data: dict, config) -> None:
    """Execute a 'run_directory' command — a batch of YAML files under
    one logical batch ``run_id``.

    Iterates the files sequentially within ONE task. Per-file boundaries
    surface as ``file_start`` / ``file_complete`` events the UI uses to
    drive its directory-progress strip; the batch as a whole emits a
    SINGLE terminal ``all_complete`` with the aggregated summary.

    Each file delegates to ``_run_test_command`` with ``_in_batch=True``,
    which:
    - SUPPRESSES the per-file ``all_complete`` (it would otherwise be a
      terminal signal that closes the WS mid-batch — Copilot review on
      PR #76); the batch loop owns the single terminal ``all_complete``.
    - Still SAVES per-file history with a fresh per-file run_id, so each
      YAML keeps its own row in ``/reports`` (the storage schema is
      one-suite-per-run; aggregating into a single record would need a
      bigger schema change and would hide per-file detail).
    """
    files: list[dict] = data.get("files") or []
    if not files:
        _emit_event(handle, {"type": "error", "message": "run_directory: no files provided"})
        return

    # Common per-file kwargs lifted out of the batch envelope.
    common = {
        "model": data.get("model"),
        "provider": data.get("provider"),
        "profile": data.get("profile"),
        "llm_profile": data.get("llm_profile"),
    }

    folder_label = data.get("folder") or ""
    _emit_log(
        handle,
        f"📁 Directory batch: {len(files)} file(s)"
        + (f" in {folder_label}" if folder_label else ""),
    )

    # Per-file run uses a temporary handle JUST to capture that file's
    # results, but events are forwarded into the batch handle so the
    # client sees them under the batch run_id. Aggregate after each file.
    aggregated_results: list[dict] = []
    aggregated_summary = {"total": 0, "passed": 0, "failed": 0, "total_cost": 0.0}

    try:
        for idx, file_entry in enumerate(files):
            test_path = file_entry.get("test_path", "")
            file_name = file_entry.get("name") or Path(test_path).name
            _emit_event(
                handle,
                {
                    "type": "file_start",
                    "index": idx,
                    "total": len(files),
                    "name": file_name,
                    "test_path": test_path,
                },
            )
            _emit_log(handle, f"\n{'#' * 50}")
            _emit_log(handle, f"📂 File {idx + 1}/{len(files)}: {file_name}")
            _emit_log(handle, f"{'#' * 50}")

            # Delegate to the single-file runner but mark it as a
            # sub-call so its terminal all_complete is suppressed —
            # the batch loop owns the single terminal all_complete
            # after the last file. Per-file save_test_run_to_file
            # still runs so each YAML keeps its own /reports row.
            # We snapshot `handle.results` length before/after to
            # slice out just this file's results for the per-file
            # `file_complete` summary.
            file_data = {**common, **file_entry, "_in_batch": True}
            pre_results_len = len(handle.results)
            try:
                await _run_test_command(handle, file_data, config)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _emit_log(handle, f"⚠️ File {file_name} crashed: {e}")

            file_results = handle.results[pre_results_len:]
            file_passed = sum(1 for r in file_results if r.get("passed"))
            file_failed = len(file_results) - file_passed
            aggregated_results.extend(file_results)
            aggregated_summary["total"] += len(file_results)
            aggregated_summary["passed"] += file_passed
            aggregated_summary["failed"] += file_failed
            aggregated_summary["total_cost"] += sum(r.get("cost", 0) or 0 for r in file_results)

            _emit_event(
                handle,
                {
                    "type": "file_complete",
                    "index": idx,
                    "total": len(files),
                    "name": file_name,
                    "test_path": test_path,
                    "summary": {
                        "total": len(file_results),
                        "passed": file_passed,
                        "failed": file_failed,
                    },
                },
            )

        # Batch-level summary + all_complete.
        handle.summary = aggregated_summary
        _emit_log(handle, f"\n{'=' * 50}")
        _emit_log(
            handle,
            f"📊 BATCH SUMMARY: {aggregated_summary['passed']} passed, "
            f"{aggregated_summary['failed']} failed across {len(files)} file(s)",
        )
        _emit_event(
            handle,
            {
                "type": "all_complete",
                "summary": aggregated_summary,
                "results": aggregated_results,
            },
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        _emit_log(handle, f"❌ Batch error: {e}")
        _emit_log(handle, f"Traceback:\n{tb}")
        _emit_event(handle, {"type": "error", "message": str(e), "traceback": tb})


async def _run_benchmark_command(handle: RunHandle, data: dict[str, Any], config) -> None:
    """Execute a 'run_benchmark' command — one suite across a matrix of
    models × providers × MCP profiles × repeats: the websocket-native
    equivalent of ``testmcpy bench``.

    Each (combo × file) runs as a ``_run_test_command`` sub-call with
    ``_in_batch=True`` (its terminal all_complete suppressed), ``_force_model``
    (the chosen model beats a suite ``model: default``), and a shared
    ``session_id``. So every run lands in /performance as its own config column
    and the set is grouped under one session. Connection/auth fields are
    constant across combos and forwarded verbatim — the dialog passes the
    user's run-args directly, no saved profile needed.
    """
    from testmcpy.benchmarks import BenchmarkComboError, build_benchmark_combos, combo_label

    # Resolve the target into a concrete file list. An explicit ``files`` list
    # (Test Manager has the tree) wins; otherwise a ``test_path`` is expanded —
    # a directory globs its *.yaml/*.yml (skipping hidden dirs like .results),
    # so the Performance-page trigger can pass just a folder.
    files: list[dict[str, Any]] = list(data.get("files") or [])
    raw_path = data.get("test_path")
    if not files and raw_path:
        p = Path(raw_path)
        if p.is_dir():
            files = [
                {"test_path": str(f), "name": f.name}
                for f in sorted(p.rglob("*.y*ml"))
                if f.is_file() and not any(part.startswith(".") for part in f.relative_to(p).parts)
            ]
        elif p.exists():
            files = [{"test_path": str(p), "name": p.name}]
    if not files:
        _emit_event(
            handle, {"type": "error", "message": f"run_benchmark: no test files at {raw_path!r}"}
        )
        return

    try:
        combos = build_benchmark_combos(
            data.get("models"),
            data.get("providers"),
            data.get("profiles"),
            int(data.get("repeat", 1)),
        )
    except BenchmarkComboError as e:
        _emit_event(handle, {"type": "error", "message": f"run_benchmark: {e}"})
        return

    session_id = data.get("session_id") or uuid.uuid4().hex
    # Connection/auth fields forwarded unchanged to every per-run sub-call.
    connection = {
        k: data[k]
        for k in (
            "mcp_url",
            "auth_type",
            "jwt_url",
            "jwt_token",
            "jwt_secret",
            "auth_token",
            "workspace_hash",
            "domain",
            "environment",
            "assistant_api_url",
            "assistant_api_token",
            "assistant_api_secret",
            "assistant_conversations_path",
            "assistant_completions_path",
        )
        if data.get(k) is not None
    }

    total_combos = len(combos)
    _emit_log(
        handle,
        f"🏁 Benchmark: {total_combos} combo(s) × {len(files)} file(s) "
        f"= {total_combos * len(files)} run(s) · session {session_id}",
    )

    aggregated_results: list[dict] = []
    aggregated_summary = {"total": 0, "passed": 0, "failed": 0, "total_cost": 0.0}

    try:
        for ci, combo in enumerate(combos):
            label = combo_label(combo)
            _emit_event(
                handle,
                {
                    "type": "combo_start",
                    "index": ci,
                    "total": total_combos,
                    "model": combo.model,
                    "provider": combo.provider,
                    "profile": combo.profile,
                    "iteration": combo.iteration,
                    "label": label,
                },
            )
            _emit_log(handle, f"\n{'━' * 50}")
            _emit_log(
                handle, f"🏁 Combo {ci + 1}/{total_combos}: {label} (repeat {combo.iteration})"
            )
            _emit_log(handle, f"{'━' * 50}")

            combo_pre_len = len(handle.results)
            for file_entry in files:
                run_data = {
                    **connection,
                    **file_entry,
                    "model": combo.model,
                    "provider": combo.provider,
                    "profile": combo.profile,
                    "_force_model": True,
                    "_in_batch": True,
                    "session_id": session_id,
                }
                try:
                    await _run_test_command(handle, run_data, config)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _emit_log(handle, f"⚠️ {label} / {file_entry.get('name', '')} crashed: {e}")

            combo_results = handle.results[combo_pre_len:]
            combo_passed = sum(1 for r in combo_results if r.get("passed"))
            aggregated_results.extend(combo_results)
            aggregated_summary["total"] += len(combo_results)
            aggregated_summary["passed"] += combo_passed
            aggregated_summary["failed"] += len(combo_results) - combo_passed
            aggregated_summary["total_cost"] += sum(r.get("cost", 0) or 0 for r in combo_results)

            _emit_event(
                handle,
                {
                    "type": "combo_complete",
                    "index": ci,
                    "total": total_combos,
                    "label": label,
                    "summary": {
                        "total": len(combo_results),
                        "passed": combo_passed,
                        "failed": len(combo_results) - combo_passed,
                    },
                },
            )

        handle.summary = aggregated_summary
        _emit_log(handle, f"\n{'=' * 50}")
        _emit_log(
            handle,
            f"📊 BENCHMARK SUMMARY: {aggregated_summary['passed']} passed, "
            f"{aggregated_summary['failed']} failed across {total_combos} combo(s)",
        )
        _emit_event(
            handle,
            {
                "type": "all_complete",
                "summary": aggregated_summary,
                "results": aggregated_results,
                "session_id": session_id,
            },
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        _emit_log(handle, f"❌ Benchmark error: {e}")
        _emit_event(handle, {"type": "error", "message": str(e), "traceback": tb})


async def _drain_to_websocket(handle: RunHandle, websocket: WebSocket, token: int) -> None:
    """Pull messages off ``handle.attached_queue`` and forward them to the
    websocket until the queue is drained AND the run is finished, OR the
    attachment is superseded, OR the socket fails.

    Returns when this attachment is done (cleanly or via supersession);
    the caller is responsible for detaching.
    """
    queue = handle.attached_queue
    if queue is None:
        return
    while True:
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            # No new traffic for 1s — re-check whether the run finished
            # (and the queue is now permanently empty) so we can exit.
            if handle.is_finished and queue.empty():
                return
            continue
        # Supersession marker — exit cleanly so the new attachment owns
        # the channel.
        if msg.get("type") == "superseded":
            try:
                await manager.send_message(msg, websocket)
            except Exception:
                pass
            return
        # Sanity-check we're still the active attachment. If a newer
        # attach quietly took over and the supersession marker is still
        # in flight, exit on the next iteration anyway via the marker.
        if handle.attachment_token != token:
            return
        try:
            await manager.send_message(msg, websocket)
        except Exception:
            # Socket closed under us — caller will detach.
            return


async def _watch_attached_run(websocket: WebSocket, handle: RunHandle, token: int) -> None:
    """Block until the client either disconnects, sends an inbound
    message we care about (stop, run_test, run_directory, attach), or
    the drain loop exits because the run finished.

    Runs ``_drain_to_websocket`` and ``websocket.receive_json`` as two
    concurrent tasks. The first to complete wins:
    - drain done → run finished, return so the caller waits for the
      next client message in the outer loop.
    - receive done with ``stop`` → cancel the registered task, keep
      draining the post-stop messages (final log + finalize) until the
      drain task returns.
    - receive done with ``WebSocketDisconnect`` → re-raise to the outer
      handler so we can clean up the attachment; the run keeps going.
    - receive done with a new ``run_test`` / ``run_directory`` /
      ``attach`` message → cancel the current drain, return so the
      caller handles the new command. (This is a weird case in
      practice but the dispatcher must not deadlock.)
    """
    drain_task = asyncio.create_task(_drain_to_websocket(handle, websocket, token))
    try:
        while True:
            recv_task = asyncio.create_task(websocket.receive_json())
            done, _pending = await asyncio.wait(
                {drain_task, recv_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if drain_task in done:
                recv_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await recv_task
                return

            # recv finished first.
            try:
                msg = recv_task.result()
            except WebSocketDisconnect:
                # Tear down the drain and bubble the disconnect.
                drain_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await drain_task
                raise
            msg_type = msg.get("type")
            if msg_type == "stop":
                if handle.task is not None:
                    handle.task.cancel()
                # Ack the stop immediately so the client can transition to
                # a "stopping…" UI state instead of sitting on stale running
                # state until the cancellation actually finalises. The
                # registry-published `stopping` event is also visible to
                # any later attachment via buffered_replay (SC-108217).
                run_registry.event(handle, {"type": "stopping", "run_id": handle.run_id})
                _emit_log(handle, "🛑 Stop requested — cancelling…")
                # Don't return yet — let the drain finish flushing the
                # post-cancel messages (final log line + the finalize
                # status) so the client sees a clean shutdown.
                continue
            # Any other message (e.g. a new run command) ends this
            # attachment and returns to the outer dispatcher.
            drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await drain_task
            # Put the message back-ish: requeue on the websocket's
            # receive — we can't actually requeue, so we synthesise a
            # follow-up by returning a sentinel via a closure. Instead,
            # raise a custom exception with the message attached.
            raise _Reattach(msg)
    finally:
        if not drain_task.done():
            drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await drain_task


class _Reattach(Exception):
    """Internal sentinel — the client sent a new run_* / attach message
    while a prior attachment was still draining. Carries the new
    message so the outer dispatcher can act on it."""

    def __init__(self, message: dict) -> None:
        super().__init__("client issued a new command mid-attach")
        self.message = message


async def handle_test_websocket(websocket: WebSocket):
    """Multi-message WebSocket dispatcher backed by the run registry.

    Accepted client messages:
    - ``{type: "run_test", test_path, ...}`` — start a single-file run.
      The run is registered and survives this WS disconnecting.
    - ``{type: "run_directory", files: [...], ...}`` — start a batch
      under one run_id.
    - ``{type: "attach", run_id}`` — reattach to an in-flight (or recently
      finished) run; receive a buffered replay + live stream.
    - ``{type: "stop"}`` — cancel the currently-attached run. Works
      whether or not this WS started the run.

    Server messages: ``run_started`` (with the registry's ``run_id``),
    ``log`` / ``log_replay``, ``test_start`` / ``test_complete``,
    ``file_start`` / ``file_complete``, ``all_complete``, ``error``,
    ``superseded``.
    """
    await manager.connect(websocket)
    config = get_config()
    current_handle: RunHandle | None = None
    current_token: int | None = None

    async def _spawn_run_task(handle: RunHandle, command_coro, data: dict) -> None:
        """Wrap ``command_coro`` so the registry status is finalized when
        it ends regardless of exit path."""

        async def _heartbeat() -> None:
            # Stamp the current DB row every ~30s so crash reconciliation
            # (storage.mark_stale_runs_interrupted) can tell a live run
            # from a dead one. db_run_id is None until RunRecord.begin()
            # and swaps per file during a directory batch.
            from sqlalchemy.exc import SQLAlchemyError

            from testmcpy.storage import get_storage

            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                db_run_id = handle.db_run_id
                if db_run_id is None:
                    continue
                try:
                    get_storage().touch_run_heartbeat(db_run_id)
                except SQLAlchemyError:
                    # Missing a beat is harmless — the reconcile cutoff
                    # (minutes) tolerates several failures in a row.
                    pass

        async def _run() -> None:
            heartbeat_task = asyncio.create_task(_heartbeat())
            try:
                if not run_registry.slots_available():
                    _emit_log(
                        handle,
                        "⏳ Run queued — waiting for a free run slot "
                        "(TESTMCPY_MAX_CONCURRENT_RUNS)…",
                    )
                async with run_registry.acquire_slot(handle):
                    await command_coro(handle, data, config)
                await run_registry.finalize(
                    handle.run_id, status="completed", summary=handle.summary
                )
            except asyncio.CancelledError:
                # Emit a terminal `all_complete` with status=stopped so the
                # client recognises the cancellation as the end of the run
                # and clears its running/stopping UI state. Without this the
                # client just sees the queue go silent and has to infer the
                # state via reattach/polling.
                run_registry.event(
                    handle,
                    {
                        "type": "all_complete",
                        "status": "stopped",
                        "summary": dict(handle.summary or {}, status="stopped"),
                        "results": list(handle.results),
                    },
                )
                await run_registry.finalize(handle.run_id, status="stopped", summary=handle.summary)
                raise
            except Exception:
                await run_registry.finalize(handle.run_id, status="error", summary=handle.summary)
                raise
            finally:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

        handle.task = asyncio.create_task(_run())

    async def _start_new_run(kind: str, command_coro, data: dict) -> None:
        """Mint a handle, send run_started, attach this socket, and watch."""
        nonlocal current_handle, current_token
        handle = await run_registry.create_run(kind=kind, meta=dict(data))
        await _spawn_run_task(handle, command_coro, data)
        queue, token = await run_registry.attach(handle)
        current_handle, current_token = handle, token
        try:
            await manager.send_message(
                {"type": "run_started", "run_id": handle.run_id, "kind": kind},
                websocket,
            )
        except Exception:
            pass
        await _watch_attached_run(websocket, handle, token)
        await run_registry.detach(handle, token)
        # DELIBERATELY do not cancel handle.task — disconnects keep it alive.

    async def _attach_history_run(run_id: str) -> None:
        """Registry miss — serve the run from the results DB instead of
        'not found'. Sends a synthesized terminal replay; there is no live
        stream to attach to, so the dispatcher just waits for the next
        client message afterwards.

        Known asymmetry: directory-batch run_ids never get a DB row (each
        file persists under its own per-file id), so a batch id that has
        aged out of the registry still resolves to 'not found' here even
        though its per-file rows are in the DB. Closing that needs a
        parent-row (or metadata.batch_id) scheme — deferred."""
        from sqlalchemy.exc import SQLAlchemyError

        from testmcpy.server.run_persistence import history_replay_messages
        from testmcpy.storage import get_storage

        try:
            record = get_storage().get_run(run_id)
        except SQLAlchemyError:
            record = None
        if record is None:
            await manager.send_message(
                {"type": "error", "message": f"run_id not found: {run_id}"},
                websocket,
            )
            return
        for msg in history_replay_messages(record):
            try:
                await manager.send_message(msg, websocket)
            except Exception:
                return

    async def _attach_existing_run(run_id: str) -> None:
        nonlocal current_handle, current_token
        handle = await run_registry.get_run(run_id)
        if handle is None:
            await _attach_history_run(run_id)
            return
        # Replay backlog so the UI rebuilds state.
        for replay_msg in run_registry.buffered_replay(handle):
            try:
                await manager.send_message(replay_msg, websocket)
            except Exception:
                break
        await manager.send_message(
            {
                "type": "run_started",
                "run_id": handle.run_id,
                "kind": handle.kind,
                "reattached": True,
                "status": handle.status,
            },
            websocket,
        )
        queue, token = await run_registry.attach(handle)
        current_handle, current_token = handle, token
        await _watch_attached_run(websocket, handle, token)
        await run_registry.detach(handle, token)

    async def _dispatch(message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "run_test":
            await _start_new_run("single", _run_test_command, message)
        elif msg_type == "run_directory":
            await _start_new_run("directory", _run_directory_command, message)
        elif msg_type == "run_benchmark":
            await _start_new_run("benchmark", _run_benchmark_command, message)
        elif msg_type == "attach":
            await _attach_existing_run(message.get("run_id", ""))
        elif msg_type == "stop":
            if current_handle is not None and current_handle.task is not None:
                current_handle.task.cancel()
                run_registry.event(
                    current_handle,
                    {"type": "stopping", "run_id": current_handle.run_id},
                )
                _emit_log(current_handle, "🛑 Stop requested — cancelling…")
        # Unknown types: silently drop. Future-compatible.

    try:
        pending: dict | None = None
        while True:
            if pending is None:
                message = await websocket.receive_json()
            else:
                message = pending
                pending = None
            try:
                await _dispatch(message)
            except _Reattach as carried:
                # The previous _watch_attached_run aborted because a new
                # command came in mid-stream. Loop back and handle it.
                pending = carried.message

    except WebSocketDisconnect:
        if current_handle is not None and current_token is not None:
            await run_registry.detach(current_handle, current_token)
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Test WebSocket error: {e}")
        if current_handle is not None and current_token is not None:
            await run_registry.detach(current_handle, current_token)
        manager.disconnect(websocket)
