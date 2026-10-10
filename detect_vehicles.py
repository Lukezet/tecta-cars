from __future__ import annotations

import argparse
import getpass
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from collections import Counter
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / ".config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(CONFIG_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(CONFIG_DIR / "matplotlib"))

import cv2
from ultralytics import YOLO


INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"
PLATES_DIR = OUTPUT_DIR / "plates"
VEHICLES_DIR = OUTPUT_DIR / "vehicles"
VIDEOS_DIR = OUTPUT_DIR / "videos"
DEFAULT_PLATE_MODEL = PROJECT_ROOT / "models" / "license_plate_detector.pt"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
PLATE_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def estimate_vehicle_color(image: object, bounds: tuple[int, int, int, int]) -> str:
    x1, y1, x2, y2 = bounds
    height, width = image.shape[:2]
    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)

    box_width = x2 - x1
    box_height = y2 - y1
    if box_width <= 0 or box_height <= 0:
        return "desconocido"

    # Favor the lower central area, where the painted body usually occupies
    # more pixels than windows, background, and surroundings.
    crop = image[
        y1 + int(box_height * 0.35) : y1 + int(box_height * 0.85),
        x1 + int(box_width * 0.08) : x1 + int(box_width * 0.92),
    ]
    if crop.size == 0:
        return "desconocido"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    hue = hsv[:, :, 0]
    color_masks = {
        "negro": value < 70,
        "blanco": (saturation < 35) & (value > 180),
        "gris": (saturation < 45) & (value >= 70) & (value <= 180),
        "rojo": ((hue < 8) | (hue >= 170)) & (saturation > 70) & (value > 60),
        "naranja": (
            (hue >= 8) & (hue < 18) & (saturation > 70) & (value > 70)
        ),
        "amarillo": (
            (hue >= 18) & (hue < 35) & (saturation > 70) & (value > 70)
        ),
        "verde": (
            (hue >= 35) & (hue < 85) & (saturation > 55) & (value > 55)
        ),
        "azul": (
            (hue >= 85) & (hue < 135) & (saturation > 55) & (value > 55)
        ),
        "violeta": (
            (hue >= 135) & (hue < 170) & (saturation > 55) & (value > 55)
        ),
    }
    color_scores = {
        color_name: int(mask.sum()) for color_name, mask in color_masks.items()
    }
    return max(color_scores, key=color_scores.get)


def intersection_over_union(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0

    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / (first_area + second_area - intersection)


def remove_duplicate_detections(
    detections: list[dict[str, object]],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for detection in sorted(
        detections, key=lambda item: float(item["confidence"]), reverse=True
    ):
        duplicate_index = next(
            (
                index
                for index, accepted in enumerate(filtered)
                if intersection_over_union(
                    detection["bounds"], accepted["bounds"]
                )
                >= 0.7
            ),
            None,
        )
        if duplicate_index is None:
            filtered.append(detection)
            continue

        accepted = filtered[duplicate_index]
        if detection["class_name"] == "car" and accepted["class_name"] != "car":
            filtered[duplicate_index] = detection

    return filtered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detecta vehículos en una imagen usando Ultralytics YOLO."
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="Nombre de una imagen dentro de input/. Si se omite, usa la primera.",
    )
    parser.add_argument(
        "--video",
        type=Path,
        help="Ruta de un video para analizar. Puede ser absoluta o relativa a input/.",
    )
    parser.add_argument(
        "--stream",
        help="URL RTSP o HTTP/MJPEG para analizar una camara en vivo.",
    )
    parser.add_argument(
        "--tapo-host",
        help="IP o nombre local de una camara Tapo. La contraseña se solicita de forma oculta.",
    )
    parser.add_argument(
        "--tapo-port",
        type=int,
        default=554,
        help="Puerto RTSP de la camara Tapo (por defecto: 554).",
    )
    parser.add_argument(
        "--tapo-stream",
        choices=("stream1", "stream2"),
        default="stream2",
        help="Calidad RTSP de la camara Tapo (por defecto: stream2).",
    )
    parser.add_argument(
        "--tapo-username",
        help="Usuario de Camera Account de Tapo.",
    )
    parser.add_argument(
        "--model",
        default="yolov8n.pt",
        help="Modelo YOLO de Ultralytics (por defecto: yolov8n.pt).",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.25,
        help="Confianza mínima entre 0 y 1 (por defecto: 0.25).",
    )
    parser.add_argument(
        "--plate-model",
        type=Path,
        default=DEFAULT_PLATE_MODEL,
        help="Modelo YOLO para patentes.",
    )
    parser.add_argument(
        "--plate-confidence",
        type=float,
        default=0.25,
        help="Confianza minima para patentes (por defecto: 0.25).",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Muestra una ventana con el analisis del video en vivo. Presiona q para salir.",
    )
    parser.add_argument(
        "--display-width",
        type=int,
        default=960,
        help="Ancho maximo de la ventana de vista previa (por defecto: 960).",
    )
    parser.add_argument(
        "--display-height",
        type=int,
        default=540,
        help="Alto maximo de la ventana de vista previa (por defecto: 540).",
    )
    parser.add_argument(
        "--frame-step",
        type=int,
        default=1,
        help="Procesa 1 de cada N frames del video (por defecto: 1).",
    )
    parser.add_argument(
        "--video-ocr-interval",
        type=int,
        default=30,
        help="Ejecuta OCR de patentes cada N frames procesados (por defecto: 30).",
    )
    parser.add_argument(
        "--plate-save-cooldown",
        type=int,
        default=90,
        help="Frames minimos antes de guardar otra captura de la misma patente (por defecto: 90).",
    )
    parser.add_argument(
        "--min-ocr-confidence",
        type=float,
        default=0.5,
        help="Confianza OCR minima para guardar una patente de video (por defecto: 0.5).",
    )
    parser.add_argument(
        "--vehicle-save-cooldown",
        type=int,
        default=90,
        help="Frames minimos antes de guardar otro recorte de vehiculo similar (por defecto: 90).",
    )
    parser.add_argument(
        "--min-vehicle-confidence",
        type=float,
        default=0.4,
        help="Confianza minima para guardar recortes de vehiculos en video (por defecto: 0.4).",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        help="Limite opcional de frames procesados para pruebas rapidas.",
    )
    parser.add_argument(
        "--no-save-video",
        action="store_true",
        help="Procesa el video sin guardar una copia MP4 anotada.",
    )
    return parser.parse_args()


def find_input_image(requested_image: Path | None) -> Path:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    if requested_image is not None:
        image_path = requested_image
        if not image_path.is_absolute():
            image_path = INPUT_DIR / image_path
        if not image_path.is_file():
            raise FileNotFoundError(f"No se encontró la imagen: {image_path}")
        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Formato de imagen no soportado: {image_path.suffix}")
        return image_path

    images = sorted(
        path
        for path in INPUT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not images:
        raise FileNotFoundError(
            f"No hay imágenes compatibles en {INPUT_DIR}. "
            "Agregá un archivo JPG, JPEG, PNG, BMP o WEBP."
        )
    return images[0]


def find_video(video_path: Path) -> Path:
    if not video_path.is_absolute():
        video_path = INPUT_DIR / video_path
    if not video_path.is_file():
        raise FileNotFoundError(f"No se encontro el video: {video_path}")
    if video_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(f"Formato de video no soportado: {video_path.suffix}")
    return video_path


def build_tapo_rtsp_url(
    host: str,
    port: int,
    stream_name: str,
    username: str,
    password: str,
) -> str:
    if not host.strip():
        raise ValueError("El host de la camara Tapo no puede estar vacio.")
    if not 1 <= port <= 65535:
        raise ValueError("El puerto de la camara Tapo debe estar entre 1 y 65535.")
    if stream_name not in {"stream1", "stream2"}:
        raise ValueError("El stream de Tapo debe ser stream1 o stream2.")
    if not username:
        raise ValueError("El usuario de Camera Account no puede estar vacio.")
    if not password:
        raise ValueError("La contraseña de Camera Account no puede estar vacia.")

    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")
    return (
        f"rtsp://{encoded_username}:{encoded_password}@"
        f"{host.strip()}:{port}/{stream_name}"
    )


def describe_video_source(source: str) -> str:
    parsed = urlsplit(source)
    if not parsed.scheme or not parsed.hostname:
        return source

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    try:
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
    except ValueError:
        return f"{parsed.scheme}://fuente-con-puerto-invalido"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


def resolve_video_source(
    args: argparse.Namespace,
    password_reader: Callable[[str], str] = getpass.getpass,
) -> tuple[str, str, str]:
    selected_sources = sum(
        source_is_selected
        for source_is_selected in (
            args.video is not None,
            bool(args.stream),
            bool(args.tapo_host),
        )
    )
    if selected_sources != 1:
        raise ValueError(
            "Debes indicar una sola fuente: --video, --stream o --tapo-host."
        )

    if args.video is not None:
        video_path = find_video(args.video)
        source = str(video_path)
        return source, video_path.stem, source

    if args.stream:
        source = args.stream
        return (
            source,
            f"stream_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            describe_video_source(source),
        )

    if not args.tapo_username:
        raise ValueError("Debes indicar --tapo-username para la Camera Account.")
    password = password_reader("Contraseña de Camera Account: ")
    source = build_tapo_rtsp_url(
        host=args.tapo_host,
        port=args.tapo_port,
        stream_name=args.tapo_stream,
        username=args.tapo_username,
        password=password,
    )
    return (
        source,
        f"tapo_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        describe_video_source(source),
    )


def open_video_capture(source: str, source_description: str) -> object:
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise ValueError(
            f"OpenCV no pudo abrir la fuente de video: {source_description}"
        )
    return capture


def collect_vehicle_detections(
    image: object, model: YOLO, confidence: float
) -> list[dict[str, object]]:
    if not 0 <= confidence <= 1:
        raise ValueError("--confidence debe estar entre 0 y 1.")

    results = model.predict(source=image, conf=confidence, verbose=False)
    result = results[0]
    detections: list[dict[str, object]] = []
    if result.boxes is not None:
        for box in result.boxes:
            class_id = int(box.cls.item())
            class_name = result.names[class_id]
            if class_name not in VEHICLE_CLASSES:
                continue

            detections.append(
                {
                    "class_name": class_name,
                    "confidence": float(box.conf.item()),
                    "bounds": tuple(map(int, box.xyxy[0].cpu().tolist())),
                }
            )

    return remove_duplicate_detections(detections)


def annotate_vehicles(
    image: object, detections: list[dict[str, object]]
) -> tuple[object, Counter[str], Counter[str]]:
    counts: Counter[str] = Counter()
    color_counts: Counter[str] = Counter()
    annotated_image = image.copy()
    for detection in detections:
        class_name = str(detection["class_name"])
        confidence_score = float(detection["confidence"])
        x1, y1, x2, y2 = detection["bounds"]
        counts[class_name] += 1
        color_name = estimate_vehicle_color(image, (x1, y1, x2, y2))
        color_counts[color_name] += 1
        cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (0, 200, 0), 2)

        label = f"{class_name} {color_name} {confidence_score:.2f}"
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        )
        label_top = max(y1, text_height + 10)
        cv2.rectangle(
            annotated_image,
            (x1, label_top - text_height - 10),
            (x1 + text_width + 8, label_top),
            (0, 200, 0),
            -1,
        )
        cv2.putText(
            annotated_image,
            label,
            (x1 + 4, label_top - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

    return annotated_image, counts, color_counts


def detect_vehicles(
    image_path: Path, model_name: str, confidence: float
) -> tuple[object, Counter[str], Counter[str]]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"OpenCV no pudo leer la imagen: {image_path}")

    model = YOLO(model_name)
    detections = collect_vehicle_detections(image, model, confidence)
    return annotate_vehicles(image, detections)


def create_ocr_reader() -> object:
    try:
        import easyocr
    except ImportError as error:
        raise RuntimeError(
            "EasyOCR no esta instalado. Ejecuta: "
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from error

    ocr_models_dir = CONFIG_DIR / "easyocr"
    ocr_models_dir.mkdir(parents=True, exist_ok=True)
    return easyocr.Reader(
        ["en"],
        gpu=False,
        model_storage_directory=str(ocr_models_dir),
        user_network_directory=str(ocr_models_dir),
        verbose=False,
    )


def prepare_plate_variants(plate_crop: object) -> list[object]:
    height, width = plate_crop.shape[:2]
    scale = max(2.0, 320 / max(width, 1), 96 / max(height, 1))
    enlarged = cv2.resize(
        plate_crop,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
    bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    main_line = enlarged[int(enlarged.shape[0] * 0.2) : int(enlarged.shape[0] * 0.95)]
    main_gray = cv2.cvtColor(main_line, cv2.COLOR_BGR2GRAY)
    main_clahe = cv2.createCLAHE(2.0, (8, 8)).apply(main_gray)
    _, main_otsu = cv2.threshold(
        main_clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return [enlarged, gray, bilateral, otsu, main_line, main_clahe, main_otsu]


def plate_format_score(text: str) -> int:
    if re.fullmatch(r"[A-Z]{3}[0-9]{3}", text):
        return 2
    if re.fullmatch(r"[A-Z]{2}[0-9]{3}[A-Z]{2}", text):
        return 2
    return 0


def joined_ocr_candidate(results: list[object]) -> tuple[str, float] | None:
    if not results:
        return None

    max_height = max(
        max(point[1] for point in item[0]) - min(point[1] for point in item[0])
        for item in results
    )
    main_results = [
        item
        for item in results
        if max(point[1] for point in item[0]) - min(point[1] for point in item[0])
        >= max_height * 0.65
    ]
    main_results.sort(key=lambda item: min(point[0] for point in item[0]))

    parts: list[str] = []
    confidences: list[float] = []
    for _, text, confidence in main_results:
        normalized = re.sub(r"[^A-Z0-9]", "", text.upper())
        if not normalized or normalized in {"ARGENTINA", "REPUBLICAARGENTINA"}:
            continue
        parts.append(normalized)
        confidences.append(float(confidence))

    joined = "".join(parts)
    if not joined or not confidences:
        return None
    return joined, sum(confidences) / len(confidences)


def find_character_crops(plate_crop: object) -> list[object]:
    height, width = plate_crop.shape[:2]
    main_line = plate_crop[
        int(height * 0.25) : int(height * 0.95),
        int(width * 0.03) : int(width * 0.97),
    ]
    gray = cv2.cvtColor(main_line, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, threshold = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    contours, _ = cv2.findContours(
        threshold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    image_height, image_width = threshold.shape
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if (
            image_height * 0.35 < box_height < image_height * 0.95
            and 3 < box_width < image_width * 0.25
            and area > 40
        ):
            boxes.append((x, y, box_width, box_height))

    boxes.sort()
    if len(boxes) not in {6, 7}:
        return []

    crops: list[object] = []
    for x, y, box_width, box_height in boxes:
        padding = 15
        crop = threshold[
            max(0, y - padding) : min(image_height, y + box_height + padding),
            max(0, x - padding) : min(image_width, x + box_width + padding),
        ]
        crops.append(
            cv2.copyMakeBorder(
                crop, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255
            )
        )
    return crops


def read_single_character(
    ocr_reader: object, character_crop: object, allowlist: str
) -> tuple[str, float] | None:
    results = ocr_reader.readtext(
        character_crop,
        detail=1,
        paragraph=False,
        allowlist=allowlist,
        decoder="beamsearch",
        min_size=5,
        contrast_ths=0.05,
        adjust_contrast=0.7,
    )
    candidates: list[tuple[str, float]] = []
    for _, text, confidence in results:
        normalized = re.sub(f"[^{allowlist}]", "", text.upper())
        if normalized:
            candidates.append((normalized[-1], float(confidence)))
    return max(candidates, key=lambda candidate: candidate[1]) if candidates else None


def segmented_argentine_candidate(
    ocr_reader: object,
    plate_crop: object,
    line_candidates: list[tuple[str, float]],
) -> tuple[str, float] | None:
    character_crops = find_character_crops(plate_crop)
    if len(character_crops) != 6:
        return None

    prefix_candidates = [
        candidate
        for candidate in line_candidates
        if re.match(r"^[A-Z]{3}", candidate[0])
    ]
    if not prefix_candidates:
        return None

    prefix, prefix_confidence = max(
        prefix_candidates, key=lambda candidate: candidate[1]
    )
    digits: list[str] = []
    digit_confidences: list[float] = []
    for character_crop in character_crops[3:]:
        result = read_single_character(ocr_reader, character_crop, "0123456789")
        if result is None:
            return None
        digit, confidence = result
        digits.append(digit)
        digit_confidences.append(confidence)

    text = prefix[:3] + "".join(digits)
    confidence = (prefix_confidence + sum(digit_confidences)) / 4
    return text, confidence


def read_plate_text(
    ocr_reader: object, plate_crop: object
) -> tuple[str, float | None, str]:
    candidates: list[tuple[str, float]] = []
    for prepared in prepare_plate_variants(plate_crop):
        results = ocr_reader.readtext(
            prepared,
            detail=1,
            paragraph=False,
            allowlist=PLATE_CHARACTERS,
            decoder="beamsearch",
            width_ths=1.5,
        )
        joined = joined_ocr_candidate(results)
        if joined is not None and 5 <= len(joined[0]) <= 10:
            candidates.append(joined)
        for _, text, confidence in results:
            normalized = re.sub(r"[^A-Z0-9]", "", text.upper())
            if 5 <= len(normalized) <= 10:
                candidates.append((normalized, float(confidence)))

    if not candidates:
        return "", None, "sin lectura"

    segmented = segmented_argentine_candidate(ocr_reader, plate_crop, candidates)
    if segmented is not None:
        candidates.append(segmented)

    best_text, best_confidence = max(
        candidates,
        key=lambda candidate: (
            plate_format_score(candidate[0]),
            candidate[1],
            len(candidate[0]),
        ),
    )
    method = "segmentado" if segmented == (best_text, best_confidence) else "linea"
    return best_text, best_confidence, method


def detect_plates_in_frame(
    image: object,
    annotated_image: object,
    plate_model: YOLO,
    confidence: float,
    crop_stem: str,
    ocr_reader: object | None,
    start_index: int = 1,
    save_crops: bool = True,
) -> tuple[list[dict[str, object]], int]:
    result = plate_model.predict(source=image, conf=confidence, verbose=False)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return [], start_index

    PLATES_DIR.mkdir(parents=True, exist_ok=True)
    image_height, image_width = image.shape[:2]
    plate_results: list[dict[str, object]] = []
    next_index = start_index

    for box in result.boxes:
        detector_confidence = float(box.conf.item())
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().tolist())
        padding_x = max(2, int((x2 - x1) * 0.04))
        padding_y = max(2, int((y2 - y1) * 0.12))
        crop_x1 = max(0, x1 - padding_x)
        crop_y1 = max(0, y1 - padding_y)
        crop_x2 = min(image_width, x2 + padding_x)
        crop_y2 = min(image_height, y2 + padding_y)
        plate_crop = image[crop_y1:crop_y2, crop_x1:crop_x2]
        if plate_crop.size == 0:
            continue

        crop_path = PLATES_DIR / f"{crop_stem}_plate_{next_index}.png"
        next_index += 1
        if save_crops:
            if not cv2.imwrite(str(crop_path), plate_crop):
                raise OSError(f"No se pudo guardar el recorte: {crop_path}")

        text = ""
        ocr_confidence = None
        ocr_method = "no ejecutado"
        if ocr_reader is not None:
            text, ocr_confidence, ocr_method = read_plate_text(ocr_reader, plate_crop)

        plate_results.append(
            {
                "text": text,
                "detector_confidence": detector_confidence,
                "ocr_confidence": ocr_confidence,
                "ocr_method": ocr_method,
                "bounds": (x1, y1, x2, y2),
                "crop_path": crop_path if save_crops else None,
                "crop": plate_crop,
            }
        )

        cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (255, 100, 0), 2)
        plate_label = f"plate {text or 'sin texto'}"
        cv2.putText(
            annotated_image,
            plate_label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 100, 0),
            2,
            cv2.LINE_AA,
        )

    return plate_results, next_index


def detect_plates(
    image_path: Path,
    annotated_image: object,
    model_path: Path,
    confidence: float,
) -> list[dict[str, object]]:
    if not 0 <= confidence <= 1:
        raise ValueError("--plate-confidence debe estar entre 0 y 1.")
    if not model_path.is_file():
        raise FileNotFoundError(f"No se encontro el modelo de patentes: {model_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"OpenCV no pudo leer la imagen: {image_path}")

    plate_model = YOLO(str(model_path))
    ocr_reader = create_ocr_reader()
    plate_results, _ = detect_plates_in_frame(
        image=image,
        annotated_image=annotated_image,
        plate_model=plate_model,
        confidence=confidence,
        crop_stem=image_path.stem,
        ocr_reader=ocr_reader,
    )
    return plate_results


def print_counts(counts: Counter[str], color_counts: Counter[str]) -> None:
    labels = {
        "car": "car",
        "motorcycle": "motorcycle",
        "bus": "bus",
        "truck": "truck",
    }
    print("Vehículos detectados:")
    for class_name in ("car", "motorcycle", "bus", "truck"):
        print(f"- {labels[class_name]}: {counts[class_name]}")
    print(f"- total: {sum(counts.values())}")
    print("Colores estimados:")
    for color_name, count in color_counts.most_common():
        print(f"- {color_name}: {count}")


def print_plate_results(plate_results: list[dict[str, object]]) -> None:
    if not plate_results:
        print("patente no detectada")
        return

    print("Patentes:")
    for index, result in enumerate(plate_results, start=1):
        text = str(result["text"]) or "texto no reconocido"
        detector_confidence = float(result["detector_confidence"])
        ocr_confidence = result["ocr_confidence"]
        print(
            f"- patente {index}: {text} "
            f"(deteccion: {detector_confidence:.2f})"
        )
        if ocr_confidence is not None:
            print(f"  OCR confidence: {float(ocr_confidence):.2f}")
        print(f"  metodo OCR: {result['ocr_method']}")
        print(f"  recorte: {result['crop_path']}")


def print_video_plate_results(plate_results: list[dict[str, object]]) -> None:
    if not plate_results:
        print("patente no detectada")
        return

    print("Patentes detectadas en video:")
    seen: set[str] = set()
    for result in plate_results:
        text = str(result["text"]) or "texto no reconocido"
        if text == "texto no reconocido" and result["ocr_method"] == "no ejecutado":
            continue
        key = f"{text}:{result['crop_path']}"
        if key in seen:
            continue
        seen.add(key)
        frame_number = int(result["frame_number"])
        detector_confidence = float(result["detector_confidence"])
        print(
            f"- frame {frame_number}: {text} "
            f"(deteccion: {detector_confidence:.2f})"
        )
        if result["ocr_confidence"] is not None:
            print(f"  OCR confidence: {float(result['ocr_confidence']):.2f}")
        print(f"  metodo OCR: {result['ocr_method']}")
        print(f"  recorte: {result['crop_path']}")


def plate_text_similarity(first: str, second: str) -> float:
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


def should_save_video_plate(
    result: dict[str, object],
    saved_results: list[dict[str, object]],
    frame_number: int,
    cooldown_frames: int,
) -> bool:
    text = str(result["text"])
    detector_confidence = float(result["detector_confidence"])
    ocr_confidence = float(result["ocr_confidence"] or 0)

    if not saved_results:
        return True

    best_match: dict[str, object] | None = None
    best_similarity = 0.0
    for saved in saved_results:
        saved_text = str(saved["text"])
        similarity = plate_text_similarity(text, saved_text)
        if text and saved_text and similarity > best_similarity:
            best_similarity = similarity
            best_match = saved

    if best_match is None:
        last_saved_frame = max(int(saved["frame_number"]) for saved in saved_results)
        return frame_number - last_saved_frame >= cooldown_frames

    saved_frame = int(best_match["frame_number"])
    saved_ocr_confidence = float(best_match["ocr_confidence"] or 0)
    saved_detector_confidence = float(best_match["detector_confidence"])
    enough_time_passed = frame_number - saved_frame >= cooldown_frames
    confidence_improved = (
        ocr_confidence > saved_ocr_confidence + 0.12
        or detector_confidence > saved_detector_confidence + 0.15
    )
    return best_similarity < 0.75 or enough_time_passed or confidence_improved


def save_video_plate_result(
    result: dict[str, object],
    video_stem: str,
    frame_number: int,
    plate_index: int,
) -> int:
    crop = result.get("crop")
    if crop is None:
        return plate_index

    PLATES_DIR.mkdir(parents=True, exist_ok=True)
    crop_path = PLATES_DIR / f"{video_stem}_frame_{frame_number:06d}_plate_{plate_index}.png"
    if not cv2.imwrite(str(crop_path), crop):
        raise OSError(f"No se pudo guardar el recorte: {crop_path}")

    result["crop_path"] = crop_path
    return plate_index + 1


def should_save_video_vehicle(
    detection: dict[str, object],
    saved_detections: list[dict[str, object]],
    frame_number: int,
    cooldown_frames: int,
) -> bool:
    if not saved_detections:
        return True

    class_name = str(detection["class_name"])
    bounds = detection["bounds"]
    best_match: dict[str, object] | None = None
    best_iou = 0.0
    for saved in saved_detections:
        if str(saved["class_name"]) != class_name:
            continue
        iou = intersection_over_union(bounds, saved["bounds"])
        if iou > best_iou:
            best_iou = iou
            best_match = saved

    if best_match is None or best_iou < 0.45:
        return True

    enough_time_passed = frame_number - int(best_match["frame_number"]) >= cooldown_frames
    confidence_improved = (
        float(detection["confidence"]) > float(best_match["confidence"]) + 0.15
    )
    return enough_time_passed or confidence_improved


def save_video_vehicle_crop(
    frame: object,
    detection: dict[str, object],
    video_stem: str,
    frame_number: int,
    vehicle_index: int,
) -> tuple[int, Path | None]:
    x1, y1, x2, y2 = detection["bounds"]
    image_height, image_width = frame.shape[:2]
    box_width = x2 - x1
    box_height = y2 - y1
    padding_x = max(4, int(box_width * 0.04))
    padding_y = max(4, int(box_height * 0.04))
    crop_x1 = max(0, x1 - padding_x)
    crop_y1 = max(0, y1 - padding_y)
    crop_x2 = min(image_width, x2 + padding_x)
    crop_y2 = min(image_height, y2 + padding_y)
    crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
    if crop.size == 0:
        return vehicle_index, None

    VEHICLES_DIR.mkdir(parents=True, exist_ok=True)
    class_name = str(detection["class_name"])
    crop_path = (
        VEHICLES_DIR
        / f"{video_stem}_frame_{frame_number:06d}_{class_name}_{vehicle_index}.jpg"
    )
    if not cv2.imwrite(str(crop_path), crop):
        raise OSError(f"No se pudo guardar el recorte: {crop_path}")
    return vehicle_index + 1, crop_path


def process_video(args: argparse.Namespace) -> None:
    source, source_name, source_description = resolve_video_source(args)

    if args.frame_step < 1:
        raise ValueError("--frame-step debe ser 1 o mayor.")
    if args.video_ocr_interval < 1:
        raise ValueError("--video-ocr-interval debe ser 1 o mayor.")
    if args.plate_save_cooldown < 1:
        raise ValueError("--plate-save-cooldown debe ser 1 o mayor.")
    if not 0 <= args.min_ocr_confidence <= 1:
        raise ValueError("--min-ocr-confidence debe estar entre 0 y 1.")
    if args.vehicle_save_cooldown < 1:
        raise ValueError("--vehicle-save-cooldown debe ser 1 o mayor.")
    if not 0 <= args.min_vehicle_confidence <= 1:
        raise ValueError("--min-vehicle-confidence debe estar entre 0 y 1.")
    if args.display_width < 1 or args.display_height < 1:
        raise ValueError("--display-width y --display-height deben ser mayores a 0.")
    if not 0 <= args.confidence <= 1:
        raise ValueError("--confidence debe estar entre 0 y 1.")
    if not 0 <= args.plate_confidence <= 1:
        raise ValueError("--plate-confidence debe estar entre 0 y 1.")
    if not args.plate_model.is_file():
        raise FileNotFoundError(f"No se encontro el modelo de patentes: {args.plate_model}")

    capture = open_video_capture(source, source_description)

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    output_fps = max(1, source_fps / args.frame_step)

    output_path: Path | None = None
    writer = None
    if not args.no_save_video:
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = VIDEOS_DIR / f"{source_name}_detected.mp4"
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            output_fps,
            (width, height),
        )
        if not writer.isOpened():
            capture.release()
            raise OSError(f"No se pudo crear el video de salida: {output_path}")

    vehicle_model = YOLO(args.model)
    plate_model = YOLO(str(args.plate_model))
    ocr_reader = create_ocr_reader()
    processed_frames = 0
    read_frames = 0
    plate_index = 1
    vehicle_index = 1
    latest_plate_results: list[dict[str, object]] = []
    all_plate_results: list[dict[str, object]] = []
    saved_vehicle_results: list[dict[str, object]] = []
    vehicle_frame_totals: Counter[str] = Counter()

    print(f"Fuente de video: {source_description}")
    print(f"Frames totales: {total_frames or 'desconocido'}")
    if output_path is not None:
        print(f"Salida: {output_path}")
    else:
        print("Grabacion de video: deshabilitada")
    if args.display:
        print("Ventana en vivo habilitada. Presiona q para salir.")
        print(f"Vista previa escalada a maximo {args.display_width}x{args.display_height}.")

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        read_frames += 1
        if (read_frames - 1) % args.frame_step != 0:
            continue

        processed_frames += 1
        detections = collect_vehicle_detections(frame, vehicle_model, args.confidence)
        annotated_frame, counts, _ = annotate_vehicles(frame, detections)
        vehicle_frame_totals.update(counts)
        for detection in detections:
            if float(detection["confidence"]) < args.min_vehicle_confidence:
                continue
            if not should_save_video_vehicle(
                detection,
                saved_vehicle_results,
                read_frames,
                args.vehicle_save_cooldown,
            ):
                continue
            vehicle_index, vehicle_crop_path = save_video_vehicle_crop(
                frame,
                detection,
                source_name,
                read_frames,
                vehicle_index,
            )
            if vehicle_crop_path is not None:
                saved_detection = detection.copy()
                saved_detection["frame_number"] = read_frames
                saved_detection["crop_path"] = vehicle_crop_path
                saved_vehicle_results.append(saved_detection)

        run_ocr = (
            processed_frames == 1
            or processed_frames % args.video_ocr_interval == 0
        )
        frame_ocr_reader = ocr_reader if run_ocr else None
        frame_plate_results, plate_index = detect_plates_in_frame(
            image=frame,
            annotated_image=annotated_frame,
            plate_model=plate_model,
            confidence=args.plate_confidence,
            crop_stem=f"{source_name}_frame_{read_frames:06d}",
            ocr_reader=frame_ocr_reader,
            start_index=plate_index,
            save_crops=False,
        )
        for result in frame_plate_results:
            result["frame_number"] = read_frames
        if frame_plate_results:
            latest_plate_results = frame_plate_results
            for result in frame_plate_results:
                if result["ocr_method"] == "no ejecutado":
                    continue
                if float(result["ocr_confidence"] or 0) < args.min_ocr_confidence:
                    continue
                if should_save_video_plate(
                    result,
                    all_plate_results,
                    read_frames,
                    args.plate_save_cooldown,
                ):
                    plate_index = save_video_plate_result(
                        result,
                        source_name,
                        read_frames,
                        plate_index,
                    )
                    all_plate_results.append(result)
        elif latest_plate_results:
            for result in latest_plate_results:
                text = str(result["text"])
                if text:
                    cv2.putText(
                        annotated_frame,
                        f"ultima patente: {text}",
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 100, 0),
                        2,
                        cv2.LINE_AA,
                    )

        progress = (
            f"frame {read_frames}/{total_frames}"
            if total_frames
            else f"frame {read_frames}"
        )
        cv2.putText(
            annotated_frame,
            progress,
            (20, height - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 200, 255),
            2,
            cv2.LINE_AA,
        )
        if writer is not None:
            writer.write(annotated_frame)

        if args.display:
            try:
                display_scale = min(
                    args.display_width / width,
                    args.display_height / height,
                    1.0,
                )
                if display_scale < 1.0:
                    preview_frame = cv2.resize(
                        annotated_frame,
                        (
                            int(width * display_scale),
                            int(height * display_scale),
                        ),
                        interpolation=cv2.INTER_AREA,
                    )
                else:
                    preview_frame = annotated_frame
                cv2.imshow("DetectaImages - video", preview_frame)
                key = cv2.waitKey(1) & 0xFF
            except cv2.error as error:
                print(f"No se pudo abrir la ventana de video: {error}")
                print("Continuo procesando sin --display.")
                args.display = False
                key = -1
            if key == ord("q"):
                break
        if args.max_frames is not None and processed_frames >= args.max_frames:
            break

    capture.release()
    if writer is not None:
        writer.release()
    if args.display:
        cv2.destroyAllWindows()

    print(f"Frames procesados: {processed_frames}")
    unique_vehicle_totals: Counter[str] = Counter(
        str(result["class_name"]) for result in saved_vehicle_results
    )
    print("Vehiculos unicos estimados:")
    for class_name in ("car", "motorcycle", "bus", "truck"):
        print(f"- {class_name}: {unique_vehicle_totals[class_name]}")
    print("Detecciones acumuladas por frame:")
    for class_name in ("car", "motorcycle", "bus", "truck"):
        print(f"- {class_name}: {vehicle_frame_totals[class_name]}")
    print("Recortes de vehiculos guardados:")
    if saved_vehicle_results:
        for result in saved_vehicle_results:
            print(
                f"- frame {result['frame_number']}: {result['class_name']} "
                f"({float(result['confidence']):.2f})"
            )
            print(f"  recorte: {result['crop_path']}")
    else:
        print("- ninguno")
    print_video_plate_results(all_plate_results)


def main() -> None:
    args = parse_args()
    if args.video is not None or args.stream or args.tapo_host:
        process_video(args)
        return

    image_path = find_input_image(args.image)
    annotated_image, counts, color_counts = detect_vehicles(
        image_path=image_path,
        model_name=args.model,
        confidence=args.confidence,
    )
    plate_results = detect_plates(
        image_path=image_path,
        annotated_image=annotated_image,
        model_path=args.plate_model,
        confidence=args.plate_confidence,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{image_path.stem}_detected{image_path.suffix}"
    if not cv2.imwrite(str(output_path), annotated_image):
        raise OSError(f"No se pudo guardar el resultado en: {output_path}")

    print(f"Imagen procesada: {image_path}")
    print(f"Resultado guardado: {output_path}")
    print_counts(counts, color_counts)
    print_plate_results(plate_results)


if __name__ == "__main__":
    main()
