import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="session")
def screenshots_dir():
    d = Path(__file__).parent / "screenshots"
    d.mkdir(exist_ok=True)
    return d


@pytest.fixture(scope="session")
def server_url():
    """Start testmcpy server for E2E tests.

    If TESTMCPY_E2E_SERVER_URL is set, use that external server instead
    of starting a new one. This lets you run E2E tests against a server
    rooted in a specific directory (e.g. preset-mcp-tests).
    """
    external_url = os.environ.get("TESTMCPY_E2E_SERVER_URL")
    if external_url:
        # Verify external server is reachable
        try:
            resp = httpx.get(f"{external_url}/api/health", timeout=5)
            if resp.status_code == 200:
                yield external_url
                return
        except (httpx.ConnectError, httpx.ReadTimeout):
            pytest.skip(f"External server at {external_url} not reachable")
            return

    port = 18765
    proc = subprocess.Popen(
        ["testmcpy", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(30):
        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
            if resp.status_code == 200:
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(1)
    else:
        proc.terminate()
        pytest.skip("Server failed to start")
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(timeout=5)
