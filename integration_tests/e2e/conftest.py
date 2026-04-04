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
    """Start testmcpy server for E2E tests."""
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
