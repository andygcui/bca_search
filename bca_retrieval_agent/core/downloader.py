"""Document downloader with deduplication."""

import hashlib
import logging
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from config import DOWNLOADS_DIR, RATE_LIMIT_DELAY, REQUEST_TIMEOUT, USER_AGENT
from core.database import Database
from schemas.document_schema import DocumentRecord, DownloadError

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16]


def file_hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_filename(title: str, max_len: int = 80) -> str:
    safe = re.sub(r"[^\w\s\-_.]", "", title)
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe[:max_len] or "document"


def detect_extension(url: str, content_type: str = "") -> str:
    path = urlparse(url).path.lower()
    for ext in (".pdf", ".docx", ".xlsx", ".xlsm", ".html", ".htm"):
        if path.endswith(ext):
            return ext.lstrip(".")
    ct_map = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/html": "html",
    }
    for mime, ext in ct_map.items():
        if mime in content_type.lower():
            return ext
    return "bin"


class DocumentDownloader:
    """Download documents with deduplication and error handling."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def download(
        self,
        url: str,
        run_id: str,
        title: Optional[str] = None,
    ) -> tuple[Optional[DocumentRecord], Optional[DownloadError]]:
        """Download a single URL. Returns (document, error)."""
        normalized = normalize_url(url)
        u_hash = url_hash(normalized)

        if self.db.document_exists_by_url_hash(u_hash):
            logger.info("Skipping duplicate URL: %s", url)
            return None, None

        run_dir = DOWNLOADS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        try:
            resp = self.session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
                stream=True,
            )
            if resp.status_code == 403:
                err = DownloadError(
                    run_id=run_id,
                    url=url,
                    error_message="403 Forbidden",
                    error_type="forbidden",
                )
                self.db.save_download_error(err)
                return None, err
            resp.raise_for_status()
            content = resp.content
        except requests.Timeout:
            err = DownloadError(
                run_id=run_id, url=url, error_message="Request timeout", error_type="timeout"
            )
            self.db.save_download_error(err)
            return None, err
        except Exception as exc:
            err = DownloadError(
                run_id=run_id, url=url, error_message=str(exc), error_type="download_failed"
            )
            self.db.save_download_error(err)
            return None, err

        f_hash = file_hash_content(content)
        if self.db.document_exists_by_hash(f_hash):
            logger.info("Skipping duplicate file hash: %s", url)
            return None, None

        ext = detect_extension(url, resp.headers.get("Content-Type", ""))
        doc_title = title or urlparse(url).path.split("/")[-1] or "document"
        fname = f"{run_id}_{safe_filename(doc_title)}_{u_hash[:8]}.{ext}"
        local_path = run_dir / fname
        local_path.write_bytes(content)

        doc = DocumentRecord(
            document_id=str(uuid.uuid4()),
            run_id=run_id,
            source_url=url,
            local_path=str(local_path),
            file_type=ext,
            file_hash=f_hash,
            url_hash=u_hash,
            title=doc_title,
            file_size=len(content),
            download_status="success",
        )
        self.db.save_document(doc)

        import time

        time.sleep(RATE_LIMIT_DELAY)
        return doc, None

    def download_batch(
        self,
        urls: list[tuple[str, Optional[str]]],
        run_id: str,
    ) -> tuple[list[DocumentRecord], list[DownloadError]]:
        """Download multiple URLs. Each item is (url, optional_title)."""
        documents = []
        errors = []
        for url, title in urls:
            doc, err = self.download(url, run_id, title)
            if doc:
                documents.append(doc)
            if err:
                errors.append(err)
        return documents, errors
