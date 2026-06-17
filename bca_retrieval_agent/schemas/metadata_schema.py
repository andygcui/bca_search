"""Metadata extraction schemas."""

from typing import Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Structured metadata extracted from a BCA document."""

    document_id: str = ""
    title: str = ""
    project_name: str = ""
    sponsor_agency: str = ""
    state: str = ""
    grant_program: str = ""
    project_type: str = ""
    mode: str = ""
    year: str = ""
    base_year_dollars: str = ""
    discount_rate: str = ""
    analysis_period: str = ""
    project_cost: str = ""
    federal_request: str = ""
    pv_benefits: str = ""
    pv_costs: str = ""
    npv: str = ""
    bcr: str = ""
    irr: str = ""
    payback_period: str = ""
    benefit_categories: list[str] = Field(default_factory=list)
    cost_categories: list[str] = Field(default_factory=list)
    methodology_notes: str = ""
    data_sources: list[str] = Field(default_factory=list)
    source_url: str = ""
    local_file_path: str = ""
    classification: str = ""
    confidence: float = 0.0
    extraction_method: str = "rules"

    def to_flat_dict(self) -> dict:
        """Flatten for CSV/Excel export."""
        data = self.model_dump()
        data["benefit_categories"] = "; ".join(self.benefit_categories)
        data["cost_categories"] = "; ".join(self.cost_categories)
        data["data_sources"] = "; ".join(self.data_sources)
        return data
