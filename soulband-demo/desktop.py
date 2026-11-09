"""Windows desktop entry. The local UI is also usable from a regular browser."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from sensing import VERSION
from qt_runtime import prepare_qt_runtime

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765"


def healthy():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            import json
            return json.load(response).get("app") == "soulband-demo"
    except (OSError, ValueError):
        return False


def ensure_server():
    if healthy():
        return None
    (ROOT / "data").mkdir(exist_ok=True)
    output = open(ROOT / "data" / "server.log", "a", encoding="utf-8")
    from urllib.parse import urlsplit
    port = urlsplit(URL).port
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
                               cwd=ROOT, stdout=output, stderr=output,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    output.close()
    for _ in range(100):
        if healthy():
            return process
        if process.poll() is not None:
            break
        time.sleep(.15)
    from desktop_launcher import stop_child
    stop_child(process)
    raise RuntimeError(f"宿主服务未能启动，请检查端口 {port} 与 data/server.log。")


def main():
    global URL
    parser = argparse.ArgumentParser(description="Soulband desktop demo")
    parser.add_argument("--browser", action="store_true", help="Open in the default browser instead of Qt")
    parser.add_argument("--smoke-test", action="store_true", help="Load the desktop UI offscreen, save a screenshot and exit")
    parser.add_argument("--qt-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ready-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    URL = f"http://127.0.0.1:{args.port}"
    if not args.qt_worker:
        from desktop_launcher import launch
        return launch(ROOT, URL, args.port, ensure_server, smoke_test=args.smoke_test, browser=args.browser)
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    prepare_qt_runtime()
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QSystemTrayIcon, QLabel, QStackedWidget
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication(sys.argv[:1])
    app.setApplicationName("宿伴 Soulband")
    try:
        process = ensure_server()
    except RuntimeError as exc:
        QMessageBox.critical(None, "宿伴启动失败", str(exc))
        return 1
    if process:
        app.aboutToQuit.connect(process.terminate)
    window = QMainWindow()
    window.setWindowTitle("宿伴 Soulband · Demo v" + VERSION)
    window.resize(1440, 980)
    window.setMinimumSize(800, 650)
    view = QWebEngineView()
    profile = QWebEngineProfile("SoulbandHost", view)
    profile_folder = Path(os.environ.get("SOULBAND_DB", ROOT / "data/soulband.sqlite3")).resolve().parent
    profile.setCachePath(str(profile_folder / "qt-host-cache"))
    profile.setPersistentStoragePath(str(profile_folder / "qt-host-profile"))
    view.setPage(QWebEnginePage(profile, view))
    stack = QStackedWidget()
    loading = QLabel("宿伴正在加载界面，请稍候…")
    loading.setStyleSheet("background:#f7f5fb;color:#695482;font-size:18px;padding:40px")
    stack.addWidget(loading)
    stack.addWidget(view)
    window.setCentralWidget(stack)
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#7b65ce"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#ffffff"))
    font = painter.font()
    font.setPixelSize(35)
    painter.setFont(font)
    painter.drawText(14, 45, "宿")
    painter.end()
    window.setWindowIcon(QIcon(pixmap))
    tray = QSystemTrayIcon(window.windowIcon(), window)
    tray.setToolTip("宿伴 Soulband")
    tray.show()
    tray.activated.connect(lambda _: window.showNormal())
    seen = set()
    def notifications():
        def received(value):
            if not isinstance(value, list):
                return
            for reminder in value:
                if reminder.get("id") in seen or reminder.get("read") or "pc" not in reminder.get("devices", []):
                    continue
                seen.add(reminder["id"])
                tray.showMessage("宿伴 · 公约提醒", reminder["message"], QSystemTrayIcon.Information, 10000)
                import json
                path = "/reminders/" + reminder["id"] + "/delivered"
                view.page().runJavaScript("api(" + json.dumps(path) + ",'POST',{device:'pc'}).catch(()=>{});")
        view.page().runJavaScript("typeof ui !== 'undefined' && ui.state ? ui.state.reminders : []", received)
    notifier = QTimer(window)
    notifier.timeout.connect(notifications)
    notifier.start(3000)
    window.show()
    loaded = {"ready": False}
    def mark_ready(value):
        if not value or loaded["ready"]:
            return
        loaded["ready"] = True
        if args.ready_file:
            args.ready_file.write_text("ready", encoding="ascii")
        stack.setCurrentWidget(view)
        print("Qt application UI rendered successfully.", flush=True)
    def probe_page():
        if not loaded["ready"]:
            view.page().runJavaScript("typeof ui !== 'undefined' && !!ui.state && !!document.querySelector('h1')", mark_ready)
    startup_timer = QTimer(window)
    startup_timer.timeout.connect(probe_page)
    startup_timer.start(300)
    def renderer_failed(status, code):
        print(f"Qt renderer terminated: {status}, exit code {code}", flush=True)
        app.exit(17)
    view.page().renderProcessTerminated.connect(renderer_failed)
    def load_finished(ok):
        if not ok:
            print("Qt failed to load the application page", flush=True)
            app.exit(18)
    view.loadFinished.connect(load_finished)
    def startup_timeout():
        if not loaded["ready"]:
            print("Qt application page did not become ready within 18 seconds", flush=True)
            app.exit(19)
    QTimer.singleShot(18000, startup_timeout)
    if args.smoke_test:
        result = {"code": 1}
        def captured(ok):
            if not ok:
                app.exit(1)
                return
            def save():
                target = ROOT / "screenshots" / "desktop-window.png"
                target.parent.mkdir(exist_ok=True)
                def verify(payload):
                    import json
                    details = json.loads(payload or "{}")
                    text = details.get("text", "")
                    if not any(marker in (text or "") for marker in ("欢迎回到寝室", "选择你的大模型")):
                        print("Desktop UI did not finish rendering", flush=True)
                        app.exit(1)
                        return
                    window.grab().save(str(target))
                    print("Desktop graphics:", json.dumps(details.get("graphics"), ensure_ascii=False), flush=True)
                    print("Desktop DOM rendered and captured:", target, flush=True)
                    result["code"] = 0
                    app.exit(0)
                view.page().runJavaScript("""JSON.stringify((()=>{
                  const gl=document.createElement('canvas').getContext('webgl');
                  const debug=gl?.getExtension('WEBGL_debug_renderer_info');
                  return {text:document.body.innerText,graphics:{webgl:!!gl,
                    renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):null}};
                })())""", verify)
            QTimer.singleShot(2500, save)
        view.loadFinished.connect(captured)
        QTimer.singleShot(25000, lambda: app.exit(result["code"]))
    view.setUrl(QUrl(URL))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
