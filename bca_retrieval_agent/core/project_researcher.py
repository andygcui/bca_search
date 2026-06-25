"""Web research and LLM synthesis for infrastructure projects."""

import json
import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import ANTHROPIC_API_KEY, OPENAI_API_KEY, PROMPTS_DIR, RATE_LIMIT_DELAY, USER_AGENT
from core.search import search_web
from schemas.project_schema import ProjectResearchResult, SourcedField, SourcedURL

logger = logging.getLogger(__name__)

_PROJECT_QUERY_TEMPLATES = [
    '"{name}"',
    '"{name}" cost estimate OR budget OR "total cost"',
    '"{name}" schedule OR "completion date" OR "open to traffic"',
    '"{name}" sponsor OR "lead agency" OR DOT',
    '"{name}" funding federal TIFIA OR BUILD OR RAISE OR INFRA',
    '"{name}" site:fhwa.dot.gov OR site:transportation.gov OR site:dot.gov',
    '"{name}" NEPA OR EIS OR environmental OR "record of decision"',
    '"{name}" news OR update OR groundbreaking OR construction',
]


def build_project_queries(project_name: str, location: str = "", sponsor: str = "") -> list[str]:
    queries = []
    for template in _PROJECT_QUERY_TEMPLATES:
        q = template.format(name=project_name)
        if location:
            q += f' "{location}"'
        queries.append(q)
    if sponsor:
        queries.append(f'"{project_name}" "{sponsor}"')
    return queries


def fetch_page_text(url: str, max_chars: int = 4000) -> str:
    """Lightweight text fetch — no download, no disk write."""
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:max_chars]
    except Exception as exc:
        logger.debug("Page fetch failed %s: %s", url, exc)
        return ""


def search_archive_org(project_name: str) -> list[dict]:
    """Search Internet Archive texts collection for the project."""
    try:
        resp = requests.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": f'"{project_name}"',
                "fl[]": ["identifier", "title", "description", "date", "mediatype"],
                "rows": 10,
                "output": "json",
                "mediatype": "texts",
            },
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        results = []
        for doc in docs:
            identifier = doc.get("identifier", "")
            if not identifier:
                continue
            results.append({
                "url": f"https://archive.org/details/{identifier}",
                "title": doc.get("title", identifier),
                "description": str(doc.get("description", ""))[:300],
                "date": doc.get("date", ""),
            })
        return results
    except Exception as exc:
        logger.warning("Archive.org search failed: %s", exc)
        return []


def _build_search_context(
    project_name: str,
    search_results: list[dict],
    page_texts: dict[str, str],
    archive_results: list[dict],
) -> str:
    """Build a context string for the LLM from all gathered sources."""
    lines = []

    lines.append(f"=== WEB SEARCH RESULTS FOR: {project_name} ===\n")
    for i, r in enumerate(search_results, 1):
        lines.append(f"[Source {i}]")
        lines.append(f"URL: {r['url']}")
        lines.append(f"Title: {r.get('title', '')}")
        if r.get("snippet"):
            lines.append(f"Snippet: {r['snippet']}")
        if r["url"] in page_texts and page_texts[r["url"]]:
            lines.append(f"Page content (excerpt): {page_texts[r['url']]}")
        lines.append("")

    if archive_results:
        lines.append("=== INTERNET ARCHIVE (archive.org) RESULTS ===\n")
        for i, r in enumerate(archive_results, 1):
            lines.append(f"[Archive {i}]")
            lines.append(f"URL: {r['url']}")
            lines.append(f"Title: {r['title']}")
            if r.get("description"):
                lines.append(f"Description: {r['description']}")
            if r.get("date"):
                lines.append(f"Date: {r['date']}")
            lines.append("")

    return "\n".join(lines)


def _parse_llm_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty response")
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
    return json.loads(text)


def _call_llm(prompt: str) -> Optional[str]:
    """Call Anthropic or OpenAI and return the text response."""
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


def _sourced(data: dict) -> SourcedField:
    if not isinstance(data, dict):
        return SourcedField()
    raw_sources = data.get("sources", [])
    sources = []
    for s in raw_sources:
        if isinstance(s, dict):
            sources.append(SourcedURL(url=s.get("url", ""), doc_type=s.get("doc_type")))
        elif isinstance(s, str):
            sources.append(SourcedURL(url=s))
    return SourcedField(
        value=data.get("value"),
        sources=sources,
        confidence=data.get("confidence", "low"),
    )


def synthesize_with_llm(
    project_name: str,
    search_results: list[dict],
    page_texts: dict[str, str],
    archive_results: list[dict],
) -> Optional[ProjectResearchResult]:
    """Use LLM to synthesize search results into a structured ProjectResearchResult."""
    prompt_template = (PROMPTS_DIR / "project_research_prompt.txt").read_text(encoding="utf-8")
    context = _build_search_context(project_name, search_results, page_texts, archive_results)
    prompt = prompt_template.replace("{project_name}", project_name).replace("{search_context}", context)

    try:
        raw = _call_llm(prompt)
        if not raw:
            return None
        data = _parse_llm_json(raw)
    except Exception as exc:
        logger.error("LLM synthesis failed: %s", exc)
        return None

    result = ProjectResearchResult(
        project_name=data.get("project_name", project_name),
        aliases=data.get("aliases", []),
        location=_sourced(data.get("location", {})),
        description=_sourced(data.get("description", {})),
        cost_estimate_current=_sourced(data.get("cost_estimate_current", {})),
        cost_estimate_prior_year=_sourced(data.get("cost_estimate_prior_year", {})),
        schedule_completion_current=_sourced(data.get("schedule_completion_current", {})),
        schedule_completion_baseline=_sourced(data.get("schedule_completion_baseline", {})),
        project_sponsor=_sourced(data.get("project_sponsor", {})),
        federal_funds=_sourced(data.get("federal_funds", {})),
        state_funds=_sourced(data.get("state_funds", {})),
        local_funds=_sourced(data.get("local_funds", {})),
        toll_funds=_sourced(data.get("toll_funds", {})),
        tifia=_sourced(data.get("tifia", {})),
        total_funding=_sourced(data.get("total_funding", {})),
        project_type=_sourced(data.get("project_type", {})),
        total_length=_sourced(data.get("total_length", {})),
        grant_programs=_sourced(data.get("grant_programs", {})),
        environmental_status=_sourced(data.get("environmental_status", {})),
        key_milestones=_sourced(data.get("key_milestones", {})),
        economic_info=_sourced(data.get("economic_info", {})),
        additional_relevant_info=_sourced(data.get("additional_relevant_info", {})),
        inconsistencies=data.get("inconsistencies", []),
        llm_verified=True,
    )
    return result
