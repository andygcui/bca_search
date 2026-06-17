"""BCA classification agent."""

import logging
from pathlib import Path
from typing import Optional

from config import EXTRACTED_TEXT_DIR
from core.classifier import classify_document
from core.database import Database
from schemas.document_schema import ClassificationResult
from schemas.run_schema import RunLog

logger = logging.getLogger(__name__)

BCA_CLASSIFICATIONS = {"Definite BCA", "Likely BCA"}


class ClassifierAgent:
    """Classifies downloaded documents as BCA or non-BCA."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def classify_run(
        self,
        run_id: str,
        run_log: Optional[RunLog] = None,
        use_llm: bool = True,
    ) -> list[ClassificationResult]:
        documents = self.db.get_documents_by_run(run_id)
        results = []

        for doc in documents:
            text_path = EXTRACTED_TEXT_DIR / run_id / f"{doc['document_id']}.txt"
            if text_path.exists():
                text = text_path.read_text(encoding="utf-8", errors="ignore")
            else:
                text = ""

            result = classify_document(
                text=text,
                document_id=doc["document_id"],
                file_type=doc.get("file_type", "pdf"),
                use_llm=use_llm,
            )
            self.db.save_classification(result)
            results.append(result)

            if run_log:
                if result.classification == "Definite BCA":
                    run_log.definite_bcas += 1
                elif result.classification == "Likely BCA":
                    run_log.likely_bcas += 1

        if run_log:
            run_log.status = "classified"
            self.db.update_run(run_log)

        return results
