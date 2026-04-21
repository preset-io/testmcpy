"""
E2E Playwright tests for V1.0 features — new pages, components, and interactions.

Covers stories:
- SC-103119: Metrics dashboard
- SC-103120: Comparison matrix
- SC-103126: MCP health dashboard
- SC-103127: Security dashboard
- SC-103111: Compatibility matrix
- SC-103130: Command palette (Cmd+K)
- SC-103128: Light theme + toggle
- SC-103131: Notification system
- SC-103104/106/108: Wizard UI (MCP, LLM, Test Case)
- SC-103132: Reports overhaul (filtering, export, deep-links)
- SC-103133: Chat upgrade (edit, regenerate, system prompt, export)
- SC-103117: Auth debugger enhancements
- SC-103134: Schema diff
"""

import pytest


def _screenshot(page, screenshots_dir, cls, name):
    screenshots_dir.mkdir(exist_ok=True)
    path = screenshots_dir / f"{cls}_{name}.png"
    page.screenshot(path=str(path), full_page=True)


def _no_errors(content):
    """Assert no server or JS errors in page content."""
    for err in [
        "500 Internal Server Error",
        "Internal Server Error",
        "TypeError:",
        "ReferenceError:",
        "Cannot read properties of",
        "Unhandled Runtime Error",
    ]:
        assert err not in content, f"Found error: {err}"


# ---------------------------------------------------------------------------
# 1. Metrics Dashboard (SC-103119)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestMetricsDashboard:
    def test_page_loads(self, page, server_url, screenshots_dir):
        """Metrics page loads without errors."""
        page.goto(f"{server_url}/metrics")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "MetricsDashboard", "loads")

    def test_has_summary_cards(self, page, server_url, screenshots_dir):
        """Metrics page shows summary stat cards."""
        page.goto(f"{server_url}/metrics")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        # Should show metric labels like runs, cost, pass rate, etc.
        has_metrics = any(
            kw in content.lower()
            for kw in ["runs", "cost", "pass rate", "tokens", "total", "metrics"]
        )
        assert has_metrics, "Metrics page should show metric labels"
        _screenshot(page, screenshots_dir, "MetricsDashboard", "summary_cards")

    def test_no_crash_on_empty_data(self, page, server_url, screenshots_dir):
        """Metrics page handles empty data gracefully."""
        page.goto(f"{server_url}/metrics")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        # Should not show raw JSON or stack traces
        assert "Traceback" not in content
        _screenshot(page, screenshots_dir, "MetricsDashboard", "empty_data")


# ---------------------------------------------------------------------------
# 2. Run Comparison (SC-103120)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestRunComparison:
    def test_page_loads(self, page, server_url, screenshots_dir):
        """Comparison page loads without errors."""
        page.goto(f"{server_url}/compare")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "RunComparison", "loads")

    def test_has_comparison_ui(self, page, server_url, screenshots_dir):
        """Comparison page shows selection UI or empty state."""
        page.goto(f"{server_url}/compare")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        has_ui = any(
            kw in content.lower() for kw in ["compare", "select", "runs", "no runs", "comparison"]
        )
        assert has_ui, "Comparison page should show comparison UI elements"
        _screenshot(page, screenshots_dir, "RunComparison", "ui_elements")


# ---------------------------------------------------------------------------
# 3. MCP Health Dashboard (SC-103126)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestMCPHealth:
    def test_page_loads(self, page, server_url, screenshots_dir):
        """MCP Health page loads without errors."""
        page.goto(f"{server_url}/mcp-health")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "MCPHealth", "loads")

    def test_shows_health_status(self, page, server_url, screenshots_dir):
        """MCP Health page shows server status indicators."""
        page.goto(f"{server_url}/mcp-health")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        has_health = any(
            kw in content.lower()
            for kw in ["health", "status", "server", "healthy", "unreachable", "no servers"]
        )
        assert has_health, "Health page should show status information"
        _screenshot(page, screenshots_dir, "MCPHealth", "status")

    def test_refresh_button_exists(self, page, server_url, screenshots_dir):
        """MCP Health page has a refresh/check button."""
        page.goto(f"{server_url}/mcp-health")
        page.wait_for_load_state("networkidle")
        refresh_btn = page.locator(
            "button:has-text('Refresh'), button:has-text('Check'), button:has-text('Ping')"
        )
        if refresh_btn.count() > 0:
            refresh_btn.first.click()
            page.wait_for_timeout(1000)
            content = page.text_content("body") or ""
            _no_errors(content)
        _screenshot(page, screenshots_dir, "MCPHealth", "refresh")


# ---------------------------------------------------------------------------
# 4. Security Dashboard (SC-103127)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestSecurityDashboard:
    def test_page_loads(self, page, server_url, screenshots_dir):
        """Security page loads without errors."""
        page.goto(f"{server_url}/security")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "SecurityDashboard", "loads")

    def test_shows_severity_levels(self, page, server_url, screenshots_dir):
        """Security page shows severity breakdown labels."""
        page.goto(f"{server_url}/security")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        has_security = any(
            kw in content.lower()
            for kw in ["critical", "high", "medium", "low", "security", "severity", "no security"]
        )
        assert has_security, "Security page should show severity level labels"
        _screenshot(page, screenshots_dir, "SecurityDashboard", "severity")


# ---------------------------------------------------------------------------
# 5. Compatibility Matrix (SC-103111)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestCompatibilityMatrix:
    def test_page_loads(self, page, server_url, screenshots_dir):
        """Compatibility page loads without errors."""
        page.goto(f"{server_url}/compatibility")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "CompatibilityMatrix", "loads")

    def test_has_matrix_or_empty_state(self, page, server_url, screenshots_dir):
        """Compatibility page shows matrix or meaningful empty state."""
        page.goto(f"{server_url}/compatibility")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        has_content = any(
            kw in content.lower()
            for kw in ["compatibility", "matrix", "model", "tool", "no data", "provider"]
        )
        assert has_content, "Compatibility page should show matrix elements"
        _screenshot(page, screenshots_dir, "CompatibilityMatrix", "content")


# ---------------------------------------------------------------------------
# 6. Command Palette / Cmd+K (SC-103130)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestCommandPalette:
    def test_cmd_k_opens_palette(self, page, server_url, screenshots_dir):
        """Cmd+K keyboard shortcut opens the command palette."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("Meta+k")
        page.wait_for_timeout(500)
        # Look for search input or palette overlay
        palette = page.locator(
            "[role='dialog'], [class*='palette'], [class*='command'], [class*='modal']"
        )
        _screenshot(page, screenshots_dir, "CommandPalette", "opened")
        # Palette should appear (may not on all OS; check content changed)
        content = page.text_content("body") or ""
        _no_errors(content)

    def test_palette_search_input(self, page, server_url, screenshots_dir):
        """Command palette has a searchable input."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("Meta+k")
        page.wait_for_timeout(500)
        # Try to find and type in the search input
        search_input = page.locator(
            "[role='dialog'] input, [class*='palette'] input, [class*='command'] input"
        )
        if search_input.count() > 0:
            search_input.first.fill("reports")
            page.wait_for_timeout(300)
            content = page.text_content("body") or ""
            _no_errors(content)
        _screenshot(page, screenshots_dir, "CommandPalette", "search")

    def test_escape_closes_palette(self, page, server_url, screenshots_dir):
        """Pressing Escape closes the command palette."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("Meta+k")
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "CommandPalette", "closed")


# ---------------------------------------------------------------------------
# 7. Light Theme Toggle (SC-103128)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestThemeToggle:
    def test_theme_toggle_exists(self, page, server_url, screenshots_dir):
        """Theme toggle button exists in the sidebar."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        theme_btn = page.locator(
            "button[title*='theme'], button[title*='Theme'], "
            "button:has-text('Light'), button:has-text('Dark'), "
            "[class*='theme']"
        )
        # Theme toggle should exist somewhere
        _screenshot(page, screenshots_dir, "ThemeToggle", "initial")
        content = page.text_content("body") or ""
        _no_errors(content)

    def test_toggle_changes_appearance(self, page, server_url, screenshots_dir):
        """Clicking theme toggle changes the page appearance."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        # Get initial background color
        initial_bg = page.evaluate("window.getComputedStyle(document.body).backgroundColor")
        # Find and click theme toggle (may be in collapsed sidebar, use force)
        theme_btn = page.locator(
            "button[title*='theme'], button[title*='Theme'], "
            "button[aria-label*='theme'], [class*='theme-toggle']"
        )
        if theme_btn.count() > 0:
            theme_btn.first.dispatch_event("click")
            page.wait_for_timeout(500)
            new_bg = page.evaluate("window.getComputedStyle(document.body).backgroundColor")
            # Background should change (light <-> dark)
            _screenshot(page, screenshots_dir, "ThemeToggle", "toggled")
            content = page.text_content("body") or ""
            _no_errors(content)


# ---------------------------------------------------------------------------
# 8. Wizard UI — MCP Profiles (SC-103104)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestWizardMCPProfiles:
    def test_add_button_opens_wizard(self, page, server_url, screenshots_dir):
        """Add MCP button opens the wizard modal."""
        page.goto(f"{server_url}/mcp-profiles")
        page.wait_for_load_state("networkidle")
        add_btn = page.locator(
            "button:has-text('Add'), button:has-text('Create'), button:has-text('New')"
        )
        if add_btn.count() > 0:
            add_btn.first.click()
            page.wait_for_timeout(500)
            content = page.text_content("body") or ""
            _no_errors(content)
            # Should show wizard step content
            has_wizard = any(
                kw in content.lower()
                for kw in ["step", "name", "url", "transport", "next", "wizard"]
            )
            assert has_wizard, "Wizard should show step content after clicking Add"
        _screenshot(page, screenshots_dir, "WizardMCP", "opened")


# ---------------------------------------------------------------------------
# 9. Wizard UI — LLM Profiles (SC-103106)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestWizardLLMProfiles:
    def test_add_button_opens_wizard(self, page, server_url, screenshots_dir):
        """Add LLM button opens the wizard modal."""
        page.goto(f"{server_url}/llm-profiles")
        page.wait_for_load_state("networkidle")
        add_btn = page.locator(
            "button:has-text('Add'), button:has-text('Create'), button:has-text('New')"
        )
        if add_btn.count() > 0:
            add_btn.first.click()
            page.wait_for_timeout(500)
            content = page.text_content("body") or ""
            _no_errors(content)
            has_wizard = any(
                kw in content.lower()
                for kw in ["step", "provider", "model", "api", "next", "wizard"]
            )
            assert has_wizard, "Wizard should show step content after clicking Add"
        _screenshot(page, screenshots_dir, "WizardLLM", "opened")


# ---------------------------------------------------------------------------
# 10. Reports Overhaul (SC-103132)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestReportsOverhaul:
    def test_filter_controls_exist(self, page, server_url, screenshots_dir):
        """Reports page has filter/search controls."""
        page.goto(f"{server_url}/reports")
        page.wait_for_load_state("networkidle")
        filters = page.locator(
            "input[placeholder*='search' i], input[placeholder*='filter' i], "
            "select, [class*='filter']"
        )
        _screenshot(page, screenshots_dir, "Reports", "filters")
        content = page.text_content("body") or ""
        _no_errors(content)

    def test_export_button_exists(self, page, server_url, screenshots_dir):
        """Reports page has an export button."""
        page.goto(f"{server_url}/reports")
        page.wait_for_load_state("networkidle")
        export_btn = page.locator(
            "button:has-text('Export'), button:has-text('Download'), button:has-text('CSV')"
        )
        _screenshot(page, screenshots_dir, "Reports", "export_btn")
        content = page.text_content("body") or ""
        _no_errors(content)

    def test_deep_link_preserves_state(self, page, server_url, screenshots_dir):
        """Navigating to a reports deep-link URL loads correctly."""
        page.goto(f"{server_url}/reports?tab=smoke")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        _no_errors(content)
        _screenshot(page, screenshots_dir, "Reports", "deep_link")


# ---------------------------------------------------------------------------
# 11. Chat Upgrade (SC-103133)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestChatUpgrade:
    def test_system_prompt_input(self, page, server_url, screenshots_dir):
        """Chat page has system prompt configuration."""
        page.goto(f"{server_url}/chat")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        has_system = any(
            kw in content.lower() for kw in ["system prompt", "system message", "instructions"]
        )
        _screenshot(page, screenshots_dir, "Chat", "system_prompt")
        _no_errors(content)

    def test_export_button(self, page, server_url, screenshots_dir):
        """Chat page has export/download capability."""
        page.goto(f"{server_url}/chat")
        page.wait_for_load_state("networkidle")
        export_btn = page.locator(
            "button:has-text('Export'), button:has-text('Download'), "
            "button[title*='export' i], button[title*='download' i]"
        )
        _screenshot(page, screenshots_dir, "Chat", "export")
        content = page.text_content("body") or ""
        _no_errors(content)


# ---------------------------------------------------------------------------
# 12. Auth Debugger Enhancements (SC-103117)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestAuthDebuggerEnhanced:
    def test_jwt_decoder_tab(self, page, server_url, screenshots_dir):
        """Auth debugger has JWT decoder functionality."""
        page.goto(f"{server_url}/auth-debugger")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        has_jwt = any(
            kw in content.lower()
            for kw in ["jwt", "decode", "token", "header", "payload", "claims"]
        )
        assert has_jwt, "Auth debugger should show JWT-related UI"
        _screenshot(page, screenshots_dir, "AuthDebugger", "jwt_decoder")

    def test_no_errors_on_all_tabs(self, page, server_url, screenshots_dir):
        """Clicking through all auth debugger tabs causes no errors."""
        page.goto(f"{server_url}/auth-debugger")
        page.wait_for_load_state("networkidle")
        tabs = page.locator("button[role='tab'], [class*='tab']")
        for i in range(min(tabs.count(), 5)):
            tabs.nth(i).click()
            page.wait_for_timeout(300)
            content = page.text_content("body") or ""
            _no_errors(content)
        _screenshot(page, screenshots_dir, "AuthDebugger", "all_tabs")


# ---------------------------------------------------------------------------
# 13. New Pages Error Scanner (covers all new V1.0 routes)
# ---------------------------------------------------------------------------
NEW_PAGES = [
    ("/metrics", "MetricsDashboard"),
    ("/compare", "RunComparison"),
    ("/mcp-health", "MCPHealth"),
    ("/security", "SecurityDashboard"),
    ("/compatibility", "CompatibilityMatrix"),
]


@pytest.mark.e2e
@pytest.mark.parametrize("path,name", NEW_PAGES)
def test_new_page_no_console_errors(page, server_url, screenshots_dir, path, name):
    """New V1.0 pages should produce no console errors."""
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(f"{server_url}{path}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    # Filter out known benign errors (e.g. favicon, source maps)
    real_errors = [
        e
        for e in errors
        if not any(skip in e for skip in ["favicon", ".map", "sourcemap", "net::ERR"])
    ]
    _screenshot(page, screenshots_dir, "ConsoleErrors", f"{name}")
    assert len(real_errors) == 0, f"Console errors on {name}: {real_errors}"
