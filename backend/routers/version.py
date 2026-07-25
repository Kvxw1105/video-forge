from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["version"])


def _git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


@router.get("/version")
def version():
    return {
        "branch": os.environ.get("VIDEOFORGE_BRANCH") or _git(["branch", "--show-current"]),
        "commit": os.environ.get("VIDEOFORGE_COMMIT") or _git(["rev-parse", "HEAD"]),
        "buildTime": os.environ.get("VIDEOFORGE_BUILD_TIME") or datetime.now(timezone.utc).isoformat(),
        "environment": os.environ.get("VIDEOFORGE_ENV") or "local",
    }
