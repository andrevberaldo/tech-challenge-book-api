"""book_scraper_documentado (portável)
=====================================

Scraper de demonstração para o site https://books.toscrape.com/.

Este módulo realiza a coleta (scraping) de categorias e livros, com suporte a:

- Requisições resilientes com *retry* e *backoff* exponencial (``requests`` + ``urllib3``).
- *Parsing* de HTML via ``BeautifulSoup``.
- Resolução de links relativos/absolutos (``urllib.parse``).
- Cache opcional de páginas de produto em disco (para acelerar reexecuções).
- Extração de preço, avaliação (estrelas), disponibilidade e estoque.
- Exportação dos dados consolidados para CSV.

Padrões adotados
----------------
- Tipagem com *type hints* (PEP 484).
- Docstrings no estilo Google (PEP 257), em Português.
- *Logging* estruturado com ``logging``.
- Nomes e responsabilidades estáveis (sem alteração de comportamento lógico).

Como usar
---------
Crie uma ``requests.Session`` via :func:`create_session` e então chame
:func:`scrape_all_categories`. Exemplo rápido::

    if __name__ == "__main__":
        s = create_session()
        result = scrape_all_categories(
            s,
            output_dir="data/raw",  # relativo a <repo>/src
            product_page_cache_dir="cache/prod_pages",  # relativo a <repo>/src
            per_book_delay=0.12,
        )
        print(result)

Variáveis de Ambiente
---------------------
- ``BOOK_SCRAPER_OUTPUT``:
    Diretório de saída (relativo a ``<repo>/src`` ou absoluto). Default: ``data/raw``.
- ``BOOK_SCRAPER_CACHE_DIR``:
    Diretório de cache de páginas de produto (relativo a ``<repo>/src`` ou absoluto).
    Default: ``cache/prod_pages``.

Observações
----------
- Este código foi escrito para fins educacionais ("Books to Scrape").
- Respeite ``robots.txt`` e termos de uso ao adaptar para outros sites.
- **Imagens em Base64 desativadas**: não embutimos base64 no CSV por padrão. As
  rotinas estão presentes apenas como utilitários e precisam ser reativadas manualmente.
"""

from __future__ import annotations

import base64
import csv
import logging
import mimetypes
import os
import re
import time
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("book_scraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constantes do scraper
# ---------------------------------------------------------------------------
BASE_URL = "https://books.toscrape.com/"
"""URL base do site alvo para scraping."""

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; BookScraper/1.0; +https://example.com/bot)"
}
"""Cabeçalhos HTTP padrão usados na sessão de scraping."""

RATING_MAP: Dict[str, int] = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}
"""Mapa de rótulos (classes CSS) de estrelas para valores inteiros."""

# ---------------------------------------------------------------------------
# Resolução de paths (portável)
# ---------------------------------------------------------------------------

def _find_src_dir() -> Path:
    """Localiza o diretório ``src`` do projeto subindo pela árvore.

    Returns:
        Path: Caminho absoluto para ``<repo>/src``.
            Se não encontrar, faz *fallback* razoável dois níveis acima do arquivo.
    """
    p = Path(__file__).resolve()
    for parent in p.parents:
        if parent.name == "src":
            return parent
    # fallback razoável
    return p.parents[2] if len(p.parents) >= 3 else p.parent


def _resolve_under_src_value(value: Optional[str], default_rel: str) -> Path:
    """Resolve um caminho relativo/absoluto contra ``<repo>/src``.

    Args:
        value: Caminho informado (absoluto ou relativo ao ``src``). Pode ser ``None``.
        default_rel: Caminho relativo padrão (dentro de ``<repo>/src``).

    Returns:
        Path: Caminho absoluto resolvido.
    """
    base = _find_src_dir()
    if value:
        q = Path(value)
        return q if q.is_absolute() else (base / q)
    return base / default_rel


def _resolve_output_dir(output_dir: Optional[str]) -> Path:
    """Resolve diretório de saída considerando arg→env→default.

    A ordem de precedência é:
      1) parâmetro ``output_dir`` (se fornecido);
      2) variável de ambiente ``BOOK_SCRAPER_OUTPUT``;
      3) default ``data/raw`` relativo a ``<repo>/src``.

    Args:
        output_dir: Caminho fornecido pelo chamador, absoluto ou relativo.

    Returns:
        Path: Caminho absoluto para o diretório de saída.
    """
    env = os.environ.get("BOOK_SCRAPER_OUTPUT")
    return _resolve_under_src_value(output_dir or env, "data/raw")


def _resolve_cache_dir(cache_dir: Optional[str]) -> Path:
    """Resolve diretório de cache considerando arg→env→default.

    A ordem de precedência é:
      1) parâmetro ``cache_dir`` (se fornecido);
      2) variável de ambiente ``BOOK_SCRAPER_CACHE_DIR``;
      3) default ``cache/prod_pages`` relativo a ``<repo>/src``.

    Args:
        cache_dir: Caminho do cache, absoluto ou relativo.

    Returns:
        Path: Caminho absoluto para o diretório de cache.
    """
    env = os.environ.get("BOOK_SCRAPER_CACHE_DIR")
    return _resolve_under_src_value(cache_dir or env, "cache/prod_pages")


# ---------------------------------------------------------------------------
# Funções utilitárias de texto e parsing
# ---------------------------------------------------------------------------

def safe_slug(text: Optional[str], maxlen: int = 50) -> str:
    """Normaliza texto em *slug* seguro para nomes de arquivos/paths.

    Remove pontuação, colapsa espaços/traços, aplica minúsculas e limita tamanho.

    Args:
        text: Texto de entrada (ou ``None``).
        maxlen: Tamanho máximo do slug.

    Returns:
        str: Slug resultante. Retorna ``"unknown"`` se o texto for vazio.
    """
    if not text:
        return "unknown"
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:maxlen].strip("-")


def parse_price(text: str) -> Optional[float]:
    """Converte um preço como ``'£51.77'`` para ``float``.

    Remove símbolos/resíduos de encoding antes de converter.

    Args:
        text: Texto do preço.

    Returns:
        Optional[float]: Valor numérico ou ``None`` se falhar.
    """
    txt = text.replace("£", "").replace("Â", "").strip()
    try:
        return float(txt)
    except Exception:
        return None


def extract_rating_from_tag(book_soup: BeautifulSoup) -> Optional[int]:
    """Extrai a avaliação (1–5) a partir das classes CSS do card do livro.

    Args:
        book_soup: Trecho ``BeautifulSoup`` do card do livro.

    Returns:
        Optional[int]: Avaliação entre 1 e 5, ou ``None`` se não encontrada.
    """
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
    """Infere extensão de imagem a partir da URL ou do cabeçalho Content-Type.

    Args:
        url: URL requisitada.
        resp: Resposta HTTP da imagem.

    Returns:
        str: Extensão com ponto (ex.: ``.jpg``). *Fallback*: ``.jpg``.
    """
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


# ---------------------------------------------------------------------------
# Sessão HTTP com retries/backoff
# ---------------------------------------------------------------------------

def create_session(
    headers: Optional[Dict[str, str]] = None,
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: Tuple[int, ...] = (500, 502, 503, 504),
) -> requests.Session:
    """Cria uma ``requests.Session`` com política de retry/backoff.

    Args:
        headers: Cabeçalhos a adicionar.
        retries: Número de tentativas em falhas (conexão/leitura/status).
        backoff_factor: Fator de *backoff* exponencial.
        status_forcelist: Códigos que disparam retry.

    Returns:
        requests.Session: Sessão configurada.
    """
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


# ---------------------------------------------------------------------------
# Carregamento e parsing de páginas
# ---------------------------------------------------------------------------

def load_page(session: requests.Session, url: str, timeout: int = 20) -> BeautifulSoup:
    """Faz o download de uma página HTML e devolve ``BeautifulSoup``.

    Ajusta a codificação quando necessário.

    Args:
        session: Sessão HTTP.
        url: URL absoluta.
        timeout: Timeout total da requisição (connect é 5s).

    Raises:
        requests.HTTPError: Quando o status HTTP é de erro.

    Returns:
        BeautifulSoup: Parser da página carregada.
    """
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
    """Obtém as categorias da *sidebar* inicial.

    Args:
        session: Sessão HTTP.
        base_url: URL base do site.

    Returns:
        List[Tuple[str, str]]: Lista de pares (nome, href_relativo).
    """
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
    """Interpreta o texto de disponibilidade (ex.: 'In stock (22 available)').

    Args:
        text: Texto bruto de disponibilidade.

    Returns:
        Tuple[bool, Optional[int]]: (em_estoque, quantidade) — quantidade pode ser ``None``.
    """
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
    """Extrai disponibilidade diretamente da página do produto.

    Args:
        product_soup: Parser da página do produto.

    Returns:
        Tuple[bool, Optional[int]]: (em_estoque, quantidade).
    """
    p = product_soup.find("p", class_="instock availability")
    if not p:
        return False, None
    text = p.get_text(separator=" ", strip=True)
    return parse_availability_text(text)


def _cache_key_for_url(url: str) -> str:
    """Gera chave SHA-1 estável para uma URL (usada no cache em disco).

    Args:
        url: URL a ser *hasheada*.

    Returns:
        str: Hex digest SHA-1.
    """
    return sha1(url.encode("utf-8")).hexdigest()


def load_product_page_with_cache(
    session: requests.Session,
    url: str,
    cache_dir: Optional[Path] = None,
    timeout: int = 20,
) -> BeautifulSoup:
    """Carrega a página do produto com cache opcional em disco.

    Args:
        session: Sessão HTTP.
        url: URL absoluta do produto.
        cache_dir: Diretório base do cache (criado se necessário).
        timeout: Timeout total.

    Raises:
        requests.HTTPError: Quando o status HTTP é de erro.

    Returns:
        BeautifulSoup: Parser da página (de cache ou rede).
    """
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
        logger.exception(
            "HTTP error loading product page %s (status %s)", url, getattr(resp, "status_code", None)
        )
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


# ---------------------------------------------------------------------------
# Coleta de livros por categoria e iteração de páginas
# ---------------------------------------------------------------------------

def get_books(
    session: requests.Session,
    category_href_or_url: str,
    base_url: str = BASE_URL,
    per_page_delay: float = 0.3,
    per_book_delay: float = 0.08,
    product_page_cache_dir: Optional[str] = None,
) -> List[Dict]:
    """Varre todas as páginas de uma categoria e extrai os livros.

    Para cada card encontrado na listagem:
      - lê preço, rating, imagem e link do produto;
      - opcionalmente abre a página do produto (cacheável) para obter disponibilidade
        e imagem em melhor qualidade.

    Args:
        session: Sessão HTTP.
        category_href_or_url: Href relativo ou URL absoluta da categoria.
        base_url: URL base (usada para resolver href relativo).
        per_page_delay: Atraso entre páginas para evitar *rate limiting*.
        per_book_delay: Atraso entre livros ao abrir a página do produto.
        product_page_cache_dir: Diretório de cache do HTML da página de produto.

    Returns:
        List[Dict]: Dicionários com ``title``, ``price``, ``rating``, ``category``,
        ``image``, ``product_page``, ``availability``, ``stock``.
    """
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
                    prod_soup = load_product_page_with_cache(
                        session,
                        product_page_url,
                        Path(product_page_cache_dir) if product_page_cache_dir else None,
                    )
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
                    # "image_base64" será preenchido depois por embed_images_as_base64 (desativado por padrão)
                }
            )

        # paginação
        next_a = parser.select_one("li.next a")
        if next_a and next_a.get("href"):
            next_href = next_a["href"]
            page_url = urljoin(page_url, next_href)
            time.sleep(per_page_delay)
        else:
            break

    return books_data


# ---------------------------------------------------------------------------
# Download/embedding de imagens (opcional)
# ---------------------------------------------------------------------------

def fetch_image_as_base64(
    session: requests.Session,
    image_url: str,
    timeout: int = 20,
    max_attempts: int = 3,
) -> str:
    """Baixa uma imagem e retorna o conteúdo em Base64.

    **Utilitário não usado por padrão** (embedding desativado).

    Args:
        session: Sessão HTTP.
        image_url: URL absoluta da imagem.
        timeout: Timeout total (connect=5s).
        max_attempts: Tentativas em falhas transitórias.

    Returns:
        str: Base64 (sem prefixo data-URI) ou string vazia em caso de erro.
    """
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
            time.sleep(0.5 * (2 ** (attempt - 1)))
    logger.exception("Giving up fetching image %s after %d attempts", image_url, max_attempts)
    return ""


def embed_images_as_base64(
    session: requests.Session,
    books: List[Dict],
    delay_seconds: float = 0.4,
    skip_existing: bool = True,
) -> None:
    """Percorre livros e (opcionalmente) preenche ``image_base64``.

    **Desativado no fluxo padrão**: as linhas de download estão comentadas.
    Mantido para referência/demonstração.

    Args:
        session: Sessão HTTP.
        books: Lista de dicionários de livros.
        delay_seconds: Pausa entre itens (ética/limites).
        skip_existing: Se ``True``, pula quando já houver base64.
    """
    for _ in books:
        # Para ativar de fato, descomente o download em sua versão anterior.
        time.sleep(delay_seconds)


# ---------------------------------------------------------------------------
# Persistência (CSV)
# ---------------------------------------------------------------------------

def save_books_to_csv_master(books: List[Dict], out_path: Path) -> None:
    """Salva os livros em CSV "mestre" (``all_books_with_images.csv``).

    A última coluna é ``image_base64`` (se existir). Campos ausentes viram ``""``.
    ``availability`` é normalizado para ``"yes"``/``"no"``/``""``.

    Args:
        books: Lista de livros (dicionários).
        out_path: Caminho do CSV de saída.
    """
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
        "image_base64",
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
                "image_base64": b.get("image_base64") or "",
            }
            writer.writerow(row)

        logger.info(
            "CSV written: %s — missing availability: %d, missing stock: %d",
            out_path,
            missing_avail_count,
            missing_stock_count,
        )


# ---------------------------------------------------------------------------
# Orquestração de scraping
# ---------------------------------------------------------------------------

def scrape_category(
    session: requests.Session,
    category_href: str,
    output_dir: Path,
    *,
    per_page_delay: float = 0.3,
    per_book_delay: float = 0.08,
    product_page_cache_dir: Optional[str] = None,
    image_delay: float = 0.4,
    skip_existing_images: bool = True,
) -> Dict:
    """Executa scraping de uma categoria específica e retorna um resumo.

    Args:
        session: Sessão HTTP.
        category_href: Href relativo da categoria (conforme *sidebar*).
        output_dir: Diretório base (mantido para assinatura consistente).
        per_page_delay: Delay entre páginas.
        per_book_delay: Delay ao abrir página do produto.
        product_page_cache_dir: Diretório do cache de produto.
        image_delay: Delay por imagem no *embedding* (se ativado).
        skip_existing_images: Se ``True``, pula *embedding* quando já existir.

    Returns:
        Dict: ``{"category_name": str | None, "count": int, "books": list}``.
    """
    cache_dir_path = _resolve_cache_dir(product_page_cache_dir)

    books = get_books(
        session,
        category_href,
        per_page_delay=per_page_delay,
        per_book_delay=per_book_delay,
        product_page_cache_dir=str(cache_dir_path) if cache_dir_path else None,
    )
    cat_name = books[0]["category"] if books else None

    # Para embutir imagens, reative manualmente a chamada abaixo:
    # embed_images_as_base64(session, books, delay_seconds=image_delay, skip_existing=skip_existing_images)

    logger.info("Scraped %d books for category %s", len(books), cat_name)
    return {"category_name": cat_name, "count": len(books), "books": books}


def scrape_all_categories(
    session: Optional[requests.Session] = None,
    output_dir: Optional[str] = None,
    *,
    per_page_delay: float = 0.25,
    per_book_delay: float = 0.08,
    product_page_cache_dir: Optional[str] = None,
    image_delay: float = 0.4,
    skip_existing_images: bool = True,
    save_master_csv: bool = True,
    max_categories: Optional[int] = None,
) -> Dict:
    """Coleta todas (ou as N primeiras) categorias e salva CSV consolidado.

    O CSV final é salvo por padrão em:
        ``<repo>/src/data/raw/all_books_with_images.csv``

    Args:
        session: Sessão HTTP (cria uma se for ``None``).
        output_dir: Diretório de saída (arg → env → default ``data/raw``).
        per_page_delay: Delay entre páginas por categoria.
        per_book_delay: Delay ao abrir páginas de produto.
        product_page_cache_dir: Diretório de cache de páginas de produto (arg → env → default).
        image_delay: Delay por imagem no *embedding* (se ativado).
        skip_existing_images: Não recalcula quando já existe base64.
        save_master_csv: Se ``True``, grava o CSV consolidado.
        max_categories: Limita o número de categorias processadas.

    Returns:
        Dict: Resumo com ``categories_count``, ``total_books``, ``output_dir`` e
        ``csv_master`` (se salvo).
    """
    session = session or create_session()

    output_dir_path = _resolve_output_dir(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    logger.info("Starting full scrape -> output: %s", output_dir_path)

    categories = get_categories(session)
    if max_categories:
        categories = categories[: max_categories]

    cache_dir_path = _resolve_cache_dir(product_page_cache_dir)

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
                product_page_cache_dir=str(cache_dir_path) if cache_dir_path else None,
            )
        except Exception as exc:
            logger.exception("Error scraping category %s: %s", cat_name, exc)
            books = []

        # (Base64 desativado) — não chamamos embed_images_as_base64 aqui.

        results.append((cat_name, books))
        total_books += len(books)
        time.sleep(0.55)

    # Achata resultados e escreve CSV
    all_books: List[Dict] = []
    for _cat_name, books in results:
        all_books.extend(books)

    master_csv = output_dir_path / "all_books_with_images.csv"
    if save_master_csv:
        save_books_to_csv_master(all_books, master_csv)
        logger.info("Saved master CSV: %s", master_csv)

    summary = {
        "categories_count": len(results),
        "total_books": total_books,
        "output_dir": str(output_dir_path),
        "csv_master": str(master_csv) if save_master_csv else None,
    }
    logger.info("Scrape finished: %s", summary)
    return summary


def trigger_scrap(task) -> None:
    """Wrapper para rodar o pipeline a partir de um *task runner* externo.

    Cria a sessão, executa :func:`scrape_all_categories` respeitando as envs
    documentadas, e marca o *task* como concluído ao final.

    Args:
        task: Objeto com método ``setTaskState(bool)`` para sinalização de término.
    """
    s = create_session()
    scrape_all_categories(
        s,
        output_dir=None,  # default: <repo>/src/data/raw
        product_page_cache_dir=None,  # default: <repo>/src/cache/prod_pages
        per_book_delay=0.12,
    )
    task.setTaskState(False)


# if __name__ == "__main__":
#     s = create_session()
#     result = scrape_all_categories(
#         s, output_dir="data/raw", product_page_cache_dir="cache/prod_pages", per_book_delay=0.12
#     )
#     print(result)
