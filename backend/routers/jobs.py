from fastapi import APIRouter, HTTPException

from services.jobs import get_job


router = APIRouter(tags=["jobs"])


@router.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    try:
        return get_job(job_id)
    except KeyError:
        raise HTTPException(404, "任务不存在")
