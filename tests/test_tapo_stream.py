import argparse
import unittest
from unittest.mock import Mock, patch

from detect_vehicles import (
    build_tapo_rtsp_url,
    describe_video_source,
    open_video_capture,
    resolve_video_source,
)


class TapoStreamTests(unittest.TestCase):
    def test_build_tapo_rtsp_url_encodes_credentials(self) -> None:
        url = build_tapo_rtsp_url(
            host="192.168.1.41",
            port=554,
            stream_name="stream2",
            username="operador@casa",
            password="p:a/ss?#",
        )

        self.assertEqual(
            url,
            "rtsp://operador%40casa:p%3Aa%2Fss%3F%23@192.168.1.41:554/stream2",
        )

    def test_describe_video_source_removes_credentials(self) -> None:
        description = describe_video_source(
            "rtsp://user:secret@192.168.1.41:554/stream2"
        )

        self.assertEqual(description, "rtsp://192.168.1.41:554/stream2")
        self.assertNotIn("user", description)
        self.assertNotIn("secret", description)

    def test_resolve_video_source_reads_password_without_logging_it(self) -> None:
        args = argparse.Namespace(
            video=None,
            stream=None,
            tapo_host="192.168.1.41",
            tapo_port=554,
            tapo_stream="stream2",
            tapo_username="camera-user",
        )

        source, source_name, source_description = resolve_video_source(
            args, password_reader=lambda _: "secret"
        )

        self.assertIn("camera-user:secret@", source)
        self.assertTrue(source_name.startswith("tapo_"))
        self.assertEqual(
            source_description, "rtsp://192.168.1.41:554/stream2"
        )

    def test_resolve_video_source_rejects_tapo_mixed_with_generic_stream(self) -> None:
        args = argparse.Namespace(
            video=None,
            stream="rtsp://example.test/live",
            tapo_host="192.168.1.41",
            tapo_port=554,
            tapo_stream="stream2",
            tapo_username="camera-user",
        )

        with self.assertRaisesRegex(ValueError, "una sola fuente"):
            resolve_video_source(args, password_reader=lambda _: "secret")

    def test_resolve_video_source_rejects_empty_password(self) -> None:
        args = argparse.Namespace(
            video=None,
            stream=None,
            tapo_host="192.168.1.41",
            tapo_port=554,
            tapo_stream="stream2",
            tapo_username="camera-user",
        )

        with self.assertRaisesRegex(ValueError, "contraseña"):
            resolve_video_source(args, password_reader=lambda _: "")

    @patch("detect_vehicles.cv2.VideoCapture")
    def test_open_video_capture_failure_does_not_reveal_credentials(
        self, video_capture: Mock
    ) -> None:
        video_capture.return_value.isOpened.return_value = False
        authenticated_url = "rtsp://camera-user:secret@192.168.1.41:554/stream2"
        safe_description = "rtsp://192.168.1.41:554/stream2"

        with self.assertRaises(ValueError) as error:
            open_video_capture(authenticated_url, safe_description)

        self.assertIn(safe_description, str(error.exception))
        self.assertNotIn("camera-user", str(error.exception))
        self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
