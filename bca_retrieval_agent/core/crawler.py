"""Targeted website crawler for BCA-related documents."""

import logging
import re
import time
from collections import deque
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from config import (
    CRAWL_LINK_KEYWORDS,
    MAX_CRAWL_DEPTH,
    MAX_CRAWL_PAGES,
    RATE_LIMIT_DELAY,
    SUPPORTED_EXTENSIONS,
    USER_AGENT,
)
from schemas.search_result_schema import SearchResult, SearchResults

logger = logging.getLogger(__name__)


class RobotsChecker:
    """Cache robots.txt rules per domain."""

    def __init__(self):
        self._parsers: dict[str, RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._parsers:
            rp = RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                return True
            self._parsers[base] = rp
        return self._parsers[base].can_fetch(USER_AGENT, url)


def _is_same_domain(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    target = domain.replace("https://", "").replace("http://", "").strip("/").lower()
    return parsed.netloc.lower().endswith(target) or target in parsed.netloc.lower()


def _link_matches_keywords(href: str, text: str = "") -> bool:
    combined = f"{href} {text}".lower()
    return any(kw in combined for kw in CRAWL_LINK_KEYWORDS)


def _is_document_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in SUPPORTED_EXTENSIONS)


def crawl_website(
    start_url: str,
    max_depth: int = MAX_CRAWL_DEPTH,
    max_pages: int = MAX_CRAWL_PAGES,
    domain: Optional[str] = None,
) -> SearchResults:
    """
    Crawl a website starting from start_url, looking for BCA-related links
    and downloadable documents.
    """
    if not start_url.startswith("http"):
        start_url = f"https://{start_url}"

    target_domain = domain or urlparse(start_url).netloc
    results = SearchResults(query=start_url, mode="crawl")
    robots = RobotsChecker()

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    while queue and len(visited) < max_pages:
        url, depth = queue.popleft()
        normalized = url.split("#")[0].rstrip("/")
        if normalized in visited:
            continue
        visited.add(normalized)

        if not robots.can_fetch(url):
            logger.info("Robots.txt disallows: %s", url)
            continue

        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            if resp.status_code == 403:
                results.errors.append(f"403 Forbidden: {url}")
                continue
            resp.raise_for_status()
        except Exception as exc:
            results.errors.append(f"Crawl error {url}: {exc}")
            continue

        content_type = resp.headers.get("Content-Type", "").lower()

        if _is_document_url(url) or "application/pdf" in content_type:
            results.results.append(
                SearchResult(url=url, title=urlparse(url).path.split("/")[-1], source="crawl")
            )
            time.sleep(RATE_LIMIT_DELAY)
            continue

        if "text/html" not in content_type and "html" not in content_type:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        if _link_matches_keywords(url, soup.get_text()[:500]):
            results.results.append(
                SearchResult(
                    url=url,
                    title=soup.title.string if soup.title else url,
                    snippet=soup.get_text()[:300],
                    source="crawl",
                )
            )

        if depth >= max_depth:
            continue

        for link in soup.find_all("a", href=True):
            href = link["href"]
            absolute = urljoin(url, href).split("#")[0]
            if not _is_same_domain(absolute, target_domain):
                continue
            link_text = link.get_text(strip=True)
            if _is_document_url(absolute) or _link_matches_keywords(absolute, link_text):
                if absolute not in visited:
                    results.results.append(
                        SearchResult(
                            url=absolute,
                            title=link_text or urlparse(absolute).path.split("/")[-1],
                            source="crawl",
                        )
                    )
            if absolute not in visited and depth + 1 <= max_depth:
                queue.append((absolute, depth + 1))

        time.sleep(RATE_LIMIT_DELAY)

    results.total = len(results.results)
    return results
