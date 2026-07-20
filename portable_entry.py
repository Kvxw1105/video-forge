"""Portable Windows entry point; sets stable runtime data before importing FastAPI."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _configure_runtime() -> None:
    executable_dir = Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False):
        root = executable_dir
    else:
        root = Path(__file__).resolve().parent
        backend = root / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
    data_dir = Path(os.environ.get("VIDEOFORGE_DATA_DIR", "")).expanduser() if os.environ.get("VIDEOFORGE_DATA_DIR") else Path(os.environ.get("LOCALAPPDATA", root)) / "VideoForge"
    os.environ["VIDEOFORGE_PORTABLE_ROOT"] = str(root)
    os.environ["VIDEOFORGE_DATA_DIR"] = str(data_dir.resolve())
    if getattr(sys, "frozen", False):
        bundled_root = Path(getattr(sys, "_MEIPASS", root))
        frontend_dist = bundled_root / "frontend" / "dist"
        os.environ.setdefault("VIDEOFORGE_FRONTEND_DIST", str(frontend_dist))


_configure_runtime()

from launcher import run


if __name__ == "__main__":
    raise SystemExit(run())
