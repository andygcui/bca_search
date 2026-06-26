"""Web research and document discovery for infrastructure projects."""

import json
import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from config import (
    ANTHROPIC_API_KEY,
    OPENAI_API_KEY,
    PROJECT_DOCUMENT_TYPES,
    PROMPTS_DIR,
    RATE_LIMIT_DELAY,
    USER_AGENT,
)
from schemas.project_schema import FoundDocument

logger = logging.getLogger(__name__)

CDX_API = "https://web.archive.org/cdx/search/cdx"
CDX_TIMEOUT = (10, 45)   # (connect_sec, read_sec) — CDX can be slow to stream large results
CDX_USER_AGENT = "Mozilla/5.0 (compatible; infrastructure-research-bot/1.0)"
DOC_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xlsm", "ppt", "pptx"}
_STOP_WORDS = {"the", "of", "and", "for", "in", "to", "a", "an", "at", "on", "by"}

_PROJECT_QUERY_TEMPLATES = [
    # Broad — catches anything indexed
    '"{name}"',
    # NEPA / environmental review (FONSI, NOI, DEIS, FEIS, Supplemental, ROD)
    '"{name}" "environmental impact" OR "NEPA" OR "FONSI" OR "record of decision" OR "notice of intent"',
    # Benefit-cost & financial planning (BCA, financial plan, cost estimate, traffic/toll study)
    '"{name}" "benefit cost" OR "financial plan" OR "cost estimate" OR "traffic study" OR "toll study"',
    # Procurement & solicitations (RFI, RFQ, RFP, SOQ, statement of interest, unsolicited proposal)
    '"{name}" "request for proposals" OR "request for qualifications" OR "statement of interest" OR "unsolicited proposal"',
    # Contracts, agreements & legal (contracts, O&M, bid tabulation, disputes)
    '"{name}" "contract" OR "agreement" OR "bid tabulation" OR "O&M" OR "disputes"',
    # Project management, risk & design (PM plans, risk assessment, audit, value engineering, design)
    '"{name}" "project management" OR "risk assessment" OR "value engineering" OR "audit"',
    # Financing & delivery (delivery options, financial feasibility, SPV, bond, P3)
    '"{name}" "bond" OR "financial feasibility" OR "public-private" OR "delivery options" OR "SPV"',
    # Progress reports & civil rights (annual report, civil rights, financial plan updates, construction progress)
    '"{name}" "annual report" OR "progress report" OR "civil rights" OR "financial plan update"',
    # Third-party & independent analysis (case study, independent review, research)
    '"{name}" "case study" OR "independent review" OR "third party" OR "research"',
]

_SUBPAGE_KEYWORDS = frozenset({
    "document", "publication", "library", "report", "file", "resource",
    "download", "archive", "plan", "study", "environmental", "procurement",
    "contract", "material", "record", "media", "docs", "project",
})


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def build_project_queries(project_name: str, location: str = "", sponsor: str = "") -> list[str]:
    queries = []
    for template in _PROJECT_QUERY_TEMPLATES:
        q = template.format(name=project_name)
        if location:
            q += f' "{location}"'
        queries.append(q)
    if sponsor:
        # Insert sponsor query at position 1 so it's always high-priority
        queries.insert(1, f'"{project_name}" "{sponsor}"')
    return queries


def _extract_keywords(text: str) -> list[str]:
    words = re.split(r"[\s\-_/]+", text.lower())
    return [w for w in words if w and len(w) > 2 and w not in _STOP_WORDS]


def _url_matches_keywords(url: str, keywords: list[str]) -> bool:
    norm = re.sub(r"[\-_/\.]", " ", url.lower())
    matches = sum(1 for kw in keywords if kw in norm)
    return matches >= max(1, len(keywords) // 3)


# ---------------------------------------------------------------------------
# Live web fetching
# ---------------------------------------------------------------------------

def fetch_page_html(url: str, timeout: int = 15) -> str:
    """Fetch raw HTML from a live URL."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return ""
        return resp.text
    except Exception as exc:
        logger.debug("HTML fetch failed %s: %s", url, exc)
        return ""


def fetch_page_text(url: str, max_chars: int = 4000) -> str:
    html = fetch_page_html(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:max_chars]


def extract_doc_links(html: str, base_url: str) -> list[dict]:
    """Extract links to document files (PDFs, Office docs) from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    docs: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        full_url = urljoin(base_url, href)
        path = full_url.lower().split("?")[0]
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        if ext not in DOC_EXTENSIONS:
            continue
        if full_url not in seen:
            seen.add(full_url)
            docs.append({"url": full_url, "title": a.get_text(strip=True)[:200] or ""})
    return docs


def extract_subpage_links(html: str, base_url: str, max_subpages: int = 5) -> list[str]:
    """Find links to likely document-listing subpages on the same domain."""
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc
    subpages: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if parsed.netloc != base_netloc or full_url == base_url:
            continue

        path = parsed.path.lower()
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        if ext in DOC_EXTENSIONS:
            continue

        link_text = a.get_text(strip=True).lower()
        combined = re.sub(r"[\-_/]", " ", path) + " " + link_text

        if any(kw in combined for kw in _SUBPAGE_KEYWORDS):
            if full_url not in seen:
                seen.add(full_url)
                subpages.append(full_url)
                if len(subpages) >= max_subpages:
                    break

    return subpages


# ---------------------------------------------------------------------------
# Wayback Machine (archive.org) helpers
# ---------------------------------------------------------------------------

def _cdx_url(url: str) -> str:
    """Strip scheme so CDX API receives a scheme-agnostic URL (it normalises internally)."""
    return re.sub(r"^https?://", "", url)


def query_wayback_snapshots(url: str, max_samples: int = 8) -> list[dict]:
    """Return a time-sampled list of Wayback snapshots for a specific page URL."""
    try:
        resp = requests.get(
            CDX_API,
            params={
                "url": _cdx_url(url),
                "output": "json",
                "fl": "timestamp,original,statuscode",
                "limit": 20,
            },
            timeout=CDX_TIMEOUT,
            headers={"User-Agent": CDX_USER_AGENT},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows or len(rows) < 2:
            return []
        header = rows[0]
        data = [
            dict(zip(header, row))
            for row in rows[1:]
            if row[header.index("statuscode")] == "200"
        ]
        if not data:
            return []
        if len(data) <= max_samples:
            return data
        step = max(1, len(data) // max_samples)
        return data[::step][:max_samples]
    except Exception as exc:
        logger.warning("CDX snapshot query failed for %s: %s", url, exc)
        return []


def query_wayback_path_pdfs(page_url: str, keywords: list[str], max_results: int = 50) -> list[dict]:
    """Find PDFs ever archived under the same URL path prefix as a known project page.

    E.g. if page_url is 'https://mdot.maryland.gov/OPPEN/Pages/i270.aspx',
    this searches CDX for all PDFs under 'mdot.maryland.gov/OPPEN*'.
    """
    parsed = urlparse(page_url)
    # Use at least 2 path segments as the prefix (enough to be project-specific)
    parts = [p for p in parsed.path.split("/") if p]
    prefix_parts = parts[:2] if len(parts) >= 2 else parts[:1] if parts else []
    if not prefix_parts:
        return []
    prefix_path = "/" + "/".join(prefix_parts)
    search_url = f"{parsed.netloc}{prefix_path}*"

    try:
        # Build the URL manually so the * wildcard isn't percent-encoded
        query_string = (
            f"url={search_url}&output=json&fl=timestamp,original,statuscode"
            f"&collapse=original&limit={max_results}"
        )
        resp = requests.get(
            f"{CDX_API}?{query_string}",
            timeout=CDX_TIMEOUT,
            headers={"User-Agent": CDX_USER_AGENT},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows or len(rows) < 2:
            return []
        header = rows[0]
        orig_idx = header.index("original")
        status_idx = header.index("statuscode")
        matched = []
        for row in rows[1:]:
            if row[status_idx] != "200":
                continue
            original = row[orig_idx]
            if not original.lower().split("?")[0].endswith(".pdf"):
                continue
            if _url_matches_keywords(original, keywords):
                d = dict(zip(header, row))
                matched.append(d)
        return matched
    except Exception as exc:
        logger.warning("CDX path PDF query failed for %s: %s", search_url, exc)
        return []


def fetch_wayback_html(original_url: str, timestamp: str) -> str:
    """Fetch a specific Wayback Machine snapshot as raw HTML."""
    wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
    try:
        resp = requests.get(
            wayback_url,
            timeout=CDX_TIMEOUT,
            headers={"User-Agent": CDX_USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return ""
        return resp.text
    except Exception as exc:
        logger.debug("Wayback fetch failed %s@%s: %s", original_url, timestamp, exc)
        return ""


def make_wayback_url(original_url: str, timestamp: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{original_url}"


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------

def classify_documents_with_llm(
    project_name: str,
    candidates: list[dict],
    batch_size: int = 40,
) -> list[FoundDocument]:
    """Batch-classify candidate documents into PROJECT_DOCUMENT_TYPES using LLM."""
    if not candidates:
        return []

    doc_type_list = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(PROJECT_DOCUMENT_TYPES))
    prompt_template = (PROMPTS_DIR / "doc_classification_prompt.txt").read_text(encoding="utf-8")

    all_found: list[FoundDocument] = []

    for batch_start in range(0, len(candidates), batch_size):
        batch = candidates[batch_start: batch_start + batch_size]
        doc_lines = []
        for i, doc in enumerate(batch, 1):
            snippet = doc.get("snippet", "")
            snippet_part = f' | Snippet: "{snippet[:300]}"' if snippet else ""
            doc_lines.append(f'[{i}] URL: {doc["url"]} | Title: "{doc.get("title", "")}"' + snippet_part)

        prompt = (
            prompt_template
            .replace("{project_name}", project_name)
            .replace("{doc_type_list}", doc_type_list)
            .replace("{documents}", "\n".join(doc_lines))
        )

        cls_map: dict[int, dict] = {}
        try:
            raw = _call_llm(prompt)
            if raw:
                cls_map = {c["index"]: c for c in _parse_json_array(raw)}
        except Exception as exc:
            logger.error("LLM classification failed (batch starting %d): %s", batch_start, exc)

        for i, doc in enumerate(batch, 1):
            cls = cls_map.get(i, {})
            doc_type = cls.get("doc_type", "Other")
            if doc_type not in PROJECT_DOCUMENT_TYPES:
                doc_type = "Other"
            all_found.append(FoundDocument(
                url=doc["url"],
                title=doc.get("title", ""),
                doc_type=doc_type,
                confidence=cls.get("confidence", "low"),
                source=doc.get("source", "live"),
                archive_timestamp=doc.get("archive_timestamp"),
                wayback_url=doc.get("wayback_url"),
                snippet=doc.get("snippet", ""),
            ))

        time.sleep(RATE_LIMIT_DELAY)

    return all_found


def _call_llm(prompt: str) -> Optional[str]:
    if ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    if OPENAI_API_KEY:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return response.choices[0].message.content

    return None


def _parse_json_array(text: str) -> list:
    text = text.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    if not text.startswith("["):
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            text = m.group(0)
    return json.loads(text)
