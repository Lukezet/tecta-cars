import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from detecta_images.database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(
            Path(self.temporary_directory.name) / "detecta_images.db"
        )
        self.database.migrate()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_zone_and_service_survive_reopening_database(self) -> None:
        camera_id = self.database.save_camera_config(
            host="192.168.1.41",
            port=554,
            stream_name="stream2",
            username="operator",
            credential_key="tapo-main",
        )
        zone_id = self.database.replace_active_zone(
            camera_id=camera_id,
            polygon=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9)],
            reference_image_path="references/zone.jpg",
            frame_width=1280,
            frame_height=720,
        )
        self.database.create_service(
            work_zone_id=zone_id,
            camera_session_id="session-1",
            logical_vehicle_id="vehicle-1",
            tracker_id=7,
            confirmed_at=datetime.fromisoformat("2026-10-07T12:00:00-03:00"),
            dwell_seconds=900,
            vehicle_class="car",
            color_name="gris",
            plate_text=None,
            detection_confidence=0.91,
            plate_confidence=None,
        )

        reopened = Database(self.database.path)
        summary = reopened.daily_summary("2026-10-07")

        self.assertEqual(summary["automatic_count"], 1)
        self.assertEqual(summary["adjustment_total"], 0)
        self.assertEqual(summary["final_total"], 1)
        self.assertEqual(len(reopened.list_services("2026-10-07")), 1)

    def test_duplicate_logical_vehicle_in_same_session_is_rejected(self) -> None:
        camera_id = self.database.save_camera_config(
            "192.168.1.41", 554, "stream2", "operator", "tapo-main"
        )
        zone_id = self.database.replace_active_zone(
            camera_id, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9)], None, 1280, 720
        )
        values = dict(
            work_zone_id=zone_id,
            camera_session_id="session-1",
            logical_vehicle_id="vehicle-1",
            tracker_id=7,
            confirmed_at=datetime.fromisoformat("2026-10-07T12:00:00-03:00"),
            dwell_seconds=900,
            vehicle_class="car",
            color_name=None,
            plate_text=None,
            detection_confidence=0.9,
            plate_confidence=None,
        )
        self.database.create_service(**values)

        duplicate = {**values, "tracker_id": 99}
        with self.assertRaisesRegex(ValueError, "ya fue contabilizado"):
            self.database.create_service(**duplicate)

        reused_tracker = {**values, "logical_vehicle_id": "vehicle-2"}
        self.database.create_service(**reused_tracker)
        self.assertEqual(len(self.database.list_services("2026-10-07")), 2)

    def test_capacity_defaults_to_two_and_persists(self) -> None:
        self.assertEqual(self.database.get_max_concurrent_vehicles(), 2)

        self.database.save_max_concurrent_vehicles(3)
        reopened = Database(self.database.path)

        self.assertEqual(reopened.get_max_concurrent_vehicles(), 3)
        with self.assertRaisesRegex(ValueError, "capacidad"):
            reopened.save_max_concurrent_vehicles(0)

    def test_manual_adjustment_requires_reason_and_never_makes_negative_total(self) -> None:
        with self.assertRaisesRegex(ValueError, "motivo"):
            self.database.create_adjustment(1, "   ")
        with self.assertRaisesRegex(ValueError, "debajo de cero"):
            self.database.create_adjustment(-1, "Correccion")

        self.database.create_adjustment(1, "Servicio omitido")
        self.database.create_adjustment(-1, "Correccion de carga")

        self.assertEqual(self.database.daily_summary()["final_total"], 0)


if __name__ == "__main__":
    unittest.main()
