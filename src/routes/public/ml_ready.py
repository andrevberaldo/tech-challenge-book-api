"""Endpoints públicos voltados ao consumo de modelos de ML."""

from __future__ import annotations
from typing import Annotated, Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from src.scripts import ml_data

router = APIRouter(prefix="/api/v1/ml", tags=["ML-Ready"])


def _handle_dataset_errors(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except FileNotFoundError as exc:  # pragma: no cover - depende do ambiente
        raise HTTPException(status_code=500, detail="Features dataset not found") from exc


def _df_to_records(df, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return df.to_dicts()


@router.get("/features")
async def ml_features(limit: Annotated[Optional[int], Query(ge=1)] = None):
    """Retorna dados de features prontos para uso em modelos."""
    df = _handle_dataset_errors(ml_data.get_features_dataframe)

    records = _df_to_records(df, limit)

    return {
        "items": records,
        "returned": len(records),
        "total": df.height,
        "limit": limit,
    }


@router.get("/training-data")
async def ml_training_data(
    ratio: Annotated[float, Query(gt=0.0, lt=1.0)] = 0.7,
    limit: Annotated[Optional[int], Query(ge=1)] = None,
    seed: Annotated[Optional[int], Query(ge=0)] = None,
):
    """Retorna divisão treino/teste (70/30 por padrão) do dataset de features."""
    train_df, test_df = _handle_dataset_errors(ml_data.get_training_split, ratio, seed)
    train_records = _df_to_records(train_df, limit)
    test_records = _df_to_records(test_df, limit)

    return {
        "metadata": {
            "total_rows": train_df.height + test_df.height,
            "train_rows": train_df.height,
            "test_rows": test_df.height,
            "train_ratio": ratio,
            "seed": seed,
            "limit": limit,
        },
        "train_data": train_records,
        "test_data": test_records,
        "train_returned": len(train_records),
        "test_returned": len(test_records),
    }


class PredictionItem(BaseModel):
    """Schema para validação de item de predição."""
    title: str = Field(..., min_length=1)
    price: float = Field(..., ge=0)
    rating: float = Field(..., ge=0, le=5)
    category: str = Field(..., min_length=1)
    availability: str = Field(..., min_length=1)
    stock: int = Field(..., ge=0)


@router.post("/predictions", status_code=status.HTTP_200_OK)
async def ml_predictions(items: List[PredictionItem]):
    """Valida payload de predições e confirma recebimento."""
    return {
        "message": "Predictions validated successfully",
        "items_received": len(items),
    }
