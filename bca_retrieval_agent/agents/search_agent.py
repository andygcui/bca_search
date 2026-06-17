"""Search agent orchestration."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from core.crawler import crawl_website
from core.database import Database
from core.search import parse_direct_urls, search_web
from schemas.run_schema import RunConfig, RunLog
from schemas.search_result_schema import SearchResult

logger = logging.getLogger(__name__)


class SearchAgent:
    """Orchestrates search across web, crawl, and direct URL modes."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def run(self, config: RunConfig) -> tuple[str, RunLog, list[SearchResult]]:
        run_id = str(uuid.uuid4())[:8]
        run_log = RunLog(
            run_id=run_id,
            query=config.query,
            target_domain=config.target_domain,
            search_mode=config.search_mode,
            start_time=datetime.utcnow().isoformat(),
            status="running",
        )
        self.db.create_run(run_log, config.model_dump_json())

        results: list[SearchResult] = []
        errors: list[str] = []

        try:
            if config.search_mode == "direct_url":
                if config.direct_urls:
                    results = [
                        SearchResult(url=u, title=u.split("/")[-1], source="direct_url")
                        for u in config.direct_urls
                    ]
                else:
                    results = parse_direct_urls(config.query)

            elif config.search_mode == "targeted_crawl":
                start = config.target_domain or config.query
                crawl_results = crawl_website(
                    start,
                    max_pages=config.max_results,
                )
                results = crawl_results.results
                errors.extend(crawl_results.errors)

            else:
                search_results = search_web(
                    query=config.query,
                    max_results=config.max_results,
                    grant_program=config.grant_program_filter,
                    project_type=config.project_type_filter,
                    state=config.state_filter,
                    file_types=config.file_types,
                    target_domain=config.target_domain,
                )
                results = search_results.results
                errors.extend(search_results.errors)

            run_log.candidate_urls = len(results)
            run_log.errors = errors
            run_log.status = "search_complete"
            run_log.end_time = datetime.utcnow().isoformat()
            self.db.update_run(run_log)

        except Exception as exc:
            logger.error("Search failed: %s", exc)
            run_log.errors.append(str(exc))
            run_log.status = "search_failed"
            run_log.end_time = datetime.utcnow().isoformat()
            self.db.update_run(run_log)

        return run_id, run_log, results
