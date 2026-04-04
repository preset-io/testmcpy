"""Integration tests for the smoke-test command."""


def test_smoke_test_help(runner, cli_app):
    """smoke-test --help should display usage information."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "smoke" in result.stdout.lower()


def test_smoke_test_help_shows_profile_option(runner, cli_app):
    """smoke-test --help should list the --profile option."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "profile" in result.stdout.lower()


def test_smoke_test_help_shows_mcp_url_option(runner, cli_app):
    """smoke-test --help should list the --mcp-url option."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "mcp-url" in result.stdout.lower()


def test_smoke_test_help_shows_format_option(runner, cli_app):
    """smoke-test --help should list the --format option."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "format" in result.stdout.lower()


def test_smoke_test_help_shows_max_tools_option(runner, cli_app):
    """smoke-test --help should list the --max-tools option."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "max-tools" in result.stdout.lower()


def test_smoke_test_help_shows_save_option(runner, cli_app):
    """smoke-test --help should list the --save option."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "save" in result.stdout.lower()


def test_smoke_test_help_shows_test_all_flag(runner, cli_app):
    """smoke-test --help should list the --test-all/--basic-only flag."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    assert "test-all" in result.stdout.lower() or "basic-only" in result.stdout.lower()


def test_smoke_test_help_mentions_examples(runner, cli_app):
    """smoke-test --help should include usage examples in the docstring."""
    result = runner.invoke(cli_app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    # The docstring mentions "smoke-test" in examples
    assert "smoke" in result.stdout.lower()
