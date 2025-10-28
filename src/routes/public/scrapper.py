# src/routes/public/scrapper.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse
import logging
from threading import Lock

# Importa direto as funções do scraper
from src.scripts.scrapper_lib import create_session, scrape_all_categories

router = APIRouter(prefix="/api/v1", tags=["Endpoints Core"])

# Estado simples + trava p/ evitar corrida
_scrapper_state = {"is_running": False, "last_result": None}
_lock = Lock()

@router.post("/scrapper", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrapping(background_tasks: BackgroundTasks):
    """Dispara o scraping em background (retorna 202)."""
    with _lock:
        if _scrapper_state["is_running"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scrapper is already running"
            )
        _scrapper_state["is_running"] = True
        _scrapper_state["last_result"] = None

    background_tasks.add_task(_run_scrapper_task)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"message": "Scrapper started in background"}
    )

@router.get("/scrapper/status")
async def scrapper_status():
    """Status do último job (e se está rodando)."""
    return _scrapper_state

def _run_scrapper_task():
    app_log = logging.getLogger(__name__)          # logs do app
    lib_log = logging.getLogger("book_scraper")    # logs da lib (já configurada no scraper)

    try:
        app_log.info("[scrapper] starting job...")
        s = create_session()
        summary = scrape_all_categories(
            s,
            output_dir=None,               # default: <repo>/src/data/raw
            product_page_cache_dir=None,   # default: <repo>/src/cache/prod_pages
            per_book_delay=0.12,
            save_master_csv=True,
        )
        _scrapper_state["last_result"] = {"status": "success", "summary": summary}
        app_log.info("[scrapper] finished. CSV: %s", summary.get("csv_master"))
    except Exception as e:
        _scrapper_state["last_result"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        app_log.exception("[scrapper] job failed")
    finally:
        _scrapper_state["is_running"] = False
