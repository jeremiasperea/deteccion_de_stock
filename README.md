# DEPOT VISION — Sistema de Conteo en Depósito

Aplicación de escritorio para conteo y clasificación de objetos en tiempo real
usando YOLOv8 + OpenCV + Flet.

## Instalación (Windows)

1. Asegurate de tener Python 3.10 o superior instalado.

2. Abrí una terminal (cmd o PowerShell) en la carpeta del proyecto y ejecutá:

   pip install -r requirements.txt

   La primera vez descarga el modelo YOLOv8n (~6 MB) automáticamente.

3. Ejecutá la app:

   python app.py

## Controles

| Botón         | Acción                                      |
|---------------|---------------------------------------------|
| ▶ Iniciar     | Abre la cámara e inicia la detección        |
| ⏸ Pausar      | Congela el procesamiento (cámara sigue)     |
| ⏹ Detener     | Cierra la cámara                            |
| 💾 Exportar CSV | Guarda el historial en el Escritorio       |

## Objetos detectados

La app detecta las siguientes categorías del modelo COCO:
persona, botella, taza, mochila, valija, silla, laptop, celular, libro, reloj.

Para agregar la clase "box" (cajas de cartón) entrenadas en modelos custom,
reemplazá `yolov8n.pt` por tu modelo `.pt` propio en la línea:
    state.model = YOLO("yolov8n.pt")

## Exportación

El archivo CSV se guarda en el Escritorio con el formato:
    conteo_YYYYMMDD_HHMMSS.csv

Columnas: una por clase + columna `timestamp` (ISO 8601).
