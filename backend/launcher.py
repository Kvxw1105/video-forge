"""Single-process local production launcher for VideoForge."""
from __future__ import annotations

import argparse
import logging
import os
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


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None
        self._mutex = None

    def acquire(self) -> bool:
        if os.name == "nt" and getattr(sys, "frozen", False):
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.GetLastError.restype = wintypes.DWORD
            mutex_name = "Local\\VideoForge-SingleInstance"
            self._mutex = kernel32.CreateMutexW(None, False, mutex_name)
            if not self._mutex:
                return False
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(self._mutex)
                self._mutex = None
                return False
            return True

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            if os.name == "nt":
                self.handle.seek(0)
                self.handle.truncate()
                self.handle.write(str(os.getpid()))
                self.handle.flush()
                return True
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(str(os.getpid()))
            self.handle.flush()
            return True
        except (OSError, IOError):
            self.handle.close()
            self.handle = None
            return False

    def release(self) -> None:
        if self._mutex is not None:
            import ctypes

            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._mutex)
            self._mutex = None
            return
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                self.handle.close()
                self.handle = None
                return
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None


def _log_path() -> Path:
    data_dir = Path(os.environ.get("VIDEOFORGE_DATA_DIR", Path.home() / "AppData" / "Local" / "VideoForge"))
    path = data_dir / "logs" / "launcher.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


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
        if not 1 <= requested <= 65535:
            raise ValueError("Port must be between 1 and 65535")
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
    log_path = _log_path()
    logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    lock = InstanceLock(log_path.parent.parent / "runtime.lock")
    if not lock.acquire():
        print("VideoForge 已在运行，未启动新的实例。")
        return 0
    try:
        dist = validate_frontend_dist(args.frontend_dist)
        port = select_port(args.port)
        app = create_app(serve_frontend=True, frontend_dist=dist)
    except Exception as error:
        logging.exception("VideoForge startup failed")
        print(f"VideoForge 启动失败\n错误摘要：{error}\n日志文件：{log_path}", file=sys.stderr)
        lock.release()
        return 2

    url = f"http://127.0.0.1:{port}"
    print(f"VideoForge production server: {url}")
    print(f"Frontend build: {dist}")
    if not args.no_browser:
        threading.Thread(target=_open_browser_when_ready, args=(url, port), daemon=True).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        return 0
    except Exception:
        logging.exception("VideoForge server stopped unexpectedly")
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(run())
