import unittest
from datetime import datetime, timedelta, timezone

from dags.lib.ingestion_metrics import IngestionMetrics


STARTED_AT = datetime(
    2026,
    7,
    18,
    10,
    0,
    0,
    tzinfo=timezone.utc,
)


class IngestionMetricsTestCase(unittest.TestCase):
    def make_metrics(self) -> IngestionMetrics:
        return IngestionMetrics(
            run_id="manual__2026-07-18",
            dag_id="ingest_and_transform_velib",
            task_id="extract_and_load_velib_task",
            started_at=STARTED_AT,
        )

    def test_records_success_metrics(self) -> None:
        metrics = self.make_metrics()
        metrics.register_fetch(
            pages_fetched=16,
            reported_total=1516,
            records_received=1516,
        )

        metrics.mark_success(
            records_inserted=61,
            finished_at=(
                STARTED_AT + timedelta(seconds=3.456)
            ),
        )

        self.assertEqual(metrics.status, "success")
        self.assertEqual(metrics.records_inserted, 61)
        self.assertEqual(metrics.duplicates_ignored, 1455)
        self.assertEqual(metrics.duration_seconds, 3.456)

    def test_records_failure_message(self) -> None:
        metrics = self.make_metrics()

        metrics.mark_failed(
            RuntimeError("API unavailable"),
            finished_at=(
                STARTED_AT + timedelta(seconds=2)
            ),
        )

        self.assertEqual(metrics.status, "failed")
        self.assertEqual(
            metrics.error_message,
            "API unavailable",
        )
        self.assertEqual(metrics.duration_seconds, 2.0)

    def test_rejects_inserted_count_above_received(self) -> None:
        metrics = self.make_metrics()
        metrics.register_fetch(
            pages_fetched=1,
            reported_total=1,
            records_received=1,
        )

        with self.assertRaisesRegex(
            ValueError,
            "cannot exceed",
        ):
            metrics.mark_success(records_inserted=2)

    def test_requires_finalization_before_persistence(
        self,
    ) -> None:
        metrics = self.make_metrics()

        with self.assertRaisesRegex(
            ValueError,
            "finalized",
        ):
            metrics.as_database_parameters()


if __name__ == "__main__":
    unittest.main()