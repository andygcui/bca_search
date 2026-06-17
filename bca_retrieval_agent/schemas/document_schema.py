"""Document schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    """A downloaded document record."""

    document_id: str
    run_id: str
    source_url: str
    local_path: str
    file_type: str
    file_hash: str
    url_hash: str
    title: Optional[str] = None
    file_size: Optional[int] = None
    download_status: str = "pending"
    extracted_text_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClassificationResult(BaseModel):
    """BCA classification result."""

    document_id: str
    classification: str
    confidence: float = 0.0
    reason: str = ""
    evidence_terms: list[str] = Field(default_factory=list)
    method: str = "rules"


class DownloadError(BaseModel):
    """Record of a failed download."""

    run_id: str
    url: str
    error_message: str
    error_type: str = "unknown"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
