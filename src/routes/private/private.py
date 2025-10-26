from fastapi import APIRouter, Depends
from src.domain.auth.service.jwt_utils import JWTUtils

router = APIRouter(prefix="/api/v1", tags=["Private"])

@router.get("/api/private", dependencies=[Depends(JWTUtils.validate_token)])
async def get_top_rated_books():
    return {"message": "You have access to this resource! 🚀🚀"}
