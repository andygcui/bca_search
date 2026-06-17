"""Web search functionality with multiple provider fallbacks."""

import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    BING_SEARCH_API_KEY,
    RATE_LIMIT_DELAY,
    SERPAPI_KEY,
    USER_AGENT,
)
from schemas.search_result_schema import SearchResult, SearchResults

logger = logging.getLogger(__name__)


def _build_search_query(
    query: str,
    grant_program: Optional[str] = None,
    project_type: Optional[str] = None,
    state: Optional[str] = None,
    file_types: Optional[list[str]] = None,
    target_domain: Optional[str] = None,
) -> str:
    """Augment user query with BCA-specific search terms and filters."""
    parts = [query.strip()]

    if "benefit" not in query.lower() and "bca" not in query.lower():
        parts.append('"benefit cost analysis" OR "benefit-cost analysis" OR BCA')

    if grant_program and grant_program != "Other":
        parts.append(f'"{grant_program}"')

    if project_type:
        parts.append(f'"{project_type}"')

    if state:
        parts.append(f'"{state}"')

    if file_types:
        for ft in file_types:
            if ft.lower() in ("pdf", "docx", "xlsx", "xlsm"):
                parts.append(f"filetype:{ft.lower()}")

    if target_domain:
        domain = target_domain.replace("https://", "").replace("http://", "").strip("/")
        parts.append(f"site:{domain}")

    return " ".join(parts)


def search_serpapi(query: str, max_results: int = 20) -> SearchResults:
    """Search using SerpAPI."""
    results = SearchResults(query=query, mode="serpapi")
    if not SERPAPI_KEY:
        results.errors.append("SERPAPI_KEY not configured")
        return results

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": SERPAPI_KEY,
                "engine": "google",
                "num": min(max_results, 100),
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("organic_results", [])[:max_results]:
            results.results.append(
                SearchResult(
                    url=item.get("link", ""),
                    title=item.get("title"),
                    snippet=item.get("snippet"),
                    source="serpapi",
                )
            )
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
    """Fallback search using DuckDuckGo HTML results."""
    results = SearchResults(query=query, mode="duckduckgo")
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for result_div in soup.select(".result")[:max_results]:
            link_tag = result_div.select_one("a.result__a")
            snippet_tag = result_div.select_one(".result__snippet")
            if link_tag and link_tag.get("href"):
                url = link_tag["href"]
                if url.startswith("//duckduckgo.com/l/?"):
                    match = re.search(r"uddg=([^&]+)", url)
                    if match:
                        from urllib.parse import unquote

                        url = unquote(match.group(1))
                results.results.append(
                    SearchResult(
                        url=url,
                        title=link_tag.get_text(strip=True),
                        snippet=snippet_tag.get_text(strip=True) if snippet_tag else None,
                        source="duckduckgo",
                    )
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
    full_query = _build_search_query(
        query, grant_program, project_type, state, file_types, target_domain
    )
    logger.info("Searching web: %s", full_query)

    if SERPAPI_KEY:
        results = search_serpapi(full_query, max_results)
        if results.results:
            return results

    if BING_SEARCH_API_KEY:
        results = search_bing(full_query, max_results)
        if results.results:
            return results

    return search_duckduckgo(full_query, max_results)


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
