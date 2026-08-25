from __future__ import annotations

import json
from pathlib import Path

from app.modules.imports.schemas import DailyDryRunSummary


class DryRunPlanMissing(RuntimeError):
    pass


class ImportPlanService:
    def __init__(self, dry_run_directory: Path) -> None:
        self.dry_run_directory = dry_run_directory

    def _path_for_day(self, day: str | None = None) -> Path:
        if day:
            return self.dry_run_directory / f"daily_dry_run_{day.replace('-', '')}.json"

        candidates = sorted(
            self.dry_run_directory.glob("daily_dry_run_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise DryRunPlanMissing(
                f"No daily dry-run plan found under {self.dry_run_directory}."
            )
        return candidates[0]

    def get_latest_or_day(self, day: str | None = None) -> DailyDryRunSummary:
        path = self._path_for_day(day)
        if not path.exists():
            raise DryRunPlanMissing(f"Daily dry-run plan not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return DailyDryRunSummary.model_validate(payload)

