"""Run tracking schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    """User configuration for a retrieval run."""

    query: str = ""
    target_domain: Optional[str] = None
    search_mode: str = "direct_url"
    max_results: int = 20
    file_types: list[str] = Field(default_factory=lambda: ["pdf", "docx", "xlsx", "html"])
    grant_program_filter: Optional[str] = None
    project_type_filter: Optional[str] = None
    state_filter: Optional[str] = None
    package_name: Optional[str] = None
    direct_urls: list[str] = Field(default_factory=list)


class RunLog(BaseModel):
    """Log summary for a retrieval run."""

    run_id: str
    query: str = ""
    target_domain: Optional[str] = None
    search_mode: str = ""
    start_time: str = ""
    end_time: Optional[str] = None
    candidate_urls: int = 0
    downloads_attempted: int = 0
    downloads_successful: int = 0
    definite_bcas: int = 0
    likely_bcas: int = 0
    errors: list[str] = Field(default_factory=list)
    status: str = "running"

    def to_dict(self) -> dict:
        return self.model_dump()
