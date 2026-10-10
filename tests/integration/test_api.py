import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from detecta_images.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "api.db"
        self.client = TestClient(create_app(database_path, start_engine=False))

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_directory.cleanup()

    def test_index_and_empty_summary_are_available(self) -> None:
        page = self.client.get("/")
        summary = self.client.get("/api/summary")

        self.assertEqual(page.status_code, 200)
        self.assertIn("DetectaImages", page.text)
        self.assertEqual(summary.json()["final_total"], 0)

    def test_first_camera_configuration_requires_password(self) -> None:
        response = self.client.put(
            "/api/camera",
            json={
                "host": "192.168.1.41",
                "port": 554,
                "stream_name": "stream2",
                "username": "operator",
                "password": None,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertNotIn("operator", response.text)

    def test_camera_rejects_ambiguous_host(self) -> None:
        response = self.client.put(
            "/api/camera",
            json={
                "host": "192.168.1.41@evil.example/path",
                "port": 554,
                "stream_name": "stream2",
                "username": "operator",
                "password": "local-secret",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_zone_requires_camera_configuration(self) -> None:
        response = self.client.put(
            "/api/zone",
            json={
                "points": [
                    {"x": 0.1, "y": 0.1},
                    {"x": 0.9, "y": 0.1},
                    {"x": 0.9, "y": 0.9},
                ],
                "frame_width": 1280,
                "frame_height": 720,
            },
        )

        self.assertEqual(response.status_code, 409)

    @patch("detecta_images.api.save_camera_password")
    def test_camera_zone_and_adjustment_flow(self, save_password) -> None:
        camera = self.client.put(
            "/api/camera",
            json={
                "host": "192.168.1.41",
                "port": 554,
                "stream_name": "stream2",
                "username": "operator",
                "password": "local-secret",
            },
        )
        zone = self.client.put(
            "/api/zone",
            json={
                "points": [
                    {"x": 0.1, "y": 0.1},
                    {"x": 0.9, "y": 0.1},
                    {"x": 0.9, "y": 0.9},
                ],
                "frame_width": 1280,
                "frame_height": 720,
            },
        )
        adjustment = self.client.post(
            "/api/adjustments", json={"delta": 1, "reason": "Servicio omitido"}
        )

        self.assertEqual(camera.status_code, 200)
        self.assertEqual(zone.status_code, 200)
        self.assertEqual(adjustment.status_code, 201)
        self.assertEqual(adjustment.json()["summary"]["final_total"], 1)
        save_password.assert_called_once_with("tapo-main", "local-secret")

    def test_negative_adjustment_is_rejected_at_zero(self) -> None:
        response = self.client.post(
            "/api/adjustments", json={"delta": -1, "reason": "Correccion"}
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("debajo de cero", response.text)

    def test_capacity_can_be_read_and_updated(self) -> None:
        initial = self.client.get("/api/settings")
        updated = self.client.put(
            "/api/settings", json={"max_concurrent_vehicles": 3}
        )

        self.assertEqual(initial.json()["max_concurrent_vehicles"], 2)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["max_concurrent_vehicles"], 3)

    def test_capacity_rejects_zero(self) -> None:
        response = self.client.put(
            "/api/settings", json={"max_concurrent_vehicles": 0}
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
