import asyncio
import sys
from pathlib import Path

import polars as pl
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scripts import ml_data  # noqa: E402  # type: ignore
from src.routes.public import ml_ready  # noqa: E402  # type: ignore
from src.routes.public.ml_ready import PredictionRequest  # noqa: E402  # type: ignore


@pytest.fixture()
def features_dataset(tmp_path, monkeypatch):
    df = pl.DataFrame(
        [
            {
                "title": "Book A",
                "price": 25.5,
                "rating": 4.7,
                "category": "Fiction",
                "availability": "In stock",
                "stock": 12,
                "feature_extra": 1,
            },
            {
                "title": "Book B",
                "price": 18.0,
                "rating": 4.1,
                "category": "Sci-Fi",
                "availability": "Out of stock",
                "stock": 0,
                "feature_extra": 2,
            },
            {
                "title": "Book C",
                "price": 32.0,
                "rating": 4.9,
                "category": "Fantasy",
                "availability": "In stock",
                "stock": 20,
                "feature_extra": 3,
            },
            {
                "title": "Book D",
                "price": 12.5,
                "rating": 3.8,
                "category": "Non Fiction",
                "availability": "In stock",
                "stock": 5,
                "feature_extra": 4,
            },
            {
                "title": "Book E",
                "price": 28.0,
                "rating": 4.0,
                "category": "Fiction",
                "availability": "In stock",
                "stock": 8,
                "feature_extra": 5,
            },
        ]
    )
    dataset_path = tmp_path / "books_features.csv"
    df.write_csv(dataset_path)
    monkeypatch.setattr(ml_data, "FEATURES_DATASET_PATH", dataset_path)
    ml_data.invalidate_caches()
    yield df
    ml_data.invalidate_caches()


def test_features_endpoint(features_dataset):
    payload = asyncio.run(ml_ready.ml_features(limit=3))
    assert payload["returned"] == 3
    assert payload["total"] == features_dataset.height
    titles = {item["title"] for item in payload["items"]}
    assert len(titles) == 3


def test_training_split(features_dataset):
    response = asyncio.run(ml_ready.ml_training_data(ratio=0.7, seed=42))
    metadata = response["metadata"]
    assert metadata["total_rows"] == features_dataset.height
    assert metadata["train_rows"] == 3  # floor(5 * 0.7) == 3
    assert metadata["test_rows"] == 2
    assert response["train_returned"] == metadata["train_rows"]
    assert response["test_returned"] == metadata["test_rows"]


def test_training_split_limit(features_dataset):
    response = asyncio.run(ml_ready.ml_training_data(limit=1))
    assert response["train_returned"] == 1
    assert response["test_returned"] <= 1


def test_predictions_endpoint(features_dataset):
    payload = {
        "items": [
            {
                "title": "Sample",
                "price": 10.0,
                "rating": 4.0,
                "category": "Fiction",
                "availavility": "In stock",
                "stock": 5,
            }
        ]
    }
    request = PredictionRequest.model_validate(payload)
    response = asyncio.run(ml_ready.ml_predictions(request))
    assert response["received"] == 1
    assert response["message"] == "Prediction payload received"
