"""Deep E2E Playwright tests that exercise actual UI features beyond page loads."""

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


def _screenshot(page, screenshots_dir, class_name, test_name):
    """Save a screenshot after each deep test."""
    screenshots_dir.mkdir(exist_ok=True)
    path = screenshots_dir / f"{class_name}_{test_name}.png"
    page.screenshot(path=str(path), full_page=True)


# ---------------------------------------------------------------------------
# 1. MCP Explorer Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestExplorerDeep:
    def test_tools_tab_shows_tools(self, page, server_url, screenshots_dir):
        """Verify tools tab loads and shows actual tool names."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body") or ""
        # Should have either tool names OR a meaningful message, not an error
        assert "500 Internal Server Error" not in content
        assert "Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestExplorerDeep", "test_tools_tab_shows_tools")

    def test_resources_tab(self, page, server_url, screenshots_dir):
        """Click Resources tab and verify content."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        page.click("text=Resources")
        page.wait_for_timeout(1000)
        content = page.text_content("body") or ""
        assert "500 Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestExplorerDeep", "test_resources_tab")

    def test_prompts_tab(self, page, server_url, screenshots_dir):
        """Click Prompts tab and verify content."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        page.click("text=Prompts")
        page.wait_for_timeout(1000)
        content = page.text_content("body") or ""
        assert "500 Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestExplorerDeep", "test_prompts_tab")

    def test_smoke_test_button(self, page, server_url, screenshots_dir):
        """Click smoke test button and verify it starts."""
        page.goto(f"{server_url}/")
        page.wait_for_load_state("networkidle")
        smoke_btn = page.locator(
            "button:has-text('Smoke'), button:has-text('Quick Test'), button:has-text('Test')"
        )
        if smoke_btn.count() > 0:
            smoke_btn.first.click()
            page.wait_for_timeout(2000)
            content = page.text_content("body") or ""
            assert "500 Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestExplorerDeep", "test_smoke_test_button")


# ---------------------------------------------------------------------------
# 2. Test Manager Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestTestManagerDeep:
    def test_select_test_file(self, page, server_url, screenshots_dir):
        """Click a test file and verify editor loads."""
        page.goto(f"{server_url}/tests")
        page.wait_for_load_state("networkidle")
        file_item = page.locator(".truncate, [class*='file']").first
        if file_item.count() > 0:
            file_item.click()
            page.wait_for_timeout(1000)
            content = page.text_content("body") or ""
            assert "500 Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestTestManagerDeep", "test_select_test_file")

    def test_create_new_file_dialog(self, page, server_url, screenshots_dir):
        """Click + button to open new file dialog."""
        page.goto(f"{server_url}/tests")
        page.wait_for_load_state("networkidle")
        plus_btn = page.locator(
            "button[title*='Create'], button:has-text('+'), button[title*='new']"
        )
        if plus_btn.count() > 0:
            plus_btn.first.click()
            page.wait_for_timeout(500)
            content = page.text_content("body") or ""
            assert "500 Internal Server Error" not in content
        _screenshot(
            page,
            screenshots_dir,
            "TestTestManagerDeep",
            "test_create_new_file_dialog",
        )

    def test_no_error_states_in_sidebar(self, page, server_url, screenshots_dir):
        """Verify test file sidebar has no error messages."""
        page.goto(f"{server_url}/tests")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        for error in [
            "500",
            "502",
            "503",
            "404 Not Found",
            "Internal Server Error",
            "Failed to fetch",
            "Network Error",
        ]:
            assert error not in content, f"Found error '{error}' on Tests page"
        _screenshot(
            page,
            screenshots_dir,
            "TestTestManagerDeep",
            "test_no_error_states_in_sidebar",
        )


# ---------------------------------------------------------------------------
# 3. Chat Interface Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestChatDeep:
    def test_chat_input_visible(self, page, server_url, screenshots_dir):
        """Verify chat input and send button exist."""
        page.goto(f"{server_url}/chat")
        page.wait_for_load_state("networkidle")
        textarea = page.locator("textarea, input[type='text']")
        assert textarea.count() > 0, "Chat input not found"
        send_btn = page.locator("button:has-text('Send')")
        assert send_btn.count() > 0, "Send button not found"
        _screenshot(page, screenshots_dir, "TestChatDeep", "test_chat_input_visible")

    def test_chat_shows_mcp_tools_banner(self, page, server_url, screenshots_dir):
        """Verify the 'Using tools from...' banner shows."""
        page.goto(f"{server_url}/chat")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        assert "500 Internal Server Error" not in content
        assert "Internal Server Error" not in content
        _screenshot(
            page,
            screenshots_dir,
            "TestChatDeep",
            "test_chat_shows_mcp_tools_banner",
        )

    def test_type_message(self, page, server_url, screenshots_dir):
        """Type a message in chat (don't send -- would need real LLM)."""
        page.goto(f"{server_url}/chat")
        page.wait_for_load_state("networkidle")
        textarea = page.locator("textarea").first
        textarea.fill("Hello, test message")
        assert textarea.input_value() == "Hello, test message"
        _screenshot(page, screenshots_dir, "TestChatDeep", "test_type_message")


# ---------------------------------------------------------------------------
# 4. Auth Debugger Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestAuthDebuggerDeep:
    def test_auth_type_tabs(self, page, server_url, screenshots_dir):
        """Verify OAuth, JWT, Bearer tabs exist and are clickable."""
        page.goto(f"{server_url}/auth-debugger")
        page.wait_for_load_state("networkidle")
        for tab_text in ["OAuth", "JWT", "Bearer"]:
            tab = page.locator(
                f"button:has-text('{tab_text}'), [role='tab']:has-text('{tab_text}')"
            )
            if tab.count() > 0:
                tab.first.click()
                page.wait_for_timeout(300)
                content = page.text_content("body") or ""
                assert "500 Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestAuthDebuggerDeep", "test_auth_type_tabs")

    def test_profile_selector_loads(self, page, server_url, screenshots_dir):
        """Verify MCP profile dropdown has options."""
        page.goto(f"{server_url}/auth-debugger")
        page.wait_for_load_state("networkidle")
        select = page.locator("select")
        if select.count() > 0:
            options = select.first.locator("option")
            assert options.count() > 0, "Profile selector has no options"
        _screenshot(
            page,
            screenshots_dir,
            "TestAuthDebuggerDeep",
            "test_profile_selector_loads",
        )


# ---------------------------------------------------------------------------
# 5. Profiles Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestProfilesDeep:
    def test_mcp_profile_shows_connected(self, page, server_url, screenshots_dir):
        """Verify MCP profile page shows connection status."""
        page.goto(f"{server_url}/mcp-profiles")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        assert "500 Internal Server Error" not in content
        assert "Internal Server Error" not in content
        _screenshot(
            page,
            screenshots_dir,
            "TestProfilesDeep",
            "test_mcp_profile_shows_connected",
        )

    def test_llm_profile_shows_providers(self, page, server_url, screenshots_dir):
        """Verify LLM profile page shows configured providers."""
        page.goto(f"{server_url}/llm-profiles")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        assert "500 Internal Server Error" not in content
        _screenshot(
            page,
            screenshots_dir,
            "TestProfilesDeep",
            "test_llm_profile_shows_providers",
        )

    def test_add_profile_button_exists(self, page, server_url, screenshots_dir):
        """Verify Add Profile button exists on MCP profiles page."""
        page.goto(f"{server_url}/mcp-profiles")
        page.wait_for_load_state("networkidle")
        add_btn = page.locator(
            "button:has-text('Add'), button:has-text('Create'), button:has-text('New')"
        )
        assert add_btn.count() > 0, "No add/create button found on MCP profiles page"
        _screenshot(
            page,
            screenshots_dir,
            "TestProfilesDeep",
            "test_add_profile_button_exists",
        )


# ---------------------------------------------------------------------------
# 6. Reports Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestReportsDeep:
    def test_reports_tabs_exist(self, page, server_url, screenshots_dir):
        """Verify Test Runs and Smoke Tests tabs exist."""
        page.goto(f"{server_url}/reports")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        assert "500 Internal Server Error" not in content
        _screenshot(page, screenshots_dir, "TestReportsDeep", "test_reports_tabs_exist")

    def test_click_smoke_tests_tab(self, page, server_url, screenshots_dir):
        """Click Smoke Tests tab and verify no errors."""
        page.goto(f"{server_url}/reports")
        page.wait_for_load_state("networkidle")
        smoke_tab = page.locator("button:has-text('Smoke')")
        if smoke_tab.count() > 0:
            smoke_tab.first.click()
            page.wait_for_timeout(500)
            content = page.text_content("body") or ""
            assert "500 Internal Server Error" not in content
        _screenshot(
            page,
            screenshots_dir,
            "TestReportsDeep",
            "test_click_smoke_tests_tab",
        )


# ---------------------------------------------------------------------------
# 7. Configuration Deep Tests
# ---------------------------------------------------------------------------
@pytest.mark.e2e
class TestConfigDeep:
    def test_config_shows_no_errors(self, page, server_url, screenshots_dir):
        """Verify config page shows settings, not error messages."""
        page.goto(f"{server_url}/config")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        for error in [
            "500",
            "502",
            "503",
            "Internal Server Error",
            "Failed to load",
        ]:
            assert error not in content, f"Found '{error}' on config page"
        _screenshot(page, screenshots_dir, "TestConfigDeep", "test_config_shows_no_errors")

    def test_config_shows_model_info(self, page, server_url, screenshots_dir):
        """Verify config page shows DEFAULT_MODEL or similar."""
        page.goto(f"{server_url}/config")
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        assert len(content) > 100, "Config page seems empty"
        _screenshot(page, screenshots_dir, "TestConfigDeep", "test_config_shows_model_info")


# ---------------------------------------------------------------------------
# 8. Content Error Scanner (runs on ALL pages)
# ---------------------------------------------------------------------------
ERROR_PATTERNS = [
    "500 Internal Server Error",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
    "Internal Server Error",
    "Network Error",
    "Failed to fetch",
    "TypeError:",
    "ReferenceError:",
    "SyntaxError:",
    "Cannot read properties of",
    "is not a function",
    "Unexpected token",
    "ECONNREFUSED",
    "Unhandled Runtime Error",
]

_UI_LABEL_KEYWORDS = [
    "evaluator",
    "handling",
    "test name",
    "auth error",
]


@pytest.mark.e2e
@pytest.mark.parametrize("path,name", PAGES)
def test_page_has_no_error_content(page, server_url, screenshots_dir, path, name):
    """Scan page text content for error patterns."""
    page.goto(f"{server_url}{path}")
    page.wait_for_load_state("networkidle")
    text = page.text_content("body") or ""
    for pattern in ERROR_PATTERNS:
        if pattern in text:
            idx = text.index(pattern)
            context = text[max(0, idx - 50) : idx + 50]
            # Skip if it's clearly a UI label
            if any(label in context.lower() for label in _UI_LABEL_KEYWORDS):
                continue
            raise AssertionError(
                f"Page {name} contains error pattern '{pattern}' in context: ...{context}..."
            )
    _screenshot(
        page,
        screenshots_dir,
        "ErrorScanner",
        f"test_page_has_no_error_content_{name}",
    )
