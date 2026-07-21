from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import CORS_ORIGINS
from frontend_host import resolve_frontend_dist

def create_app(*, serve_frontend: bool | None = None, frontend_dist=None) -> FastAPI:
    app = FastAPI(title="VideoForge", version="0.1.0")
    app.state.production_mode = bool(serve_frontend)
    app.state.frontend_dist = resolve_frontend_dist(frontend_dist) if serve_frontend else None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from routers import project, voiceover, export, assets, settings, render, template, subtitle, library, audio_analysis, jobs, system_readiness, structured_audio
    app.include_router(project.router)
    app.include_router(voiceover.router)
    app.include_router(export.router)
    app.include_router(assets.router)
    app.include_router(settings.router)
    app.include_router(render.router)
    app.include_router(template.router)
    app.include_router(subtitle.router)
    app.include_router(library.router)
    app.include_router(audio_analysis.router)
    app.include_router(jobs.router)
    app.include_router(system_readiness.router)
    app.include_router(structured_audio.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": app.version}

    if serve_frontend:
        from frontend_host import mount_frontend
        mount_frontend(app, frontend_dist)
    return app


app = create_app()
