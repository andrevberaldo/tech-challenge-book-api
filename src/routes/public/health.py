from __future__ import annotations

"""
Health & Version routes
-----------------------

GET /api/v1/health
    • Sempre verifica se a API está viva.
    • Valida a fonte de dados principal (CSV) e, se houver credenciais de banco
      (DB_HOST definido), também checa conectividade com o Postgres na AWS.
    • Se a lib `psycopg` estiver instalada, executa `SELECT 1` com timeout;
      caso contrário, faz um *fallback* para um teste TCP (socket) no host:porta.
    • O campo `status` será "ok" se todos os checks executados estiverem OK;
      caso qualquer um falhe, retorna "degraded" com detalhes do erro.

ENV esperadas (todas opcionais, com defaults seguros):
    USE_DATABASE            → "true"/"false" (apenas informativo neste handler)
    BOOKS_CSV_PATH          → caminho p/ CSV bruto (abs ou relativo a <repo>/src)
    DB_HOST, DB_PORT        → destino do Postgres (ex.: RDS AWS)
    DB_USER, DB_PASSWORD    → credenciais
    DB_NAME                 → default: "postgres"
    DB_SSLMODE              → default: "prefer" (psycopg)
    DB_CONNECT_TIMEOUT      → segundos (psycopg). default: 3
    DB_TCP_TIMEOUT          → segundos (socket). default: 2.5

GET /api/v1/version
    • Retorna o hash de versão via env GIT_HASH.
"""

import csv
import os
import socket
import time
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter

# psycopg é opcional — se não estiver instalado, caímos no teste TCP
try:  # psycopg 3
    import psycopg  # type: ignore
    _HAS_PSYCOPG = True
except Exception:
    psycopg = None  # type: ignore
    _HAS_PSYCOPG = False

router = APIRouter(prefix="/api/v1", tags=["Endpoints Core"])  # mantém padrão do projeto

# ─────────────────────────────────────────────────────────────
# Resolução de caminho do CSV (aceita absoluto ou relativo a <repo>/src)
# ─────────────────────────────────────────────────────────────
def _resolve_csv_path() -> Path:
    env = os.environ.get("BOOKS_CSV_PATH")
    base = Path(__file__).resolve().parents[2]  # <repo>/src
    if not env:
        return base / "data" / "raw" / "all_books_with_images.csv"
    p = Path(env)
    return p if p.is_absolute() else (base / p)

CSV_PATH: Path = _resolve_csv_path()

# Flags/credenciais
USE_DATABASE: bool = os.environ.get("USE_DATABASE", "false").strip().lower() == "true"
DB_HOST: str = os.environ.get("DB_HOST", "")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "")
DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")
DB_NAME: str = os.environ.get("DB_NAME", "postgres")
DB_SSLMODE: str = os.environ.get("DB_SSLMODE", "prefer")
DB_CONNECT_TIMEOUT: int = int(os.environ.get("DB_CONNECT_TIMEOUT", "3"))
DB_TCP_TIMEOUT: float = float(os.environ.get("DB_TCP_TIMEOUT", "2.5"))


# ─────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────
def _check_csv(path: Path) -> Dict[str, Optional[object]]:
    """Valida existência/leitura do CSV e retorna contagem de linhas."""
    exists = path.exists()
    readable = False
    count: Optional[int] = None
    error: Optional[str] = None

    if exists:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                next(reader, None)  # header
                count = sum(1 for _ in reader)
            readable = True
        except Exception as e:
            error = f"CSV read error: {type(e).__name__}: {e}"
    else:
        error = "CSV file not found"

    return {
        "ok": bool(exists and readable),
        "path": str(path),
        "exists": exists,
        "readable": readable,
        "count": count,
        "error": error,
    }


def _check_db() -> Dict[str, Optional[object]]:
    """Tenta conexão no Postgres com psycopg (SELECT 1) e *fallback* TCP.

    Executado **somente** quando `DB_HOST` está definido. Não expõe senha.
    """
    if not DB_HOST:
        return {"skipped": True}

    detail: Dict[str, Optional[object]] = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER or None,
        "name": DB_NAME or None,
        "driver": "psycopg3" if _HAS_PSYCOPG else "socket",
        "ok": False,
        "latency_ms": None,
        "error": None,
        "skipped": False,
    }

    start = time.time()

    if _HAS_PSYCOPG:
        # Checagem real com SELECT 1
        try:
            with psycopg.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER or None,
                password=DB_PASSWORD or None,
                connect_timeout=DB_CONNECT_TIMEOUT,
                sslmode=DB_SSLMODE,
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    _ = cur.fetchone()
            detail["ok"] = True
        except Exception as e:
            detail["error"] = f"{type(e).__name__}: {e}"
        finally:
            detail["latency_ms"] = int((time.time() - start) * 1000)
    else:
        # Fallback: apenas verifica se porta está aberta (TCP handshake)
        try:
            with socket.create_connection((DB_HOST, DB_PORT), timeout=DB_TCP_TIMEOUT):
                detail["ok"] = True
        except Exception as e:
            detail["error"] = f"{type(e).__name__}: {e}"
        finally:
            detail["latency_ms"] = int((time.time() - start) * 1000)

    return detail


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/health")
async def health_check():
    """Verifica status da API e conectividade (CSV e, se configurado, Postgres).

    • Sempre realiza o check do CSV (fonte base da aplicação).
    • Se `DB_HOST` estiver configurado, também executa o check do banco.
    • `status` será "ok" somente se **todos** os checks executados estiverem OK.
    """
    checks: Dict[str, Dict[str, Optional[object]]] = {}

    # CSV
    csv_result = _check_csv(CSV_PATH)
    checks["csv"] = csv_result

    # DB (executa somente se houver host definido)
    db_result = _check_db() if DB_HOST else {"skipped": True}
    checks["database"] = db_result

    # status agregado
    ran_db = not db_result.get("skipped", False)
    overall_ok = bool(csv_result.get("ok") and (db_result.get("ok") if ran_db else True))

    payload = {
        "status": "ok" if overall_ok else "degraded",
        "mode": "database" if USE_DATABASE else "csv",
        "checks": checks,
    }
    return payload


@router.get("/version")
async def version():
    return {"version": os.getenv("GIT_HASH", "unknown-version")}