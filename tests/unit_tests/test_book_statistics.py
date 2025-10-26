import sys
from pathlib import Path
import asyncio

import polars as pl
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scripts import book_statistics  # noqa: E402  # isort:skip
from src.routes.public import insights  # noqa: E402  # isort:skip


@pytest.fixture()
def sample_dataset(tmp_path, monkeypatch):
    df = pl.DataFrame(
        [
            {"id": 1, "title": "Book A", "rating": 5, "price": 45.5, "category": "Fiction", "product_page": "a"},
            {"id": 2, "title": "Book B", "rating": 4, "price": 25.0, "category": "Fiction", "product_page": "b"},
            {"id": 3, "title": "Book C", "rating": 5, "price": 35.0, "category": "Sci-Fi", "product_page": "c"},
            {"id": 4, "title": "Book D", "rating": 3, "price": 15.0, "category": "Sci-Fi", "product_page": "d"},
        ]
    )
    dataset_path = tmp_path / "books_processed.csv"
    df.write_csv(dataset_path)
    monkeypatch.setattr(book_statistics, "DATASET_PATH", dataset_path)
    book_statistics.invalidate_cache()
    yield df
    book_statistics.invalidate_cache()


def test_get_overview_statistics(sample_dataset):
    stats = book_statistics.get_overview_statistics()
    assert stats["total_books"] == sample_dataset.height
    expected_avg = round(sum(sample_dataset["price"].to_list()) / sample_dataset.height, 2)
    assert stats["average_price"] == expected_avg
    distribution = {row["rating"]: row["count"] for row in stats["rating_distribution"]}
    assert distribution == {5.0: 2, 4.0: 1, 3.0: 1}


def test_get_category_statistics(sample_dataset):
    categories = book_statistics.get_category_statistics()
    cat_map = {row["category"]: row for row in categories}
    assert cat_map["Fiction"]["book_count"] == 2
    assert cat_map["Sci-Fi"]["book_count"] == 2
    assert cat_map["Fiction"]["average_price"] == 35.25


def test_get_top_rated_books(sample_dataset):
    books = book_statistics.get_top_rated_books(limit=2)
    assert len(books) == 2
    assert books[0]["title"] == "Book A"
    assert books[1]["title"] == "Book C"


def test_get_books_in_price_range(sample_dataset):
    books = book_statistics.get_books_in_price_range(20, 40)
    titles = {book["title"] for book in books}
    assert titles == {"Book B", "Book C"}


def test_price_range_validation():
    with pytest.raises(ValueError):
        book_statistics.get_books_in_price_range(50, 10)


def test_overview_endpoint(sample_dataset):
    payload = asyncio.run(insights.stats_overview())
    assert payload["total_books"] == 4


def test_categories_endpoint(sample_dataset):
    payload = asyncio.run(insights.stats_by_category())
    assert payload["total_categories"] == 2


def test_top_rated_endpoint(sample_dataset):
    payload = asyncio.run(insights.books_top_rated(limit=1))
    assert payload["returned"] == 1
    assert payload["items"][0]["title"] == "Book A"


def test_price_range_endpoint(sample_dataset):
    payload = asyncio.run(insights.books_by_price_range(min_price=20, max_price=40))
    assert payload["count"] == 2
    titles = {book["title"] for book in payload["items"]}
    assert titles == {"Book B", "Book C"}
