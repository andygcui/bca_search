"""Web search functionality with multiple provider fallbacks."""

import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests

from config import (
    BING_SEARCH_API_KEY,
    RATE_LIMIT_DELAY,
    SERPAPI_KEY,
    USER_AGENT,
)
from schemas.search_result_schema import SearchResult, SearchResults

logger = logging.getLogger(__name__)


_QUERY_DIRECTIVES = re.compile(
    r"^(find|get|retrieve|search\s+for|show\s+me|list|give\s+me)\s+",
    re.IGNORECASE,
)


_GUIDE_EXCLUSIONS = (
    '-"user guide" -"guidance document" -"how to" -manual -template -toolkit '
    '-handbook -webinar -training -"fact sheet" -factsheet -"nofo" -"notice of funding"'
)


def _build_search_query(
    query: str,
    grant_program: Optional[str] = None,
    project_type: Optional[str] = None,
    state: Optional[str] = None,
    file_types: Optional[list[str]] = None,
    target_domain: Optional[str] = None,
    include_filetype_operators: bool = True,
    exclude_guides: bool = True,
) -> str:
    """Augment user query with BCA-specific search terms and filters."""
    clean = _QUERY_DIRECTIVES.sub("", query.strip())
    parts = [clean]

    if "benefit" not in clean.lower():
        parts.append('"benefit cost analysis" OR "benefit-cost analysis"')

    if grant_program and grant_program != "Other":
        parts.append(f'"{grant_program}"')

    if project_type:
        parts.append(f'"{project_type}"')

    if state:
        parts.append(f'"{state}"')

    # filetype: operators work in SerpAPI/Bing but break DuckDuckGo — caller controls this
    if include_filetype_operators and file_types:
        doc_types = [ft.lower() for ft in file_types if ft.lower() in ("pdf", "docx", "xlsx", "xlsm")]
        if len(doc_types) == 1:
            parts.append(f"filetype:{doc_types[0]}")
        elif doc_types:
            parts.append("(" + " OR ".join(f"filetype:{ft}" for ft in doc_types) + ")")

    if target_domain:
        domain = target_domain.replace("https://", "").replace("http://", "").strip("/")
        parts.append(f"site:{domain}")

    if exclude_guides:
        parts.append(_GUIDE_EXCLUSIONS)

    return " ".join(parts)


def search_serpapi(query: str, max_results: int = 100) -> SearchResults:
    """Search using SerpAPI with pagination to reach max_results."""
    results = SearchResults(query=query, mode="serpapi")
    if not SERPAPI_KEY:
        results.errors.append("SERPAPI_KEY not configured")
        return results

    start = 0
    page_size = 10  # Google returns 10 per page
    try:
        while len(results.results) < max_results:
            resp = requests.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": SERPAPI_KEY,
                    "engine": "google",
                    "num": page_size,
                    "start": start,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            batch = data.get("organic_results", [])
            if not batch:
                break

            for item in batch:
                results.results.append(
                    SearchResult(
                        url=item.get("link", ""),
                        title=item.get("title"),
                        snippet=item.get("snippet"),
                        source="serpapi",
                    )
                )

            if len(batch) < page_size:
                break  # Google has no more results

            start += page_size
            time.sleep(0.5)

        results.total = len(results.results)
    except Exception as exc:
        logger.error("SerpAPI search failed: %s", exc)
        results.errors.append(f"SerpAPI error: {exc}")

    return results


def search_bing(query: str, max_results: int = 20) -> SearchResults:
    """Search using Bing Web Search API."""
    results = SearchResults(query=query, mode="bing")
    if not BING_SEARCH_API_KEY:
        results.errors.append("BING_SEARCH_API_KEY not configured")
        return results

    try:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            headers={"Ocp-Apim-Subscription-Key": BING_SEARCH_API_KEY},
            params={"q": query, "count": min(max_results, 50)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("webPages", {}).get("value", [])[:max_results]:
            results.results.append(
                SearchResult(
                    url=item.get("url", ""),
                    title=item.get("name"),
                    snippet=item.get("snippet"),
                    source="bing",
                )
            )
        results.total = len(results.results)
    except Exception as exc:
        logger.error("Bing search failed: %s", exc)
        results.errors.append(f"Bing error: {exc}")

    return results


def search_duckduckgo(query: str, max_results: int = 20) -> SearchResults:
    """Search using the duckduckgo-search library."""
    results = SearchResults(query=query, mode="duckduckgo")
    try:
        from ddgs import DDGS

        items = DDGS().text(query, max_results=max_results)
        if items:
            for item in items:
                results.results.append(
                    SearchResult(
                        url=item.get("href", ""),
                        title=item.get("title"),
                        snippet=item.get("body"),
                        source="duckduckgo",
                    )
                )
        else:
            results.errors.append(
                f"DuckDuckGo returned 0 results for query: {query!r} — "
                "possible rate limit; wait a moment and try again"
            )
        results.total = len(results.results)
        time.sleep(RATE_LIMIT_DELAY)
    except Exception as exc:
        logger.error("DuckDuckGo search failed: %s", exc)
        results.errors.append(f"DuckDuckGo error: {exc}")

    return results


def search_web(
    query: str,
    max_results: int = 20,
    grant_program: Optional[str] = None,
    project_type: Optional[str] = None,
    state: Optional[str] = None,
    file_types: Optional[list[str]] = None,
    target_domain: Optional[str] = None,
) -> SearchResults:
    """
    Perform web search using available providers in priority order:
    SerpAPI -> Bing -> DuckDuckGo.
    """
    api_query = _build_search_query(
        query, grant_program, project_type, state, file_types, target_domain,
        include_filetype_operators=True,
    )
    ddg_query = _build_search_query(
        query, grant_program, project_type, state, file_types, target_domain,
        include_filetype_operators=False,
    )
    logger.info("Searching web: %s", api_query)

    if SERPAPI_KEY:
        results = search_serpapi(api_query, max_results)
        if results.results:
            results.results = _sort_results(results.results)
            return results

    if BING_SEARCH_API_KEY:
        results = search_bing(api_query, max_results)
        if results.results:
            results.results = _sort_results(results.results)
            return results

    results = search_duckduckgo(ddg_query, max_results)
    results.results = _sort_results(results.results)
    return results


_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm"}


def _is_document_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DOCUMENT_EXTENSIONS)


def _sort_results(results: list[SearchResult]) -> list[SearchResult]:
    """Put direct document URLs first, HTML pages second."""
    return sorted(results, key=lambda r: (0 if _is_document_url(r.url) else 1))


def parse_direct_urls(url_text: str) -> list[SearchResult]:
    """Parse a newline or comma-separated list of URLs."""
    results = []
    for line in re.split(r"[\n,]+", url_text):
        url = line.strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            parsed = urlparse(url)
            results.append(
                SearchResult(
                    url=url,
                    title=parsed.path.split("/")[-1] or url,
                    source="direct_url",
                )
            )
    return results
