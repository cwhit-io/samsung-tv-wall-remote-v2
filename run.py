#!/usr/bin/env python3
"""Helper to manage the frontend dev server.

Usage examples:
    python run.py start            # runs `npm start` (PORT=8002, PUBLIC_URL=/)
  python run.py start --port 3000 # run on different port
  python run.py start --detached # run in background and log to frontend/frontend.log
  python run.py install          # run `npm install` in ./frontend
    python run.py build            # run `npm run build` with PUBLIC_URL=/

This script is intended for dev convenience on Linux/macOS.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(ROOT, "frontend")


def check_frontend_dir() -> None:
    if not os.path.isdir(FRONTEND_DIR):
        print(f"Error: frontend directory not found at {FRONTEND_DIR}", file=sys.stderr)
        sys.exit(2)


def check_npm() -> None:
    if shutil.which("npm") is None:
        print("Error: `npm` not found. Please install Node.js and npm.", file=sys.stderr)
        sys.exit(2)


def run_install() -> int:
    check_frontend_dir()
    check_npm()
    print("Running npm install in frontend/ ...")
    return subprocess.call(["npm", "install"], cwd=FRONTEND_DIR)


def run_build(public_url: str) -> int:
    check_frontend_dir()
    check_npm()
    env = os.environ.copy()
    env["PUBLIC_URL"] = public_url
    print(f"Building frontend with PUBLIC_URL={public_url} ...")
    return subprocess.call(["npm", "run", "build"], cwd=FRONTEND_DIR, env=env)


def run_start(port: int, public_url: str, detached: bool) -> int:
    check_frontend_dir()
    check_npm()
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["PUBLIC_URL"] = public_url

    if detached:
        log_path = os.path.join(FRONTEND_DIR, "frontend.log")
        print(f"Starting frontend detached (logs -> {log_path})")
        with open(log_path, "ab") as f:
            p = subprocess.Popen(["npm", "start"], cwd=FRONTEND_DIR, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"Frontend started with PID {p.pid}")
        return 0
    else:
        # Replace current process (so signals like ctrl-C are forwarded)
        print(f"Starting frontend on port {port} (PUBLIC_URL={public_url}) ...")
        try:
            # Ensure we run in the frontend directory so npm finds package.json
            os.chdir(FRONTEND_DIR)
            os.execvpe("npm", ["npm", "start"], env)
        except FileNotFoundError:
            print("Error: npm not found in PATH after checking. Is Node.js installed?", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Error launching npm start: {e}", file=sys.stderr)
            return 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Manage the React frontend dev server")
    sub = p.add_subparsers(dest="cmd")

    start = sub.add_parser("start", help="Start the dev server (npm start)")
    start.add_argument("--port", type=int, default=8002, help="Port to run the dev server on (default: 8002)")
    start.add_argument("--public-url", default="/", help="PUBLIC_URL for the build/dev server (default: /)")
    start.add_argument("--detached", action="store_true", help="Run in background and log output to frontend/frontend.log")

    sub.add_parser("install", help="Run npm install in frontend/")

    build = sub.add_parser("build", help="Run npm run build in frontend/")
    build.add_argument("--public-url", default="/", help="PUBLIC_URL for the build (default: /)")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)
    return args


def main() -> int:
    args = parse_args()
    if args.cmd == "install":
        return run_install()
    if args.cmd == "build":
        return run_build(args.public_url)
    if args.cmd == "start":
        return run_start(args.port, args.public_url, args.detached)
    print("Unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
