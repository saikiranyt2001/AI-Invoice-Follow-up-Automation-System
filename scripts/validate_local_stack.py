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
    parser = argparse.ArgumentParser(description="Start a clean local stack and validate it end to end.")
    parser.add_argument("--backend-port", type=int, default=8011)
    parser.add_argument("--frontend-port", type=int, default=4173)
    parser.add_argument("--db-path", default=str(BACKEND_DIR / "validation_stack.db"))
    parser.add_argument("--password", default="StrongPass123!")
    return parser.parse_args()


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    args = parse_args()
    python = sys.executable

    backend_env = os.environ.copy()
    backend_env["DATABASE_URL"] = f"sqlite:///{Path(args.db_path).as_posix()}"
    backend_env.setdefault("AUTH_SECRET_KEY", "local-stack-validation-secret")

    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE"] = f"http://127.0.0.1:{args.backend_port}"

    backend = subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.backend_port)],
        cwd=BACKEND_DIR,
        env=backend_env,
    )
    frontend = subprocess.Popen(
        npm_command("run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.frontend_port)),
        cwd=FRONTEND_DIR,
        env=frontend_env,
    )

    try:
        time.sleep(5)
        run(
            [python, "smoke_test.py", "--base-url", f"http://127.0.0.1:{args.backend_port}", "--password", args.password],
            BACKEND_DIR,
            backend_env,
        )
        run(
            [
                python,
                "stack_health_check.py",
                "--backend-url",
                f"http://127.0.0.1:{args.backend_port}/health",
                "--frontend-url",
                f"http://127.0.0.1:{args.frontend_port}",
            ],
            BACKEND_DIR,
        )
    finally:
        for proc in (frontend, backend):
            proc.terminate()
        for proc in (frontend, backend):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    print("LOCAL_STACK_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
