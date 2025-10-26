"""
Tipos de dados e modelos Pydantic para a pipeline de processamento de livros.

Este módulo define os schemas de dados utilizados na pipeline de ETL,
garantindo tipagem segura e validação dos dados.
"""

from typing import List, Dict
from pydantic import BaseModel, Field
from enum import Enum
from pathlib import Path
import polars as pl

# Diretório base do projeto
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "src" / "data"


class PriceRange(str, Enum):
    """Faixas de preço dos livros."""
    LOW = "Baixo"
    MEDIUM = "Médio"  
    HIGH = "Alto"
    PREMIUM = "Premium"


class RatingCategory(str, Enum):
    """Categorias de rating."""
    VERY_LOW = "Muito Baixo"  # 1
    LOW = "Baixo"             # 2
    MEDIUM = "Médio"          # 3
    HIGH = "Alto"             # 4
    VERY_HIGH = "Muito Alto"  # 5


class StockLevel(str, Enum):
    """Níveis de estoque."""
    LOW = "Baixo"      # 1-5
    MEDIUM = "Médio"   # 6-15
    HIGH = "Alto"      # 16+


class RawBookData(BaseModel):
    """Schema para os dados brutos dos livros."""
    title: str
    price: float = Field(gt=0, description="Preço deve ser positivo")
    rating: int = Field(ge=1, le=5, description="Rating deve estar entre 1 e 5")
    category: str
    image: str
    product_page: str
    availability: str
    stock: int = Field(ge=0, description="Stock deve ser não-negativo")
    image_base64: str


class ProcessedBookData(BaseModel):
    """Schema para os dados processados (após limpeza básica)."""
    id: str = Field(description="ID único do livro")
    title: str
    price: float = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    category: str
    image: str
    product_page: str
    availability: int = Field(ge=0, le=1, description="0 para não, 1 para sim")
    stock: int = Field(ge=0)
    image_base64: str


class BookFeatures(BaseModel):
    """Schema para os dados com features criadas."""
    id: str
    title: str
    price: float
    rating: int
    category: str
    image: str
    product_page: str
    availability: int
    stock: int
    image_base64: str
    
    # Features derivadas
    price_range: PriceRange
    has_subtitle: bool = Field(description="Título contém ':'")
    has_series: bool = Field(description="Título contém '('")
    starts_with_the: bool = Field(description="Título começa com 'The'")
    title_length: int = Field(ge=0, description="Comprimento do título")
    rating_category: RatingCategory
    stock_level: StockLevel
    title_word_count: int = Field(ge=0, description="Número de palavras no título")
    has_numbers: bool = Field(description="Título contém números")
    popularity_score: float = Field(ge=0, description="Score de popularidade baseado em rating e stock")
    

class PipelineConfig(BaseModel):
    """Configuração da pipeline."""
    input_file: str = str(DATA_DIR / "raw" / "all_books_with_images.csv")
    processed_output: str = str(DATA_DIR / "processed" / "books_processed.csv")
    features_output: str = str(DATA_DIR / "features" / "books_features.csv")
    
    # Configurações de limpeza
    default_category: str = "Outros"
    problematic_categories: List[str] = ["Add a comment", "Default"]
    
    # Configurações de features
    price_ranges: Dict[str, tuple] = {
        "Baixo": (0, 20),
        "Médio": (20, 40),
        "Alto": (40, 50),
        "Premium": (50, float('inf'))
    }
    
    stock_ranges: Dict[str, tuple] = {
        "Baixo": (0, 5),
        "Médio": (6, 15),
        "Alto": (16, float('inf'))
    }


class PipelineStats(BaseModel):
    """Estatísticas da execução da pipeline."""
    total_records: int
    null_records_found: int
    duplicate_titles: int
    categories_cleaned: int
    processed_records: int
    features_created: int
    execution_time_seconds: float
    
    
def validate_polars_dataframe(df: pl.DataFrame, required_columns: List[str]) -> bool:
    """
    Valida se um DataFrame Polars contém as colunas necessárias.
    
    Args:
        df: DataFrame Polars a ser validado
        required_columns: Lista das colunas obrigatórias
        
    Returns:
        bool: True se válido, False caso contrário
    """
    return all(col in df.columns for col in required_columns)


def get_raw_data_schema() -> List[str]:
    """Retorna as colunas esperadas nos dados brutos."""
    return [
        "title", "price", "rating", "category", "image", 
        "product_page", "availability", "stock", "image_base64"
    ]


def get_processed_data_schema() -> List[str]:
    """Retorna as colunas esperadas nos dados processados."""
    return [
        "id", "title", "price", "rating", "category", "image",
        "product_page", "availability", "stock", "image_base64"
    ]


def get_features_schema() -> List[str]:
    """Retorna as colunas esperadas nos dados com features."""
    base_columns = get_processed_data_schema()
    feature_columns = [
        "price_range", "has_subtitle", "has_series", "starts_with_the",
        "title_length", "rating_category", "stock_level", 
        "title_word_count", "has_numbers", "popularity_score"
    ]
    return base_columns + feature_columns