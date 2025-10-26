from fastapi import APIRouter
import os

router = APIRouter(tags=["Public"])

@router.get("/health")
async def health_check():
    return {"message": "ok"}

@router.get("/version")
async def version():
    return {
        "version": os.getenv("GIT_HASH", "unknown-version")
    }
