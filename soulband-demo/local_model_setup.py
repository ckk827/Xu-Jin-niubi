"""Ollama preparation starts only after an explicit host-side button click."""
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()
STATUS = {"running": False, "model": "", "output": [], "error": None, "ready": False}


def status():
    with LOCK:
        return {**STATUS, "output": list(STATUS["output"])}


def start(model):
    with LOCK:
        if STATUS["running"]:
            raise ValueError("本地模型正在准备，请等待当前任务完成")
        STATUS.update(running=True, model=model, output=["正在检查 Ollama 和模型；缺少时开始下载…"],
                      error=None, ready=False)
    def worker():
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "prepare_model.py"), "--model", model],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            with process.stdout:
                for line in process.stdout:
                    with LOCK:
                        STATUS["output"] = (STATUS["output"] + [line.rstrip()])[-25:]
            code = process.wait()
            with LOCK:
                STATUS.update(ready=code == 0,
                              error=None if code == 0 else "本地模型准备失败，请查看下方日志后重试")
        except Exception as exc:
            with LOCK:
                STATUS["error"] = "本地模型准备失败（" + type(exc).__name__ + "）"
        finally:
            with LOCK:
                STATUS["running"] = False
    threading.Thread(target=worker, daemon=True).start()
    return status()
