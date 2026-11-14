"""Explicit project-bound entry point for the detached Windows launcher."""

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import os
from pathlib import Path
import sys
import traceback

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--stdout-log", required=True)
    parser.add_argument("--stderr-log", required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    # PowerShell redirection retains inherited capture pipes on Windows. Open
    # logs here so ShellExecute can detach the process without those handles.
    with ExitStack() as stack:
        output = stack.enter_context(open(arguments.stdout_log, "a", encoding="utf-8", buffering=1))
        errors = stack.enter_context(open(arguments.stderr_log, "a", encoding="utf-8", buffering=1))
        stack.enter_context(redirect_stdout(output))
        stack.enter_context(redirect_stderr(errors))
        try:
            import uvicorn

            uvicorn.run(
                "lab.api:create_app", factory=True, host="127.0.0.1",
                port=arguments.port, access_log=False,
            )
        except Exception:
            traceback.print_exc()
            raise SystemExit(1)
