"""Project research agent — one targeted search per document type."""

import logging
import time

from config import RATE_LIMIT_DELAY
from core.project_researcher import (
    extract_doc_links,
    fetch_page_html,
    fetch_wayback_html,
    make_wayback_url,
    query_wayback_snapshots,
)
from core.search import search_web
from schemas.project_schema import FoundDocument, ProjectResearchResult

logger = logging.getLogger(__name__)

_MAX_RESULTS_PER_TYPE = 5   # top results to consider per document type search
_WAYBACK_SNAPSHOTS = 6      # Wayback snapshots to check per best-result page
_HTML_EXTENSIONS = {"htm", "html", "aspx", "php", "jsp", "cfm"}
_DOC_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xlsm", "ppt", "pptx"}

# One targeted query per document type. Each query is combined with the project
# name + location at runtime to produce the full search string.
# Single keyword per type — no OR. Google relaxes OR queries when there are no
# exact matches, which produces garbage results (e.g. "SR" → the movie "Sr.").
# One specific term forces Google to either find something real or return nothing.
_DOC_TYPE_QUERIES: dict[str, str] = {
    "Agency Annual Report":
        '"annual report"',
    "Finding of No Significant Impact":
        'FONSI',
    "Notice of Intent":
        '"notice of intent"',
    "Draft Environmental Impact Statement":
        'DEIS',
    "Final Environmental Impact Statement":
        'FEIS',
    "Supplemental DEIS/FEIS":
        '"supplemental EIS"',
    "Record of Decision":
        '"record of decision"',
    "Delivery Options Evaluation":
        '"delivery options"',
    "Benefit-Cost Analysis Report":
        '"benefit-cost analysis"',
    "Initial Financial Plan":
        '"initial financial plan"',
    "Cost Estimate Review":
        '"cost estimate review"',
    "Traffic Revenue Study or Toll Study":
        '"traffic revenue study"',
    "Civil Rights Compliance Review Report":
        '"civil rights" "Title VI"',
    "Request for Information":
        '"request for information"',
    "Request for Qualifications":
        '"request for qualifications"',
    "Request for Proposals":
        '"request for proposals"',
    "Contract and Comprehensive Agreements":
        '"comprehensive agreement"',
    "Financial Plan Annual Updates":
        '"financial plan update"',
    "Construction Progress Reports":
        '"construction progress"',
    "Proposals Statement of Qualifications":
        '"statement of qualifications"',
    "Project Management Plans":
        '"project management plan"',
    "Risk Assessment (Register)":
        '"risk assessment"',
    "Financial Feasibility/Viability Report":
        '"financial feasibility"',
    "Project Audit Report":
        '"audit report"',
    "SPV Financial Statements":
        '"special purpose vehicle"',
    "Bond Official Statement":
        '"official statement" bond',
    "Disputes and Legal Actions":
        'litigation',
    "O&M Contract & Report":
        '"operations and maintenance"',
    "Bid Tabulation/Proposal Evaluation":
        '"bid tabulation"',
    "Statement of Interest":
        '"statement of interest"',
    "Value Engineering Study":
        '"value engineering"',
    "Unsolicited Proposal":
        '"unsolicited proposal"',
    "Plan & Design Estimation":
        '"design estimate"',
    "Third Party Case Study":
        '"case study"',
}

# Keywords that confirm a result matches its category — used for confidence scoring
_CONFIDENCE_SIGNALS: dict[str, list[str]] = {
    "Agency Annual Report": ["annual report"],
    "Finding of No Significant Impact": ["fonsi", "finding of no significant"],
    "Notice of Intent": ["notice of intent", " noi "],
    "Draft Environmental Impact Statement": ["deis", "draft environmental impact", "draft eis"],
    "Final Environmental Impact Statement": ["feis", "final environmental impact", "final eis"],
    "Supplemental DEIS/FEIS": ["supplemental eis", "supplemental deis", "supplemental feis", "seis"],
    "Record of Decision": ["record of decision", " rod "],
    "Delivery Options Evaluation": ["delivery option", "p3", "public-private"],
    "Benefit-Cost Analysis Report": ["benefit cost", "benefit-cost", " bca "],
    "Initial Financial Plan": ["initial financial plan", " ifp "],
    "Cost Estimate Review": ["cost estimate", " ice "],
    "Traffic Revenue Study or Toll Study": ["traffic study", "toll study", "revenue study"],
    "Civil Rights Compliance Review Report": ["civil rights", "title vi"],
    "Request for Information": [" rfi ", "request for information"],
    "Request for Qualifications": [" rfq ", "request for qualifications"],
    "Request for Proposals": [" rfp ", "request for proposals"],
    "Contract and Comprehensive Agreements": ["comprehensive agreement", "design-build contract", "dbfom"],
    "Financial Plan Annual Updates": ["financial plan update", "annual update"],
    "Construction Progress Reports": ["construction progress", "progress report"],
    "Proposals Statement of Qualifications": ["statement of qualifications", " soq "],
    "Project Management Plans": ["project management plan", " pmp "],
    "Risk Assessment (Register)": ["risk assessment", "risk register"],
    "Financial Feasibility/Viability Report": ["financial feasibility", "financial viability"],
    "Project Audit Report": ["project audit", "audit report"],
    "SPV Financial Statements": [" spv ", "special purpose vehicle"],
    "Bond Official Statement": ["official statement", "revenue bond", "bond offering"],
    "Disputes and Legal Actions": ["dispute", "litigation", "legal action"],
    "O&M Contract & Report": ["o&m", "operations and maintenance"],
    "Bid Tabulation/Proposal Evaluation": ["bid tabulation", "bid tab", "proposal evaluation"],
    "Statement of Interest": ["statement of interest", " soi "],
    "Value Engineering Study": ["value engineering", "ve study"],
    "Unsolicited Proposal": ["unsolicited proposal"],
    "Plan & Design Estimation": ["design estimate", "plan and profile", "% design"],
    "Third Party Case Study": ["case study", "independent review", "third party"],
}


def _score_confidence(doc_type: str, url: str, title: str, snippet: str) -> str:
    """Return 'high', 'medium', or 'low' based on keyword presence."""
    signals = _CONFIDENCE_SIGNALS.get(doc_type, [])
    combined = " " + (url + " " + title + " " + snippet).lower() + " "
    if any(sig in combined for sig in signals):
        return "high"
    # Fell back to medium — search was targeted so result is plausibly relevant
    return "medium"


class ProjectResearchAgent:
    """Runs one targeted search per document type and returns confident matches."""

    def research(
        self,
        project_name: str,
        location: str = "",
        sponsor: str = "",
    ) -> ProjectResearchResult:
        logger.info("Starting project research for: %s", project_name)

        # Project name quoted so it's always required; type keywords wrapped in parens
        # so OR alternatives don't escape the project name constraint.
        base = f'"{project_name}"'

        found_documents: list[FoundDocument] = []
        sources_searched: set[str] = set()
        seen_doc_urls: set[str] = set()

        for doc_type, type_query in _DOC_TYPE_QUERIES.items():
            query = f"{base} {type_query}"
            logger.info("Searching for [%s]: %s", doc_type, query)

            try:
                sr = search_web(query=query, max_results=_MAX_RESULTS_PER_TYPE, raw=True)
                for r in sr.results:
                    sources_searched.add(r.url)
                    if r.url in seen_doc_urls:
                        continue
                    confidence = _score_confidence(
                        doc_type, r.url, r.title or "", r.snippet or ""
                    )
                    if confidence in ("high", "medium"):
                        seen_doc_urls.add(r.url)
                        found_documents.append(FoundDocument(
                            url=r.url,
                            title=r.title or "",
                            doc_type=doc_type,
                            confidence=confidence,
                            source="live",
                            snippet=r.snippet or "",
                        ))
                time.sleep(RATE_LIMIT_DELAY)
            except Exception as exc:
                logger.warning("Search failed for [%s]: %s", doc_type, exc)

        logger.info("Live search complete: %d documents across %d categories",
                    len(found_documents),
                    len({d.doc_type for d in found_documents}))

        # ------------------------------------------------------------------
        # Phase 2: Wayback Machine — for each category, take the best HTML
        # result and look for historically linked documents that no longer
        # appear on the current live page.
        # ------------------------------------------------------------------
        best_html_by_type: dict[str, FoundDocument] = {}
        for doc in found_documents:
            url = doc.url
            ext = url.lower().split("?")[0].rsplit(".", 1)[-1] if "." in url else ""
            if ext in _DOC_EXTENSIONS:
                continue  # PDFs/docs don't link to other files usefully
            existing = best_html_by_type.get(doc.doc_type)
            if existing is None or (doc.confidence == "high" and existing.confidence != "high"):
                best_html_by_type[doc.doc_type] = doc

        snapshots_checked = 0
        for doc_type, best_doc in best_html_by_type.items():
            url = best_doc.url
            logger.info("Wayback check [%s]: %s", doc_type, url)

            # Grab links on the current live page
            current_html = fetch_page_html(url)
            current_links: set[str] = set()
            if current_html:
                current_links = {d["url"] for d in extract_doc_links(current_html, url)}

            snapshots = query_wayback_snapshots(url, max_samples=_WAYBACK_SNAPSHOTS)
            for snap in snapshots:
                snapshots_checked += 1
                ts = snap["timestamp"]
                snap_html = fetch_wayback_html(url, ts)
                if not snap_html:
                    continue
                wayback_url = make_wayback_url(url, ts)
                for linked in extract_doc_links(snap_html, url):
                    linked_url = linked["url"]
                    if linked_url in seen_doc_urls or linked_url in current_links:
                        continue
                    seen_doc_urls.add(linked_url)
                    title = linked.get("title", "")
                    confidence = _score_confidence(doc_type, linked_url, title, "")
                    found_documents.append(FoundDocument(
                        url=linked_url,
                        title=title,
                        doc_type=doc_type,
                        confidence=confidence,
                        source="archive",
                        archive_timestamp=ts,
                        wayback_url=wayback_url,
                        snippet="",
                    ))

        logger.info("Wayback complete: checked %d snapshots, total docs now %d",
                    snapshots_checked, len(found_documents))

        return ProjectResearchResult(
            project_name=project_name,
            found_documents=found_documents,
            sources_searched=list(sources_searched),
            archive_snapshots_checked=snapshots_checked,
            llm_verified=False,
        )
