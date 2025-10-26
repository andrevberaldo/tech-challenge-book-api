from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer
from src.domain.auth.service.auth_service import AuthService

router = APIRouter(prefix="/api/v1", tags=["Auth"])
basic_auth = HTTPBasic()
jwt_auth = HTTPBearer()

@router.get("/auth/login")
async def get_api_token(credentials: HTTPBasicCredentials = Depends(basic_auth)):
    """
        Endpoint para obter o acessToken e o refreshToken. \n
        O usuário e senha devem ser informados no header Authorization com o Basic esquema.
    """
    auth_service = AuthService()

    return auth_service.generate_access_and_refresh_token(credentials)
    
    
@router.get("/auth/refresh")
async def refresh_api_token(credentials: HTTPAuthorizationCredentials = Depends(jwt_auth)):
    """
        Endpoint para renovar o accessToken que tem vida útil menor que o refreshToken. \n
        O refreshToken deve ser informado no header Authorization com o Bearer schema.
    """
    auth_service = AuthService()

    return auth_service.renovate_access_token(credentials)


