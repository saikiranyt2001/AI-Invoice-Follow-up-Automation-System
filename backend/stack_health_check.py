from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check frontend and backend health endpoints")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000/health", help="Backend health URL")
    parser.add_argument("--frontend-url", default="http://localhost:5173", help="Frontend URL")
    parser.add_argument("--timeout", type=float, default=5.0, help="Request timeout in seconds")
    return parser.parse_args()


def check_url(url: str, timeout: float) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            payload = response.read().decode("utf-8", errors="replace")
            return True, f"status={status} body={payload[:200]}"
    except HTTPError as exc:
        return False, f"http_error status={exc.code}"
    except URLError as exc:
        return False, f"url_error reason={exc.reason}"
    except Exception as exc:  # pragma: no cover
        return False, f"error {exc}"


def main() -> int:
    args = parse_args()

    backend_ok, backend_msg = check_url(args.backend_url, args.timeout)
    frontend_ok, frontend_msg = check_url(args.frontend_url, args.timeout)

    print(f"BACKEND {'PASS' if backend_ok else 'FAIL'} {backend_msg}")
    print(f"FRONTEND {'PASS' if frontend_ok else 'FAIL'} {frontend_msg}")

    if not backend_ok or not frontend_ok:
        print("STACK_HEALTH_FAIL")
        return 1

    # Validate expected backend JSON shape when /health is used.
    if args.backend_url.rstrip("/").endswith("/health"):
        try:
            body = backend_msg.split("body=", 1)[1]
            payload = json.loads(body)
            if payload.get("status") != "ok":
                print("BACKEND FAIL unexpected health payload")
                print("STACK_HEALTH_FAIL")
                return 1
        except Exception:
            print("BACKEND FAIL non-json health payload")
            print("STACK_HEALTH_FAIL")
            return 1

    print("STACK_HEALTH_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
