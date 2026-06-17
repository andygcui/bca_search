"""Crawler and downloader agent."""

import logging
from typing import Optional

from core.database import Database
from core.downloader import DocumentDownloader
from core.text_extractor import extract_text
from schemas.document_schema import DocumentRecord, DownloadError
from schemas.run_schema import RunLog

logger = logging.getLogger(__name__)


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
        documents, errors = self.downloader.download_batch(urls, run_id)

        for doc in documents:
            try:
                text = extract_text(
                    doc.local_path, doc.file_type, run_id, doc.document_id
                )
                doc.extracted_text_path = str(
                    __import__("config").EXTRACTED_TEXT_DIR / run_id / f"{doc.document_id}.txt"
                )
                self.db.save_document(doc)
            except Exception as exc:
                logger.error("Text extraction failed for %s: %s", doc.document_id, exc)
                if run_log:
                    run_log.errors.append(f"Extraction failed {doc.document_id}: {exc}")

        if run_log:
            run_log.downloads_attempted = len(urls)
            run_log.downloads_successful = len(documents)
            self.db.update_run(run_log)

        return documents, errors
