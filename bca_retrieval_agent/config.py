"""Application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Data directories
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
EXTRACTED_TEXT_DIR = DATA_DIR / "extracted_text"
INDEXES_DIR = DATA_DIR / "indexes"
RUNS_DIR = DATA_DIR / "runs"

OUTPUTS_DIR = BASE_DIR / "outputs"
ZIP_DIR = OUTPUTS_DIR / "zip"
CSV_DIR = OUTPUTS_DIR / "csv"
EXCEL_DIR = OUTPUTS_DIR / "excel"

LOGS_DIR = BASE_DIR / "logs"
PROMPTS_DIR = BASE_DIR / "prompts"
DB_PATH = DATA_DIR / "bca_retrieval.db"

# Search API keys (optional)
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
BING_SEARCH_API_KEY = os.getenv("BING_SEARCH_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# HTTP settings
USER_AGENT = os.getenv(
    "USER_AGENT",
    "BCA-Retrieval-Agent/1.0 (transportation research; +https://github.com/bca-search)",
)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "1.0"))
MAX_CRAWL_DEPTH = int(os.getenv("MAX_CRAWL_DEPTH", "2"))
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "50"))

# File types
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".html", ".htm"}

GRANT_PROGRAMS = ["BUILD", "RAISE", "INFRA", "MEGA", "CRISI", "BIP", "SS4A", "Other"]
PROJECT_TYPES = [
    "Bridge",
    "Highway",
    "Rail",
    "Transit",
    "Freight",
    "Safety",
    "Multimodal",
    "Active Transportation",
]
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
]

CLASSIFICATIONS = [
    "Definite BCA",
    "Likely BCA",
    "Related grant document",
    "Not a BCA",
    "Workbook / calculation file",
    "Unknown",
]

# BCA keyword indicators
STRONG_BCA_INDICATORS = [
    "benefit-cost analysis",
    "benefit cost analysis",
    "bca technical memorandum",
    "benefit-cost ratio",
    "bcr",
    "net present value",
    "npv",
    "present value benefits",
    "present value costs",
    "discount rate",
    "value of travel time",
    "crash modification factor",
    "usdot bca guidance",
]

WORKBOOK_INDICATORS = [
    "bcr",
    "npv",
    "summary",
    "inputs",
    "benefits",
    "costs",
    "discounting",
    "sensitivity",
]

CRAWL_LINK_KEYWORDS = [
    "bca",
    "benefit-cost",
    "benefit cost",
    "benefit_cost",
    "cost-benefit",
    "technical memorandum",
    "grant application",
    "build",
    "raise",
    "infra",
    "crisi",
    "bip",
    "ss4a",
    "application",
    "appendix",
    "workbook",
    "xlsx",
    "pdf",
]


def ensure_directories() -> None:
    """Create all required directories if they do not exist."""
    for directory in (
        DOWNLOADS_DIR,
        EXTRACTED_TEXT_DIR,
        INDEXES_DIR,
        RUNS_DIR,
        ZIP_DIR,
        CSV_DIR,
        EXCEL_DIR,
        LOGS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
