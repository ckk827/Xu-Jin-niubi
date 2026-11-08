"""Windows desktop entry. The local UI is also usable from a regular browser."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from sensing import VERSION

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
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8765"],
                               cwd=ROOT, stdout=output, stderr=output,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    output.close()
    for _ in range(100):
        if healthy():
            return process
        if process.poll() is not None:
            break
        time.sleep(.15)
    process.terminate()
    raise RuntimeError("宿主服务未能启动，请检查端口 8765 与 data/server.log。")


def main():
    parser = argparse.ArgumentParser(description="Soulband desktop demo")
    parser.add_argument("--browser", action="store_true", help="Open in the default browser instead of Qt")
    parser.add_argument("--smoke-test", action="store_true", help="Load the desktop UI offscreen, save a screenshot and exit")
    args = parser.parse_args()
    if args.smoke_test:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    if args.browser:
        ensure_server()
        import webbrowser
        webbrowser.open(URL)
        return
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QSystemTrayIcon
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
    view.setUrl(QUrl(URL))
    window.setCentralWidget(view)
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
    if args.smoke_test:
        result = {"code": 1}
        def captured(ok):
            if not ok:
                app.exit(1)
                return
            def save():
                target = ROOT / "screenshots" / "desktop-window.png"
                target.parent.mkdir(exist_ok=True)
                def verify(text):
                    if "欢迎回到寝室" not in (text or ""):
                        print("Desktop UI did not finish rendering", flush=True)
                        app.exit(1)
                        return
                    window.grab().save(str(target))
                    print("Desktop DOM rendered and captured:", target, flush=True)
                    result["code"] = 0
                    app.exit(0)
                view.page().runJavaScript("document.body.innerText", verify)
            QTimer.singleShot(2500, save)
        view.loadFinished.connect(captured)
        QTimer.singleShot(25000, lambda: app.exit(result["code"]))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
