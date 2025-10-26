# Scripts - Módulos de Processamento de Dados

Este diretório contém os módulos responsáveis pela pipeline de ETL, análises estatísticas e utilitários para consumo de dados por modelos de ML.

---

## Estrutura de Arquivos

### **Core Pipeline**

#### `data_processing_pipeline.py`
Pipeline principal que orquestra a execução completa do processamento de dados.
- Executa limpeza de dados (data cleaning)
- Executa feature engineering
- Gera logs e estatísticas de execução
- Pode ser executado diretamente: `python -m src.scripts.data_processing_pipeline`

#### `data_cleaning.py`
Módulo responsável pela limpeza e validação dos dados brutos.
- Remove/trata valores nulos e duplicatas
- Normaliza categorias problemáticas
- Cria IDs únicos
- Transforma colunas (ex: availability yes/no → 1/0)
- **Entrada:** `data/raw/all_books_with_images.csv`
- **Saída:** `data/processed/books_processed.csv`

#### `feature_engineering.py`
Cria features derivadas para análise e modelos de ML.
- Categorização de preços (price_range)
- Features de título (has_subtitle, has_series, title_length, etc.)
- Categorização de ratings e stock
- One-hot encoding de categorias
- Score de popularidade
- **Entrada:** `data/processed/books_processed.csv`
- **Saída:** `data/features/books_features.csv`

---

### **Data Types & Configuration**

#### `data_types.py`
Define modelos Pydantic e tipos de dados usados em toda a aplicação.
- `PipelineConfig`: Configuração da pipeline (caminhos, parâmetros)
- `PipelineStats`: Estatísticas de execução
- Enums: `PriceRange`, `RatingCategory`, `StockLevel`
- Garante validação e type safety

---

### **Statistics & ML Data**

#### `book_statistics.py`
Funções para cálculo de estatísticas sobre a coleção de livros.
- `get_overview_statistics()`: Total de livros, preço médio, distribuição de ratings
- `get_category_statistics()`: Métricas agregadas por categoria
- `get_top_rated_books()`: Livros com melhores avaliações
- `get_books_in_price_range()`: Filtro por faixa de preço
- Usado pelos endpoints `/api/v1/stats/*` e `/api/v1/books/*`

#### `ml_data.py`
Utilitários para preparação de dados voltados a modelos de ML.
- Carregamento com cache do dataset de features
- `get_features_dataframe()`: Retorna features completas
- `get_training_split()`: Divisão treino/teste (70/30 padrão)
- Casting e normalização de tipos
- Usado pelos endpoints `/api/v1/ml/*`

#### `ml_datasets.py`
Preparação de datasets específicos para treinamento/inferência.
- `get_feature_matrix()`: Matriz de features para modelos
- `get_training_dataset()`: Dataset formatado para treino/teste
- Suporta seleção de colunas e splits customizados

---

### **Web Scraping**

#### `scrapper_lib.py`
Biblioteca para extração de dados de livros da web.
- `trigger_scrap()`: Inicia processo de scraping
- Coleta títulos, preços, ratings, categorias, imagens
- Salva dados brutos em `data/raw/all_books_with_images.csv`
- Usado pelo endpoint `/scrapper`

---

## Uso Rápido

### Executar Pipeline Completa
```bash
python -m src.scripts.data_processing_pipeline
```

### Importar em Código
```python
from src.scripts import run_pipeline
from src.scripts.book_statistics import get_overview_statistics
from src.scripts.ml_data import get_training_split

# Executar pipeline
stats = run_pipeline()

# Obter estatísticas
overview = get_overview_statistics()

# Preparar dados para ML
train_df, test_df = get_training_split(ratio=0.7)
```

---

## Fluxo de Dados

```
[Web Scraping]
    ↓
data/raw/all_books_with_images.csv
    ↓
[Data Cleaning]
    ↓
data/processed/books_processed.csv
    ↓
[Feature Engineering]
    ↓
data/features/books_features.csv
    ↓
[Statistics & ML APIs]
```

---

## Configuração

A pipeline usa `PipelineConfig` definido em `data_types.py`:

```python
PipelineConfig(
    input_file="data/raw/all_books_with_images.csv",
    processed_output="data/processed/books_processed.csv",
    features_output="data/features/books_features.csv",
    default_category="Outros",
    problematic_categories=["Add a comment", "Default"]
)
```

## 📊 Resultados da Última Execução

- **Registros processados:** 1000
- **Tempo de execução:** 0.42s  
- **Features criadas:** 59
- **Categorias limpas:** 219
- **Distribuição de preços:**
  - Médio (20-40): 401 livros (40.1%)
  - Alto (40-50): 205 livros (20.5%)
  - Premium (>50): 198 livros (19.8%)
  - Baixo (≤20): 196 livros (19.6%)

## 🔧 Dependências

- `polars` - Processamento eficiente de dados
- `pydantic` - Validação e tipagem de dados
- `pathlib` - Manipulação de caminhos
- `uuid` - Geração de IDs únicos

## 📈 Próximos Passos

Os dados estão prontos para:
- ✅ Análise exploratória avançada
- ✅ Modelagem preditiva de preços
- ✅ Sistema de recomendação de livros
- ✅ API de consulta de dados

## 🎯 Qualidade dos Dados

- **0 valores nulos** - Dataset íntegro
- **1000 IDs únicos** - Identificação consistente
- **59 features** - Rico conjunto para ML
- **Validação completa** - Dados confiáveis para análise

---

**Desenvolvido para Tech Challenge**  
*Pipeline otimizada com Polars + Pydantic*