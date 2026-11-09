"""Actual TLS handshake: trusted project CA passes, wrong trust/name and HTTP fail."""
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

ROOT=Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock: sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    env={**os.environ,"SOULBAND_DB":str(ROOT/"tests/.data"/("tls-"+uuid.uuid4().hex+".sqlite3"))}
    env["SOULBAND_INITIAL_MODE"] = "demo"
    process=subprocess.Popen([sys.executable,"-m","uvicorn","app:app","--host","127.0.0.1","--port",str(port),"--ssl-certfile","data/tls/server.crt","--ssl-keyfile","data/tls/server.key"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    context=ssl.create_default_context(cafile=str(ROOT/"data/tls/soulband-ca.crt"))
    url=f"https://127.0.0.1:{port}/api/health"
    checks=[]
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url,context=context,timeout=1) as response: assert json.load(response)["app"]=="soulband-demo"
                break
            except OSError: time.sleep(.1)
        else: raise AssertionError("TLS host did not become ready")
        checks.append("trusted_project_ca_health")
        try: urllib.request.urlopen(url,context=ssl.create_default_context(),timeout=3)
        except urllib.error.URLError as exc: assert isinstance(exc.reason,ssl.SSLCertVerificationError)
        else: raise AssertionError("Untrusted project CA unexpectedly accepted")
        checks.append("untrusted_ca_rejected")
        with socket.create_connection(("127.0.0.1",port),timeout=3) as connection:
            try: context.wrap_socket(connection,server_hostname="wrong.soulband.invalid")
            except ssl.SSLCertVerificationError: pass
            else: raise AssertionError("Wrong server name accepted")
        checks.append("wrong_hostname_rejected")
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",timeout=3)
        except (OSError, __import__('http.client',fromlist=['RemoteDisconnected']).RemoteDisconnected): pass
        else: raise AssertionError("TLS listener accepted a silent cleartext downgrade")
        checks.append("no_cleartext_downgrade")
        report={"checks":checks,"count":len(checks),"certificate_verification":True}
        target=ROOT.parent/"output/release-2026-11-08/tls.json"
        target.write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report,indent=2))
    finally: process.terminate();process.wait(timeout=10)


if __name__=="__main__": main()
