from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestionMetrics:
    run_id: str
    dag_id: str
    task_id: str
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    status: str = "running"
    pages_fetched: int = 0
    reported_total: int = 0
    records_received: int = 0
    records_inserted: int = 0
    duplicates_ignored: int = 0
    error_message: str | None = None

    def register_fetch(
        self,
        *,
        pages_fetched: int,
        reported_total: int,
        records_received: int,
    ) -> None:
        values = (
            pages_fetched,
            reported_total,
            records_received,
        )

        if any(value < 0 for value in values):
            raise ValueError(
                "Fetch metrics cannot contain negative values"
            )

        self.pages_fetched = pages_fetched
        self.reported_total = reported_total
        self.records_received = records_received

    def mark_success(
        self,
        *,
        records_inserted: int,
        finished_at: datetime | None = None,
    ) -> None:
        if records_inserted < 0:
            raise ValueError(
                "records_inserted cannot be negative"
            )

        if records_inserted > self.records_received:
            raise ValueError(
                "records_inserted cannot exceed records_received"
            )

        self.records_inserted = records_inserted
        self.duplicates_ignored = (
            self.records_received - records_inserted
        )
        self.status = "success"
        self.finished_at = finished_at or utc_now()
        self.error_message = None

    def mark_failed(
        self,
        error: BaseException,
        *,
        finished_at: datetime | None = None,
    ) -> None:
        self.status = "failed"
        self.finished_at = finished_at or utc_now()
        self.error_message = str(error)[:4000]

    @property
    def duration_seconds(self) -> float:
        if self.finished_at is None:
            raise ValueError(
                "Metrics are not finalized"
            )

        return round(
            (
                self.finished_at - self.started_at
            ).total_seconds(),
            3,
        )

    def as_database_parameters(self) -> dict:
        if self.status not in {"success", "failed"}:
            raise ValueError(
                "Metrics must be finalized before persistence"
            )

        return {
            "run_id": self.run_id,
            "dag_id": self.dag_id,
            "task_id": self.task_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "pages_fetched": self.pages_fetched,
            "reported_total": self.reported_total,
            "records_received": self.records_received,
            "records_inserted": self.records_inserted,
            "duplicates_ignored": self.duplicates_ignored,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }