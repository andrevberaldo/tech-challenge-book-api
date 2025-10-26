"""Endpoints públicos para estatísticas e insights dos livros."""

from fastapi import APIRouter, HTTPException, Query
from src.scripts.book_statistics import (
	get_books_in_price_range,
	get_category_statistics,
	get_overview_statistics,
	get_top_rated_books,
)

router = APIRouter(prefix="/api/v1", tags=["Insights"])


def _handle_dataset_errors(func, *args, **kwargs):
	"""Executa a função e converte erros de dataset em HTTPException."""
	try:
		return func(*args, **kwargs)
	except FileNotFoundError as exc:  # pragma: no cover - depende do ambiente
		raise HTTPException(status_code=500, detail="Processed dataset not found") from exc


@router.get("/stats/overview")
async def stats_overview():
	"""Retorna estatísticas gerais da coleção de livros."""
	return _handle_dataset_errors(get_overview_statistics)


@router.get("/stats/categories")
async def stats_by_category():
	"""Retorna métricas agregadas por categoria."""
	categories = _handle_dataset_errors(get_category_statistics)
	return {"categories": categories, "total_categories": len(categories)}


@router.get("/books/top-rated")
async def books_top_rated(limit: int = Query(default=10, ge=1, le=100)):
	"""Retorna os livros com as melhores avaliações."""
	books = _handle_dataset_errors(get_top_rated_books, limit)
	return {"items": books, "limit": limit, "returned": len(books)}


@router.get("/books/price-range")
async def books_by_price_range(
	min_price: float = Query(..., ge=0.0, alias="min"),
	max_price: float = Query(..., ge=0.0, alias="max"),
):
	"""Filtra livros dentro da faixa de preço solicitada."""
	if min_price > max_price:
		raise HTTPException(status_code=400, detail="'min' must be less than or equal to 'max'")

	books = _handle_dataset_errors(get_books_in_price_range, min_price, max_price)
	return {
		"items": books,
		"filters": {"min": min_price, "max": max_price},
		"count": len(books),
	}
