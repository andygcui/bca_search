# BCA Retrieval and Intelligence Agent

A local retrieval, indexing, and benchmarking system for transportation **Benefit-Cost Analysis (BCA)** documents.

This is **not** a chatbot and **not** a BCA generator. It searches public sources, downloads candidate documents, classifies them, extracts metadata, and packages results for download.

## Features

- **Three search modes**: general web search, targeted website crawl, direct URL list
- **Multi-format support**: PDF, DOCX, XLSX/XLSM, HTML
- **Rule-based BCA classifier** with optional LLM enhancement (OpenAI / Anthropic)
- **Metadata extraction**: BCR, NPV, discount rate, grant program, project type, and more
- **SQLite index** for run history and document tracking
- **Exports**: CSV, Excel, and ZIP packages with documents, text, and metadata
- **Deduplication** by URL hash and file content hash

## Project Structure

```
bca_retrieval_agent/
├── app.py                  # Streamlit UI
├── config.py               # Configuration and constants
├── agents/                 # Orchestration agents
├── core/                   # Core processing modules
├── schemas/                # Pydantic data models
├── prompts/                # LLM prompt templates
├── data/                   # Downloads, extracted text, database
├── outputs/                # CSV, Excel, ZIP exports
└── logs/                   # Run logs
```

## Setup

### 1. Create a virtual environment

```bash
cd bca_retrieval_agent
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment (optional)

```bash
cp .env.example .env
```

Edit `.env` to add API keys if available. **The app works without any API keys** using direct URL mode and rule-based processing.

| Variable | Purpose | Required |
|----------|---------|----------|
| `SERPAPI_KEY` | Google search via SerpAPI | No |
| `BING_SEARCH_API_KEY` | Bing Web Search API | No |
| `OPENAI_API_KEY` | LLM classification & metadata | No |
| `ANTHROPIC_API_KEY` | LLM classification & metadata | No |

### 4. Run the app

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## Search Modes

### Direct URL List (recommended for MVP)

Paste one or more URLs (one per line) and click **Run Search**. The system downloads, extracts text, and processes each document.

```
https://www.transportation.gov/sites/dot.gov/files/2021-06/Example_BCA.pdf
```

### General Web Search

Enter a natural language query such as:

- `Find bridge replacement BCAs`
- `Find RAISE grant BCAs in Maryland`
- `Find CRISI rail BCAs`

Search provider priority: **SerpAPI → Bing → DuckDuckGo HTML fallback**.

### Targeted Website Crawl

Provide a domain or starting URL (e.g. `transportation.gov`). The crawler follows BCA-related links within that domain, respecting `robots.txt` and rate limits.

## Workflow

1. **Run Search** — Discover and download candidate documents
2. **Classify Documents** — Score each document as Definite BCA, Likely BCA, etc.
3. **Extract Metadata** — Pull structured fields (BCR, NPV, grant program, etc.)
4. **Export Results** — Generate CSV and Excel indexes
5. **Download ZIP** — Package documents, text, metadata, and run log

## Classification Categories

| Category | Description |
|----------|-------------|
| Definite BCA | Formal BCA technical memorandum or report |
| Likely BCA | Strong BCA indicators, incomplete analysis |
| Related grant document | Grant application referencing BCA |
| Not a BCA | Environmental, cost estimate, unrelated |
| Workbook / calculation file | Spreadsheet with BCA calculations |
| Unknown | Insufficient information |

## Limitations

- Not every grant application document is a BCA — the classifier distinguishes memos, workbooks, narratives, and unrelated files
- Web search without API keys relies on DuckDuckGo HTML parsing, which may be rate-limited
- Metadata extraction uses regex/rules first; LLM improves accuracy when API keys are configured
- Crawling respects `robots.txt` but cannot access login-protected or paywalled content
- Large PDFs and workbooks may have truncated text extraction for performance

## Future Roadmap

- RAG over collected BCAs with semantic search
- Vector database integration
- Benchmarking dashboards (BCR distributions, benefit category comparison)
- Automatic formula extraction from workbooks
- Cross-grant-program comparison tools
- Citation-backed answer generation
- Scheduled crawling of DOT websites

## License

MIT
