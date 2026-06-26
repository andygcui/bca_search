"""Schema for project research results."""

from typing import Optional
from pydantic import BaseModel, Field


class FoundDocument(BaseModel):
    """A document found during project research."""
    url: str
    title: str = ""
    doc_type: str = "Other"          # one of PROJECT_DOCUMENT_TYPES
    confidence: str = "medium"        # high / medium / low
    source: str = "live"              # "live" or "archive"
    archive_timestamp: Optional[str] = None   # e.g. "20210315123456"
    wayback_url: Optional[str] = None         # direct Wayback Machine access URL
    snippet: str = ""


class ProjectResearchResult(BaseModel):
    """Structured research output for an infrastructure project."""
    project_name: str
    aliases: list[str] = Field(default_factory=list)
    found_documents: list[FoundDocument] = Field(default_factory=list)
    sources_searched: list[str] = Field(default_factory=list)
    archive_snapshots_checked: int = 0
    llm_verified: bool = False
