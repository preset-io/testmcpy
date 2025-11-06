"""
Theme customization for testmcpy TUI.

Provides color schemes and styling for the terminal interface.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ColorScheme:
    """Color scheme definition for the TUI."""

    name: str
    primary: str  # Main brand color
    secondary: str  # Secondary accent
    success: str  # Success states
    error: str  # Error states
    warning: str  # Warning states
    info: str  # Info messages
    dim: str  # Dimmed/disabled text
    background: str  # Background color
    surface: str  # Surface/panel color
    border: str  # Border color
    text: str  # Primary text color
    text_muted: str  # Muted text color


# Default theme - Cyan/Dark (testmcpy brand colors)
DEFAULT_THEME = ColorScheme(
    name="default",
    primary="#00D9FF",  # Cyan (testmcpy brand)
    secondary="#7C3AED",  # Purple
    success="#10B981",  # Green
    error="#EF4444",  # Red
    warning="#F59E0B",  # Yellow/Orange
    info="#3B82F6",  # Blue
    dim="#6B7280",  # Gray
    background="#0F172A",  # Dark blue-gray
    surface="#1E293B",  # Slightly lighter
    border="#334155",  # Border gray
    text="#F8FAFC",  # Almost white
    text_muted="#94A3B8",  # Muted gray
)

# Light mode theme
LIGHT_THEME = ColorScheme(
    name="light",
    primary="#0891B2",  # Darker cyan for light bg
    secondary="#7C3AED",  # Purple
    success="#059669",  # Darker green
    error="#DC2626",  # Darker red
    warning="#D97706",  # Darker orange
    info="#2563EB",  # Darker blue
    dim="#9CA3AF",  # Gray
    background="#FFFFFF",  # White
    surface="#F8FAFC",  # Light gray
    border="#E2E8F0",  # Light border
    text="#0F172A",  # Dark text
    text_muted="#64748B",  # Muted dark gray
)

# High contrast theme
HIGH_CONTRAST_THEME = ColorScheme(
    name="high_contrast",
    primary="#00FFFF",  # Bright cyan
    secondary="#FF00FF",  # Magenta
    success="#00FF00",  # Bright green
    error="#FF0000",  # Bright red
    warning="#FFFF00",  # Bright yellow
    info="#0000FF",  # Bright blue
    dim="#808080",  # Gray
    background="#000000",  # Pure black
    surface="#1A1A1A",  # Dark gray
    border="#FFFFFF",  # White border
    text="#FFFFFF",  # Pure white
    text_muted="#AAAAAA",  # Light gray
)


# Available themes
THEMES = {
    "default": DEFAULT_THEME,
    "light": LIGHT_THEME,
    "high_contrast": HIGH_CONTRAST_THEME,
}

ThemeName = Literal["default", "light", "high_contrast"]


def get_theme(name: str = "default") -> ColorScheme:
    """Get a theme by name, fallback to default if not found."""
    return THEMES.get(name, DEFAULT_THEME)


def list_themes() -> list[str]:
    """List all available theme names."""
    return list(THEMES.keys())


# Rich color mappings for terminal output
def get_rich_theme_colors(theme: ColorScheme) -> dict[str, str]:
    """Convert theme to Rich color mappings for terminal output."""
    return {
        "primary": theme.primary,
        "secondary": theme.secondary,
        "success": theme.success,
        "error": theme.error,
        "warning": theme.warning,
        "info": theme.info,
        "dim": theme.dim,
        "text": theme.text,
        "text.muted": theme.text_muted,
    }


# Textual CSS color mappings
def get_textual_css_vars(theme: ColorScheme) -> str:
    """Generate Textual CSS variables for a theme."""
    return f"""
    $primary: {theme.primary};
    $secondary: {theme.secondary};
    $success: {theme.success};
    $error: {theme.error};
    $warning: {theme.warning};
    $info: {theme.info};
    $dim: {theme.dim};
    $background: {theme.background};
    $surface: {theme.surface};
    $border: {theme.border};
    $text: {theme.text};
    $text-muted: {theme.text_muted};
    """
