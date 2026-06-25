"""Rule-based and optional LLM metadata extraction."""

import json
import logging
import re
from typing import Optional

from config import ANTHROPIC_API_KEY, GRANT_PROGRAMS, OPENAI_API_KEY, PROMPTS_DIR, US_STATES
from schemas.metadata_schema import DocumentMetadata

logger = logging.getLogger(__name__)

BCA_FIELDS_PATTERNS = {
    "bcr": [
        r"benefit[- ]cost ratio[:\s]*([0-9.]+)",
        r"\bBCR[:\s]*([0-9.]+)",
        r"benefit/cost ratio[:\s]*([0-9.]+)",
    ],
    "npv": [
        r"net present value[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(?:million|M)?",
        r"\bNPV[:\s]*\$?([\d,]+(?:\.\d+)?)",
    ],
    "discount_rate": [
        r"discount rate[:\s]*([0-9.]+%?)",
        r"real discount rate[:\s]*([0-9.]+%?)",
    ],
    "analysis_period": [
        r"analysis period[:\s]*(\d+)\s*years?",
        r"(\d+)[- ]year analysis period",
    ],
    "project_cost": [
        r"(?:total )?project cost[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(?:million|M)?",
        r"capital cost[:\s]*\$?([\d,]+(?:\.\d+)?)",
    ],
    "federal_request": [
        r"federal (?:share|request|funding)[:\s]*\$?([\d,]+(?:\.\d+)?)",
    ],
    "pv_benefits": [
        r"present value (?:of )?benefits[:\s]*\$?([\d,]+(?:\.\d+)?)",
    ],
    "pv_costs": [
        r"present value (?:of )?costs[:\s]*\$?([\d,]+(?:\.\d+)?)",
    ],
    "irr": [
        r"\bIRR[:\s]*([0-9.]+%?)",
        r"internal rate of return[:\s]*([0-9.]+%?)",
    ],
    "payback_period": [
        r"payback period[:\s]*(\d+(?:\.\d+)?)\s*years?",
    ],
    "base_year_dollars": [
        r"base year[:\s]*(\d{4})",
        r"(\d{4})\s*dollars",
    ],
}

BENEFIT_CATEGORIES = [
    "travel time savings",
    "vehicle operating costs",
    "safety",
    "emissions",
    "reliability",
    "freight",
    "agglomeration",
    "health",
    "resilience",
]

COST_CATEGORIES = [
    "capital costs",
    "operating and maintenance",
    "right of way",
    "construction engineering",
    "planning",
    "residual value",
]


def _extract_field(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _detect_grant_program(text: str) -> str:
    text_upper = text.upper()
    for program in GRANT_PROGRAMS:
        if program != "Other" and program in text_upper:
            return program
    return ""


def _detect_state(text: str) -> str:
    for state in US_STATES:
        if re.search(rf"\b{state}\b", text):
            return state
    state_names = {
        "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
        "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
        "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
        "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
        "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
        "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
        "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
        "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
        "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
        "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
        "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
        "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
        "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    }
    for name, abbr in state_names.items():
        if name.lower() in text.lower():
            return abbr
    return ""


def _detect_project_type(text: str) -> str:
    types_map = {
        "bridge": "Bridge",
        "highway": "Highway",
        "rail": "Rail",
        "transit": "Transit",
        "freight": "Freight",
        "safety": "Safety",
        "multimodal": "Multimodal",
        "bicycle": "Active Transportation",
        "pedestrian": "Active Transportation",
        "active transportation": "Active Transportation",
    }
    text_lower = text.lower()
    for keyword, ptype in types_map.items():
        if keyword in text_lower:
            return ptype
    return ""


def _detect_year(text: str) -> str:
    match = re.search(r"\b(20[0-2]\d)\b", text[:2000])
    return match.group(1) if match else ""


def extract_metadata_rules(
    text: str,
    document_id: str,
    source_url: str = "",
    local_path: str = "",
    classification: str = "",
    confidence: float = 0.0,
) -> DocumentMetadata:
    """Extract metadata using regex and rules."""
    meta = DocumentMetadata(
        document_id=document_id,
        source_url=source_url,
        local_file_path=local_path,
        classification=classification,
        confidence=confidence,
        extraction_method="rules",
    )

    title_match = re.search(
        r"(?:benefit[- ]cost analysis|BCA)[:\s\-–]*(.*?)(?:\n|$)",
        text[:3000],
        re.IGNORECASE,
    )
    if title_match:
        meta.title = title_match.group(0).strip()[:200]
    elif text.strip():
        meta.title = text.strip()[:150]

    project_match = re.search(
        r"project(?:\s+name)?[:\s]+(.+?)(?:\n|$)",
        text[:5000],
        re.IGNORECASE,
    )
    if project_match:
        meta.project_name = project_match.group(1).strip()[:200]

    agency_match = re.search(
        r"(?:sponsor|prepared (?:by|for)|agency)[:\s]+(.+?)(?:\n|$)",
        text[:5000],
        re.IGNORECASE,
    )
    if agency_match:
        meta.sponsor_agency = agency_match.group(1).strip()[:200]

    for field, patterns in BCA_FIELDS_PATTERNS.items():
        value = _extract_field(text, patterns)
        if value and hasattr(meta, field):
            setattr(meta, field, value)

    meta.grant_program = _detect_grant_program(text)
    meta.state = _detect_state(text)
    meta.project_type = _detect_project_type(text)
    meta.year = _detect_year(text)

    text_lower = text.lower()
    meta.benefit_categories = [b for b in BENEFIT_CATEGORIES if b in text_lower]
    meta.cost_categories = [c for c in COST_CATEGORIES if c in text_lower]

    methodology_match = re.search(
        r"(?:methodology|analytical approach)[:\s]+(.{50,500}?)(?:\n\n|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if methodology_match:
        meta.methodology_notes = methodology_match.group(1).strip()[:500]

    sources = re.findall(
        r"(?:data source|source)[:\s]+(.+?)(?:\n|$)",
        text[:10000],
        re.IGNORECASE,
    )
    meta.data_sources = [s.strip()[:200] for s in sources[:5]]

    filled = sum(1 for v in meta.model_dump().values() if v and v != [] and v != 0.0)
    meta.confidence = min(0.9, 0.2 + filled * 0.04)

    return meta


def extract_metadata_llm(text: str, document_id: str) -> Optional[DocumentMetadata]:
    """Optional LLM metadata extraction."""
    prompt_path = PROMPTS_DIR / "metadata_extraction_prompt.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    excerpt = text[:12000]
    prompt = prompt_template.replace("{document_text}", excerpt)

    try:
        if OPENAI_API_KEY:
            return _extract_openai(prompt, document_id)
        if ANTHROPIC_API_KEY:
            return _extract_anthropic(prompt, document_id)
    except Exception as exc:
        logger.error("LLM metadata extraction failed: %s", exc)
    return None


def _parse_llm_json(response_text: str) -> dict:
    text = response_text.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    return json.loads(text)


def _extract_openai(prompt: str, document_id: str) -> DocumentMetadata:
    import openai

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    data = _parse_llm_json(response.choices[0].message.content or "{}")
    data["document_id"] = document_id
    data["extraction_method"] = "llm_openai"
    data["confidence"] = 0.75
    return DocumentMetadata(**{k: v for k, v in data.items() if k in DocumentMetadata.model_fields})


def _extract_anthropic(prompt: str, document_id: str) -> DocumentMetadata:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_llm_json(response.content[0].text)
    data["document_id"] = document_id
    data["extraction_method"] = "llm_anthropic"
    data["confidence"] = 0.75
    return DocumentMetadata(**{k: v for k, v in data.items() if k in DocumentMetadata.model_fields})


def extract_metadata(
    text: str,
    document_id: str,
    source_url: str = "",
    local_path: str = "",
    classification: str = "",
    classification_confidence: float = 0.0,
    use_llm: bool = True,
) -> DocumentMetadata:
    """Extract metadata using rules, optionally enhanced by LLM."""
    rules_meta = extract_metadata_rules(
        text, document_id, source_url, local_path, classification, classification_confidence
    )

    if not use_llm:
        return rules_meta

    llm_meta = extract_metadata_llm(text, document_id)
    if not llm_meta:
        return rules_meta

    merged = rules_meta.model_dump()
    llm_data = llm_meta.model_dump()
    for key, value in llm_data.items():
        if value and (not merged.get(key) or merged.get(key) == "" or merged.get(key) == []):
            merged[key] = value
    merged["extraction_method"] = "rules+llm"
    merged["confidence"] = max(rules_meta.confidence, llm_meta.confidence)
    return DocumentMetadata(**merged)
