"""The `authlib.jose module is deprecated` warning (emitted transitively by
fastmcp's JWT verifier) must not surface from a normal testmcpy import.

authlib installs its own ``simplefilter("always", AuthlibDeprecationWarning)``,
so a naive ignore registered too early is overridden; testmcpy/__init__.py
works around that. This guards the fix in a fresh subprocess (a same-process
test can't re-trigger the import-time warning once modules are cached).
"""

import subprocess
import sys


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )


def test_authlib_jose_deprecation_not_emitted_on_import():
    # Importing testmcpy (which runs the silencer) then pulling in the fastmcp
    # client chain must not print the authlib deprecation warning to stderr.
    result = _run("import testmcpy\nfrom testmcpy.src.mcp_client import MCPClient\nprint('ok')\n")
    assert "ok" in result.stdout
    assert "authlib.jose module is deprecated" not in result.stderr, result.stderr


def test_warning_is_present_without_the_silencer():
    # Sanity check that the warning genuinely fires when the silencer is bypassed
    # — otherwise the test above could pass for the wrong reason (e.g. authlib or
    # fastmcp absent). If fastmcp/authlib isn't installed, skip rather than fail.
    result = _run(
        "import warnings\n"
        "warnings.simplefilter('always')\n"
        "try:\n"
        "    import authlib.jose  # noqa\n"
        "except ImportError:\n"
        "    print('NO_AUTHLIB')\n"
    )
    if "NO_AUTHLIB" in result.stdout:
        import pytest

        pytest.skip("authlib not installed")
    assert "authlib.jose module is deprecated" in result.stderr, result.stderr
