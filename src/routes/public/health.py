from fastapi import APIRouter
import os

router = APIRouter(prefix="/api/v1", tags=["Endpoints Core"])

@router.get("/health")
async def health_check():
    return {"message": "ok"}

@router.get("/version")
async def version():
    return {
        "version": os.getenv("GIT_HASH", "unknown-version")
    }
