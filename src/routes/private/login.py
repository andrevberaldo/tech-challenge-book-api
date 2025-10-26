from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer
from src.domain.auth.service.auth_service import AuthService

router = APIRouter(prefix="/api/v1", tags=["Auth"])
basic_auth = HTTPBasic()
jwt_auth = HTTPBearer()

@router.post("/auth/login")
async def get_api_token(credentials: HTTPBasicCredentials = Depends(basic_auth)):
    auth_service = AuthService()

    return auth_service.generate_access_and_refresh_token(credentials)
    
    
@router.post("/auth/refresh")
async def refresh_api_token(credentials: HTTPAuthorizationCredentials = Depends(jwt_auth)):
    auth_service = AuthService()

    return auth_service.renovate_access_token(credentials)


