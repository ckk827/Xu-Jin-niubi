"""Verify the real native window, with Chromium's sandbox enabled and an isolated DB."""
import json
import os
from pathlib import Path
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    folder = ROOT / "tests/.data" / ("native-desktop-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    os.environ["SOULBAND_DB"] = str(folder / "state.sqlite3")
    os.environ["SOULBAND_INITIAL_MODE"] = "unconfigured"
    # Use a visible Windows window, the same platform as normal desktop startup.
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ.pop("QTWEBENGINE_DISABLE_SANDBOX", None)
    os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
    os.environ.pop("QT_OPENGL", None)
    os.environ.pop("QT_QUICK_BACKEND", None)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    import desktop
    import desktop_launcher
    desktop.URL = f"http://127.0.0.1:{port}"
    result = desktop_launcher.launch(ROOT, desktop.URL, port, desktop.ensure_server, smoke_test=True)
    report = json.loads((folder / "desktop-startup.json").read_text(encoding="utf-8"))
    assert result == 0, report
    assert report["renderer"] == "qt" and report["qt_exit_code"] == 0, report
    assert "Qt application UI rendered successfully" in (folder / "desktop.log").read_text(encoding="utf-8")
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "Owned backend was not stopped"
    log = (folder / "desktop.log").read_text(encoding="utf-8")
    graphics = next(json.loads(line.split("Desktop graphics: ", 1)[1]) for line in log.splitlines() if line.startswith("Desktop graphics: "))
    report.update(sandbox_enabled=True, window_platform="windows", forced_software_rendering=False, graphics=graphics, isolated_database=True,
                  backend_stopped=True, artifacts=str(folder))
    (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
