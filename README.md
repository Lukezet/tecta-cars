# Detector de vehiculos y patentes

Prototipo en Python que usa Ultralytics YOLO, OpenCV y EasyOCR para:

- detectar autos, motos, buses y camiones;
- estimar el color de los vehiculos;
- localizar patentes con un segundo modelo YOLO;
- guardar recortes de las patentes;
- intentar leer el texto con OCR.

La imagen anotada se guarda en `output/`. Los recortes de patentes se guardan
en `output/plates/`.

## Requisitos

- Python 3.10 o superior.
- Conexion a internet en la primera ejecucion de EasyOCR.
- Modelo de vehiculos `yolov8n.pt`.
- Modelo de patentes `models/license_plate_detector.pt`.

## Instalacion

En PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ejecucion

Coloca una imagen JPG, JPEG, PNG, BMP o WEBP dentro de `input/` y ejecuta:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --image calle.jpg
```

Si omites `--image`, se procesa la primera imagen de `input/` en orden
alfabetico.

La confianza de vehiculos y patentes se configura por separado:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --image calle.jpg --confidence 0.4 --plate-confidence 0.35
```

Tambien se puede usar otro modelo YOLO de patentes:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --image calle.jpg --plate-model models\otro_modelo.pt
```

## Salidas

- `output/<imagen>_detected.<extension>`: vehiculos y patentes anotados.
- `output/plates/<imagen>_plate_<numero>.png`: recortes de patentes.
- Consola: conteos, colores, texto OCR y confianzas.

El OCR es una estimacion. Patentes pequenas, borrosas, tapadas o con mucha
perspectiva pueden detectarse sin que el texto se lea correctamente.

El flujo de patentes es:

1. detectar la patente en la imagen completa;
2. recortar y guardar la region detectada;
3. ampliar, mejorar contraste y binarizar el recorte;
4. leer la linea completa con EasyOCR;
5. si el formato argentino queda incompleto, segmentar caracteres y recomponer
   formatos `ABC123` o `AB123CD`.
