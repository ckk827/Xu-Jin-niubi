"""Small WebEngine reproduction; uses its own page/profile, never business data."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def modules():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    result = {}
    for name in ("msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll", "icuuc.dll", "icuin.dll"):
        handle = kernel.GetModuleHandleW(name)
        if handle:
            buffer = ctypes.create_unicode_buffer(32768)
            kernel.GetModuleFileNameW(handle, buffer, len(buffer))
            result[name] = buffer.value
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    args.folder.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --enable-logging=stderr --v=1")
    os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.debug=true"
    print("before Qt:", json.dumps(modules()), flush=True)
    from qt_runtime import prepare_qt_runtime
    prepare_qt_runtime()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    app = QApplication([])
    view = QWebEngineView()
    profile = QWebEngineProfile(view)
    profile.setCachePath(str(args.folder / "cache"))
    profile.setPersistentStoragePath(str(args.folder / "profile"))
    view.setPage(QWebEnginePage(profile, view))
    view.resize(800, 600)
    view.setWindowTitle("Soulband Qt diagnostic")
    view.show()
    print("after Qt:", json.dumps(modules()), flush=True)
    def rendered(value):
        print("JavaScript:", value, flush=True)
        if value == "Qt renderer OK":
            view.grab().save(str(args.folder / "page.png"))
            app.exit(0)
        else:
            app.exit(23)
    def loaded(ok):
        print("loadFinished:", ok, flush=True)
        if ok:
            view.page().runJavaScript("document.querySelector('h1').textContent", rendered)
        else:
            app.exit(22)
    view.loadFinished.connect(loaded)
    view.page().renderProcessTerminated.connect(lambda status, code: (print("renderer:", status, code, flush=True), app.exit(17)))
    QTimer.singleShot(15000, lambda: app.exit(24))
    view.setHtml("<html><body><h1>Qt renderer OK</h1></body></html>")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
