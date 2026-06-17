"""Search result schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single search or crawl result."""

    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    source: str = "unknown"
    discovered_at: datetime = Field(default_factory=datetime.utcnow)


class SearchResults(BaseModel):
    """Collection of search results."""

    query: str
    mode: str
    results: list[SearchResult] = Field(default_factory=list)
    total: int = 0
    errors: list[str] = Field(default_factory=list)
