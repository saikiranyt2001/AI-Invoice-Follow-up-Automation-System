from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"


def npm_command(*args: str) -> list[str]:
    executable = "npm.cmd" if sys.platform.startswith("win") else "npm"
    return [executable, *args]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backend and frontend locally with a clean dev database.")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--db-path", default=str(BACKEND_DIR / "local_stack.db"))
    return parser.parse_args()


def start_process(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(command, cwd=cwd, env=env)


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    args = parse_args()
    python = sys.executable

    backend_env = os.environ.copy()
    backend_env.setdefault("DATABASE_URL", f"sqlite:///{Path(args.db_path).as_posix()}")

    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE"] = f"http://127.0.0.1:{args.backend_port}"

    backend = start_process(
        [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.backend_port)],
        BACKEND_DIR,
        backend_env,
    )
    frontend = start_process(
        npm_command("run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.frontend_port)),
        FRONTEND_DIR,
        frontend_env,
    )

    print(f"Backend:  http://127.0.0.1:{args.backend_port}")
    print(f"Frontend: http://127.0.0.1:{args.frontend_port}")
    print("Press Ctrl+C to stop both processes.")

    try:
        while True:
            if backend.poll() is not None:
                return backend.returncode or 1
            if frontend.poll() is not None:
                return frontend.returncode or 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping local stack...")
    finally:
        terminate_process(frontend)
        terminate_process(backend)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
