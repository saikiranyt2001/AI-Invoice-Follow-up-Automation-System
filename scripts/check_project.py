from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"


def npm_command(*args: str) -> list[str]:
    executable = "npm.cmd" if sys.platform.startswith("win") else "npm"
    return [executable, *args]


def run_step(title: str, command: list[str], cwd: Path) -> None:
    print(f"\n== {title} ==")
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    python = sys.executable

    run_step("Backend Ruff Lint", [python, "-m", "ruff", "check", "."], BACKEND_DIR)
    run_step("Backend Ruff Format Check", [python, "-m", "ruff", "format", "--check", "."], BACKEND_DIR)
    run_step("Backend Tests", [python, "-m", "pytest"], BACKEND_DIR)
    run_step("Frontend Check", npm_command("run", "check"), FRONTEND_DIR)

    print("\nPROJECT_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
