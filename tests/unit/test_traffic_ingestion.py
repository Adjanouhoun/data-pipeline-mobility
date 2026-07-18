import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

from dags.lib.traffic_ingestion import (
    TrafficRecordError,
    classify_upsert_results,
    load_traffic_records,
    parse_api_datetime,
    parse_coordinates,
    parse_optional_decimal,
    transform_traffic_record,
)


class TrafficIngestionTestCase(unittest.TestCase):
    def setUp(self):
        self.ingested_at = datetime(
            2026,
            7,
            18,
            1,
            30,
            0,
            tzinfo=timezone.utc,
        )

        self.complete_record = {
            "iu_ac": "6462",
            "libelle": "Av_Flandre",
            "t_1h": "2026-07-17T22:00:00+00:00",
            "q": 526.0,
            "k": 8.13333,
            "etat_trafic": "Fluide",
            "iu_nd_amont": "3339",
            "libelle_nd_amont": "Flandre-Ourcq",
            "iu_nd_aval": "3342",
            "libelle_nd_aval": "Flandre-Nantes",
            "etat_barre": "Ouvert",
            "date_debut": "2002-03-05",
            "date_fin": "2023-01-01",
            "geo_point_2d": {
                "lon": 2.379594010595371,
                "lat": 48.89267717769227,
            },
            "geo_shape": {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [2.379148, 48.892335],
                        [2.380039, 48.893018],
                    ],
                },
                "properties": {},
            },
        }

    def test_parse_api_datetime_normalizes_utc(self):
        result = parse_api_datetime(
            "2026-07-18T00:00:00+02:00"
        )

        self.assertEqual(
            result,
            datetime(
                2026,
                7,
                17,
                22,
                0,
                0,
                tzinfo=timezone.utc,
            ),
        )

    def test_parse_optional_decimal_preserves_null(self):
        result = parse_optional_decimal(
            None,
            "vehicle_flow",
        )

        self.assertIsNone(result)

    def test_parse_optional_decimal_rejects_non_finite(self):
        with self.assertRaises(TrafficRecordError):
            parse_optional_decimal(
                "NaN",
                "occupancy_rate",
            )

    def test_parse_coordinates_rejects_invalid_range(self):
        with self.assertRaises(TrafficRecordError):
            parse_coordinates(
                {
                    "lon": 200,
                    "lat": 48.8,
                }
            )

    def test_transform_traffic_record(self):
        result = transform_traffic_record(
            self.complete_record,
            ingested_at=self.ingested_at,
            source_run_id="traffic_dag::manual_run",
        )

        self.assertEqual(len(result), 18)
        self.assertEqual(result[0], "6462")
        self.assertEqual(result[1], "Av_Flandre")
        self.assertEqual(
            result[2],
            datetime(
                2026,
                7,
                17,
                22,
                0,
                0,
                tzinfo=timezone.utc,
            ),
        )
        self.assertEqual(result[3], Decimal("526.0"))
        self.assertEqual(result[4], Decimal("8.13333"))
        self.assertEqual(result[5], "Fluide")
        self.assertEqual(result[6], "Ouvert")
        self.assertEqual(result[7], "3339")
        self.assertEqual(result[9], "3342")
        self.assertAlmostEqual(
            result[13],
            2.379594010595371,
        )
        self.assertAlmostEqual(
            result[14],
            48.89267717769227,
        )
        self.assertIn(
            '"LineString"',
            result[15],
        )
        self.assertEqual(
            result[16],
            self.ingested_at,
        )
        self.assertEqual(
            result[17],
            "traffic_dag::manual_run",
        )

    def test_transform_traffic_record_accepts_null_measurements(
        self,
    ):
        record = dict(self.complete_record)
        record["q"] = None
        record["k"] = None
        record["geo_point_2d"] = None
        record["geo_shape"] = None

        result = transform_traffic_record(
            record,
            ingested_at=self.ingested_at,
            source_run_id="traffic_dag::manual_run",
        )

        self.assertIsNone(result[3])
        self.assertIsNone(result[4])
        self.assertIsNone(result[13])
        self.assertIsNone(result[14])
        self.assertIsNone(result[15])

    def test_transform_traffic_record_rejects_invalid_timestamp(
        self,
    ):
        record = dict(self.complete_record)
        record["t_1h"] = "invalid"

        with self.assertRaises(TrafficRecordError):
            transform_traffic_record(
                record,
                ingested_at=self.ingested_at,
                source_run_id="traffic_dag::manual_run",
            )

    def test_transform_traffic_record_requires_aware_ingestion_time(
        self,
    ):
        with self.assertRaises(TrafficRecordError):
            transform_traffic_record(
                self.complete_record,
                ingested_at=datetime(
                    2026,
                    7,
                    18,
                    1,
                    30,
                ),
                source_run_id="traffic_dag::manual_run",
            )

    def test_classify_upsert_results(self):
        result = classify_upsert_results(
            returned_rows=[
                (True,),
                (True,),
                (False,),
            ],
            records_received=5,
        )

        self.assertEqual(result.records_received, 5)
        self.assertEqual(result.records_inserted, 2)
        self.assertEqual(result.records_updated, 1)
        self.assertEqual(result.records_unchanged, 2)

    def test_load_traffic_records_accepts_empty_batch(self):
        connection = Mock()

        result = load_traffic_records(
            connection=connection,
            transformed_records=[],
        )

        self.assertEqual(result.records_received, 0)
        self.assertEqual(result.records_inserted, 0)
        self.assertEqual(result.records_updated, 0)
        self.assertEqual(result.records_unchanged, 0)
        connection.cursor.assert_not_called()

    @patch(
        "dags.lib.traffic_ingestion.execute_values"
    )
    def test_load_traffic_records_uses_bulk_upsert(
        self,
        execute_values_mock,
    ):
        connection = MagicMock()
        cursor = Mock()
        cursor_context = connection.cursor.return_value

        enter_method_name = "_" * 2 + "enter" + "_" * 2
        getattr(
            cursor_context,
            enter_method_name,
        ).return_value = cursor

        execute_values_mock.return_value = [
            (True,),
            (False,),
        ]

        transformed_records = [
            tuple(range(18)),
            tuple(range(18)),
            tuple(range(18)),
        ]

        result = load_traffic_records(
            connection=connection,
            transformed_records=transformed_records,
        )

        self.assertEqual(result.records_inserted, 1)
        self.assertEqual(result.records_updated, 1)
        self.assertEqual(result.records_unchanged, 1)

        execute_values_mock.assert_called_once()
        self.assertEqual(
            execute_values_mock.call_args.kwargs["page_size"],
            1000,
        )
        self.assertTrue(
            execute_values_mock.call_args.kwargs["fetch"]
        )