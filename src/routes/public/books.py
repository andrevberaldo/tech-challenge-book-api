# src/routes/books.py
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import polars as pl
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1", tags=["Books"])

# ─────────────────────────────────────────────────────────────
# Resolução de caminho do CSV processado (portável)
# Default: <repo>/src/data/processed/books_processed.csv
# Pode sobrescrever com env BOOKS_PROCESSED_PATH (abs ou relativo a <repo>/src)
# ─────────────────────────────────────────────────────────────
def _find_src_dir() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if parent.name == "src":
            return parent
    # fallback: se não achar, assume o diretório atual
    return p.parent

def _resolve_processed_path() -> Path:
    env = os.environ.get("BOOKS_PROCESSED_PATH")
    base = _find_src_dir()  # <repo>/src
    if not env:
        return base / "data" / "processed" / "books_processed.csv"
    p = Path(env)
    return p if p.is_absolute() else (base / p)

DATASET_PATH: Path = _resolve_processed_path()


# ─────────────────────────────────────────────────────────────
# Carregamento do dataset com cache invalidado por mtime
# ─────────────────────────────────────────────────────────────
def _csv_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0

@lru_cache(maxsize=1)
def _cached_df(_snapshot_mtime: float) -> pl.DataFrame:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Processed dataset not found at {DATASET_PATH}")
    df = pl.read_csv(DATASET_PATH, infer_schema_length=0)
    # Garantir tipos das colunas principais
    casts = []
    for name, dtype in [("price", pl.Float64), ("rating", pl.Int64), ("stock", pl.Int64), ("availability", pl.Int64)]:
        if name in df.columns:
            casts.append(pl.col(name).cast(dtype, strict=False))
    if casts:
        df = df.with_columns(casts)
    return df

def _get_df() -> pl.DataFrame:
    return _cached_df(_csv_mtime(DATASET_PATH))


# ─────────────────────────────────────────────────────────────
# Helpers de conversão
# ─────────────────────────────────────────────────────────────
BOOK_FIELDS = ["id", "title", "price", "rating", "category", "image", "product_page", "availability", "stock"]

def _ensure_fields(df: pl.DataFrame) -> pl.DataFrame:
    cols = {c for c in df.columns}
    missing = [c for c in BOOK_FIELDS if c not in cols]
    if missing:
        # acrescenta colunas faltantes como None
        df = df.with_columns([pl.lit(None).alias(c) for c in missing])
    return df.select([c for c in BOOK_FIELDS if c in df.columns])

def _rows_to_dicts(df: pl.DataFrame) -> List[dict]:
    return [dict(r) for r in df.to_dicts()]


# ─────────────────────────────────────────────────────────────
# Endpoints
# IMPORTANTE: defina /books/search ANTES de /books/{id} para evitar 422
# ─────────────────────────────────────────────────────────────

@router.get("/books/search")
async def search_books(
    title: Optional[str] = Query(None, description="Filtro parcial por título (case-insensitive)"),
    category: Optional[str] = Query(None, description="Filtro parcial por categoria (case-insensitive)"),
) -> List[dict]:
    """
    Busca livros por título e/ou categoria.
    Pelo menos um parâmetro deve ser fornecido.
    """
    if not title and not category:
        raise HTTPException(status_code=422, detail="Provide at least one of: title, category")

    try:
        df = _get_df()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    df = _ensure_fields(df)

    filt = pl.lit(True)
    if title:
        t = title.lower()
        filt = filt & pl.col("title").cast(pl.Utf8, strict=False).fill_null("").str.to_lowercase().str.contains(t, literal=True)
    if category:
        c = category.lower()
        filt = filt & pl.col("category").cast(pl.Utf8, strict=False).fill_null("").str.to_lowercase().str.contains(c, literal=True)

    out = df.filter(filt)
    return _rows_to_dicts(out)


@router.get("/books")
async def list_books() -> List[dict]:
    """Lista todos os livros disponíveis no dataset processado."""
    try:
        df = _get_df()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    df = _ensure_fields(df)
    return _rows_to_dicts(df)


@router.get("/books/{book_id}")
async def get_book(book_id: str) -> dict:
    """Retorna os detalhes completos de um livro específico pelo ID (string)."""
    try:
        df = _get_df()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    df = _ensure_fields(df)
    row = df.filter(pl.col("id") == book_id).limit(1)

    if row.height == 0:
        raise HTTPException(status_code=404, detail="Book not found")

    return _rows_to_dicts(row)[0]


@router.get("/categories")
async def list_categories() -> List[str]:
    """Lista todas as categorias distintas presentes no dataset processado."""
    try:
        df = _get_df()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if "category" not in df.columns:
        return []
    cats = (
        df.select(pl.col("category").cast(pl.Utf8, strict=False))
          .drop_nulls()
          .unique()
          .sort("category")
          .to_series()
          .to_list()
    )
    return [c for c in cats if isinstance(c, str)]
