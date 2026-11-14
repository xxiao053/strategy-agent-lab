"""Exercise the Windows launcher against an isolated, real HTTP service."""

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")


@pytest.fixture
def isolated_project(tmp_path):
    # A foreground launcher that waits for the server forever must fail this test.
    project = tmp_path / "local project with spaces"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "start.ps1", project / "start.ps1")
    helper = ROOT / "scripts" / "start-local.py"
    if helper.exists():
        shutil.copy2(helper, scripts / helper.name)
    environment = project / ".venv"
    (environment / "Scripts").mkdir(parents=True)
    shutil.copy2(sys.executable, environment / "Scripts" / "python.exe")
    shutil.copy2(Path(sys.prefix) / "pyvenv.cfg", environment / "pyvenv.cfg")
    packages = environment / "Lib" / "site-packages"
    packages.mkdir(parents=True)
    (packages / "test-dependencies.pth").write_text(
        str(Path(sys.prefix) / "Lib" / "site-packages") + "\n", encoding="utf-8"
    )
    (project / "lab").mkdir()
    (project / "lab" / "__init__.py").touch()
    (project / "lab" / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "from fastapi.responses import HTMLResponse\n"
        "def create_app():\n"
        "    app = FastAPI()\n"
        "    @app.get('/api/bootstrap')\n"
        "    def bootstrap(): return {'local_only': True}\n"
        "    @app.get('/')\n"
        "    def home(): return HTMLResponse('<html>isolated startup fixture</html>')\n"
        "    return app\n",
        encoding="utf-8",
    )
    (project / "web" / "dist").mkdir(parents=True)
    (project / "web" / "dist" / "index.html").write_text("fixture", encoding="utf-8")
    return project


def unused_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def start(project, port):
    return subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(project / "start.ps1"), "-Port", str(port)],
        cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def fixture_processes(project):
    """Resolve exact fixture-owned processes, never a broad image-name kill."""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "@(Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | "
         "Select-Object ProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"],
        capture_output=True, text=True, check=True,
    )
    processes = json.loads(result.stdout or "[]")
    if isinstance(processes, dict):
        processes = [processes]
    root = str(project).lower()
    return [p for p in processes if root in (p.get("CommandLine") or "").lower()
            or root in (p.get("ExecutablePath") or "").lower()]


def cleanup(project, launcher):
    if launcher.poll() is None:
        launcher.terminate()
    for process in fixture_processes(project):
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"Stop-Process -Id {int(process['ProcessId'])} -ErrorAction SilentlyContinue"],
            capture_output=True, check=False,
        )
    launcher.communicate(timeout=10)


def test_launcher_returns_ready_and_service_survives_launcher_exit(isolated_project):
    port = unused_port()
    launcher = start(isolated_project, port)
    try:
        try:
            stdout, stderr = launcher.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            pytest.fail("start.ps1 must return after readiness, not remain a foreground server")
        assert launcher.returncode == 0, stdout + stderr
        assert f"http://127.0.0.1:{port}" in stdout
        assert re.search(r"PID\s*[:=]?\s*\d+", stdout, re.IGNORECASE), stdout
        time.sleep(0.3)
        with urlopen(f"http://127.0.0.1:{port}/api/bootstrap", timeout=3) as response:
            assert json.load(response) == {"local_only": True}
        with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
            assert b"isolated startup fixture" in response.read()
    finally:
        cleanup(isolated_project, launcher)


def test_existing_instance_is_reused_without_duplicate_process(isolated_project):
    port = unused_port()
    launcher = start(isolated_project, port)
    try:
        stdout, stderr = launcher.communicate(timeout=15)
        assert launcher.returncode == 0, stdout + stderr
        before = {p["ProcessId"] for p in fixture_processes(isolated_project)}
        repeated = start(isolated_project, port)
        try:
            stdout, stderr = repeated.communicate(timeout=10)
            assert repeated.returncode == 0, stdout + stderr
            assert "already" in stdout.lower(), stdout
            assert {p["ProcessId"] for p in fixture_processes(isolated_project)} == before
        finally:
            if repeated.poll() is None:
                repeated.terminate()
                repeated.communicate(timeout=10)
    finally:
        cleanup(isolated_project, launcher)


def test_unrelated_listener_is_not_reused_or_stopped(isolated_project):
    class UnrelatedHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"unrelated service")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), UnrelatedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    launcher = start(isolated_project, port)
    try:
        stdout, stderr = launcher.communicate(timeout=10)
        assert launcher.returncode != 0, stdout + stderr
        assert "occupied" in (stdout + stderr).lower(), stdout + stderr
        with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
            assert response.read() == b"unrelated service"
        assert not fixture_processes(isolated_project)
    finally:
        cleanup(isolated_project, launcher)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_startup_failure_returns_error_and_preserves_diagnostic_log(isolated_project):
    # Import failures must not disappear into the hidden process's console.
    (isolated_project / "lab" / "api.py").write_text(
        "raise RuntimeError('isolated startup failure')\n", encoding="utf-8"
    )
    launcher = start(isolated_project, unused_port())
    try:
        stdout, stderr = launcher.communicate(timeout=15)
        assert launcher.returncode != 0, stdout + stderr
        logs = list((isolated_project / "logs").glob("*.stderr.log"))
        assert len(logs) == 1
        assert "isolated startup failure" in logs[0].read_text(encoding="utf-8")
        # PowerShell wraps exception lines at the host width, including paths.
        assert "".join(str(logs[0]).split()) in "".join((stdout + stderr).split())
    finally:
        cleanup(isolated_project, launcher)
