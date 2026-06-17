"""Packaging and export agent."""

import json
import logging
from datetime import datetime
from typing import Optional

from config import LOGS_DIR, RUNS_DIR
from core.database import Database
from core.packager import create_zip_package, export_csv, export_excel
from schemas.run_schema import RunLog

logger = logging.getLogger(__name__)


class PackagingAgent:
    """Creates CSV, Excel, and ZIP exports for a run."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def export_run(
        self,
        run_id: str,
        package_name: Optional[str] = None,
        run_log: Optional[RunLog] = None,
    ) -> dict[str, str]:
        index = self.db.get_full_index(run_id)
        name = package_name or f"bca_retrieval_run_{run_id}"

        csv_path = export_csv(index, run_id, name)
        excel_path = export_excel(index, run_id, name)
        zip_path = create_zip_package(run_id, self.db, name)

        if run_log:
            run_log.end_time = datetime.utcnow().isoformat()
            run_log.status = "exported"
            self.db.update_run(run_log)
            log_path = RUNS_DIR / f"{run_id}_log.json"
            log_path.write_text(
                json.dumps(run_log.to_dict(), indent=2),
                encoding="utf-8",
            )
            logs_copy = LOGS_DIR / f"{run_id}.json"
            logs_copy.write_text(
                json.dumps(run_log.to_dict(), indent=2),
                encoding="utf-8",
            )

        return {
            "csv": csv_path,
            "excel": excel_path,
            "zip": zip_path,
        }
