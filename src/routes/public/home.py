from fastapi import APIRouter
from fastapi.responses import FileResponse
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

router = APIRouter(prefix="/api/v1", tags=["Endpoints Core"])

@router.get("/")
async def home():
    file_path = os.path.join(TEMPLATES_DIR, "home.html")
    return FileResponse(file_path)