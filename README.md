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

EasyOCR instala `opencv-python-headless`, que no permite abrir ventanas. Si vas
a usar `--display`, ejecuta una vez:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python-headless
.\.venv\Scripts\python.exe -m pip install --force-reinstall "opencv-python>=4.9,<5"
```

## Ejecucion de imagenes

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

## Ejecucion de videos

Para procesar un video y guardar una copia anotada:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --video C:\ruta\video.mp4
```

El video resultante queda en `output/videos/`.

## Ejecucion con camara/stream

Tambien se puede analizar una camara en vivo si el celular o camara IP expone
una URL RTSP o HTTP/MJPEG.

Ejemplo RTSP generico (solo para fuentes sin autenticacion):

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --stream "rtsp://192.168.1.50:554/live" --display
```

No incluyas usuario y contraseña en `--stream`: quedarian visibles en el historial
y en la lista de procesos. Para la Tapo usa el helper seguro descripto debajo.

Ejemplo HTTP/MJPEG:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --stream "http://192.168.1.50:8080/video" --display
```

Con el helper:

```powershell
.\run_video.ps1 -Stream "http://192.168.1.50:8080/video"
```

El celular y la PC deben estar en la misma red Wi-Fi, salvo que configures VPN
o redireccionamiento seguro.

### Camara Tapo C510W

La Tapo debe tener una `Camera Account` habilitada desde la aplicacion. Para usar
el flujo secundario sin exponer la contraseña en el historial de PowerShell:

```powershell
.\run_tapo.ps1 -CameraUsername "usuario-de-camara"
```

El helper usa `192.168.1.41:554/stream2`, solicita la contraseña de forma oculta,
muestra el analisis en vivo y no guarda un MP4 continuo. Presiona `q` para salir.
La contraseña no debe escribirse en el comando, en este README ni en archivos del
repositorio.

Para una prueba corta de 10 cuadros:

```powershell
.\run_tapo.ps1 -CameraUsername "usuario-de-camara" -MaxFrames 10
```

Si cambia la IP asignada por el router:

```powershell
.\run_tapo.ps1 -HostAddress "192.168.1.50" -CameraUsername "usuario-de-camara"
```

Para ver el analisis en vivo mientras procesa:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --video C:\ruta\video.mp4 --display
```

Presiona `q` en la ventana para cortar el procesamiento.
La vista previa se escala por defecto a un maximo de `960x540`, sin cambiar el
video guardado. Si necesitas otro tamano:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --video C:\ruta\video.mp4 --display --display-width 800 --display-height 450
```

Para evitar comandos largos, tambien podes usar el helper de PowerShell:

```powershell
.\run_video.ps1
```

PowerShell no continua una linea solo porque empieza con `--`. Si queres partir
un comando largo en varias lineas, cada linea intermedia debe terminar con
backtick:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py `
  --video "C:\Users\NB138\Downloads\20260613_093125.mp4" `
  --display `
  --display-width 800 `
  --display-height 450 `
  --frame-step 5 `
  --video-ocr-interval 10 `
  --plate-save-cooldown 150 `
  --min-ocr-confidence 0.65
```

Opciones utiles para video:

```powershell
.\.venv\Scripts\python.exe detect_vehicles.py --video C:\ruta\video.mp4 --frame-step 2 --video-ocr-interval 30
```

- `--frame-step 2`: procesa 1 de cada 2 frames para acelerar.
- `--video-ocr-interval 30`: intenta leer patentes cada 30 frames procesados.
- `--plate-save-cooldown 90`: evita guardar demasiadas capturas repetidas de la misma patente.
- `--min-ocr-confidence 0.5`: descarta lecturas OCR muy debiles en video.
- `--vehicle-save-cooldown 90`: evita guardar demasiadas capturas repetidas del mismo vehiculo.
- `--min-vehicle-confidence 0.4`: confianza minima para guardar recortes de vehiculos.
- `--max-frames 100`: procesa solo 100 frames para pruebas rapidas.

Para pruebas iniciales suele alcanzar con guardar una captura buena por patente.
Un valor razonable es `--plate-save-cooldown 90` a `150`, y subir
`--video-ocr-interval` si la computadora trabaja muy lento.

## Salidas

- `output/<imagen>_detected.<extension>`: vehiculos y patentes anotados.
- `output/videos/<video>_detected.mp4`: video anotado.
- `output/plates/<imagen>_plate_<numero>.png`: recortes de patentes.
- `output/vehicles/<video>_frame_<numero>_<clase>_<numero>.jpg`: recortes de vehiculos en video.
- Consola: conteos, colores, texto OCR y confianzas. En video se informan
  primero los vehiculos unicos estimados y luego las detecciones acumuladas por
  frame como metrica tecnica.

El OCR es una estimacion. Patentes pequenas, borrosas, tapadas o con mucha
perspectiva pueden detectarse sin que el texto se lea correctamente.

## Aplicacion de conteo local

La interfaz web local guarda la zona, los servicios y los ajustes en SQLite. Para
iniciarla:

```powershell
.\run_app.ps1
```

Luego abri `http://127.0.0.1:8000`. En **Configuracion**, guarda la IP, usuario y
contraseña de `Camera Account`; la contraseña se almacena mediante el gestor seguro
de Windows. Cuando la camara vuelva a estar en la misma red, configura la zona sobre
el video y deja la camara fija, sin patrullaje.

La API y la interfaz escuchan solamente en `127.0.0.1`: no estan expuestas a otras
PCs ni a Internet.

El flujo de patentes es:

1. detectar la patente en la imagen completa;
2. recortar y guardar la region detectada;
3. ampliar, mejorar contraste y binarizar el recorte;
4. leer la linea completa con EasyOCR;
5. si el formato argentino queda incompleto, segmentar caracteres y recomponer
   formatos `ABC123` o `AB123CD`.
