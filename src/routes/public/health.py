from fastapi import APIRouter
import os

router = APIRouter(tags=["Public"])

@router.get("/health")
async def health_check():
    """
        Testa se a API está executando com sucesso.
    """
    return {"message": "ok"}

@router.get("/version")
async def version():
    """
        Retorna a versão hash da API.
    """
    return {
        "version": os.getenv("GIT_HASH", "unknown-version")
    }
