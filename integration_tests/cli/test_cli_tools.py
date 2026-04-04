"""Integration tests for the tools command."""


def test_tools_help(runner, cli_app):
    """tools --help should display usage information."""
    result = runner.invoke(cli_app, ["tools", "--help"])
    assert result.exit_code == 0
    assert "tool" in result.stdout.lower()


def test_tools_help_shows_format_option(runner, cli_app):
    """tools --help should list the --format option."""
    result = runner.invoke(cli_app, ["tools", "--help"])
    assert result.exit_code == 0
    assert "format" in result.stdout.lower()


def test_tools_help_shows_filter_option(runner, cli_app):
    """tools --help should list the --filter option."""
    result = runner.invoke(cli_app, ["tools", "--help"])
    assert result.exit_code == 0
    assert "filter" in result.stdout.lower()


def test_tools_help_shows_detail_option(runner, cli_app):
    """tools --help should list the --detail option."""
    result = runner.invoke(cli_app, ["tools", "--help"])
    assert result.exit_code == 0
    assert "detail" in result.stdout.lower()


def test_tools_help_shows_profile_option(runner, cli_app):
    """tools --help should list the --profile option."""
    result = runner.invoke(cli_app, ["tools", "--help"])
    assert result.exit_code == 0
    assert "profile" in result.stdout.lower()


def test_tools_help_shows_mcp_url_option(runner, cli_app):
    """tools --help should list the --mcp-url option."""
    result = runner.invoke(cli_app, ["tools", "--help"])
    assert result.exit_code == 0
    assert "mcp-url" in result.stdout.lower()


def test_export_help(runner, cli_app):
    """export --help should display usage information."""
    result = runner.invoke(cli_app, ["export", "--help"])
    assert result.exit_code == 0
    assert "export" in result.stdout.lower()


def test_export_help_lists_formats(runner, cli_app):
    """export --help should mention supported formats."""
    result = runner.invoke(cli_app, ["export", "--help"])
    assert result.exit_code == 0
    assert "format" in result.stdout.lower()
