# src/scripts/scrapper_lib.py
"""
Scraper (portável) para https://books.toscrape.com/

Resumo
------
- Faz scraping das categorias e livros (title, price, rating, category, image,
  product_page, availability, stock).
- Requisições resilientes (requests + urllib3 Retry/backoff).
- Parsing com BeautifulSoup.
- **Sem cache de HTML, sem imagens em Base64 e sem Polars.**
- Exporta um CSV "mestre" em <repo>/src/data/raw/all_books_with_images.csv.

Caminhos padrão
---------------
- CSV bruto (raw): src/data/raw/all_books_with_images.csv

Variáveis de ambiente (opcionais)
---------------------------------
- BOOK_SCRAPER_OUTPUT -> altera diretório de saída "raw"

Uso rápido
----------
from src.scripts.scrapper_lib import trigger_scrap
trigger_scrap()  # executa e grava o CSV no caminho padrão
"""

from __future__ import annotations

import csv
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("book_scraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

BASE_URL = "https://books.toscrape.com/"

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; BookScraper/1.0; +https://example.com/bot)"
}

RATING_MAP: Dict[str, int] = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

# ─────────────────────────────────────────────────────────────
# Resolução de paths (portável; relativos a <repo>/src por padrão)
# ─────────────────────────────────────────────────────────────
def _find_src_dir() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if parent.name == "src":
            return parent
    return p.parents[2] if len(p.parents) >= 3 else p.parent

def _resolve_under_src(value: Optional[str], default_rel: str) -> Path:
    base = _find_src_dir()
    if value:
        q = Path(value)
        return q if q.is_absolute() else (base / q)
    return base / default_rel

def _resolve_output_raw_dir(output_dir: Optional[str]) -> Path:
    # CSV “mestre” → default src/data/raw
    env = os.environ.get("BOOK_SCRAPER_OUTPUT")
    return _resolve_under_src(output_dir or env, "src/data/raw")

# ─────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────
def safe_slug(text: Optional[str], maxlen: int = 50) -> str:
    if not text:
        return "unknown"
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:maxlen].strip("-")

def parse_price(text: str) -> Optional[float]:
    txt = text.replace("£", "").replace("Â", "").strip()
    try:
        return float(txt)
    except Exception:
        return None

def extract_rating_from_tag(book_soup: BeautifulSoup) -> Optional[int]:
    p = book_soup.find("p", class_="star-rating")
    if p:
        classes = p.get("class", [])
        for cls in classes:
            if cls in RATING_MAP:
                return RATING_MAP[cls]
    for name, val in RATING_MAP.items():
        if book_soup.find("p", class_=f"star-rating {name}"):
            return val
    return None

def get_extension_from_url_or_ct(url: str, resp: requests.Response) -> str:
    # Mantido como utilitário genérico; não baixamos imagens aqui.
    path = urlparse(url).path
    ext = Path(path).suffix
    if ext:
        return ext.lower()
    ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ct:
        ext = mimetypes.guess_extension(ct)
        if ext:
            return ext
    return ".jpg"

def create_session(
    headers: Optional[Dict[str, str]] = None,
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: Tuple[int, ...] = (500, 502, 503, 504),
) -> requests.Session:
    s = requests.Session()
    s.headers.update(headers or DEFAULT_HEADERS)
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def load_page(session: requests.Session, url: str, timeout: int = 20) -> BeautifulSoup:
    resp = session.get(url, timeout=(5, min(timeout, 15)))
    try:
        resp.raise_for_status()
    except Exception:
        logger.exception("HTTP error loading %s (status %s)", url, getattr(resp, "status_code", None))
        raise
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "html.parser")

def get_categories(session: requests.Session, base_url: str = BASE_URL) -> List[Tuple[str, str]]:
    parser = load_page(session, base_url)
    links = parser.select("ul.nav.nav-list ul li a")
    cats: List[Tuple[str, str]] = []
    for a in links:
        href = a.get("href")
        name = a.get_text(strip=True)
        if href:
            cats.append((name, href))
    logger.info("Found %d categories", len(cats))
    return cats

def parse_availability_text(text: str) -> Tuple[bool, Optional[int]]:
    text = (text or "").strip()
    lowered = text.lower()
    in_stock = "in stock" in lowered
    m = re.search(r"\((\d+)\s*available\)", text, re.I)
    if m:
        return True, int(m.group(1))
    m2 = re.search(r"(\d+)", text)
    if m2:
        return in_stock, int(m2.group(1))
    return in_stock, None

def parse_availability_from_product_page(product_soup: BeautifulSoup) -> Tuple[bool, Optional[int]]:
    p = product_soup.find("p", class_="instock availability")
    if not p:
        return False, None
    text = p.get_text(separator=" ", strip=True)
    return parse_availability_text(text)

# ─────────────────────────────────────────────────────────────
# Coleta de livros por categoria e iteração de páginas (sem cache)
# ─────────────────────────────────────────────────────────────
def get_books(
    session: requests.Session,
    category_href_or_url: str,
    base_url: str = BASE_URL,
    per_page_delay: float = 0.3,
    per_book_delay: float = 0.08,
) -> List[Dict]:
    books_data: List[Dict] = []
    page_url = urljoin(base_url, category_href_or_url)

    while True:
        parser = load_page(session, page_url)
        h1 = parser.find("h1")
        type_category = h1.get_text(strip=True) if h1 else None

        book_nodes = parser.find_all("article", class_="product_pod")
        for book in book_nodes:
            try:
                a_tag = book.h3.a
                title = a_tag.get("title") or a_tag.get_text(strip=True)
            except Exception:
                title = None

            price_tag = book.find("p", class_="price_color")
            price = parse_price(price_tag.get_text(strip=True)) if price_tag else None
            rating = extract_rating_from_tag(book)

            img_tag = book.find("img")
            image_url = urljoin(page_url, img_tag["src"]) if img_tag and img_tag.get("src") else None

            prod_href = a_tag.get("href") if a_tag else None
            product_page_url = urljoin(page_url, prod_href) if prod_href else None
            if product_page_url:
                product_page_url, _ = urldefrag(product_page_url)

            availability = False
            stock: Optional[int] = None

            if product_page_url:
                try:
                    prod_soup = load_page(session, product_page_url)
                    availability, stock = parse_availability_from_product_page(prod_soup)

                    # Em algumas páginas, a imagem de melhor resolução está no detalhe
                    prod_img = prod_soup.select_one(".thumbnail img") or prod_soup.select_one("div.item img")
                    if prod_img and prod_img.get("src"):
                        image_url = urljoin(product_page_url, prod_img["src"])
                except Exception:
                    logger.exception("Failed to load/parse product page %s", product_page_url)
                time.sleep(per_book_delay)

            books_data.append(
                {
                    "title": title,
                    "price": price,
                    "rating": rating,
                    "category": type_category,
                    "image": image_url,
                    "product_page": product_page_url,
                    "availability": availability,
                    "stock": stock,
                }
            )

        next_a = parser.select_one("li.next a")
        if next_a and next_a.get("href"):
            next_href = next_a["href"]
            page_url = urljoin(page_url, next_href)
            time.sleep(per_page_delay)
        else:
            break

    return books_data

# ─────────────────────────────────────────────────────────────
# Persistência (CSV)
# ─────────────────────────────────────────────────────────────
def save_books_to_csv_master(books: List[Dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "title",
        "price",
        "rating",
        "category",
        "image",
        "product_page",
        "availability",
        "stock",
    ]

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()

        missing_stock_count = 0
        missing_avail_count = 0

        for b in books:
            availability = b.get("availability")
            stock = b.get("stock")
            if availability is None:
                missing_avail_count += 1
            if stock is None:
                missing_stock_count += 1

            row = {
                "title": b.get("title") or "",
                "price": "" if b.get("price") is None else b.get("price"),
                "rating": "" if b.get("rating") is None else b.get("rating"),
                "category": b.get("category") or "",
                "image": b.get("image") or "",
                "product_page": b.get("product_page") or "",
                "availability": "yes" if availability else "no" if availability is not None else "",
                "stock": "" if stock is None else int(stock),
            }
            writer.writerow(row)

        logger.info(
            "CSV written: %s — missing availability: %d, missing stock: %d",
            out_path,
            missing_avail_count,
            missing_stock_count,
        )

# ─────────────────────────────────────────────────────────────
# Orquestração
# ─────────────────────────────────────────────────────────────
def scrape_category(
    session: requests.Session,
    category_href: str,
    output_dir: Path,
    *,
    per_page_delay: float = 0.3,
    per_book_delay: float = 0.08,
) -> Dict:
    books = get_books(
        session,
        category_href,
        per_page_delay=per_page_delay,
        per_book_delay=per_book_delay,
    )
    cat_name = books[0]["category"] if books else None
    logger.info("Scraped %d books for category %s", len(books), cat_name)
    return {"category_name": cat_name, "count": len(books), "books": books}

def scrape_all_categories(
    session: Optional[requests.Session] = None,
    output_dir: Optional[str] = None,
    *,
    per_page_delay: float = 0.25,
    per_book_delay: float = 0.08,
    save_master_csv: bool = True,
    max_categories: Optional[int] = None,
) -> Dict:
    """
    Saída padrão:
      - CSV “mestre”: <repo>/src/data/raw/all_books_with_images.csv
    """
    session = session or create_session()

    raw_dir = _resolve_output_raw_dir(output_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting full scrape -> raw: %s", raw_dir)

    categories = get_categories(session)
    if max_categories:
        categories = categories[:max_categories]

    results: List[Tuple[str, List[Dict]]] = []
    total_books = 0

    for idx, (cat_name, cat_href) in enumerate(categories, start=1):
        logger.info("[%d/%d] Scraping category: %s", idx, len(categories), cat_name)
        try:
            books = get_books(
                session,
                cat_href,
                per_page_delay=per_page_delay,
                per_book_delay=per_book_delay,
            )
        except Exception as exc:
            logger.exception("Error scraping category %s: %s", cat_name, exc)
            books = []

        results.append((cat_name, books))
        total_books += len(books)
        time.sleep(0.55)

    all_books: List[Dict] = []
    for _cat_name, books in results:
        all_books.extend(books)

    csv_master = raw_dir / "all_books_with_images.csv"
    if save_master_csv:
        save_books_to_csv_master(all_books, csv_master)
        logger.info("Saved master CSV: %s", csv_master)

    summary = {
        "categories_count": len(results),
        "total_books": total_books,
        "raw_dir": str(raw_dir),
        "csv_master": str(csv_master) if save_master_csv else None,
    }
    logger.info("Scrape finished: %s", summary)
    return summary

def trigger_scrap():
    """
    Executa o pipeline com defaults portáveis (somente CSV bruto).
    - CSV “mestre”: src/data/raw/all_books_with_images.csv
    """
    s = create_session()
    return scrape_all_categories(
        s,
        output_dir=None,
        per_book_delay=0.12,
    )
 