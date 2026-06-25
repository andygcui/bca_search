"""Project research agent — searches, fetches, and synthesizes project data."""

import logging
import time
from urllib.parse import urlparse

from config import ANTHROPIC_API_KEY, OPENAI_API_KEY, RATE_LIMIT_DELAY
from core.project_researcher import (
    build_project_queries,
    fetch_page_text,
    search_archive_org,
    synthesize_with_llm,
)
from core.search import search_web
from schemas.project_schema import ProjectResearchResult, SourcedField

logger = logging.getLogger(__name__)

_GOV_DOMAINS = {".gov", ".dot.gov", ".fhwa.dot.gov", ".transportation.gov"}
_MAX_PAGE_FETCHES = 5


def _is_gov_url(url: str) -> bool:
    return ".gov" in urlparse(url).netloc


class ProjectResearchAgent:
    """Orchestrates web research for an infrastructure project."""

    def research(
        self,
        project_name: str,
        location: str = "",
        sponsor: str = "",
    ) -> ProjectResearchResult:
        logger.info("Starting project research for: %s", project_name)

        # 1. Build and run targeted search queries
        queries = build_project_queries(project_name, location, sponsor)
        all_results: list[dict] = []
        seen_urls: set[str] = set()

        for query in queries:
            try:
                sr = search_web(query=query, max_results=10)
                for r in sr.results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_results.append({
                            "url": r.url,
                            "title": r.title or "",
                            "snippet": r.snippet or "",
                        })
                time.sleep(RATE_LIMIT_DELAY)
            except Exception as exc:
                logger.warning("Search failed for query %r: %s", query, exc)

        logger.info("Found %d unique URLs across all queries", len(all_results))

        # 2. Fetch full page text for top results, prioritising .gov domains
        sorted_results = sorted(all_results, key=lambda r: (0 if _is_gov_url(r["url"]) else 1))
        page_texts: dict[str, str] = {}
        fetched = 0
        for r in sorted_results:
            if fetched >= _MAX_PAGE_FETCHES:
                break
            text = fetch_page_text(r["url"])
            if text:
                page_texts[r["url"]] = text
                fetched += 1
            time.sleep(RATE_LIMIT_DELAY)

        # 3. Search archive.org
        archive_results = search_archive_org(project_name)
        logger.info("Archive.org returned %d results", len(archive_results))

        # 4. LLM synthesis
        result: ProjectResearchResult
        has_llm = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)

        if has_llm:
            llm_result = synthesize_with_llm(project_name, all_results, page_texts, archive_results)
            if llm_result:
                result = llm_result
            else:
                result = ProjectResearchResult(project_name=project_name)
        else:
            result = ProjectResearchResult(project_name=project_name)

        result.sources_searched = list(seen_urls)
        result.archive_sources = [r["url"] for r in archive_results]
        return result
