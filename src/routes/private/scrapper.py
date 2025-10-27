from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from src.scripts.scrapper_lib import trigger_scrap
from src.domain.auth.service.jwt_utils import JWTUtils

router = APIRouter(prefix="/api/v1", tags=["Data Pipeline"])

# Estado do scrapper (controle de execução única)
scrapper_state = {"is_running": False, "last_result": None}


@router.put("/scrapper", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(JWTUtils.validate_token)])
async def trigger_scrapping(background_tasks: BackgroundTasks):
    """
    Inicia o scraping de dados em background.
    
    Retorna 202 Accepted se iniciado com sucesso, ou 409 se já está rodando.
    """
    if scrapper_state["is_running"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scrapper is already running"
        )
    
    # Marcar como em execução
    scrapper_state["is_running"] = True
    scrapper_state["last_result"] = None
    
    # Adicionar tarefa em background
    background_tasks.add_task(_run_scrapper_task)
    
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"message": "Scrapper started in background"}
    )


@router.get("/scrapper/status", dependencies=[Depends(JWTUtils.validate_token)])
async def scrapper_status():
    """Retorna o status atual do scrapping."""
    return {
        "is_running": scrapper_state["is_running"],
        "last_result": scrapper_state["last_result"]
    }


def _run_scrapper_task():
    """Tarefa executada em background para rodar o scrapper."""
    try:
        trigger_scrap()
        scrapper_state["last_result"] = {
            "status": "success",
            "message": "Scrapping completed successfully"
        }
    except Exception as e:
        scrapper_state["last_result"] = {
            "status": "error",
            "error": str(e)
        }
    finally:
        scrapper_state["is_running"] = False