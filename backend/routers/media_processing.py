from fastapi import APIRouter, HTTPException

from media_processing.contracts import MediaExecutionRequest
from media_processing.mediakit_provider import MediaKitProvider
from media_processing.native_provider import VideoForgeNativeMediaProvider
from media_processing.registry import discover_providers
from media_processing.service import execute

router = APIRouter(tags=["media-processing"])


@router.get("/api/media/providers")
def list_media_providers():
    return {"default": "videoforge_native", "providers": discover_providers()}


@router.get("/api/media/providers/videoforge-native")
def discover_native_media():
    return VideoForgeNativeMediaProvider().discover()


@router.get("/api/media/providers/mediakit")
def discover_mediakit():
    return MediaKitProvider().discover()


@router.post("/api/projects/{project_id}/media/execute")
def execute_media(project_id: str, request: MediaExecutionRequest):
    try:
        return execute(project_id, request)
    except KeyError:
        raise HTTPException(404, "project_not_found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
