"""Rule-based and optional LLM BCA classifier."""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from config import (
    CLASSIFICATIONS,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    PROMPTS_DIR,
    STRONG_BCA_INDICATORS,
    WORKBOOK_INDICATORS,
)
from schemas.document_schema import ClassificationResult

logger = logging.getLogger(__name__)

GRANT_DOC_INDICATORS = [
    "grant application",
    "narrative",
    "project description",
    "application appendix",
    "letter of support",
    "environmental assessment",
    "nea",
    "ceqa",
    "nepa",
]

NOT_BCA_INDICATORS = [
    "environmental impact",
    "biological assessment",
    "cost estimate only",
    "bid tabulation",
    "right of way",
]


def _count_indicators(text: str, indicators: list[str]) -> list[str]:
    text_lower = text.lower()
    found = []
    for indicator in indicators:
        if indicator in text_lower:
            found.append(indicator)
    return found


def _workbook_score(text: str, file_type: str) -> float:
    if file_type.lower() in ("xlsx", "xlsm"):
        base = 0.4
    else:
        base = 0.0
    found = _count_indicators(text, WORKBOOK_INDICATORS)
    formula_count = len(re.findall(r"\[formula\]=", text))
    score = base + min(0.5, len(found) * 0.08) + min(0.2, formula_count * 0.02)
    return min(1.0, score)


def classify_rules(text: str, file_type: str = "pdf") -> ClassificationResult:
    """Rule-based BCA classification."""
    if not text or len(text.strip()) < 50:
        return ClassificationResult(
            document_id="",
            classification="Unknown",
            confidence=0.3,
            reason="Insufficient text for classification",
            evidence_terms=[],
            method="rules",
        )

    strong = _count_indicators(text, STRONG_BCA_INDICATORS)
    grant = _count_indicators(text, GRANT_DOC_INDICATORS)
    not_bca = _count_indicators(text, NOT_BCA_INDICATORS)
    wb_score = _workbook_score(text, file_type)

    if wb_score >= 0.6 and file_type.lower() in ("xlsx", "xlsm"):
        return ClassificationResult(
            document_id="",
            classification="Workbook / calculation file",
            confidence=min(0.95, 0.5 + wb_score * 0.4),
            reason=f"Spreadsheet with {len(_count_indicators(text, WORKBOOK_INDICATORS))} workbook indicators",
            evidence_terms=_count_indicators(text, WORKBOOK_INDICATORS),
            method="rules",
        )

    if len(strong) >= 4:
        return ClassificationResult(
            document_id="",
            classification="Definite BCA",
            confidence=min(0.98, 0.7 + len(strong) * 0.05),
            reason=f"Found {len(strong)} strong BCA indicators",
            evidence_terms=strong,
            method="rules",
        )

    if len(strong) >= 2:
        return ClassificationResult(
            document_id="",
            classification="Likely BCA",
            confidence=min(0.85, 0.5 + len(strong) * 0.1),
            reason=f"Found {len(strong)} BCA indicators",
            evidence_terms=strong,
            method="rules",
        )

    if len(strong) >= 1 and len(grant) >= 1:
        return ClassificationResult(
            document_id="",
            classification="Related grant document",
            confidence=0.6,
            reason="BCA terms present but document appears to be grant-related",
            evidence_terms=strong + grant,
            method="rules",
        )

    if len(grant) >= 2 and len(strong) == 0:
        return ClassificationResult(
            document_id="",
            classification="Related grant document",
            confidence=0.55,
            reason="Grant document indicators without strong BCA content",
            evidence_terms=grant,
            method="rules",
        )

    if len(not_bca) >= 2:
        return ClassificationResult(
            document_id="",
            classification="Not a BCA",
            confidence=0.7,
            reason="Document appears to be non-BCA (environmental/cost estimate)",
            evidence_terms=not_bca,
            method="rules",
        )

    if len(strong) == 1:
        return ClassificationResult(
            document_id="",
            classification="Likely BCA",
            confidence=0.45,
            reason="Single BCA indicator found",
            evidence_terms=strong,
            method="rules",
        )

    return ClassificationResult(
        document_id="",
        classification="Unknown",
        confidence=0.25,
        reason="No clear BCA indicators found",
        evidence_terms=[],
        method="rules",
    )


def classify_llm(text: str, document_id: str) -> Optional[ClassificationResult]:
    """Optional LLM classification using OpenAI or Anthropic."""
    prompt_path = PROMPTS_DIR / "classifier_prompt.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    excerpt = text[:8000]
    prompt = prompt_template.replace("{document_text}", excerpt)

    try:
        if OPENAI_API_KEY:
            return _classify_openai(prompt, document_id)
        if ANTHROPIC_API_KEY:
            return _classify_anthropic(prompt, document_id)
    except Exception as exc:
        logger.error("LLM classification failed: %s", exc)
    return None


def _parse_llm_json(response_text: str) -> dict:
    text = response_text.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    return json.loads(text)


def _classify_openai(prompt: str, document_id: str) -> ClassificationResult:
    import openai

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    data = _parse_llm_json(response.choices[0].message.content or "{}")
    classification = data.get("classification", "Unknown")
    if classification not in CLASSIFICATIONS:
        classification = "Unknown"
    return ClassificationResult(
        document_id=document_id,
        classification=classification,
        confidence=float(data.get("confidence", 0.5)),
        reason=data.get("reason", ""),
        evidence_terms=data.get("evidence_terms", []),
        method="llm_openai",
    )


def _classify_anthropic(prompt: str, document_id: str) -> ClassificationResult:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_llm_json(response.content[0].text)
    classification = data.get("classification", "Unknown")
    if classification not in CLASSIFICATIONS:
        classification = "Unknown"
    return ClassificationResult(
        document_id=document_id,
        classification=classification,
        confidence=float(data.get("confidence", 0.5)),
        reason=data.get("reason", ""),
        evidence_terms=data.get("evidence_terms", []),
        method="llm_anthropic",
    )


def classify_document(
    text: str,
    document_id: str,
    file_type: str = "pdf",
    use_llm: bool = True,
) -> ClassificationResult:
    """
    Classify a document using rules first, optionally enhanced by LLM.
    LLM result is used only if it has higher confidence than rules.
    """
    rules_result = classify_rules(text, file_type)
    rules_result.document_id = document_id

    if not use_llm:
        return rules_result

    llm_result = classify_llm(text, document_id)
    if llm_result and llm_result.confidence > rules_result.confidence:
        return llm_result

    return rules_result
