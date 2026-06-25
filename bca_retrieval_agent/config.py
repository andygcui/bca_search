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

PROJECT_DOCUMENT_TYPES = [
    "Agency Annual Report",
    "Finding of No Significant Impact",
    "Notice of Intent",
    "Draft Environmental Impact Statement",
    "Final Environmental Impact Statement",
    "Supplemental DEIS/FEIS",
    "Record of Decision",
    "Delivery Options Evaluation",
    "Benefit-Cost Analysis Report",
    "Initial Financial Plan",
    "Cost Estimate Review",
    "Traffic Revenue Study or Toll Study",
    "Civil Rights Compliance Review Report",
    "Request for Information",
    "Request for Qualifications",
    "Request for Proposals",
    "Contract and Comprehensive Agreements",
    "Financial Plan Annual Updates",
    "Construction Progress Reports",
    "Proposals Statement of Qualifications",
    "Project Management Plans",
    "Risk Assessment (Register)",
    "Financial Feasibility/Viability Report",
    "Project Audit Report",
    "SPV Financial Statements",
    "Bond Official Statement",
    "Disputes and Legal Actions",
    "O&M Contract & Report",
    "Bid Tabulation/Proposal Evaluation",
    "Statement of Interest",
    "Value Engineering Study",
    "Unsolicited Proposal",
    "Plan & Design Estimation",
    "Third Party Case Study",
    "Other",
]

# Targeted search queries per grant program for finding applicant-published BCAs.
# Run through search_web() (SerpAPI → Bing → DuckDuckGo).
GRANT_SEARCH_QUERIES: dict[str, list[str]] = {
    "RAISE": [
        '"RAISE grant" "benefit cost analysis" filetype:pdf',
        '"RAISE" "benefit-cost analysis" "technical memorandum" filetype:pdf',
        '"RAISE grant" "benefit-cost ratio" filetype:pdf',
    ],
    "BUILD": [
        '"BUILD grant" "benefit cost analysis" filetype:pdf',
        '"BUILD" "benefit-cost analysis" "technical memorandum" filetype:pdf',
        '"BUILD grant" "benefit-cost ratio" filetype:pdf',
    ],
    "CRISI": [
        '"CRISI" "benefit cost analysis" filetype:pdf',
        '"CRISI grant" "benefit-cost analysis" rail filetype:pdf',
        '"consolidated rail infrastructure" "benefit cost analysis" filetype:pdf',
    ],
    "BIP": [
        '"bridge investment program" "benefit cost analysis" filetype:pdf',
        '"BIP" "benefit-cost analysis" bridge filetype:pdf',
        '"bridge investment program" "benefit-cost ratio" filetype:pdf',
    ],
    "SS4A": [
        '"SS4A" "benefit cost analysis" filetype:pdf',
        '"safe streets" "benefit-cost analysis" filetype:pdf',
        '"SS4A grant" "benefit-cost ratio" filetype:pdf',
    ],
    "INFRA": [
        '"INFRA grant" "benefit cost analysis" filetype:pdf',
        '"INFRA" "benefit-cost analysis" "technical memorandum" filetype:pdf',
    ],
    "MEGA": [
        '"MEGA grant" "benefit cost analysis" filetype:pdf',
        '"MEGA" "benefit-cost analysis" "technical memorandum" filetype:pdf',
    ],
}

# Alias so app.py can enumerate seedable programs without duplication
GRANT_SEED_SOURCES: dict[str, list] = {k: [] for k in GRANT_SEARCH_QUERIES}
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
