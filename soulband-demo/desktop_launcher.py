"""Supervise the native renderer so a WebEngine crash cannot silently close the app."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


def stop_child(process):
    if process is None or process.poll() is not None:
        return
    if sys.platform == "win32":
        # Only this launcher's own process tree, including the Windows venv redirector.
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        process.terminate()
    process.wait(timeout=10)


def wait_for_renderer(process, ready_file, timeout=20):
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if ready_file.exists():
            return process.wait()
        if time.monotonic() >= deadline:
            stop_child(process)
            return 124
        time.sleep(.1)
    return process.returncode


def find_edge():
    candidates = [Path(os.environ.get(name, "")) / "Microsoft/Edge/Application/msedge.exe"
                  for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    return next((str(path) for path in candidates if path.is_file()), None) or shutil.which("msedge")


def request_browser(url, *, edge=False):
    """Request a normal browser window; OS acceptance is not proof it appeared."""
    if edge:
        executable = find_edge()
        if not executable:
            raise OSError("未找到 Microsoft Edge，请使用默认浏览器或手动打开网址")
        # A normal window also works when Edge's app-mode handoff is ignored.
        process = subprocess.Popen(
            [executable, "--new-window", url],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return
        if code:
            raise OSError(f"Edge 启动命令退出，代码 {code}")
    elif sys.platform == "win32":
        # Let Windows dispatch the URL to the user's default browser. Passing an
        # executable to ShellExecute can succeed without displaying app mode.
        os.startfile(url)
    else:
        import webbrowser
        if not webbrowser.open(url, new=1):
            raise OSError("默认浏览器未接受打开请求")


def open_browser_window(url, folder, smoke_test=False):
    if smoke_test:
        # A native-renderer check must not turn into a successful native result
        # by launching an unrelated browser or weakening Chromium's sandbox.
        raise RuntimeError("Qt 原生界面检查失败；正常启动将使用系统浏览器备用窗口。请查看 desktop.log")
    print("宿伴服务已就绪，浏览器地址：" + url, flush=True)
    print("若没有自动出现页面，请把上面的地址复制到浏览器地址栏。", flush=True)
    use_edge = False
    while True:
        try:
            request_browser(url, edge=use_edge)
            print("已向" + ("Edge 普通窗口" if use_edge else "系统默认浏览器") + "发送打开请求。", flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            # Keep the host alive even if URL associations or Edge fail, so the
            # printed URL remains usable from a manually opened browser.
            print("自动打开失败：" + str(exc), flush=True)
        while True:
            try:
                action = input("保留此控制台。输入 R 重试默认浏览器，E 尝试 Edge；直接回车停止服务：").strip().lower()
            except EOFError:
                # IDEs without an interactive stdin must not kill the host.
                while True:
                    time.sleep(1)
            if action in ("", "q"):
                return
            if action in ("r", "e"):
                use_edge = action == "e"
                break


def launch(root, url, port, ensure_server, *, smoke_test=False, browser=False):
    folder = Path(os.environ.get("SOULBAND_DB", root / "data/soulband.sqlite3")).resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    server = None
    worker = None
    report = {"renderer": None, "qt_exit_code": None, "smoke_test": smoke_test}
    try:
        server = ensure_server()
        if browser:
            report["renderer"] = "browser"
            open_browser_window(url, folder, smoke_test)
            return 0
        ready_file = folder / ("desktop-ready-" + uuid.uuid4().hex)
        qt_temp = folder / "qt-temp"
        qt_temp.mkdir(exist_ok=True)
        environment = {**os.environ, "TEMP": str(qt_temp), "TMP": str(qt_temp), "PYTHONIOENCODING": "utf-8"}
        command = [sys.executable, "-u", str(root / "desktop.py"), "--qt-worker",
                   "--ready-file", str(ready_file), "--port", str(port)]
        if smoke_test:
            command.append("--smoke-test")
        print("正在打开宿伴界面…", flush=True)
        with (folder / "desktop.log").open("ab") as log:
            worker = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=log,
                                      creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            code = wait_for_renderer(worker, ready_file)
        report["qt_exit_code"] = code
        if code == 0:
            if smoke_test and not ready_file.exists():
                raise RuntimeError("Qt 检查进程退出，但页面没有完成加载")
            report["renderer"] = "qt"
            return 0
        report["renderer"] = "browser"
        print(f"Qt 界面未能正常运行（退出码 {code}），正在尝试普通浏览器。", flush=True)
        print("详细日志：" + str(folder / "desktop.log"), flush=True)
        open_browser_window(url, folder, smoke_test)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print("宿伴启动失败：" + str(exc), file=sys.stderr, flush=True)
        return 1
    finally:
        stop_child(worker)
        stop_child(server)
        (folder / "desktop-startup.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
