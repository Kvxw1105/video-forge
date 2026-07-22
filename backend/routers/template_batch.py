"""HTTP boundary for durable template batch production."""
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from services.jobs import start_job
from services import template_batch_service as batches

router = APIRouter(prefix="/api/batches/template-production", tags=["template-batches"])


def _error(error: Exception):
    if isinstance(error, batches.BatchError):
        status = 409 if error.code == "idempotency_key_conflict" else 404 if error.code == "batch_not_found" else 422
        raise HTTPException(status, {"code": error.code, "message": str(error)}) from error
    if isinstance(error, ValidationError):
        raise HTTPException(422, {"code": "invalid_batch_spec", "message": str(error)}) from error
    raise error


@router.post("/plan")
def plan(data: dict):
    try: return batches.plan(data)
    except Exception as error: _error(error)


@router.post("")
def start(data: dict):
    try: return batches.start(data, start_job)
    except Exception as error: _error(error)


@router.get("")
def list_all():
    return batches.list_batches()


@router.get("/{batch_id}")
def get_one(batch_id: str):
    try: return batches.get(batch_id)
    except Exception as error: _error(error)


@router.post("/{batch_id}/resume")
def resume(batch_id: str):
    try: return batches.resume(batch_id, start_job)
    except Exception as error: _error(error)


@router.get("/{batch_id}/manifest")
def get_manifest(batch_id: str):
    try: return batches.manifest(batch_id)
    except Exception as error: _error(error)
