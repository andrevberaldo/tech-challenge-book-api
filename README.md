# Tech Challenge Book API
API FastAPI desenvolvida para o Tech Challenge como plataforma de consulta, análise e preparação de dados de livros coletados via web scraping do site `books.toscrape.com`.

## Documentação Principal
- [Home da Wiki](https://github.com/andrevberaldo/tech-challenge-book-api/wiki/Tech-Challenge-Book-API)
- [Visão Geral e Arquitetura](https://github.com/andrevberaldo/tech-challenge-book-api/wiki/Vis%C3%A3o-Geral-e-Arquitetura)
- [Instalação e Configuração](https://github.com/andrevberaldo/tech-challenge-book-api/wiki/Instala%C3%A7%C3%A3o-e-Configura%C3%A7%C3%A3o)
- [Documentação das Rotas](https://github.com/andrevberaldo/tech-challenge-book-api/wiki/Documenta%C3%A7%C3%A3o-das-Rotas)
- [Exemplos de Chamadas HTTP](https://github.com/andrevberaldo/tech-challenge-book-api/wiki/Exemplos-de-Chamadas-HTTP)
- [Operação e Execução](https://github.com/andrevberaldo/tech-challenge-book-api/wiki/Opera%C3%A7%C3%A3o-e-Execu%C3%A7%C3%A3o)

> Este README resume os pontos-chave; consulte a Wiki para detalhes completos, diagramas e atualizações.

## Principais Recursos
- Rotas públicas para listar, buscar e detalhar livros processados (`/api/v1/books`, `/api/v1/categories`, etc.).
- Rotas privadas com autenticação JWT para estatísticas, pipeline de dados, scrapper e datasets prontos para Machine Learning.
- Pipeline de dados idempotente que limpa, valida e gera artefatos (`processed` e `features`).
- Web scraping resiliente com `requests` + `BeautifulSoup` para manter o dataset atualizado.
- Suporte opcional a PostgreSQL para armazenar usuários e tokens, com fallback em memória para desenvolvimento.
- Scripts de automação (`devops/`, `src/scripts/`) e testes unitários/smoke com `pytest`.

## Arquitetura em Alto Nível
```
src/
├─ app.py                 # Configura FastAPI e registra routers
├─ routes/                # Endpoints públicos e privados
├─ domain/                # Serviços de negócio e repositórios (auth, user)
├─ scripts/               # Pipelines, scrapper e utilitários de ML
├─ data/                  # Artefatos raw, processed e features
├─ docs/                  # Diagramas (HTML) servidos pelas rotas privadas
└─ templates/             # Landing page pública
```

Fluxo de dados resumido:
```
Scrapper → src/data/raw/all_books_with_images.csv
Pipeline (limpeza + features) → processed/books_processed.csv → features/books_features.csv
Rotas → servem os CSVs com cache e conversões em tempo real
```

## Preparando o Ambiente (sem Docker)
1. Crie e ative um ambiente virtual:
  ```bash
  python -m venv .venv
  # Linux/macOS
  source .venv/bin/activate
  # Windows PowerShell
  .\.venv\Scripts\Activate.ps1
  ```
2. Instale as dependências:
  ```bash
  pip install -r requirements.txt
  ```
3. Crie o arquivo `.env` na raiz:
  ```ini
  JWT_SECRET=secret_here
  USE_DATABASE=False
  ```
4. Inicie o servidor:
  - Linux/macOS: `./devops/start_local.sh`
  - Windows PowerShell: `./devops/start_local.ps1`

A API ficará disponível em `http://localhost:4000` com documentação Swagger em `/docs`.

## Executando com Docker Compose
1. Ajuste `.env` com credenciais para os serviços containerizados:
  ```ini
  JWT_SECRET=secret_here
  USE_DATABASE=False
  DB_HOST=postgres
  DB_USER=admin
  DB_PASSWORD=admin
  ```
2. Suba os containers:
  ```bash
  docker compose up --build
  ```
3. Serviços expostos:
  - API: `http://localhost:4000`
  - PostgreSQL: `localhost:5432`
  - pgAdmin4: `http://localhost:5050` (`admin@admin.com` / `admin`)

Para popular usuário e tokens no banco, rode os scripts `init/01-schema.sql` e `init/02-seed.sql` dentro do container do Postgres.

## Variáveis de Ambiente
| Nome | Obrigatório | Padrão | Descrição |
|------|-------------|--------|-----------|
| `JWT_SECRET` | Sim | — | Chave usada para assinar e validar JWT. |
| `USE_DATABASE` | Não | `False` | Quando `True`, usa o PostgreSQL em vez de repositórios memória. |
| `BOOKS_CSV_PATH` | Não | `src/data/raw/all_books_with_images.csv` | Fonte bruta usada pelo health-check. |
| `BOOKS_PROCESSED_PATH` | Não | `src/data/processed/books_processed.csv` | Dataset servido pelas rotas públicas. |
| `BOOK_SCRAPER_OUTPUT` | Não | `src/data/raw` | Diretório de saída do scrapper. |
| `GIT_HASH` | Não | `unknown-version` | Hash exibido em `/api/v1/version`. |
| `DB_HOST` | Quando `USE_DATABASE=True` | — | Host do PostgreSQL. |
| `DB_PORT` | Não | `5432` | Porta do Postgres. |
| `DB_USER` | Quando `USE_DATABASE=True` | — | Usuário do Postgres. |
| `DB_PASSWORD` | Quando `USE_DATABASE=True` | — | Senha do Postgres. |
| `DB_NAME` | Não | `book-api` | Nome do banco. |
| `DB_SSLMODE` | Não | `prefer` | Modo SSL para psycopg (health-check). |
| `DB_CONNECT_TIMEOUT` | Não | `3` | Timeout (s) para psycopg. |
| `DB_TCP_TIMEOUT` | Não | `2.5` | Timeout (s) para fallback TCP. |

## Autenticação e Autorização
1. `GET /api/v1/auth/login`: exige `Authorization: Basic` e retorna `accessToken` (curta duração) + `refreshToken`.
2. `GET /api/v1/auth/refresh`: recebe `Authorization: Bearer <refreshToken>` e devolve novo `accessToken`.
3. Rotas privadas (`/api/v1/stats/*`, `/api/v1/ml/*`, `/api/v1/data-process`, etc.) usam `Depends(JWTUtils.validate_token)`, então envie `Authorization: Bearer <accessToken>`.
4. Repositórios reais (`DBAuthRepository`, `DBUserRepository`) são ativados com `USE_DATABASE=True`; caso contrário, versões in-memory são utilizadas para desenvolvimento rápido.

## Pipelines e Scrapper
- **Scrapper**: `PUT /api/v1/scrapper` (assíncrono) ou `python -c "from src.scripts.scrapper_lib import trigger_scrap; trigger_scrap()"`.
- **Pipeline de processamento**: `PUT /api/v1/data-process` ou `python -m src.scripts.data_processing_pipeline`.
- Artefatos gerados: `src/data/raw/`, `src/data/processed/`, `src/data/features/`.
- As rotas invalidam caches automaticamente ao detectar mudanças nos arquivos.

## Testes
```
pytest
```
- `tests/unit_tests/`: valida pipelines, estatísticas e contratos das rotas.
- `tests/smoke_tests/`: verificação rápida pós-deploy.

## Estrutura de Pastas (resumo)
```
devops/            Scripts de bootstrap para Linux/Windows
init/              DDL e seed do PostgreSQL
notebooks/         Análises exploratórias e recomendações
src/               Código da API, domínio e pipelines
tests/             Suite de testes unitários e smoke
wiki/              Conteúdo pronto para a aba Wiki do GitHub
```

## Próximos Passos
- Consulte a Wiki para diagramas, exemplos detalhados de requisições e checklists de operação.
- Ajuste variáveis de observabilidade (`OTEL_*`) caso deseje instrumentar a aplicação.
