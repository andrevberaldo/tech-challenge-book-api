"""Utilitários para preparação de datasets voltados a modelos de ML."""

from __future__ import annotations
from functools import lru_cache
from math import floor
from pathlib import Path
from typing import Optional, Tuple
import polars as pl

BASE_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FEATURES_DATASET_PATH = BASE_DATA_DIR / "features" / "books_features.csv"


def _cast_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Garante tipos consistentes para colunas principais."""
    casts = []
    if "price" in df.columns:
        casts.append(pl.col("price").cast(pl.Float64, strict=False))
    if "rating" in df.columns:
        casts.append(pl.col("rating").cast(pl.Float64, strict=False))
    if "stock" in df.columns:
        casts.append(pl.col("stock").cast(pl.Int64, strict=False))
    if casts:
        df = df.with_columns(casts)
    return df


@lru_cache(maxsize=1)
def load_features_dataframe() -> pl.DataFrame:
    """Carrega o dataset de features em cache."""
    if not FEATURES_DATASET_PATH.exists():
        raise FileNotFoundError(f"Features dataset not found at {FEATURES_DATASET_PATH}")
    df = pl.read_csv(FEATURES_DATASET_PATH, infer_schema_length=0)
    df = _cast_columns(df)
    # Remover image_base64 se existir (campo muito grande e desnecessário para ML)
    if "image_base64" in df.columns:
        df = df.drop("image_base64")
    return df


def invalidate_caches() -> None:
    """Invalida caches armazenados em memória (útil para testes)."""
    load_features_dataframe.cache_clear()


def get_features_dataframe() -> pl.DataFrame:
    """Retorna uma cópia do dataset de features."""
    return load_features_dataframe().clone()


def get_training_split(ratio: float = 0.7, seed: Optional[int] = None) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Obtém a divisão treino/teste do dataset de features."""
    if not 0 < ratio < 1:
        raise ValueError("ratio must be between 0 and 1")

    df = get_features_dataframe()
    total_rows = df.height
    if total_rows == 0:
        return df, df.clone()

    if total_rows > 1:
        df = df.sample(fraction=1.0, with_replacement=False, shuffle=True, seed=seed)

    train_rows = max(1, floor(total_rows * ratio))
    train_rows = min(train_rows, total_rows)

    train_df = df.head(train_rows)
    test_df = df.slice(train_rows)
    return train_df, test_df
