"""Native Qt client plus real local Windows API, with an isolated test host."""
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
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    env={**os.environ,"SOULBAND_DB":str(ROOT/"tests/.data"/("windows-member-"+uuid.uuid4().hex+".sqlite3"))}
    env["SOULBAND_INITIAL_MODE"] = "demo"
    secure=os.getenv("SOULBAND_WINDOWS_TLS")=="1"
    server_command=[sys.executable,"-m","uvicorn","app:app","--host","127.0.0.1","--port",str(port)]
    if secure: server_command += ["--ssl-keyfile","data/tls/server.key","--ssl-certfile","data/tls/server.crt"]
    server=subprocess.Popen(server_command,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    scheme="https" if secure else "http"
    base=f"{scheme}://127.0.0.1:{port}"
    context=ssl.create_default_context(cafile=str(ROOT/"data/tls/soulband-ca.crt")) if secure else None
    try:
        for _ in range(80):
            try:urllib.request.urlopen(base+"/api/health",timeout=1,context=context).close();break
            except OSError:time.sleep(.1)
        req=urllib.request.Request(base+"/api/access/code",data=json.dumps({"member_id":"m2"}).encode(),headers={"Content-Type":"application/json"})
        code=json.load(urllib.request.urlopen(req,context=context))["code"]
        packaged=os.environ.get("SOULBAND_WINDOWS_EXE")
        command=[packaged] if packaged else [sys.executable,"peer_desktop.py"]
        result=subprocess.run(command+["--smoke-test","--host",base,"--code",code],cwd=ROOT,env=env,capture_output=True,timeout=60)
        print(result.stdout.decode(errors="replace"))
        if result.returncode:
            print(result.stderr.decode(errors="replace"));raise AssertionError("Windows member UI smoke failed")
        state=json.load(urllib.request.urlopen(base+"/api/state",context=context))
        pc=state["members"][1]["devices"][0]
        assert pc["source"]=="windows_live",pc
        report={"checks":["native_pairing","authorized_webview_identity","real_local_windows_peer_sampling","client_exit_pauses_sampling"],"count":4,"transport":scheme,"packaged_exe":packaged,"different_physical_computers_tested":False,"source":pc["source"],"paused":pc["signal"]=="unknown"}
        assert report["paused"]
        path=ROOT.parent/"output/release-2026-11-08/windows-client.json"
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:server.terminate();server.wait(timeout=10)


if __name__=="__main__":main()
