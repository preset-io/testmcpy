import pytest

PAGES = [
    ("/", "MCPExplorer"),
    ("/tests", "TestManager"),
    ("/reports", "Reports"),
    ("/generation-history", "GenerationHistory"),
    ("/chat", "Chat"),
    ("/auth-debugger", "AuthDebugger"),
    ("/config", "Configuration"),
    ("/mcp-profiles", "MCPProfiles"),
    ("/llm-profiles", "LLMProfiles"),
]


@pytest.mark.e2e
@pytest.mark.parametrize("path,name", PAGES)
def test_no_console_errors(page, server_url, path, name):
    """Verify no JavaScript console errors on each page."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(f"{server_url}{path}")
    page.wait_for_load_state("networkidle")

    assert errors == [], f"JS console errors on {name} ({path}): {errors}"
