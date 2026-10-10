from __future__ import annotations

import threading
import time
import uuid
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / ".config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(CONFIG_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(CONFIG_DIR / "matplotlib"))

import cv2
import numpy as np
from ultralytics import YOLO

from .counting import CountingEngine, point_in_polygon
from .credentials import get_camera_password
from .database import Database
from .identity import LogicalVehicleManager, VehicleObservation, normalize_plate


EVIDENCE_DIR = PROJECT_ROOT / "data" / "evidence"
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def estimate_color(
    frame: np.ndarray,
    bounds: tuple[int, int, int, int],
    excluded_bounds: list[tuple[int, int, int, int]] | None = None,
) -> str:
    x1, y1, x2, y2 = bounds
    crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
    if crop.size == 0:
        return "desconocido"

    height, width = crop.shape[:2]
    body_y1 = int(height * 0.42)
    body_y2 = max(int(height * 0.82), body_y1 + 1)
    body_x1 = int(width * 0.08)
    body_x2 = max(int(width * 0.92), body_x1 + 1)
    body = crop[body_y1:body_y2, body_x1:body_x2]
    if body.size == 0:
        body = crop
    hsv = cv2.cvtColor(body, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    saturation_channel = hsv[:, :, 1]
    value_channel = hsv[:, :, 2]
    usable = np.ones(hue.shape, dtype=bool)
    sample_x1 = max(0, x1) + body_x1
    sample_y1 = max(0, y1) + body_y1
    for excluded_x1, excluded_y1, excluded_x2, excluded_y2 in excluded_bounds or []:
        overlap_x1 = max(sample_x1, excluded_x1) - sample_x1
        overlap_y1 = max(sample_y1, excluded_y1) - sample_y1
        overlap_x2 = min(sample_x1 + body.shape[1], excluded_x2) - sample_x1
        overlap_y2 = min(sample_y1 + body.shape[0], excluded_y2) - sample_y1
        if overlap_x1 < overlap_x2 and overlap_y1 < overlap_y2:
            usable[overlap_y1:overlap_y2, overlap_x1:overlap_x2] = False
    if int(np.count_nonzero(usable)) < 50:
        usable[:, :] = True

    chromatic = (
        (saturation_channel >= 45)
        & (value_channel >= 25)
        & (value_channel <= 245)
        & usable
    )
    minimum_chromatic = max(50, int(chromatic.size * 0.08))
    if int(np.count_nonzero(chromatic)) >= minimum_chromatic:
        weights = saturation_channel.astype(np.float32) / 255.0
        color_masks = {
            "rojo": chromatic & ((hue < 10) | (hue >= 170)),
            "naranja": chromatic & (hue >= 10) & (hue < 22),
            "amarillo": chromatic & (hue >= 22) & (hue < 35),
            "verde": chromatic & (hue >= 35) & (hue < 85),
            "azul": chromatic & (hue >= 85) & (hue < 135),
            "violeta": chromatic & (hue >= 135) & (hue < 170),
        }
        scores = {
            color: float(np.sum(weights[mask]))
            for color, mask in color_masks.items()
        }
        return max(scores, key=scores.get)

    saturation = float(np.median(saturation_channel[usable]))
    value = float(np.median(value_channel[usable]))
    if value < 65:
        return "negro"
    if saturation < 35 and value > 185:
        return "blanco"
    return "gris"


class CameraEngine:
    def __init__(self, database: Database, dwell_seconds: int = 900):
        self.database = database
        self.counter = CountingEngine(
            dwell_seconds=dwell_seconds, absence_grace_seconds=60
        )
        self.identity = LogicalVehicleManager(
            max_vehicles=self._configured_capacity(), absence_grace_seconds=60
        )
        self.session_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest_jpeg: bytes | None = None
        self._status: dict[str, object] = {
            "state": "not_configured",
            "message": "Configurá la cámara para comenzar.",
            "last_frame_at": None,
            "active_tracks": [],
        }
        self._track_details: dict[int, dict[str, object]] = {}

    def _configured_capacity(self) -> int:
        try:
            value = int(self.database.get_max_concurrent_vehicles())
            return value if value >= 1 else 2
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return 2

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def _thread_main(self) -> None:
        while not self._stop.is_set():
            try:
                self._run()
                return
            except Exception:
                self.counter.pause(time.monotonic())
                self._set_status(
                    state="error",
                    message="El motor encontró un error y volverá a intentar.",
                    active_tracks=self.counter.active_tracks(time.monotonic()),
                )
                if self._stop.wait(5):
                    return

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def restart(self) -> None:
        self.stop()
        self.session_id = uuid.uuid4().hex
        self.counter = CountingEngine(
            dwell_seconds=self.counter.dwell_seconds, absence_grace_seconds=60
        )
        self.identity = LogicalVehicleManager(
            max_vehicles=self._configured_capacity(), absence_grace_seconds=60
        )
        self._track_details.clear()
        self.start()

    def status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._status)

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def _set_status(self, **values: object) -> None:
        with self._lock:
            self._status.update(values)

    def _source(self) -> str | None:
        config = self.database.get_camera_config()
        if not config:
            return None
        password = get_camera_password(str(config["credential_key"]))
        if not password:
            self._set_status(
                state="credentials_required",
                message="Volvé a guardar la contraseña de la cámara.",
            )
            return None
        username = quote(str(config["username"]), safe="")
        encoded_password = quote(password, safe="")
        return (
            f"rtsp://{username}:{encoded_password}@{config['host']}:"
            f"{config['port']}/{config['stream_name']}"
        )

    def _run(self) -> None:
        source = self._source()
        if source is None:
            return
        zone = self.database.get_active_zone()
        polygon = [tuple(point) for point in zone["polygon"]] if zone else None
        zone_id = int(zone["id"]) if zone else None
        self._set_status(state="starting", message="Iniciando detección...")
        model = YOLO(str(PROJECT_ROOT / "yolov8n.pt"))
        plate_model = YOLO(str(PROJECT_ROOT / "models" / "license_plate_detector.pt"))
        from detect_vehicles import create_ocr_reader

        ocr_reader = create_ocr_reader()
        delay = 1.0
        while not self._stop.is_set():
            capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                self._set_status(state="reconnecting", message="Sin conexión. Reintentando...")
                self._stop.wait(delay)
                delay = min(delay * 2, 30)
                continue
            delay = 1.0
            if polygon is None:
                self._set_status(
                    state="zone_required",
                    message="Video conectado. Configurá la zona de trabajo.",
                )
            else:
                self.counter.resume(time.monotonic())
                self._set_status(state="counting", message="Conteo activo")
            try:
                self._read_loop(capture, model, plate_model, ocr_reader, polygon, zone_id)
            finally:
                capture.release()
            if not self._stop.is_set():
                self.counter.pause(time.monotonic())
                self._set_status(state="reconnecting", message="Video interrumpido. Reintentando...")
                self._stop.wait(delay)

    def _read_loop(
        self,
        capture: cv2.VideoCapture,
        model: YOLO,
        plate_model: YOLO,
        ocr_reader: object,
        polygon: list[tuple[float, float]] | None,
        zone_id: int | None,
    ) -> None:
        frame_number = 0
        while not self._stop.is_set():
            ok, frame = capture.read()
            if not ok:
                return
            frame_number += 1
            if (frame_number - 1) % 3 != 0:
                continue
            if polygon is None or zone_id is None:
                encoded, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if encoded:
                    with self._lock:
                        self._latest_jpeg = buffer.tobytes()
                self._set_status(
                    state="zone_required",
                    message="Video conectado. Configurá la zona de trabajo.",
                    last_frame_at=datetime.now().astimezone().isoformat(),
                    active_tracks=[],
                )
                continue
            result = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False,
                conf=0.25,
                classes=list(VEHICLE_CLASSES),
                agnostic_nms=False,
            )[0]
            now = time.monotonic()
            seen: set[int] = set()
            height, width = frame.shape[:2]
            source_frame = frame.copy()
            plate_results: list[dict[str, object]] = []
            if (frame_number - 1) % 90 == 0:
                try:
                    from detect_vehicles import detect_plates_in_frame

                    plate_results, _ = detect_plates_in_frame(
                        image=source_frame,
                        annotated_image=frame,
                        plate_model=plate_model,
                        confidence=0.25,
                        crop_stem=f"live-{frame_number}",
                        ocr_reader=ocr_reader,
                        save_crops=False,
                    )
                except Exception:
                    plate_results = []
            observations: list[VehicleObservation] = []
            details_by_tracker: dict[int, dict[str, object]] = {}
            detections: list[dict[str, object]] = []
            if result.boxes is not None and result.boxes.id is not None:
                for box, track_tensor in zip(result.boxes, result.boxes.id):
                    class_id = int(box.cls.item())
                    if class_id not in VEHICLE_CLASSES:
                        continue
                    tracker_id = int(track_tensor.item())
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().tolist())
                    point = ((x1 + x2) / 2 / width, y2 / height)
                    if not point_in_polygon(point, polygon):
                        continue
                    detections.append(
                        {
                            "tracker_id": tracker_id,
                            "bounds": (x1, y1, x2, y2),
                            "point": point,
                            "class_id": class_id,
                            "confidence": float(box.conf.item()),
                        }
                    )
            for detection in detections:
                tracker_id = int(detection["tracker_id"])
                x1, y1, x2, y2 = detection["bounds"]
                point = detection["point"]
                class_id = int(detection["class_id"])
                confidence = float(detection["confidence"])
                occluders = [
                    other["bounds"]
                    for other in detections
                    if int(other["tracker_id"]) != tracker_id
                    and float(other["point"][1]) > float(point[1]) + 0.12
                ]
                color = estimate_color(
                    source_frame, (x1, y1, x2, y2), occluders
                )
                plate_text = self._plate_for_bounds(
                    plate_results, (x1, y1, x2, y2)
                )
                observations.append(
                    VehicleObservation(
                        tracker_id=tracker_id,
                        bounds=(x1 / width, y1 / height, x2 / width, y2 / height),
                        point=point,
                        confidence=confidence,
                        vehicle_class=VEHICLE_CLASSES[class_id],
                        color_name=color,
                        plate_text=plate_text,
                    )
                )
                details_by_tracker[tracker_id] = {
                    "bounds": (x1, y1, x2, y2),
                    "vehicle_class": VEHICLE_CLASSES[class_id],
                    "color_name": color,
                    "confidence": confidence,
                    "frame": source_frame,
                    "tracker_id": tracker_id,
                }
            for match in self.identity.match_frame(observations, now):
                observation = match.observation
                logical_id = match.logical_vehicle_id
                seen.add(logical_id)
                detail = details_by_tracker[observation.tracker_id]
                detail["identity_key"] = match.identity_key
                previous_detail = self._track_details.get(logical_id, {})
                if observation.plate_text:
                    detail["plate_text"] = observation.plate_text
                    detail["best_plate_frame"] = source_frame
                    detail["best_plate_bounds"] = detail["bounds"]
                else:
                    for key in ("plate_text", "best_plate_frame", "best_plate_bounds"):
                        if key in previous_detail:
                            detail[key] = previous_detail[key]
                self._track_details[logical_id] = detail
                for event in self.counter.update(
                    logical_id, observation.point, now, polygon
                ):
                    self._confirm_service(
                        event.logical_vehicle_id,
                        observation.tracker_id,
                        event.dwell_seconds,
                        zone_id,
                        plate_model,
                        ocr_reader,
                    )
                x1, y1, x2, y2 = detail["bounds"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (29, 78, 216), 2)
                cv2.putText(
                    frame,
                    f"Vehiculo {logical_id}",
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (29, 78, 216),
                    2,
                )
            self.counter.mark_frame_complete(seen, now)
            pixel_polygon = np.array(
                [[int(x * width), int(y * height)] for x, y in polygon], dtype=np.int32
            )
            cv2.polylines(frame, [pixel_polygon], True, (216, 78, 29), 2)
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if encoded:
                with self._lock:
                    self._latest_jpeg = buffer.tobytes()
            self._set_status(
                state="counting",
                message="Conteo activo",
                last_frame_at=datetime.now().astimezone().isoformat(),
                active_tracks=self.counter.active_tracks(now),
            )

    def _confirm_service(
        self,
        logical_vehicle_id: int,
        tracker_id: int,
        dwell_seconds: int,
        zone_id: int,
        plate_model: YOLO,
        ocr_reader: object,
    ) -> None:
        detail = self._track_details.get(logical_vehicle_id)
        if not detail:
            return
        confirmed_at = datetime.now().astimezone()
        day_dir = EVIDENCE_DIR / confirmed_at.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        temp_token = uuid.uuid4().hex
        temp_vehicle = day_dir / f".{temp_token}_vehicle.tmp.jpg"
        if not cv2.imwrite(str(temp_vehicle), detail["frame"]):
            raise OSError("No se pudo guardar la evidencia del servicio")

        plate_text = None
        plate_confidence = None
        plate_crop = None
        try:
            from detect_vehicles import detect_plates_in_frame

            plate_frame = detail.get("best_plate_frame", detail["frame"])
            bounds = detail.get("best_plate_bounds", detail.get("bounds"))
            plate_image = plate_frame
            if isinstance(bounds, tuple) and len(bounds) == 4:
                x1, y1, x2, y2 = map(int, bounds)
                candidate = plate_frame[
                    max(0, y1):max(0, y2), max(0, x1):max(0, x2)
                ]
                if candidate.size:
                    plate_image = candidate
            plate_results, _ = detect_plates_in_frame(
                image=plate_image,
                annotated_image=plate_image.copy(),
                plate_model=plate_model,
                confidence=0.25,
                crop_stem=temp_token,
                ocr_reader=ocr_reader,
                save_crops=False,
            )
            if plate_results:
                best = max(
                    plate_results,
                    key=lambda item: float(item.get("ocr_confidence") or 0),
                )
                if str(best.get("text") or "").strip():
                    plate_text = str(best["text"])
                    plate_confidence = float(best.get("ocr_confidence") or 0)
                plate_crop = best.get("crop")
        except Exception:
            plate_text = None
            plate_confidence = None
            plate_crop = None

        temp_plate = day_dir / f".{temp_token}_plate.tmp.png"
        if plate_crop is not None and not cv2.imwrite(str(temp_plate), plate_crop):
            temp_plate = None

        service_id: int | None = None
        final_paths: list[Path] = []
        try:
            service_id = self.database.create_service(
                work_zone_id=zone_id,
                camera_session_id=self.session_id,
                logical_vehicle_id=str(detail["identity_key"]),
                tracker_id=tracker_id,
                confirmed_at=confirmed_at,
                dwell_seconds=dwell_seconds,
                vehicle_class=str(detail["vehicle_class"]),
                color_name=str(detail["color_name"]),
                plate_text=plate_text,
                detection_confidence=float(detail["confidence"]),
                plate_confidence=plate_confidence,
            )
            image_path = day_dir / f"service_{service_id}_vehicle.jpg"
            temp_vehicle.replace(image_path)
            final_paths.append(image_path)
            self.database.add_evidence(
                service_id,
                "vehicle",
                image_path.relative_to(PROJECT_ROOT).as_posix(),
                confirmed_at,
            )
            if temp_plate is not None:
                plate_path = day_dir / f"service_{service_id}_plate.png"
                temp_plate.replace(plate_path)
                final_paths.append(plate_path)
                self.database.add_evidence(
                    service_id,
                    "plate",
                    plate_path.relative_to(PROJECT_ROOT).as_posix(),
                    confirmed_at,
                )
        except Exception:
            temp_vehicle.unlink(missing_ok=True)
            if temp_plate is not None:
                temp_plate.unlink(missing_ok=True)
            for path in final_paths:
                path.unlink(missing_ok=True)
            if service_id is not None:
                self.database.delete_service(service_id)
            raise

    @staticmethod
    def _plate_for_bounds(
        plate_results: list[dict[str, object]],
        vehicle_bounds: tuple[int, int, int, int],
    ) -> str | None:
        x1, y1, x2, y2 = vehicle_bounds
        candidates: list[tuple[float, str]] = []
        for result in plate_results:
            bounds = result.get("bounds")
            if not isinstance(bounds, tuple) or len(bounds) != 4:
                continue
            px1, py1, px2, py2 = bounds
            center_x = (int(px1) + int(px2)) / 2
            center_y = (int(py1) + int(py2)) / 2
            plate = normalize_plate(str(result.get("text") or ""))
            confidence = float(result.get("ocr_confidence") or 0)
            if plate and confidence >= 0.5 and x1 <= center_x <= x2 and y1 <= center_y <= y2:
                candidates.append((confidence, plate))
        return max(candidates)[1] if candidates else None
