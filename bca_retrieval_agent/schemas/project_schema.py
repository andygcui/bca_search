"""Schema for project research results."""

from typing import Optional
from pydantic import BaseModel, Field


class SourcedURL(BaseModel):
    """A source URL with its document type classification."""
    url: str
    doc_type: Optional[str] = None  # one of PROJECT_DOCUMENT_TYPES


class SourcedField(BaseModel):
    """A data field with its source URL(s) and confidence level."""
    value: Optional[str] = None
    sources: list[SourcedURL] = Field(default_factory=list)
    confidence: str = "low"  # low, medium, high


class ProjectResearchResult(BaseModel):
    """Structured research output for an infrastructure project."""

    project_name: str
    aliases: list[str] = Field(default_factory=list)

    # Core FHWA tracking fields
    location: SourcedField = Field(default_factory=SourcedField)
    description: SourcedField = Field(default_factory=SourcedField)
    cost_estimate_current: SourcedField = Field(default_factory=SourcedField)
    cost_estimate_prior_year: SourcedField = Field(default_factory=SourcedField)
    schedule_completion_current: SourcedField = Field(default_factory=SourcedField)
    schedule_completion_baseline: SourcedField = Field(default_factory=SourcedField)
    project_sponsor: SourcedField = Field(default_factory=SourcedField)
    federal_funds: SourcedField = Field(default_factory=SourcedField)
    state_funds: SourcedField = Field(default_factory=SourcedField)
    local_funds: SourcedField = Field(default_factory=SourcedField)
    toll_funds: SourcedField = Field(default_factory=SourcedField)
    tifia: SourcedField = Field(default_factory=SourcedField)
    total_funding: SourcedField = Field(default_factory=SourcedField)

    # Extra fields the agent identifies as relevant
    project_type: SourcedField = Field(default_factory=SourcedField)
    total_length: SourcedField = Field(default_factory=SourcedField)
    grant_programs: SourcedField = Field(default_factory=SourcedField)
    environmental_status: SourcedField = Field(default_factory=SourcedField)
    key_milestones: SourcedField = Field(default_factory=SourcedField)
    economic_info: SourcedField = Field(default_factory=SourcedField)
    additional_relevant_info: SourcedField = Field(default_factory=SourcedField)

    # Verification
    inconsistencies: list[str] = Field(default_factory=list)
    sources_searched: list[str] = Field(default_factory=list)
    archive_sources: list[str] = Field(default_factory=list)
    llm_verified: bool = False
