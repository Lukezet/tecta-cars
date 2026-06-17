from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from pathlib import Path


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
DEFAULT_PLATE_MODEL = PROJECT_ROOT / "models" / "license_plate_detector.pt"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
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


def detect_vehicles(
    image_path: Path, model_name: str, confidence: float
) -> tuple[object, Counter[str], Counter[str]]:
    if not 0 <= confidence <= 1:
        raise ValueError("--confidence debe estar entre 0 y 1.")

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"OpenCV no pudo leer la imagen: {image_path}")

    model = YOLO(model_name)
    results = model.predict(source=image, conf=confidence, verbose=False)
    result = results[0]
    counts: Counter[str] = Counter()
    color_counts: Counter[str] = Counter()
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

    annotated_image = image.copy()
    for detection in remove_duplicate_detections(detections):
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
    result = plate_model.predict(source=image, conf=confidence, verbose=False)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return []

    PLATES_DIR.mkdir(parents=True, exist_ok=True)
    ocr_reader = create_ocr_reader()
    image_height, image_width = image.shape[:2]
    plate_results: list[dict[str, object]] = []

    for index, box in enumerate(result.boxes, start=1):
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

        crop_path = PLATES_DIR / f"{image_path.stem}_plate_{index}.png"
        if not cv2.imwrite(str(crop_path), plate_crop):
            raise OSError(f"No se pudo guardar el recorte: {crop_path}")

        text, ocr_confidence, ocr_method = read_plate_text(ocr_reader, plate_crop)
        plate_results.append(
            {
                "text": text,
                "detector_confidence": detector_confidence,
                "ocr_confidence": ocr_confidence,
                "ocr_method": ocr_method,
                "crop_path": crop_path,
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


def main() -> None:
    args = parse_args()
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
