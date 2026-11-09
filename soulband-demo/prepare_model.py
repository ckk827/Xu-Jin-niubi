"""Prepare an isolated official Ollama runtime; no installer, PATH edits or services."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import time
import urllib.request
import zipfile

import certifi

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT.parent / "output" / "runtime" / "ollama"


def open_download(url, timeout=30):
    # Keep system/enterprise roots, and supplement Anaconda's default CA store.
    # Apply the same verified context to GitHub's redirected release assets.
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return urllib.request.urlopen(url, timeout=timeout, context=context)


def request(url, data=None, timeout=30):
    body = None if data is None else json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"User-Agent": "Soulband-local-setup", "Content-Type": "application/json"}), timeout=timeout) as response:
        return json.load(response)


def ensure_service():
    try:
        return request("http://127.0.0.1:11434/api/tags", timeout=2)
    except OSError:
        pass
    exe = shutil.which("ollama") or str(RUNTIME / "ollama.exe")
    if not Path(exe).is_file():
        RUNTIME.mkdir(parents=True, exist_ok=True)
        archive = RUNTIME / "ollama-windows-amd64.zip"
        # Resolve the version first so archive and checksum cannot come from different releases.
        with open_download("https://github.com/ollama/ollama/releases/latest", timeout=30) as response:
            version = response.geturl().rstrip("/").rsplit("/", 1)[-1]
        if not version.startswith("v"):
            raise RuntimeError("Cannot resolve official Ollama release")
        base = f"https://github.com/ollama/ollama/releases/download/{version}/"
        with open_download(base + "sha256sum.txt", timeout=30) as response:
            checksums = response.read().decode()
        expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip("*./") == archive.name)
        if not archive.is_file() or hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() != expected:
            print("Downloading official Ollama", version, flush=True)
            with open_download(base + archive.name, timeout=60) as source, archive.open("wb") as target:
                done = 0
                while block := source.read(4 * 1024 * 1024):
                    target.write(block)
                    done += len(block)
                    if done % (64 * 1024 * 1024) == 0:
                        print("Downloaded bytes:", done, flush=True)
            with archive.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                    raise RuntimeError("Official archive checksum mismatch; runtime was not executed")
        with zipfile.ZipFile(archive) as zipped:
            for name in zipped.namelist():
                if not (RUNTIME / name).resolve().is_relative_to(RUNTIME.resolve()):
                    raise RuntimeError("Unsafe archive path")
            zipped.extractall(RUNTIME)
        (RUNTIME / "source.json").write_text(json.dumps({"version": version, "url": base + archive.name, "sha256": expected}), encoding="utf-8")
    environment = os.environ.copy()
    environment["OLLAMA_HOST"] = "127.0.0.1:11434"
    environment["OLLAMA_MODELS"] = str(RUNTIME / "models")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "server.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([exe, "serve"], env=environment, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    (RUNTIME / "process.json").write_text(json.dumps({"pid": process.pid}), encoding="utf-8")
    for _ in range(60):
        try:
            return request("http://127.0.0.1:11434/api/tags", timeout=2)
        except OSError:
            time.sleep(1)
    raise RuntimeError("Ollama did not become ready; inspect output/runtime/ollama/server.log")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:7b")
    args = parser.parse_args()
    available = ensure_service()
    if args.model not in [v["name"] for v in available["models"]]:
        print("Pulling model:", args.model, flush=True)
        body = json.dumps({"model": args.model, "stream": True}).encode()
        with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/pull", data=body, headers={"Content-Type": "application/json"}), timeout=120) as response:
            last = ""
            for line in response:
                value = json.loads(line)
                if "error" in value:
                    raise RuntimeError(value["error"])
                status = value.get("status", "")
                if status != last:
                    print(status, flush=True); last = status
            if last != "success":
                raise RuntimeError("Model pull did not finish successfully")
    print(json.dumps(request("http://127.0.0.1:11434/api/tags"), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
