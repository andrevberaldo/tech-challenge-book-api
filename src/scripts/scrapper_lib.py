import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
from pathlib import Path
import csv
import re
import mimetypes
import time
import os
import logging
import base64
from typing import List, Dict, Tuple, Optional
from hashlib import sha1

logger = logging.getLogger("book_scraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

BASE_URL = "https://books.toscrape.com/"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BookScraper/1.0; +https://example.com/bot)"
}

RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5
}

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
    status_forcelist: Tuple[int, ...] = (500, 502, 503, 504)
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
    cats = []
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

def _cache_key_for_url(url: str) -> str:
    return sha1(url.encode("utf-8")).hexdigest()

def load_product_page_with_cache(session: requests.Session, url: str, cache_dir: Optional[Path] = None, timeout: int = 20) -> BeautifulSoup:
    if cache_dir:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = _cache_key_for_url(url)
        cache_file = cache_dir / f"{key}.html"
        if cache_file.exists():
            text = cache_file.read_text(encoding="utf-8")
            return BeautifulSoup(text, "html.parser")
    resp = session.get(url, timeout=(5, min(timeout, 15)))
    try:
        resp.raise_for_status()
    except Exception:
        logger.exception("HTTP error loading product page %s (status %s)", url, getattr(resp, "status_code", None))
        raise
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    text = resp.text
    if cache_dir:
        try:
            cache_file.write_text(text, encoding="utf-8")
        except Exception:
            logger.exception("Could not write cache file %s", cache_file)
    return BeautifulSoup(text, "html.parser")

def get_books(session: requests.Session, category_href_or_url: str, base_url: str = BASE_URL,
              per_page_delay: float = 0.3, per_book_delay: float = 0.08,
              product_page_cache_dir: Optional[str] = None) -> List[Dict]:
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
            stock = None
            if product_page_url:
                try:
                    prod_soup = load_product_page_with_cache(
                        session,
                        product_page_url,
                        Path(product_page_cache_dir) if product_page_cache_dir else None
                    )
                    availability, stock = parse_availability_from_product_page(prod_soup)
                    prod_img = prod_soup.select_one(".thumbnail img") or prod_soup.select_one("div.item img")
                    if prod_img and prod_img.get("src"):
                        image_url = urljoin(product_page_url, prod_img["src"])
                except Exception:
                    logger.exception("Failed to load/parse product page %s", product_page_url)
                time.sleep(per_book_delay)
            books_data.append({
                "title": title,
                "price": price,
                "rating": rating,
                "category": type_category,
                "image": image_url,
                "product_page": product_page_url,
                "availability": availability,
                "stock": stock,
                # image_base64 will be added later by embed_images_as_base64 (kept last)
            })
        next_a = parser.select_one("li.next a")
        if next_a and next_a.get("href"):
            next_href = next_a["href"]
            page_url = urljoin(page_url, next_href)
            time.sleep(per_page_delay)
        else:
            break
    return books_data

def fetch_image_as_base64(session: requests.Session, image_url: str, timeout: int = 20, max_attempts: int = 3) -> str:
    if not image_url:
        return ""
    timeout_tuple = (5, min(timeout, 15))
    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(image_url, stream=False, timeout=timeout_tuple)
            resp.raise_for_status()
            content = resp.content
            if not content:
                logger.warning("Empty content for image %s", image_url)
                return ""
            return base64.b64encode(content).decode("utf-8")
        except requests.exceptions.ReadTimeout as exc:
            logger.warning("ReadTimeout fetching image (attempt %d/%d) %s: %s", attempt, max_attempts, image_url, exc)
        except requests.exceptions.ConnectTimeout as exc:
            logger.warning("ConnectTimeout fetching image (attempt %d/%d) %s: %s", attempt, max_attempts, image_url, exc)
        except requests.exceptions.HTTPError as exc:
            logger.warning("HTTP error fetching image %s: %s", image_url, exc)
            break
        except requests.exceptions.RequestException as exc:
            logger.warning("RequestException fetching image (attempt %d/%d) %s: %s", attempt, max_attempts, image_url, exc)
        if attempt < max_attempts:
            sleep_seconds = 0.5 * (2 ** (attempt - 1))
            time.sleep(sleep_seconds)
    logger.exception("Giving up fetching image %s after %d attempts", image_url, max_attempts)
    return ""

def embed_images_as_base64(session: requests.Session, books: List[Dict],
                           delay_seconds: float = 0.4, skip_existing: bool = True):
    for idx, b in enumerate(books, start=1):
        # preserve original 'image' (URL) and add 'image_base64' as the last field in each dict
        img_field = b.get("image") or ""
        existing_b64 = b.get("image_base64")
        if skip_existing and isinstance(existing_b64, str) and len(existing_b64) > 200:
            time.sleep(delay_seconds)
            continue
        if skip_existing and isinstance(img_field, str) and len(img_field) > 200:
            if re.fullmatch(r"[A-Za-z0-9+/=\s]{200,}", img_field):
                b["image_base64"] = img_field
                time.sleep(delay_seconds)
                continue
        # b64 = fetch_image_as_base64(session, img_field, timeout=20)
        # b["image_base64"] = b64
        time.sleep(delay_seconds)

def save_books_to_csv_master(books: List[Dict], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # image_base64 is last column
    fieldnames = ["title", "price", "rating", "category", "image", "product_page", "availability", "stock", "image_base64"]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_ALL)
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
                "image_base64": b.get("image_base64") or "",
            }
            writer.writerow(row)
        logger.info("CSV written: %s — missing availability: %d, missing stock: %d", out_path, missing_avail_count, missing_stock_count)

def scrape_category(session: requests.Session, category_href: str,
                    output_dir: Path, *, per_page_delay: float = 0.3,
                    per_book_delay: float = 0.08,
                    product_page_cache_dir: Optional[str] = None,
                    image_delay: float = 0.4, skip_existing_images: bool = True) -> Dict:
    books = get_books(session, category_href, per_page_delay=per_page_delay,
                      per_book_delay=per_book_delay, product_page_cache_dir=product_page_cache_dir)
    cat_name = books[0]["category"] if books else None
    # if books:
    #     embed_images_as_base64(session, books, delay_seconds=image_delay, skip_existing=skip_existing_images)
    logger.info("Scraped %d books for category %s", len(books), cat_name)
    return {
        "category_name": cat_name,
        "count": len(books),
        "books": books,
    }

def scrape_all_categories(session: Optional[requests.Session] = None,
                          output_dir: Optional[str] = None,
                          *,
                          per_page_delay: float = 0.25,
                          per_book_delay: float = 0.08,
                          product_page_cache_dir: Optional[str] = None,
                          image_delay: float = 0.4,
                          skip_existing_images: bool = True,
                          save_master_csv: bool = True,
                          max_categories: Optional[int] = None) -> Dict:
    session = session or create_session()
    output_dir = Path(output_dir or os.environ.get("BOOK_SCRAPER_OUTPUT", "data")).resolve()
    csv_dir = output_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Starting full scrape -> output: %s", output_dir)
    categories = get_categories(session)
    if max_categories:
        categories = categories[:max_categories]
    results: List[Tuple[str, List[Dict]]] = []
    total_books = 0
    for idx, (cat_name, cat_href) in enumerate(categories, start=1):
        logger.info("[%d/%d] Scraping category: %s", idx, len(categories), cat_name)
        try:
            books = get_books(session, cat_href, per_page_delay=per_page_delay,
                              per_book_delay=per_book_delay, product_page_cache_dir=product_page_cache_dir)
        except Exception as exc:
            logger.exception("Error scraping category %s: %s", cat_name, exc)
            books = []
        if books:
            embed_images_as_base64(session, books, delay_seconds=image_delay, skip_existing=skip_existing_images)
        results.append((cat_name, books))
        total_books += len(books)
        time.sleep(0.55)
    all_books: List[Dict] = []
    for _cat_name, books in results:
        all_books.extend(books)
    master_csv = csv_dir / "all_books_with_images.csv"
    if save_master_csv:
        save_books_to_csv_master(all_books, master_csv)
        logger.info("Saved master CSV: %s", master_csv)
    summary = {
        "categories_count": len(results),
        "total_books": total_books,
        "output_dir": str(output_dir),
        "csv_master": str(master_csv) if save_master_csv else None,
    }
    logger.info("Scrape finished: %s", summary)
    return summary

def trigger_scrap():
    s = create_session()
    scrape_all_categories(s, output_dir="data/raw", product_page_cache_dir="cache/prod_pages", per_book_delay=0.12)
