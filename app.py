"""
Sistema de Conteo y Clasificación de Objetos en Depósito
Flet 0.85.1 + YOLOv8 + OpenCV
pip install flet ultralytics opencv-python pandas
"""

import flet as ft
from flet import (
    Page, Image, Text, Column, Row, Container, ElevatedButton,
    Divider, ScrollMode, CrossAxisAlignment, MainAxisAlignment,
    FontWeight, TextAlign, BoxFit, AnimationCurve, Animation,
    Border, BorderSide, Padding, ButtonStyle, RoundedRectangleBorder,
)
import cv2, pandas as pd, time, os, traceback, asyncio, threading
from datetime import datetime
from collections import defaultdict
from ultralytics import YOLO

TARGET_CLASSES = {
    "person":     "👤 Persona",
    "bottle":     "🍶 Botella",
    "cup":        "☕ Taza",
    "backpack":   "🎒 Mochila",
    "suitcase":   "🧳 Valija",
    "chair":      "🪑 Silla",
    "laptop":     "💻 Laptop",
    "cell phone": "📱 Celular",
    "book":       "📚 Libro",
    "clock":      "⏰ Reloj",
}
CLASS_COLORS = {
    "person":     (255, 100,  50),
    "bottle":     ( 50, 200, 255),
    "cup":        (100, 255, 150),
    "backpack":   (200,  50, 255),
    "suitcase":   (255, 200,  50),
    "chair":      ( 50, 255, 200),
    "laptop":     (255,  50, 200),
    "cell phone": (150, 255,  50),
    "book":       ( 50, 150, 255),
    "clock":      (255, 150,  50),
}

class AppState:
    def __init__(self):
        self.running     = False
        self.paused      = False
        self.history     = []
        self.fps         = 0.0
        self.frame_count = 0
        self.cap         = None
        # cola de actualizaciones de UI para el hilo secundario
        self.ui_queue    = []
        self.ui_lock     = threading.Lock()

state = AppState()

def border_all(w, c):
    s = BorderSide(w, c)
    return Border(top=s, bottom=s, left=s, right=s)


# ─── Hilo de detección (threading.Thread puro, sin tocar UI) ─────────────────
def detection_worker(img_ctrl, stats_col, fps_text,
                     detect_log, btn_start, btn_pause):
    """
    Corre en un threading.Thread normal.
    No llama page.update() — encola cambios en state.ui_queue.
    El loop async en main() drena la cola y llama page.update().
    """

    def enqueue(fn):
        with state.ui_lock:
            state.ui_queue.append(fn)

    def log(msg, color="#aaaacc"):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        def _update():
            entry = Text(f"[{ts}] {msg}", size=11,
                         font_family="monospace", color=color)
            detect_log.controls = [entry] + detect_log.controls[:200]
        enqueue(_update)

    try:
        log("▶ Hilo de detección iniciado", "#66ff99")
        log("⏳ Cargando modelo YOLOv8n...")

        model = YOLO("yolov8n.pt")
        log("✅ Modelo cargado", "#66ff99")

        log("📷 Abriendo cámara (índice 0)...")
        state.cap = cv2.VideoCapture(0)
        state.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        state.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not state.cap.isOpened():
            log("❌ No se pudo abrir la cámara.", "#ff4444")
            def _restore():
                btn_start.disabled = False
                btn_pause.disabled = True
            enqueue(_restore)
            state.running = False
            return

        w = int(state.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(state.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        log(f"✅ Cámara abierta {w}x{h}", "#66ff99")
        log("🔄 Loop de detección activo...")

        prev_time = time.time()

        while state.running:
            if state.paused:
                time.sleep(0.05)
                continue

            ret, frame = state.cap.read()
            if not ret:
                log("⚠️ Frame vacío, reintentando...", "#ffaa00")
                time.sleep(0.1)
                continue

            results = model(frame, verbose=False)[0]
            counts  = defaultdict(int)

            for box in results.boxes:
                cls_id = int(box.cls[0])
                label  = model.names[cls_id]
                conf   = float(box.conf[0])
                if label in TARGET_CLASSES and conf > 0.4:
                    counts[label] += 1
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    color = CLASS_COLORS.get(label, (200, 200, 200))
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    tag = f"{TARGET_CLASSES[label].split()[-1]} {conf:.0%}"
                    cv2.rectangle(frame, (x1, y1-22),
                                  (x1+len(tag)*9, y1), color, -1)
                    cv2.putText(frame, tag, (x1+3, y1-5),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.55, (10,10,10), 1)

            now = time.time()
            state.fps = 1.0 / max(now - prev_time, 1e-9)
            prev_time = now
            state.frame_count += 1
            cv2.putText(frame, f"FPS: {state.fps:.1f}", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,120), 2)

            _, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            frame_bytes = bytes(buf)

            total = sum(counts.values())

            # Capturar para closure
            _fb    = frame_bytes
            _fps   = state.fps
            _fc    = state.frame_count
            _cnt   = dict(counts)
            _total = total

            def _update_ui(fb=_fb, fps=_fps, fc=_fc,
                           cnt=_cnt, total=_total):
                img_ctrl.src    = fb
                fps_text.value  = f"⚡ {fps:.1f} FPS  •  🖼 Frame #{fc}"

                cards = []
                for lbl, display in TARGET_CLASSES.items():
                    n = cnt.get(lbl, 0)
                    emoji, name = display.split(" ", 1)
                    cards.append(Container(
                        content=Column([
                            Text(emoji, size=20,
                                 text_align=TextAlign.CENTER),
                            Text(str(n), size=26,
                                 weight=FontWeight.BOLD,
                                 color="#4a9eff" if n>0 else "#555577",
                                 text_align=TextAlign.CENTER),
                            Text(name, size=10, color="#8888aa",
                                 text_align=TextAlign.CENTER),
                        ], spacing=2,
                           horizontal_alignment=CrossAxisAlignment.CENTER),
                        bgcolor="#1e3a5f" if n>0 else "#1a1a2e",
                        border=border_all(
                            1, "#4a9eff" if n>0 else "#2a2a4a"),
                        border_radius=10,
                        padding=Padding(left=8, top=8, right=8, bottom=8),
                        width=88,
                        animate=Animation(200, AnimationCurve.EASE_OUT),
                    ))
                cards.append(Container(
                    content=Column([
                        Text("∑", size=20, text_align=TextAlign.CENTER,
                             color="#f0b429"),
                        Text(str(total), size=26,
                             weight=FontWeight.BOLD,
                             color="#f0b429",
                             text_align=TextAlign.CENTER),
                        Text("TOTAL", size=10, color="#8888aa",
                             text_align=TextAlign.CENTER),
                    ], spacing=2,
                       horizontal_alignment=CrossAxisAlignment.CENTER),
                    bgcolor="#1e2a0a",
                    border=border_all(1, "#f0b429"),
                    border_radius=10,
                    padding=Padding(left=8, top=8, right=8, bottom=8),
                    width=88,
                    animate=Animation(200, AnimationCurve.EASE_OUT),
                ))
                stats_col.controls = [
                    Row(cards, wrap=True, spacing=6, run_spacing=6)]

            enqueue(_update_ui)

            # Log detección cada 30 frames
            if state.frame_count % 30 == 0 and total > 0:
                ts    = datetime.now().strftime("%H:%M:%S")
                parts = [f"{TARGET_CLASSES[k].split()[-1]}:{v}"
                         for k, v in counts.items() if v > 0]
                state.history.append(
                    {**dict(counts),
                     "timestamp": datetime.now().isoformat()})
                log(f"📦 [{ts}] " + "  ".join(parts), "#aaffcc")

            time.sleep(0.03)  # ~30 fps max

    except Exception:
        err = traceback.format_exc()
        for line in err.strip().split("\n"):
            log(f"💥 {line}", "#ff4444")
        state.running = False

    finally:
        if state.cap:
            state.cap.release()
            log("📷 Cámara liberada.", "#888899")

        def _restore():
            state.running      = False
            btn_start.disabled = False
            btn_pause.disabled = True
            btn_pause.text     = "⏸ Pausar"
            fps_text.value     = "⚡ -- FPS"
            img_ctrl.src = (
                "https://placehold.co/"
                "640x480/0d0d1a/333366?text=Detenido")

        enqueue(_restore)
        log("⏹ Hilo finalizado.", "#888899")


# ─── Main ────────────────────────────────────────────────────────────────────
def main(page: Page):
    page.title         = "Sistema de Conteo en Depósito"
    page.bgcolor       = "#0d0d1a"
    page.window.width  = 1200
    page.window.height = 800
    page.padding       = 0
    page.fonts         = {"monospace": "Consolas"}

    header = Container(
        content=Row([
            Column([
                Text("DEPOT VISION", size=20, weight=FontWeight.BOLD,
                     color="#4a9eff", font_family="monospace"),
                Text("Conteo y Clasificación en Depósito · YOLOv8 + Flet",
                     size=11, color="#555577"),
            ], spacing=2),
        ]),
        bgcolor="#111128",
        padding=Padding(left=20, top=12, right=20, bottom=12),
        border=Border(bottom=BorderSide(1, "#1e1e3a")),
    )

    img_ctrl = Image(
        src="https://placehold.co/640x480/0d0d1a/333366?text=Presiona+Iniciar",
        width=640, height=480,
        fit=BoxFit.CONTAIN,
        border_radius=8,
    )
    cam_container = Container(
        content=img_ctrl,
        bgcolor="#0a0a18",
        border=border_all(1, "#1e1e3a"),
        border_radius=10,
        padding=4,
    )

    fps_text  = Text("⚡ -- FPS", size=11, color="#555577",
                     font_family="monospace")
    stats_col = Column(
        [Text("Presioná Iniciar para comenzar.", size=12, color="#555577")],
        spacing=8,
    )
    detect_log = Column([], spacing=1, scroll=ScrollMode.AUTO)
    log_container = Container(
        content=Column([
            Text("🛠 LOG DE SISTEMA", size=10, color="#555577",
                 font_family="monospace"),
            Divider(height=1, color="#1e1e3a"),
            detect_log,
        ], spacing=4),
        bgcolor="#08080f",
        border=border_all(1, "#1e1e3a"),
        border_radius=8,
        padding=10,
        height=240,
    )

    btn_start = ElevatedButton("▶ Iniciar",
        style=ButtonStyle(bgcolor={"": "#1a3a6a", "hovered": "#1e4a8a"},
            color="#4a9eff", shape=RoundedRectangleBorder(radius=6),
            side=BorderSide(1, "#2a5aaa")))
    btn_pause = ElevatedButton("⏸ Pausar", disabled=True,
        style=ButtonStyle(bgcolor={"": "#1a2a1a", "hovered": "#1e3a1e"},
            color="#44cc88", shape=RoundedRectangleBorder(radius=6),
            side=BorderSide(1, "#2a6a3a")))
    btn_stop = ElevatedButton("⏹ Detener",
        style=ButtonStyle(bgcolor={"": "#2a1a1a", "hovered": "#3a1e1e"},
            color="#ff6644", shape=RoundedRectangleBorder(radius=6),
            side=BorderSide(1, "#6a2a2a")))
    btn_export = ElevatedButton("💾 Exportar CSV",
        style=ButtonStyle(bgcolor={"": "#1a1a0a", "hovered": "#2a2a0e"},
            color="#f0b429", shape=RoundedRectangleBorder(radius=6),
            side=BorderSide(1, "#6a5a0a")))

    # ── Loop async que drena la cola de UI ───────────────────────────────
    async def ui_loop():
        while True:
            with state.ui_lock:
                pending = list(state.ui_queue)
                state.ui_queue.clear()
            if pending:
                for fn in pending:
                    try:
                        fn()
                    except Exception as ex:
                        print(f"UI update error: {ex}")
                try:
                    page.update()
                except Exception:
                    pass
            await asyncio.sleep(0.03)

    def on_start(e):
        if state.running:
            return
        state.running     = True
        state.paused      = False
        state.frame_count = 0
        state.history.clear()
        btn_start.disabled = True
        btn_pause.disabled = False

        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        detect_log.controls = [
            Text(f"[{ts}] ⏳ Iniciando...",
                 size=11, font_family="monospace", color="#ffcc44")
        ]
        page.update()

        # Lanzar hilo de detección (threading puro, no bloqueante)
        t = threading.Thread(
            target=detection_worker,
            args=(img_ctrl, stats_col, fps_text,
                  detect_log, btn_start, btn_pause),
            daemon=True,
        )
        t.start()

        # Lanzar loop async de UI
        page.run_task(ui_loop)

    def on_pause(e):
        if not state.running:
            return
        state.paused   = not state.paused
        btn_pause.text = "▶ Reanudar" if state.paused else "⏸ Pausar"
        page.update()

    def on_stop(e):
        state.running = False

    def on_export(e):
        if not state.history:
            page.show_dialog(ft.SnackBar(
                content=Text("No hay datos para exportar aún."),
                open=True))
            return
        fname = f"conteo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path  = os.path.join(os.path.expanduser("~"), "Desktop", fname)
        pd.DataFrame(state.history).fillna(0).to_csv(path, index=False)
        page.show_dialog(ft.SnackBar(
            content=Text(f"✅ Exportado: {fname}"), open=True))

    btn_start.on_click  = on_start
    btn_pause.on_click  = on_pause
    btn_stop.on_click   = on_stop
    btn_export.on_click = on_export

    right_panel = Container(
        content=Column([
            fps_text,
            Divider(height=1, color="#1e1e3a"),
            Text("OBJETOS DETECTADOS", size=10, color="#333355",
                 font_family="monospace"),
            stats_col,
            Divider(height=1, color="#1e1e3a"),
            log_container,
        ], spacing=10, scroll=ScrollMode.AUTO),
        bgcolor="#111128",
        border=border_all(1, "#1e1e3a"),
        border_radius=10,
        padding=14,
        expand=True,
    )

    body = Container(
        content=Column([
            Row([
                Column([
                    cam_container,
                    Row([btn_start, btn_pause, btn_stop, btn_export],
                        spacing=8),
                ], spacing=10),
                right_panel,
            ], spacing=12,
               vertical_alignment=CrossAxisAlignment.START,
               expand=True),
        ], expand=True),
        padding=Padding(left=14, top=14, right=14, bottom=14),
        expand=True,
    )

    page.add(header, body)


ft.app(main)
