"""Single-process local production launcher for VideoForge."""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from frontend_host import validate_frontend_dist
from main import create_app


DEFAULT_PORT = 8765
PORT_ATTEMPTS = 20


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def select_port(requested: int | None) -> int:
    if requested is not None:
        if not is_port_available(requested):
            raise RuntimeError(f"Port {requested} is unavailable")
        return requested
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_ATTEMPTS):
        if is_port_available(port):
            return port
    raise RuntimeError(f"No available local port in range {DEFAULT_PORT}-{DEFAULT_PORT + PORT_ATTEMPTS - 1}")


def _open_browser_when_ready(url: str, port: int) -> None:
    for _ in range(100):
        if not is_port_available(port):
            webbrowser.open(url)
            return
        time.sleep(0.05)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run VideoForge as one local production process")
    parser.add_argument("--port", type=int, default=None, help="Use an explicit local port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    parser.add_argument("--frontend-dist", type=Path, default=None, help="Override frontend/dist")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dist = validate_frontend_dist(args.frontend_dist)
        port = select_port(args.port)
        app = create_app(serve_frontend=True, frontend_dist=dist)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    url = f"http://127.0.0.1:{port}"
    print(f"VideoForge production server: {url}")
    print(f"Frontend build: {dist}")
    if not args.no_browser:
        threading.Thread(target=_open_browser_when_ready, args=(url, port), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
