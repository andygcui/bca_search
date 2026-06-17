"""Export packaging: CSV, Excel, and ZIP."""

import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config import CSV_DIR, EXCEL_DIR, RUNS_DIR, ZIP_DIR, ensure_directories
from core.database import Database

logger = logging.getLogger(__name__)


def export_csv(index: list[dict], run_id: str, package_name: Optional[str] = None) -> str:
    """Export metadata index to CSV."""
    ensure_directories()
    name = package_name or f"bca_index_{run_id}"
    out_path = CSV_DIR / f"{name}.csv"
    df = pd.DataFrame(index)
    df.to_csv(out_path, index=False)
    return str(out_path)


def export_excel(index: list[dict], run_id: str, package_name: Optional[str] = None) -> str:
    """Export metadata index to Excel."""
    ensure_directories()
    name = package_name or f"bca_index_{run_id}"
    out_path = EXCEL_DIR / f"{name}.xlsx"
    df = pd.DataFrame(index)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="BCA Index", index=False)
    return str(out_path)


def create_zip_package(
    run_id: str,
    db: Optional[Database] = None,
    package_name: Optional[str] = None,
) -> str:
    """
    Create a ZIP package containing:
    - downloaded documents
    - extracted text files
    - metadata CSV and Excel
    - run log JSON
    """
    ensure_directories()
    db = db or Database()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_name = package_name or f"bca_retrieval_run_{timestamp}"
    zip_path = ZIP_DIR / f"{zip_name}.zip"

    index = db.get_full_index(run_id)
    csv_path = export_csv(index, run_id, zip_name)
    excel_path = export_excel(index, run_id, zip_name)

    run = db.get_run(run_id)
    run_log_path = RUNS_DIR / f"{run_id}_log.json"
    if run:
        run_log_path.write_text(json.dumps(run, indent=2, default=str), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in index:
            local_path = row.get("local_path")
            if local_path and Path(local_path).exists():
                zf.write(local_path, arcname=f"documents/{Path(local_path).name}")

            doc_id = row.get("document_id", "")
            from config import EXTRACTED_TEXT_DIR

            text_path = EXTRACTED_TEXT_DIR / run_id / f"{doc_id}.txt"
            if text_path.exists():
                zf.write(text_path, arcname=f"extracted_text/{text_path.name}")

        zf.write(csv_path, arcname="metadata/index.csv")
        zf.write(excel_path, arcname="metadata/index.xlsx")
        if run_log_path.exists():
            zf.write(run_log_path, arcname="run_log.json")

    logger.info("Created ZIP package: %s", zip_path)
    return str(zip_path)
