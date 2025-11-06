"""
Configuration screen for testmcpy TUI.

Allows editing of LLM settings, MCP profiles, and advanced settings.
"""

from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Select, Static

from testmcpy.config import Config, reload_config
from testmcpy.mcp_profiles import (
    AuthConfig,
    MCPConfig,
    MCPProfile,
    list_available_profiles,
    load_profile,
    save_profile,
)


class ConfigSection(Container):
    """Base class for configuration sections."""

    DEFAULT_CSS = """
    ConfigSection {
        height: auto;
        border: solid $border;
        border-title-color: $primary;
        margin: 1;
        padding: 1;
    }

    ConfigSection > Label {
        margin-bottom: 1;
        color: $text-muted;
    }

    ConfigSection Input {
        margin-bottom: 1;
    }
    """


class LLMSettingsSection(ConfigSection):
    """LLM provider and model configuration."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.border_title = "LLM Settings"

    def compose(self) -> ComposeResult:
        """Compose the LLM settings section."""
        yield Label("Configure your LLM provider and default model")

        # Provider selection
        providers = [
            ("Anthropic (Claude)", "anthropic"),
            ("OpenAI (GPT)", "openai"),
            ("Ollama (Local)", "ollama"),
        ]
        current_provider = self.config.default_provider or "anthropic"
        yield Label("Default Provider:")
        yield Select(
            providers,
            value=current_provider,
            id="provider_select",
        )

        # Model selection (will update based on provider)
        yield Label("Default Model:")
        yield Input(
            value=self.config.default_model or "",
            placeholder="e.g., claude-haiku-4-5",
            id="model_input",
        )

        # API Keys section
        yield Label("API Keys:")
        with Horizontal():
            yield Button("Configure API Keys", id="configure_keys_btn", variant="primary")


class MCPProfilesSection(ConfigSection):
    """MCP profiles management."""

    def __init__(self, profiles: list[MCPProfile]):
        super().__init__()
        self.profiles = profiles
        self.border_title = "MCP Profiles"

    def compose(self) -> ComposeResult:
        """Compose the MCP profiles section."""
        yield Label(f"Manage your MCP service profiles ({len(self.profiles)} configured)")

        if not self.profiles:
            yield Static("No profiles configured. Add one to get started.", classes="dim")
            yield Button("+ Add Profile", id="add_profile_btn", variant="success")
        else:
            # List existing profiles
            for i, profile in enumerate(self.profiles):
                with Container(classes="profile-item"):
                    # Profile header
                    with Horizontal():
                        status = "●" if profile.is_default else "○"
                        yield Label(f"{status} {profile.profile_id}")
                        yield Button("Edit", id=f"edit_profile_{i}", variant="default")
                        yield Button("Delete", id=f"delete_profile_{i}", variant="error")

                    # Profile details
                    mcp_count = len(profile.mcps) if profile.mcps else 0
                    yield Label(
                        f"  {mcp_count} MCP service(s) configured",
                        classes="dim",
                    )

                    if profile.mcps:
                        first_mcp = profile.mcps[0]
                        yield Label(f"  URL: {first_mcp.mcp_url}", classes="dim")
                        yield Label(f"  Auth: {first_mcp.auth.auth_type}", classes="dim")

            # Add new profile button
            yield Button("+ Add Profile", id="add_profile_btn", variant="success")


class AdvancedSettingsSection(ConfigSection):
    """Advanced settings configuration."""

    def __init__(self):
        super().__init__()
        self.border_title = "Advanced Settings"

    def compose(self) -> ComposeResult:
        """Compose the advanced settings section."""
        yield Label("Configure timeouts, retries, and other advanced options")

        # Test timeout
        yield Label("Test Timeout (seconds):")
        yield Input(value="30", placeholder="30", id="timeout_input")

        # Max retries
        yield Label("Max Retries:")
        yield Input(value="3", placeholder="3", id="retries_input")

        # Enable caching
        with Horizontal():
            yield Checkbox("Enable Caching", value=True, id="caching_checkbox")

        # Log level
        yield Label("Log Level:")
        log_levels = [
            ("DEBUG", "DEBUG"),
            ("INFO", "INFO"),
            ("WARNING", "WARNING"),
            ("ERROR", "ERROR"),
        ]
        yield Select(log_levels, value="INFO", id="log_level_select")

        # Theme selection
        yield Label("Theme:")
        themes = [
            ("Default (Cyan/Dark)", "default"),
            ("Light Mode", "light"),
            ("High Contrast", "high_contrast"),
        ]
        yield Select(themes, value="default", id="theme_select")


class ConfigScreen(Screen):
    """Configuration screen for editing testmcpy settings."""

    BINDINGS = [
        Binding("s", "save", "Save", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("escape", "quit", "Quit", show=False),
        Binding("h", "go_home", "Home", priority=True),
    ]

    DEFAULT_CSS = """
    ConfigScreen {
        background: $background;
    }

    #config_container {
        width: 100%;
        height: 100%;
    }

    .profile-item {
        border: solid $border;
        margin: 1;
        padding: 1;
    }

    .dim {
        color: $dim;
    }

    Button {
        margin-right: 1;
    }
    """

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self.config = Config()
        self.profiles = list_available_profiles()
        self.has_changes = False

    def compose(self) -> ComposeResult:
        """Compose the configuration screen."""
        yield Header()
        with VerticalScroll(id="config_container"):
            yield LLMSettingsSection(self.config)
            yield MCPProfilesSection(self.profiles)
            yield AdvancedSettingsSection()
        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.title = "testmcpy - Configuration"
        self.sub_title = "Edit settings and profiles"

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Mark as having changes when input changes."""
        self.has_changes = True

    @on(Select.Changed)
    def on_select_changed(self, event: Select.Changed) -> None:
        """Mark as having changes when select changes."""
        self.has_changes = True

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Mark as having changes when checkbox changes."""
        self.has_changes = True

    @on(Button.Pressed, "#configure_keys_btn")
    def show_api_keys_modal(self) -> None:
        """Show API keys configuration modal."""
        self.app.push_screen(APIKeysModal())

    @on(Button.Pressed, "#add_profile_btn")
    def show_add_profile_modal(self) -> None:
        """Show add profile modal."""
        self.app.push_screen(AddProfileModal())

    def action_save(self) -> None:
        """Save configuration changes."""
        if not self.has_changes:
            self.notify("No changes to save", severity="information")
            return

        # Gather values from UI
        try:
            # LLM Settings
            provider_select = self.query_one("#provider_select", Select)
            model_input = self.query_one("#model_input", Input)

            # Advanced settings
            timeout_input = self.query_one("#timeout_input", Input)
            retries_input = self.query_one("#retries_input", Input)
            caching_checkbox = self.query_one("#caching_checkbox", Checkbox)
            log_level_select = self.query_one("#log_level_select", Select)
            theme_select = self.query_one("#theme_select", Select)

            # Save to ~/.testmcpy
            config_file = Path.home() / ".testmcpy"
            config_lines = []

            if provider_select.value:
                config_lines.append(f"DEFAULT_PROVIDER={provider_select.value}")
            if model_input.value:
                config_lines.append(f"DEFAULT_MODEL={model_input.value}")

            # Add advanced settings as comments (these are app-level, not config file)
            config_lines.append(f"\n# Advanced Settings")
            config_lines.append(f"# TEST_TIMEOUT={timeout_input.value}")
            config_lines.append(f"# MAX_RETRIES={retries_input.value}")
            config_lines.append(f"# ENABLE_CACHING={'true' if caching_checkbox.value else 'false'}")
            config_lines.append(f"# LOG_LEVEL={log_level_select.value}")
            config_lines.append(f"# THEME={theme_select.value}")

            # Preserve existing API keys and other settings
            if config_file.exists():
                with open(config_file, "r") as f:
                    existing_lines = f.readlines()
                    for line in existing_lines:
                        line = line.strip()
                        if line.startswith("ANTHROPIC_API_KEY=") or line.startswith("OPENAI_API_KEY="):
                            if line not in config_lines:
                                config_lines.append(line)

            # Write config
            with open(config_file, "w") as f:
                f.write("\n".join(config_lines))

            # Reload config
            reload_config()

            self.has_changes = False
            self.notify("Configuration saved successfully", severity="information")

        except Exception as e:
            self.notify(f"Error saving configuration: {e}", severity="error")

    def action_quit(self) -> None:
        """Quit the configuration screen."""
        if self.has_changes:
            # Show confirmation modal
            self.app.push_screen(ConfirmQuitModal(self._do_quit))
        else:
            self._do_quit()

    def _do_quit(self) -> None:
        """Actually quit the screen."""
        self.app.pop_screen()

    def action_go_home(self) -> None:
        """Navigate to home screen."""
        if self.has_changes:
            self.notify("Save or discard changes first", severity="warning")
        else:
            self.app.switch_screen("home")


class APIKeysModal(Screen):
    """Modal for configuring API keys."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
        Binding("s", "save", "Save"),
    ]

    DEFAULT_CSS = """
    APIKeysModal {
        align: center middle;
    }

    #api_keys_dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the API keys modal."""
        with Container(id="api_keys_dialog"):
            yield Label("Configure API Keys", classes="title")
            yield Label("API keys are stored in ~/.testmcpy", classes="dim")

            yield Label("Anthropic API Key:")
            yield Input(
                password=True,
                placeholder="sk-ant-...",
                id="anthropic_key",
            )

            yield Label("OpenAI API Key:")
            yield Input(
                password=True,
                placeholder="sk-...",
                id="openai_key",
            )

            yield Label("Ollama Base URL:")
            yield Input(
                value="http://localhost:11434",
                placeholder="http://localhost:11434",
                id="ollama_url",
            )

            with Horizontal():
                yield Button("Save", variant="primary", id="save_keys_btn")
                yield Button("Cancel", variant="default", id="cancel_keys_btn")

    @on(Button.Pressed, "#save_keys_btn")
    def save_keys(self) -> None:
        """Save API keys to config."""
        try:
            anthropic_key = self.query_one("#anthropic_key", Input).value
            openai_key = self.query_one("#openai_key", Input).value
            ollama_url = self.query_one("#ollama_url", Input).value

            config_file = Path.home() / ".testmcpy"
            config_lines = []

            # Read existing config
            if config_file.exists():
                with open(config_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        # Skip old API key lines
                        if not any(
                            [
                                line.startswith("ANTHROPIC_API_KEY="),
                                line.startswith("OPENAI_API_KEY="),
                                line.startswith("OLLAMA_BASE_URL="),
                            ]
                        ):
                            config_lines.append(line)

            # Add new keys if provided
            if anthropic_key:
                config_lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")
            if openai_key:
                config_lines.append(f"OPENAI_API_KEY={openai_key}")
            if ollama_url:
                config_lines.append(f"OLLAMA_BASE_URL={ollama_url}")

            # Write config
            with open(config_file, "w") as f:
                f.write("\n".join(config_lines))

            reload_config()
            self.app.pop_screen()
            self.notify("API keys saved successfully", severity="information")

        except Exception as e:
            self.notify(f"Error saving API keys: {e}", severity="error")

    @on(Button.Pressed, "#cancel_keys_btn")
    def action_dismiss(self) -> None:
        """Cancel and close the modal."""
        self.app.pop_screen()


class AddProfileModal(Screen):
    """Modal for adding a new MCP profile."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
        Binding("s", "save", "Save"),
    ]

    DEFAULT_CSS = """
    AddProfileModal {
        align: center middle;
    }

    #add_profile_dialog {
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the add profile modal."""
        with Container(id="add_profile_dialog"):
            yield Label("Add MCP Profile", classes="title")
            yield Label("Create a new MCP service profile", classes="dim")

            yield Label("Profile Name:")
            yield Input(placeholder="e.g., prod, dev, staging", id="profile_name")

            yield Label("MCP URL:")
            yield Input(
                placeholder="https://your-server.com/mcp",
                id="mcp_url",
            )

            yield Label("Auth Type:")
            auth_types = [
                ("Bearer Token", "bearer"),
                ("JWT (Dynamic)", "jwt"),
                ("OAuth", "oauth"),
            ]
            yield Select(auth_types, value="bearer", id="auth_type")

            yield Label("Auth Token (for Bearer):")
            yield Input(
                password=True,
                placeholder="Your bearer token",
                id="auth_token",
            )

            with Horizontal():
                yield Checkbox("Set as default", value=False, id="set_default")

            with Horizontal():
                yield Button("Test Connection", variant="default", id="test_conn_btn")
                yield Button("Save", variant="primary", id="save_profile_btn")
                yield Button("Cancel", variant="default", id="cancel_profile_btn")

    @on(Button.Pressed, "#test_conn_btn")
    @work
    async def test_connection(self) -> None:
        """Test the MCP connection."""
        self.notify("Testing connection...", severity="information")
        # TODO: Implement actual connection test
        # For now, just simulate
        import asyncio

        await asyncio.sleep(1)
        self.notify("Connection test not yet implemented", severity="warning")

    @on(Button.Pressed, "#save_profile_btn")
    def save_profile_data(self) -> None:
        """Save the new profile."""
        try:
            profile_name = self.query_one("#profile_name", Input).value
            mcp_url = self.query_one("#mcp_url", Input).value
            auth_type = self.query_one("#auth_type", Select).value
            auth_token = self.query_one("#auth_token", Input).value
            set_default = self.query_one("#set_default", Checkbox).value

            if not profile_name:
                self.notify("Profile name is required", severity="error")
                return
            if not mcp_url:
                self.notify("MCP URL is required", severity="error")
                return

            # Create profile
            auth_config = AuthConfig(auth_type=auth_type, token=auth_token if auth_token else None)

            mcp_config = MCPConfig(
                name=profile_name,
                mcp_url=mcp_url,
                auth=auth_config,
            )

            profile = MCPProfile(
                profile_id=profile_name,
                is_default=set_default,
                mcps=[mcp_config],
            )

            # Save profile to .mcp_services.yaml
            save_profile(profile)

            self.app.pop_screen()
            self.notify(f"Profile '{profile_name}' created successfully", severity="information")

        except Exception as e:
            self.notify(f"Error creating profile: {e}", severity="error")

    @on(Button.Pressed, "#cancel_profile_btn")
    def action_dismiss(self) -> None:
        """Cancel and close the modal."""
        self.app.pop_screen()


class ConfirmQuitModal(Screen):
    """Modal to confirm quitting with unsaved changes."""

    DEFAULT_CSS = """
    ConfirmQuitModal {
        align: center middle;
    }

    #confirm_dialog {
        width: 50;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1;
    }
    """

    def __init__(self, on_confirm: callable):
        super().__init__()
        self.on_confirm = on_confirm

    def compose(self) -> ComposeResult:
        """Compose the confirmation modal."""
        with Container(id="confirm_dialog"):
            yield Label("Unsaved Changes", classes="title")
            yield Label("You have unsaved changes. Are you sure you want to quit?", classes="warning")

            with Horizontal():
                yield Button("Discard Changes", variant="error", id="discard_btn")
                yield Button("Cancel", variant="default", id="cancel_btn")

    @on(Button.Pressed, "#discard_btn")
    def confirm_quit(self) -> None:
        """Confirm quitting without saving."""
        self.app.pop_screen()  # Remove this modal
        self.on_confirm()

    @on(Button.Pressed, "#cancel_btn")
    def cancel_quit(self) -> None:
        """Cancel quitting."""
        self.app.pop_screen()
