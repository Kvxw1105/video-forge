"""Safe serving of the built React application from FastAPI."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_frontend_dist(frontend_dist: str | Path | None = None) -> Path:
    configured = frontend_dist or os.environ.get("VIDEOFORGE_FRONTEND_DIST")
    return Path(configured).expanduser().resolve() if configured else (PROJECT_ROOT / "frontend" / "dist").resolve()


def validate_frontend_dist(frontend_dist: str | Path | None = None) -> Path:
    dist = resolve_frontend_dist(frontend_dist)
    index = dist / "index.html"
    assets = dist / "assets"
    if not index.is_file():
        raise RuntimeError(
            f"Frontend production build not found: {dist}\n\n"
            "Run:\ncd frontend\nnpm install\nnpm run build"
        )
    if not assets.is_dir() or not any(path.is_file() for path in assets.iterdir()):
        raise RuntimeError(
            f"Frontend assets not found: {assets}\n\n"
            "Run:\ncd frontend\nnpm install\nnpm run build"
        )
    return dist


def mount_frontend(app: FastAPI, frontend_dist: str | Path | None = None) -> FastAPI:
    dist = validate_frontend_dist(frontend_dist)
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    index = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path == "" or full_path.startswith("api/"):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(index)
        if full_path == "assets" or full_path.startswith("assets/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        if Path(full_path).suffix:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(index)

    return app
