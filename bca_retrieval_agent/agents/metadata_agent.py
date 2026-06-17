"""Metadata extraction agent."""

import logging
from typing import Optional

from config import EXTRACTED_TEXT_DIR
from core.database import Database
from core.metadata_extractor import extract_metadata
from schemas.metadata_schema import DocumentMetadata
from schemas.run_schema import RunLog

logger = logging.getLogger(__name__)

EXTRACTABLE_CLASSIFICATIONS = {"Definite BCA", "Likely BCA", "Workbook / calculation file"}


class MetadataAgent:
    """Extracts structured metadata from classified BCA documents."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def extract_run(
        self,
        run_id: str,
        run_log: Optional[RunLog] = None,
        use_llm: bool = True,
        all_documents: bool = False,
    ) -> list[DocumentMetadata]:
        documents = self.db.get_documents_by_run(run_id)
        metadata_list = []

        for doc in documents:
            clf = self.db.get_classification(doc["document_id"])
            classification = clf["classification"] if clf else "Unknown"
            confidence = clf["confidence"] if clf else 0.0

            if not all_documents and classification not in EXTRACTABLE_CLASSIFICATIONS:
                continue

            text_path = EXTRACTED_TEXT_DIR / run_id / f"{doc['document_id']}.txt"
            text = ""
            if text_path.exists():
                text = text_path.read_text(encoding="utf-8", errors="ignore")

            meta = extract_metadata(
                text=text,
                document_id=doc["document_id"],
                source_url=doc.get("source_url", ""),
                local_path=doc.get("local_path", ""),
                classification=classification,
                classification_confidence=confidence,
                use_llm=use_llm,
            )
            self.db.save_metadata(meta)
            metadata_list.append(meta)

        if run_log:
            run_log.status = "metadata_extracted"
            self.db.update_run(run_log)

        return metadata_list
