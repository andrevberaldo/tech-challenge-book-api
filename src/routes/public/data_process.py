"""Endpoint público para executar a pipeline de processamento de dados."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse
from src.scripts.data_processing_pipeline import run_pipeline

router = APIRouter(prefix="/api/v1", tags=["Endpoints Core"])

# Estado da pipeline (simples para controle de execução única)
pipeline_state = {"is_running": False}


@router.post("/data-process", status_code=status.HTTP_202_ACCEPTED)
async def trigger_data_process(background_tasks: BackgroundTasks):
    """
    Inicia a execução da pipeline de processamento em background.
    
    Retorna 202 Accepted se iniciada com sucesso, ou 409 se já está rodando.
    """
    if pipeline_state["is_running"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Data processing is already running"
        )
    
    # Marcar como em execução
    pipeline_state["is_running"] = True
    
    # Adicionar tarefa em background
    background_tasks.add_task(_run_pipeline_task)
    
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"message": "Data processing started in background"}
    )


def _run_pipeline_task():
    """Tarefa executada em background para rodar a pipeline."""
    try:
        run_pipeline()
    except Exception:
        pass  # Silenciar erros - apenas processar
    finally:
        pipeline_state["is_running"] = False
