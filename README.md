# DEPOT VISION — Sistema de Conteo en Depósito

Aplicación de escritorio que cuenta y clasifica objetos en tiempo real desde una
cámara, usando YOLOv8 + OpenCV + Flet.

> **Estado actual (2026-10-03): refactor en curso, no listo para producción.**
> El código se está migrando del monolito `app.py` a un paquete con arquitectura
> limpia (`src/depot_vision/`). La prueba manual con cámara real (gate G.1)
> **todavía no pasó**. Seguimiento detallado: [`odd/tasks/clean-architecture-refactor.md`](odd/tasks/clean-architecture-refactor.md).

## Ejecutar la app (Windows, con cámara)

1. Python 3.10 o superior.
2. Instalar dependencias:

   ```
   pip install -r requirements.txt
   ```

3. Ejecutar **con el directorio de trabajo en un disco de Windows** (por ejemplo
   `C:\Users\<usuario>`), no dentro de una ruta `\\wsl.localhost\...`:

   ```
   python <ruta-al-repo>\app.py
   ```

   Desde una ruta de WSL, `ultralytics` falla al importarse porque lee
   `/etc/os-release` del Linux de WSL.

4. La primera vez que se presiona **Iniciar** se descarga `yolov8n.pt` (~6 MB) en
   `src/depot_vision/weights/` (ignorado por git).

## Controles

| Botón | Acción |
|---|---|
| ▶ Iniciar | Abre la cámara e inicia la detección |
| ⏸ Pausar / ▶ Reanudar | Congela o reanuda el procesamiento |
| ⏹ Detener | Detiene la sesión y libera la cámara |
| 💾 Exportar CSV | Guarda el historial en `export_dir` |

## Configuración

Todas las claves son opcionales. Prioridad: **flag de línea de comandos > variable
`DEPOT_VISION_*` > archivo INI > valor por defecto**. Ver
[`depot_vision.ini.example`](depot_vision.ini.example).

| Clave | Default | Flag de ejemplo |
|---|---|---|
| `confidence_threshold` | `0.4` | `--confidence-threshold 0.5` |
| `model_weights` | `yolov8n.pt` | `--model-weights C:\modelos\cajas.pt` |
| `export_dir` | `~` (carpeta de usuario) | `--export-dir "~/Desktop"` |
| `camera_index` | `0` | `--camera-index 1` |
| `frame_width` / `frame_height` | `640` / `480` | `--frame-width 1280` |
| `stop_timeout_s` | `5.0` | `--stop-timeout-s 3` |

Archivo INI: se busca en `$DEPOT_VISION_CONFIG`, luego `./depot_vision.ini`, luego
`~/.config/depot_vision/config.ini` (sección `[depot_vision]`).

> Cambio respecto del monolito: el CSV ya **no** se guarda en el Escritorio por
> defecto, sino en `export_dir` (`~`).

## Exportación

Archivo `conteo_YYYYMMDD_HHMMSS.csv`: una columna por clase + `timestamp`
(ISO 8601, hora local). Se agrega una fila cada 30 frames con detecciones.

## Objetos detectados

Clases COCO: persona, botella, taza, mochila, valija, silla, laptop, celular,
libro, reloj. Para un modelo propio (por ejemplo cajas), usar `model_weights` con
la ruta absoluta al `.pt`.

## Arquitectura

```
src/depot_vision/
├── domain/        Reglas puras: conteo, sesión, reintentos, eventos, config
├── ports/         Interfaces (Protocols) que el dominio y la aplicación usan
├── application/   SessionController, capture_loop (orquestación de la sesión)
├── adapters/      OpenCV, Ultralytics, pandas, bus de eventos, reloj, config
└── presentation/  Vista Flet, renderer de eventos, composición (flet_app.run)
```

Las dependencias van solo hacia adentro: `presentation > application | adapters >
ports > domain`. Lo verifica `import-linter` y un test de reglas de dependencia.

`app.py` hoy solo delega en `depot_vision.presentation.flet_app.run()`; el código
viejo del monolito sigue en el archivo pero sin usarse (se elimina en la tarea T6).

## Desarrollo (Linux / WSL)

```
python3 -m venv .venv-linux
.venv-linux/bin/pip install -r requirements-dev.txt -r requirements-ci.txt
.venv-linux/bin/pytest -q
.venv-linux/bin/ruff check .
.venv-linux/bin/mypy
PYTHONPATH=src .venv-linux/bin/lint-imports
```

Los tests no usan cámara, red ni pesos reales (todo se inyecta con fakes).

## Estado del refactor

| Etapa | Qué | Rama | Estado |
|---|---|---|---|
| T1b | Dominio: config, eventos, frames | `refactor/ca-1b-domain` | ✅ |
| T2 | Ports + config en capas | `refactor/ca-2-ports` | ✅ |
| T3a/T3b | Adapters (cámara, YOLO, CSV, etc.) | `refactor/ca-3a-adapters`, `refactor/ca-3b-adapters` | ✅ |
| T4a/T4b | Controller, capture loop, bus de eventos | `refactor/ca-4a-controller`, `refactor/ca-4b-loop` | ✅ |
| T5a/T5b | Presentación Flet + recableado de `app.py` | `refactor/ca-5a-presentation`, `refactor/ca-5b-wiring` | ✅ código / ❌ prueba manual |
| G.1 | Prueba con cámara real | — | ❌ falló, a diagnosticar |
| T6 | `app.py` mínimo, limpieza final | — | ⏳ bloqueado por G.1 |

Las ramas están apiladas (cada una parte de la anterior). `main` todavía tiene el
monolito original.

## Próximo paso

Diagnosticar qué falló en la prueba manual (G.1) y corregirlo antes de T6.
