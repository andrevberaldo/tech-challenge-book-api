"""Utilitários para estatísticas dos livros processados."""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
import polars as pl

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "books_processed.csv"


@lru_cache(maxsize=1)
def _load_books_dataframe() -> pl.DataFrame:
    """Carrega o dataset processado de livros com cache em memória."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Processed dataset not found at {DATASET_PATH}")
    return pl.read_csv(DATASET_PATH, infer_schema_length=0)


def invalidate_cache() -> None:
    """Limpa o cache do dataset, útil em testes."""
    _load_books_dataframe.cache_clear()


def _prepare_dataframe(df: pl.DataFrame) -> pl.DataFrame:
    """Garante que colunas numéricas estejam no tipo correto."""
    return df.with_columns(
        [
            pl.col("price").cast(pl.Float64, strict=False),
            pl.col("rating").cast(pl.Float64, strict=False),
        ]
    )


def _get_dataframe(dataframe: Optional[pl.DataFrame] = None) -> pl.DataFrame:
    """Retorna o DataFrame fornecido ou carrega o dataset padrão."""
    if dataframe is not None:
        return _prepare_dataframe(dataframe)
    return _prepare_dataframe(_load_books_dataframe())


def get_overview_statistics(dataframe: Optional[pl.DataFrame] = None) -> Dict[str, Any]:
    """Calcula estatísticas gerais como total de livros e distribuição de ratings."""
    df = _get_dataframe(dataframe)

    total_books = df.height
    mean_value = df["price"].mean() if total_books else 0.0
    avg_price = float(mean_value) if mean_value is not None else 0.0

    rating_distribution = (
        df.group_by("rating")
        .agg(pl.len().alias("count"))
        .sort("rating")
        .to_dicts()
    )

    distribution = [
        {"rating": float(row["rating"]), "count": int(row["count"])}
        for row in rating_distribution
    ]

    return {
        "total_books": total_books,
        "average_price": round(avg_price, 2),
        "rating_distribution": distribution,
    }


def get_category_statistics(dataframe: Optional[pl.DataFrame] = None) -> List[Dict[str, Any]]:
    """Agrupa estatísticas por categoria (quantidade e preços)."""
    df = _get_dataframe(dataframe)

    grouped = (
        df.group_by("category")
        .agg(
            [
                pl.len().alias("book_count"),
                pl.col("price").mean().alias("average_price"),
                pl.col("price").min().alias("min_price"),
                pl.col("price").max().alias("max_price"),
            ]
        )
        .sort("book_count", descending=True)
    )

    results: List[Dict[str, Any]] = []

    for row in grouped.to_dicts():
        count = int(row["book_count"])
        avg_value = row["average_price"]
        min_value = row["min_price"]
        max_value = row["max_price"]
        avg_price = float(avg_value) if (count and avg_value is not None) else 0.0

        results.append(
            {
                "category": row["category"],
                "book_count": count,
                "average_price": round(avg_price, 2),
                "min_price": round(float(min_value), 2) if (count and min_value is not None) else 0.0,
                "max_price": round(float(max_value), 2) if (count and max_value is not None) else 0.0,
            }
        )

    return results


def get_top_rated_books(limit: int = 10, dataframe: Optional[pl.DataFrame] = None) -> List[Dict[str, Any]]:
    """Retorna os livros com melhor avaliação ordenados por rating e preço."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    
    df = _get_dataframe(dataframe)

    selected = (
        df.sort(["rating", "price"], descending=[True, True])
        .select(["id", "title", "rating", "price", "category", "product_page"])
        .head(limit)
    )

    books = []

    for row in selected.to_dicts():
        books.append(
            {
                "id": row["id"],
                "title": row["title"],
                "rating": float(row["rating"]),
                "price": round(float(row["price"]), 2),
                "category": row["category"],
                "product_page": row["product_page"],
            }
        )

    return books


def get_books_in_price_range(
    min_price: float,
    max_price: float,
    dataframe: Optional[pl.DataFrame] = None,
) -> List[Dict[str, Any]]:
    """Filtra livros dentro de uma faixa específica de preço."""
    if min_price < 0 or max_price < 0:
        raise ValueError("price filters must be non-negative")
    
    if min_price > max_price:
        raise ValueError("min_price must be less than or equal to max_price")
    
    df = _get_dataframe(dataframe)

    filtered = (
        df.filter((pl.col("price") >= min_price) & (pl.col("price") <= max_price))
        .sort("price")
        .select(["id", "title", "rating", "price", "category", "product_page"])
    )

    books = []

    for row in filtered.to_dicts():
        books.append(
            {
                "id": row["id"],
                "title": row["title"],
                "rating": float(row["rating"]),
                "price": round(float(row["price"]), 2),
                "category": row["category"],
                "product_page": row["product_page"],
            }
        )

    return books
