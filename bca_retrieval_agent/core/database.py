"""SQLite database layer for BCA retrieval runs."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

from config import DB_PATH, ensure_directories
from schemas.document_schema import ClassificationResult, DocumentRecord, DownloadError
from schemas.metadata_schema import DocumentMetadata
from schemas.run_schema import RunLog


class Database:
    """SQLite persistence for runs, documents, metadata, and errors."""

    def __init__(self, db_path: Optional[str] = None):
        ensure_directories()
        self.db_path = str(db_path or DB_PATH)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    query TEXT,
                    target_domain TEXT,
                    search_mode TEXT,
                    config_json TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    candidate_urls INTEGER DEFAULT 0,
                    downloads_attempted INTEGER DEFAULT 0,
                    downloads_successful INTEGER DEFAULT 0,
                    definite_bcas INTEGER DEFAULT 0,
                    likely_bcas INTEGER DEFAULT 0,
                    errors_json TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'running',
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    source_url TEXT,
                    local_path TEXT,
                    file_type TEXT,
                    file_hash TEXT,
                    url_hash TEXT,
                    title TEXT,
                    file_size INTEGER,
                    download_status TEXT,
                    extracted_text_path TEXT,
                    created_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS classification_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT,
                    classification TEXT,
                    confidence REAL,
                    reason TEXT,
                    evidence_terms_json TEXT,
                    method TEXT,
                    created_at TEXT,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id)
                );

                CREATE TABLE IF NOT EXISTS metadata (
                    document_id TEXT PRIMARY KEY,
                    metadata_json TEXT,
                    extraction_method TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id)
                );

                CREATE TABLE IF NOT EXISTS download_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    url TEXT,
                    error_message TEXT,
                    error_type TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_documents_run ON documents(run_id);
                CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);
                CREATE INDEX IF NOT EXISTS idx_documents_url_hash ON documents(url_hash);
            """)

    def create_run(self, run_log: RunLog, config_json: str = "{}") -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runs
                   (run_id, query, target_domain, search_mode, config_json,
                    start_time, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_log.run_id,
                    run_log.query,
                    run_log.target_domain,
                    run_log.search_mode,
                    config_json,
                    run_log.start_time,
                    run_log.status,
                    datetime.utcnow().isoformat(),
                ),
            )

    def update_run(self, run_log: RunLog) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE runs SET
                   end_time=?, candidate_urls=?, downloads_attempted=?,
                   downloads_successful=?, definite_bcas=?, likely_bcas=?,
                   errors_json=?, status=?
                   WHERE run_id=?""",
                (
                    run_log.end_time,
                    run_log.candidate_urls,
                    run_log.downloads_attempted,
                    run_log.downloads_successful,
                    run_log.definite_bcas,
                    run_log.likely_bcas,
                    json.dumps(run_log.errors),
                    run_log.status,
                    run_log.run_id,
                ),
            )

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def save_document(self, doc: DocumentRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO documents
                   (document_id, run_id, source_url, local_path, file_type,
                    file_hash, url_hash, title, file_size, download_status,
                    extracted_text_path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc.document_id,
                    doc.run_id,
                    doc.source_url,
                    doc.local_path,
                    doc.file_type,
                    doc.file_hash,
                    doc.url_hash,
                    doc.title,
                    doc.file_size,
                    doc.download_status,
                    doc.extracted_text_path,
                    doc.created_at.isoformat(),
                ),
            )

    def get_document(self, document_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id=?", (document_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_documents_by_run(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def document_exists_by_hash(self, file_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM documents WHERE file_hash=? LIMIT 1", (file_hash,)
            ).fetchone()
            return row is not None

    def document_exists_by_url_hash(self, url_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM documents WHERE url_hash=? LIMIT 1", (url_hash,)
            ).fetchone()
            return row is not None

    def save_classification(self, result: ClassificationResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO classification_results
                   (document_id, classification, confidence, reason,
                    evidence_terms_json, method, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.document_id,
                    result.classification,
                    result.confidence,
                    result.reason,
                    json.dumps(result.evidence_terms),
                    result.method,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_classification(self, document_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM classification_results
                   WHERE document_id=? ORDER BY id DESC LIMIT 1""",
                (document_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_classifications_by_run(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.*, d.source_url, d.title, d.local_path
                   FROM classification_results c
                   JOIN documents d ON c.document_id = d.document_id
                   WHERE d.run_id=?
                   ORDER BY c.confidence DESC""",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metadata
                   (document_id, metadata_json, extraction_method, created_at, updated_at)
                   VALUES (?, ?, ?, COALESCE(
                       (SELECT created_at FROM metadata WHERE document_id=?), ?
                   ), ?)""",
                (
                    metadata.document_id,
                    json.dumps(metadata.model_dump()),
                    metadata.extraction_method,
                    metadata.document_id,
                    now,
                    now,
                ),
            )

    def get_metadata(self, document_id: str) -> Optional[DocumentMetadata]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM metadata WHERE document_id=?", (document_id,)
            ).fetchone()
            if row:
                return DocumentMetadata(**json.loads(row["metadata_json"]))
            return None

    def get_metadata_by_run(self, run_id: str) -> list[DocumentMetadata]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT m.metadata_json FROM metadata m
                   JOIN documents d ON m.document_id = d.document_id
                   WHERE d.run_id=?""",
                (run_id,),
            ).fetchall()
            return [DocumentMetadata(**json.loads(r["metadata_json"])) for r in rows]

    def save_download_error(self, error: DownloadError) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO download_errors
                   (run_id, url, error_message, error_type, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    error.run_id,
                    error.url,
                    error.error_message,
                    error.error_type,
                    error.timestamp.isoformat(),
                ),
            )

    def get_download_errors(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM download_errors WHERE run_id=? ORDER BY timestamp",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_full_index(self, run_id: str) -> list[dict[str, Any]]:
        """Build a combined index of documents with classification and metadata."""
        docs = self.get_documents_by_run(run_id)
        index = []
        for doc in docs:
            row: dict[str, Any] = {
                "document_id": doc["document_id"],
                "source_url": doc["source_url"],
                "local_path": doc["local_path"],
                "file_type": doc["file_type"],
                "title": doc["title"],
                "download_status": doc["download_status"],
            }
            clf = self.get_classification(doc["document_id"])
            if clf:
                row["classification"] = clf["classification"]
                row["classification_confidence"] = clf["confidence"]
                row["classification_reason"] = clf["reason"]
            meta = self.get_metadata(doc["document_id"])
            if meta:
                row.update(meta.to_flat_dict())
            index.append(row)
        return index
