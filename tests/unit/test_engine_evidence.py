import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from detecta_images.engine import CameraEngine


class EngineEvidenceTests(unittest.TestCase):
    def _engine_with_track(self) -> tuple[CameraEngine, Mock]:
        database = Mock()
        engine = CameraEngine(database)
        engine._track_details[1] = {
            "frame": np.zeros((80, 120, 3), dtype=np.uint8),
            "vehicle_class": "car",
            "color_name": "gris",
            "confidence": 0.9,
            "identity_key": "test-vehicle-1",
            "bounds": (0, 0, 120, 80),
        }
        return engine, database

    @patch("detecta_images.engine.cv2.imwrite", return_value=False)
    def test_failed_vehicle_evidence_does_not_create_service(self, _) -> None:
        engine, database = self._engine_with_track()

        with self.assertRaisesRegex(OSError, "evidencia"):
            engine._confirm_service(1, 4, 900, 1, Mock(), Mock())

        database.create_service.assert_not_called()

    def test_recognized_plate_is_persisted_with_both_evidences(self) -> None:
        engine, database = self._engine_with_track()
        database.create_service.return_value = 12
        plate_crop = np.zeros((20, 60, 3), dtype=np.uint8)
        plate_result = {
            "text": "AB123CD",
            "ocr_confidence": 0.88,
            "crop": plate_crop,
        }

        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            with (
                patch("detecta_images.engine.PROJECT_ROOT", temporary_root),
                patch(
                    "detecta_images.engine.EVIDENCE_DIR",
                    temporary_root / "data" / "evidence",
                ),
                patch(
                    "detect_vehicles.detect_plates_in_frame",
                    return_value=([plate_result], 2),
                ),
            ):
                engine._confirm_service(1, 4, 900, 1, Mock(), Mock())

        create_arguments = database.create_service.call_args.kwargs
        self.assertEqual(create_arguments["logical_vehicle_id"], "test-vehicle-1")
        self.assertEqual(create_arguments["plate_text"], "AB123CD")
        self.assertEqual(create_arguments["plate_confidence"], 0.88)
        self.assertEqual(database.add_evidence.call_count, 2)
        database.delete_service.assert_not_called()

    def test_plate_is_assigned_only_when_it_is_inside_vehicle_bounds(self) -> None:
        plate_results = [
            {"text": "AA111AA", "ocr_confidence": 0.99, "bounds": (200, 10, 240, 30)},
            {"text": "AB123CD", "ocr_confidence": 0.80, "bounds": (20, 30, 70, 50)},
        ]

        selected = CameraEngine._plate_for_bounds(
            plate_results, (0, 0, 120, 80)
        )

        self.assertEqual(selected, "AB123CD")


if __name__ == "__main__":
    unittest.main()
