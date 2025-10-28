from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["Endpoints Core"])

# -------------------------------------------------------------------
# Resolvedor de caminho do CSV (portável)
# -------------------------------------------------------------------
def _resolve_csv_path() -> Path:
    env = os.environ.get("BOOKS_CSV_PATH")
    base = Path(__file__).resolve().parents[2]  # <repo>/src
    if not env:
        return base / "data" / "raw" / "all_books_with_images.csv"
    p = Path(env)
    return p if p.is_absolute() else (base / p)

CSV_PATH: str = str(_resolve_csv_path())

# ===============================
# Modelos (Pydantic)
# ===============================
class Book(BaseModel):
    """id = número da linha no CSV (1-based, sem contar o cabeçalho)."""
    id: int
    title: str
    price: Optional[float] = None
    rating: Optional[int] = None
    category: Optional[str] = None
    image: Optional[str] = None
    product_page: Optional[str] = None
    availability: Optional[bool] = None
    stock: Optional[int] = None
    image_base64: Optional[str] = None

# ===============================
# Utils
# ===============================
def _to_float(x):
    try:
        return float(x) if x not in (None, "") else None
    except Exception:
        return None

def _to_int(x):
    try:
        return int(float(x)) if x not in (None, "") else None
    except Exception:
        return None

def _to_bool(x):
    if isinstance(x, bool):
        return x
    s = str(x or "").strip().lower()
    if s in ("yes", "true", "1"):
        return True
    if s in ("no", "false", "0", ""):
        return False
    return None

def _row_to_book(row: dict, rownum_1based: int) -> Book:
    return Book(
        id=rownum_1based,
        title=row.get("title") or "",
        price=_to_float(row.get("price")),
        rating=_to_int(row.get("rating")),
        category=row.get("category") or None,
        image=row.get("image") or None,
        product_page=row.get("product_page") or None,
        availability=_to_bool(row.get("availability")),
        stock=_to_int(row.get("stock")),
        image_base64=row.get("image_base64") or None,
    )

def _read_csv(path: str) -> List[Book]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found at {p}")
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [_row_to_book(row, i) for i, row in enumerate(reader, start=1)]

def _csv_mtime(path: str) -> float:
    try:
        return Path(path).stat().st_mtime
    except FileNotFoundError:
        return 0.0

@lru_cache(maxsize=1)
def _cached_books(_snapshot_mtime: float) -> List[Book]:
    return _read_csv(CSV_PATH)

def _get_books() -> List[Book]:
    return _cached_books(_csv_mtime(CSV_PATH))

def _norm_q(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2 or None

# ===============================
# Endpoints (agora sem conflito)
# ===============================

@router.get("/books", response_model=List[Book])
async def list_books() -> List[Book]:
    try:
        return _get_books()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

@router.get("/books/search", response_model=List[Book])
async def search_books(
    title: Optional[str] = Query(None, description="Filtro parcial por título (case-insensitive)"),
    category: Optional[str] = Query(None, description="Filtro parcial por categoria (case-insensitive)"),
) -> List[Book]:
    t = _norm_q(title)
    c = _norm_q(category)
    if not t and not c:
        raise HTTPException(status_code=422, detail="Provide at least one of: title, category")

    try:
        books = _get_books()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    t_low = t.lower() if t else None
    c_low = c.lower() if c else None

    def _match(b: Book) -> bool:
        ok = True
        if t_low is not None:
            ok = ok and (t_low in (b.title or "").lower())
        if c_low is not None:
            ok = ok and (c_low in (b.category or "").lower())
        return ok

    return [b for b in books if _match(b)]

# --- ID (linha do CSV, 1-based) — VERSÃO COM PREFIXO ESTÁVEL
@router.get("/books/id/{book_id:int}", response_model=Book)
async def get_book_by_id(book_id: int) -> Book:
    try:
        books = _get_books()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if book_id < 1 or book_id > len(books):
        raise HTTPException(status_code=404, detail="Book not found")
    return books[book_id - 1]

# --- ALIAS para manter compatibilidade com /api/v1/books/1
@router.get("/books/{book_id:int}", response_model=Book)
async def get_book_legacy(book_id: int) -> Book:
    return await get_book_by_id(book_id)  # reutiliza a lógica acima

@router.get("/categories", response_model=List[str])
async def list_categories() -> List[str]:
    try:
        cats = {b.category for b in _get_books() if b.category}
        return sorted(cats)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))