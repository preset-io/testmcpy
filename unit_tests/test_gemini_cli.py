"""Unit tests for GeminiCLIProvider."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testmcpy.src.llm_integration import GeminiCLIProvider, LLMResult, create_llm_provider
from testmcpy.src.model_registry import Provider, get_model, get_models_by_provider

# ---------------------------------------------------------------------------
# Factory / Registry
# ---------------------------------------------------------------------------


class TestGeminiCLIFactory:
    """Verify the provider is properly wired into the factory and model registry."""

    def test_create_llm_provider_gemini_cli(self):
        """create_llm_provider('gemini-cli', ...) should return a GeminiCLIProvider."""
        with patch.object(GeminiCLIProvider, "_find_gemini_cli", return_value="/usr/bin/gemini"):
            provider = create_llm_provider("gemini-cli", "gemini-2.5-pro")
        assert isinstance(provider, GeminiCLIProvider)
        assert provider.model == "gemini-2.5-pro"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_llm_provider("nonexistent-provider", "some-model")

    def test_model_registry_has_gemini_cli_models(self):
        models = get_models_by_provider("gemini-cli")
        assert len(models) >= 2
        ids = [m.id for m in models]
        assert "gemini-cli-2.5-pro" in ids
        assert "gemini-cli-2.5-flash" in ids

    def test_model_lookup_by_alias(self):
        model = get_model("gcli-pro")
        assert model is not None
        assert model.provider == Provider.GEMINI_CLI

    def test_default_model_is_pro(self):
        models = get_models_by_provider("gemini-cli")
        defaults = [m for m in models if m.is_default]
        assert len(defaults) == 1
        assert defaults[0].id == "gemini-cli-2.5-pro"


# ---------------------------------------------------------------------------
# CLI discovery
# ---------------------------------------------------------------------------


class TestGeminiCLIDiscovery:
    def test_find_gemini_cli_from_env(self, tmp_path):
        fake_cli = tmp_path / "gemini"
        fake_cli.touch()
        with patch.dict("os.environ", {"GEMINI_CLI_PATH": str(fake_cli)}):
            provider = GeminiCLIProvider.__new__(GeminiCLIProvider)
            path = provider._find_gemini_cli()
        assert path == str(fake_cli)

    def test_find_gemini_cli_not_found(self):
        provider = GeminiCLIProvider.__new__(GeminiCLIProvider)
        with patch.dict("os.environ", {"GEMINI_CLI_PATH": ""}, clear=False):
            # Mock subprocess.run to always raise FileNotFoundError (no CLI found)
            with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
                with pytest.raises(FileNotFoundError, match="Gemini CLI not found"):
                    provider._find_gemini_cli()


# ---------------------------------------------------------------------------
# Prompt / parse helpers
# ---------------------------------------------------------------------------


class TestGeminiCLIPromptAndParse:
    def _make_provider(self):
        provider = GeminiCLIProvider.__new__(GeminiCLIProvider)
        provider.model = "gemini-2.5-pro"
        provider.gemini_cli_path = "/usr/bin/gemini"
        provider.tool_discovery = MagicMock()
        return provider

    def test_create_tool_prompt_no_tools(self):
        p = self._make_provider()
        assert p._create_tool_prompt("hello", []) == "hello"

    def test_create_tool_prompt_with_tools(self):
        p = self._make_provider()
        tools = [
            {
                "name": "list_charts",
                "description": "List charts",
                "parameters": {"type": "object", "properties": {"page": {}}},
            }
        ]
        result = p._create_tool_prompt("show charts", tools)
        assert "list_charts" in result
        assert "TOOL_CALL" in result
        assert "show charts" in result

    def test_parse_tool_calls_flat(self):
        """Flat JSON (no nested braces) is matched by the first regex alternative."""
        p = self._make_provider()
        response = 'Some text\nTOOL_CALL: {"name": "health_check"}\nMore text'
        calls = p._parse_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "health_check"
        assert calls[0]["arguments"] == {}

    def test_parse_tool_calls_nested_args(self):
        """Nested braces (one level) are matched correctly."""
        p = self._make_provider()
        response = 'TOOL_CALL: {"name": "call_tool", "arguments": {"name": "list_charts"}}'
        calls = p._parse_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "call_tool"
        assert calls[0]["arguments"] == {"name": "list_charts"}

    def test_parse_tool_calls_no_match(self):
        p = self._make_provider()
        assert p._parse_tool_calls("No tool calls here") == []


# ---------------------------------------------------------------------------
# generate_with_tools
# ---------------------------------------------------------------------------


class TestGeminiCLIGenerate:
    def _make_provider(self):
        provider = GeminiCLIProvider.__new__(GeminiCLIProvider)
        provider.model = "gemini-2.5-pro"
        provider.gemini_cli_path = "/usr/bin/gemini"
        provider.tool_discovery = MagicMock()
        provider.tool_discovery.execute_tool_call = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_generate_success(self):
        p = self._make_provider()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"The answer is 42", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await p.generate_with_tools("What is the answer?", [])

        assert isinstance(result, LLMResult)
        assert result.response == "The answer is 42"
        assert result.tool_calls == []
        assert result.cost == 0.0
        assert result.duration > 0

    @pytest.mark.asyncio
    async def test_generate_with_tool_call(self):
        p = self._make_provider()

        stdout = b'TOOL_CALL: {"name": "health_check", "arguments": {}}\nAll good.'
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(stdout, b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await p.generate_with_tools("check health", [])

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "health_check"
        p.tool_discovery.execute_tool_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_cli_error(self):
        p = self._make_provider()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"auth failed"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await p.generate_with_tools("hi", [])

        assert "Gemini CLI error" in result.response

    @pytest.mark.asyncio
    async def test_generate_timeout(self):
        p = self._make_provider()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await p.generate_with_tools("hi", [], timeout=1.0)

        assert "timed out" in result.response
