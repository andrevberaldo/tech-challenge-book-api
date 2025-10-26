import sys
from pathlib import Path
import asyncio

import polars as pl
import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scripts import book_statistics, ml_datasets  # noqa: E402  # isort:skip
from src.routes.public import insights  # noqa: E402  # isort:skip


@pytest.fixture()
def ml_dataset(tmp_path, monkeypatch):
    features_path = tmp_path / "books_features.csv"
    train_path = tmp_path / "train_features.csv"
    test_path = tmp_path / "test_features.csv"
    processed_path = tmp_path / "books_processed.csv"

    base_records = [
        {
            "id": 1,
            "title": "A",
            "price": 10.0,
            "rating": 4,
            "category": "Cat",
            "image": "",
            "product_page": "a",
            "availability": "In",
            "stock": 5,
            "image_base64": "",
        },
        {
            "id": 2,
            "title": "B",
            "price": 15.0,
            "rating": 5,
            "category": "Cat",
            "image": "",
            "product_page": "b",
            "availability": "In",
            "stock": 3,
            "image_base64": "",
        },
    ]

    features_df = pl.DataFrame([record | {"feature_x": 0.1, "feature_y": 0.5} for record in base_records])
    features_df.write_csv(features_path)

    train_df = pl.DataFrame({"feature_x": [0.1], "price": [10.0]})
    test_df = pl.DataFrame({"feature_x": [0.5], "price": [15.0]})
    processed_df = pl.DataFrame(base_records)

    train_df.write_csv(train_path)
    test_df.write_csv(test_path)
    processed_df.write_csv(processed_path)

    monkeypatch.setattr(ml_datasets, "FEATURES_PATH", features_path)
    monkeypatch.setattr(ml_datasets, "TRAIN_PATH", train_path)
    monkeypatch.setattr(ml_datasets, "TEST_PATH", test_path)
    monkeypatch.setattr(ml_datasets, "PROCESSED_PATH", processed_path)
    ml_datasets.invalidate_cache()

    monkeypatch.setattr(book_statistics, "DATASET_PATH", processed_path)
    book_statistics.invalidate_cache()

    yield
    ml_datasets.invalidate_cache()
    book_statistics.invalidate_cache()


def test_ml_features_all_columns(ml_dataset):
    payload = asyncio.run(insights.ml_features())
    assert payload["rows"] == 2
    assert payload["columns"] == "all"
    assert len(payload["data"][0]) >= 2


def test_ml_features_selected_columns(ml_dataset):
    payload = asyncio.run(insights.ml_features(columns="feature_x,feature_y"))
    assert payload["columns"] == ["feature_x", "feature_y"]
    assert set(payload["data"][0].keys()) == {"feature_x", "feature_y"}


def test_ml_features_invalid_column(ml_dataset):
    with pytest.raises(HTTPException):  # type: ignore
        asyncio.run(insights.ml_features(columns="invalid"))


def test_ml_training_data_full(ml_dataset):
    payload = asyncio.run(insights.ml_training_data())
    assert payload["info"]["train_rows"] == 1
    assert payload["info"]["test_rows"] == 1


def test_ml_training_data_split(ml_dataset):
    payload = asyncio.run(insights.ml_training_data(split="train"))
    assert "train" in payload and len(payload["train"]) == 1


def test_ml_training_data_invalid_split(ml_dataset):
    with pytest.raises(HTTPException):  # type: ignore
        asyncio.run(insights.ml_training_data(split="invalid"))


def test_ml_predictions_success():
    payload = asyncio.run(insights.ml_predictions({"predictions": [1, 2, 3]}))
    assert payload["count"] == 3
    assert payload["predictions"] == [1.0, 2.0, 3.0]


def test_ml_predictions_invalid_payload():
    with pytest.raises(HTTPException):  # type: ignore
        asyncio.run(insights.ml_predictions({"predictions": [1, "a"]}))
