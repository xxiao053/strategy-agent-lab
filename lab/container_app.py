"""Trusted local Compose controller entry point; never runs generated imports."""
from pathlib import Path
import os
from .docker_runtime import cleanup_owned


def main():
    root=Path(os.environ['LAB_DATA_ROOT'])/'runs'
    cleanup_owned(root)
    import uvicorn
    try:uvicorn.run('lab.api:create_app',factory=True,host='0.0.0.0',port=8765,access_log=False)
    finally:cleanup_owned(root)


if __name__=='__main__':main()
