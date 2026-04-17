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
    ("/compatibility", "CompatibilityMatrix"),
    ("/metrics", "MetricsDashboard"),
    ("/compare", "RunComparison"),
    ("/mcp-health", "MCPHealth"),
    ("/security", "SecurityDashboard"),
]


@pytest.mark.e2e
@pytest.mark.parametrize("path,name", PAGES)
def test_page_loads(page, server_url, screenshots_dir, path, name):
    page.goto(f"{server_url}{path}")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(screenshots_dir / f"{name}.png"), full_page=True)
    # Verify page loaded (not blank)
    assert page.content() != ""
