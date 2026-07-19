from fastapi import APIRouter, Request

from services.system_readiness import get_readiness

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/readiness")
def readiness(request: Request, refresh: bool = False):
    production_mode = bool(getattr(request.app.state, "production_mode", False))
    return get_readiness(
        refresh=refresh,
        production_mode=production_mode,
        frontend_dist=getattr(request.app.state, "frontend_dist", None),
        app_name=request.app.title,
        app_version=request.app.version,
    ).model_dump(mode="json")
