"""Start the real Qt member client against an isolated HTTPS host and CA."""
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import prepare_tls


def main():
    folder = ROOT / "tests/.data" / ("windows-tls-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    prepare_tls.prepare(folder / "tls")
    context = ssl.create_default_context(cafile=str(folder / "tls/soulband-ca.crt"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "SOULBAND_DB": str(folder / "state.sqlite3"), "TEMP": str(folder), "TMP": str(folder)}
    env["SOULBAND_INITIAL_MODE"] = "demo"
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port),
                               "--ssl-certfile", str(folder / "tls/server.crt"), "--ssl-keyfile", str(folder / "tls/server.key")],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    base = f"https://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", context=context, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError("isolated TLS host did not start")
        req = urllib.request.Request(base + "/api/access/code", data=b'{"member_id":"m2"}', headers={"Content-Type": "application/json"})
        code = json.load(urllib.request.urlopen(req, context=context))["code"]
        entry = "import sys;from pathlib import Path;import peer_desktop;peer_desktop.CA_FILE=Path(sys.argv.pop(1));sys.exit(peer_desktop.main())"
        result = subprocess.run([sys.executable, "-c", entry, str(folder / "tls/soulband-ca.crt"), "--smoke-test", "--host", base, "--code", code],
                                cwd=ROOT, env=env, capture_output=True, timeout=65)
        if result.returncode:
            raise AssertionError(f"Qt exit {result.returncode}: " + result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        state = json.load(urllib.request.urlopen(base + "/api/state", context=context))
        device = state["members"][1]["devices"][0]
        assert device["source"] == "windows_live", device
        assert device["signal"] == "unknown", device  # exit pauses this peer
        try:
            urllib.request.urlopen(base + "/api/health", context=ssl.create_default_context(), timeout=3)
        except urllib.error.URLError as exc:
            assert isinstance(exc.reason, ssl.SSLCertVerificationError)
        else:
            raise AssertionError("untrusted CA accepted")
        with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
            try:
                context.wrap_socket(connection, server_hostname="wrong.soulband.invalid")
            except ssl.SSLCertVerificationError:
                pass
            else:
                raise AssertionError("wrong hostname accepted")
        print(json.dumps({"checks": ["qt_start_with_project_ca", "https_pairing", "webengine_trusted_ca_and_identity", "windows_sampling", "exit_pauses_sampling", "untrusted_ca_rejected", "wrong_hostname_rejected"], "count": 7, "different_physical_computers": False,
                          "chromium_sandbox_disabled_for_test": env.get("QTWEBENGINE_DISABLE_SANDBOX") == "1"}, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
