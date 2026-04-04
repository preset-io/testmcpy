"""Integration tests for basic CLI commands: version, help, init."""

import os


def test_version_flag(runner, cli_app):
    """--version flag should exit 0 and print version info."""
    result = runner.invoke(cli_app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.stdout.lower() or "testmcpy" in result.stdout.lower()


def test_version_short_flag(runner, cli_app):
    """-v flag should also show version."""
    result = runner.invoke(cli_app, ["-v"])
    assert result.exit_code == 0


def test_help_flag(runner, cli_app):
    """--help flag should exit 0 and describe the CLI."""
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert "testmcpy" in result.stdout.lower() or "mcp" in result.stdout.lower()


def test_help_lists_commands(runner, cli_app):
    """--help should list known sub-commands."""
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    # These commands are registered via the CLI
    assert "run" in result.stdout
    assert "tools" in result.stdout


def test_init_creates_project_structure(runner, cli_app, tmp_path):
    """init command should create tests/ and evals/ dirs with example files."""
    result = runner.invoke(cli_app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "tests").is_dir()
    assert (tmp_path / "evals").is_dir()
    # Should create an example test file
    assert (tmp_path / "tests" / "example_tests.yaml").exists()


def test_init_creates_config_file(runner, cli_app, tmp_path):
    """init command should create a config YAML file."""
    result = runner.invoke(cli_app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    # Check that some config file exists in the target directory
    yaml_files = list(tmp_path.glob("*.yaml")) + list(tmp_path.glob("*.yml"))
    assert len(yaml_files) > 0


def test_init_idempotent(runner, cli_app, tmp_path):
    """Running init twice should not fail."""
    result1 = runner.invoke(cli_app, ["init", str(tmp_path)])
    assert result1.exit_code == 0
    result2 = runner.invoke(cli_app, ["init", str(tmp_path)])
    assert result2.exit_code == 0


def test_init_default_path(runner, cli_app, tmp_path):
    """init with no path should default to current directory."""
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(cli_app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "tests").is_dir()
    finally:
        os.chdir(original_cwd)
