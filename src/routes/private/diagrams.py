from fastapi import APIRouter, Depends
from src.domain.auth.service.jwt_utils import JWTUtils
from fastapi.responses import FileResponse
import os

router = APIRouter(prefix="/api/v1/diagrams", tags=["Diagrams"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIAGRAMS_PATH = os.path.join(BASE_DIR, "docs")

@router.get("/auth_flow", dependencies=[Depends(JWTUtils.validate_token)])
async def get_auth_strategy():
    """
        Retorna um html com o diagrama de estratégia para autenticação da API.
    """
    file_path = os.path.join(DIAGRAMS_PATH, "auth_flow.html")
    return FileResponse(file_path)


@router.get("/cicd", dependencies=[Depends(JWTUtils.validate_token)])
async def get_cicd_strategy():
    """
        Retorna um html com o diagrama de estratégia de cicd da API.
    """
    file_path = os.path.join(DIAGRAMS_PATH, "cicd_strategy.html")
    return FileResponse(file_path)


@router.get("/observability", dependencies=[Depends(JWTUtils.validate_token)])
async def get_observability_strategy():
    """
        Retorna um html com o diagrama de estratégia observabilidade da API.
    """
    file_path = os.path.join(DIAGRAMS_PATH, "observability.html")
    return FileResponse(file_path)


@router.get("/scaling_strategy", dependencies=[Depends(JWTUtils.validate_token)])
async def get_scaling_strategy():
    """
        Retorna um html com o diagrama de estratégia para escalar a API.
    """
    file_path = os.path.join(DIAGRAMS_PATH, "scaling_strategy.html")
    return FileResponse(file_path)


@router.get("/scrapping_process", dependencies=[Depends(JWTUtils.validate_token)])
async def get_scrapping_process():
    """
        Retorna um html com o diagrama do processo de scrapping.
    """
    file_path = os.path.join(DIAGRAMS_PATH, "scrapping_process.html")
    return FileResponse(file_path)
