"""Crawler and downloader agent."""

import logging
from typing import Optional
from urllib.parse import urlparse

from config import EXTRACTED_TEXT_DIR
from core.crawler import crawl_website
from core.database import Database
from core.downloader import DocumentDownloader
from core.text_extractor import extract_text
from schemas.document_schema import DocumentRecord, DownloadError
from schemas.run_schema import RunLog

logger = logging.getLogger(__name__)

_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm"}


def _is_document_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DOCUMENT_EXTENSIONS)


class CrawlerAgent:
    """Downloads documents and extracts text."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.downloader = DocumentDownloader(self.db)

    def download_and_extract(
        self,
        run_id: str,
        urls: list[tuple[str, Optional[str]]],
        run_log: Optional[RunLog] = None,
    ) -> tuple[list[DocumentRecord], list[DownloadError]]:
        # Split URLs: direct document links vs. HTML pages from search results.
        # For HTML pages, do a shallow crawl to discover linked documents.
        doc_urls: list[tuple[str, Optional[str]]] = []
        seen_urls: set[str] = set()

        for url, title in urls:
            if _is_document_url(url):
                if url not in seen_urls:
                    seen_urls.add(url)
                    doc_urls.append((url, title))
            else:
                logger.info("Crawling HTML page for document links: %s", url)
                try:
                    crawl_results = crawl_website(
                        url,
                        max_depth=1,
                        max_pages=30,
                        domain=urlparse(url).netloc,
                    )
                    for result in crawl_results.results:
                        if _is_document_url(result.url) and result.url not in seen_urls:
                            seen_urls.add(result.url)
                            doc_urls.append((result.url, result.title))
                except Exception as exc:
                    logger.warning("Shallow crawl failed for %s: %s", url, exc)
                    if run_log:
                        run_log.errors.append(f"Crawl failed {url}: {exc}")

        if not doc_urls:
            logger.warning("No document URLs found after discovery step.")

        documents, errors = self.downloader.download_batch(doc_urls, run_id)

        for doc in documents:
            try:
                extract_text(doc.local_path, doc.file_type, run_id, doc.document_id)
                doc.extracted_text_path = str(
                    EXTRACTED_TEXT_DIR / run_id / f"{doc.document_id}.txt"
                )
                self.db.save_document(doc)
            except Exception as exc:
                logger.error("Text extraction failed for %s: %s", doc.document_id, exc)
                if run_log:
                    run_log.errors.append(f"Extraction failed {doc.document_id}: {exc}")

        if run_log:
            run_log.downloads_attempted = len(doc_urls)
            run_log.downloads_successful = len(documents)
            self.db.update_run(run_log)

        return documents, errors
