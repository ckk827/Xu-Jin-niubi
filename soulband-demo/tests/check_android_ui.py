"""Native UI smoke test on the explicitly named Android emulator; not iQOO evidence."""
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ADB = Path("D:/SoulbandBuild/android-sdk/platform-tools/adb.exe")
DEVICE = "emulator-5556"
OUT = ROOT.parent / "output/release-2026-11-08/android-ui"


def adb(*args):
    result = subprocess.run([str(ADB), "-s", DEVICE, *args], capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout.decode(errors="replace")


def nodes():
    adb("shell", "uiautomator", "dump", "/sdcard/soulband-ui.xml")
    (OUT / "current.xml").write_text(adb("shell", "cat", "/sdcard/soulband-ui.xml"), encoding="utf-8")
    result = list(ET.parse(OUT / "current.xml").iter("node"))
    unrelated = next((n for n in result if "isn't responding" in n.attrib.get("text", "") and "Soulband" not in n.attrib.get("text", "") and "宿伴" not in n.attrib.get("text", "")), None)
    if unrelated is not None:
        close = next((n for n in result if n.attrib.get("resource-id") == "android:id/aerr_close"), None)
        if close is not None:
            tap_node(close);time.sleep(1);return nodes()
    return result


def tap_node(node):
    x1,y1,x2,y2 = map(int,re.findall(r"\d+",node.attrib["bounds"]))
    adb("shell","input","tap",str((x1+x2)//2),str((y1+y2)//2))


def find(text, scroll=False):
    for _ in range(8 if scroll else 1):
        found=next((n for n in nodes() if text in n.attrib.get("text","")),None)
        if found is not None:return found
        if scroll:adb("shell","input","swipe","500","2000","500","600","300")
    raise AssertionError("Native UI text not found: "+text)


def click(text, scroll=False):tap_node(find(text,scroll));time.sleep(.4)


def enter(index,text):
    inputs=[n for n in nodes() if n.attrib.get("class")=="android.widget.EditText"]
    tap_node(inputs[index]);adb("shell","input","keyevent","123")
    adb("shell","input","keyevent","--longpress","67")
    # Select all via CTRL+A; content is ASCII test data, no shell interpolation.
    adb("shell","input","keycombination","113","29")
    adb("shell","input","text",text.replace(" ","%s"))
    adb("shell","input","keyevent","111")


def page(name):
    adb("shell","input","swipe","500","500","500","2100","250")
    spinner=next(n for n in nodes() if n.attrib.get("class")=="android.widget.Spinner")
    tap_node(spinner);click(name)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert adb("shell","getprop","sys.boot_completed").strip()=="1","Start Soulband_API35 emulator first"
    apk=ROOT.parent/"output/apk/Soulband-v0.4.0-debug.apk"
    import shutil
    staged = Path("D:/SoulbandBuild/qa/Soulband-v0.4.0-debug.apk")
    staged.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(apk, staged)
    assert "Success" in adb("install","-r",str(staged))
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    env={**os.environ,"SOULBAND_DB":str(ROOT/"tests/.data"/("android-ui-"+uuid.uuid4().hex+".sqlite3"))}
    env["SOULBAND_INITIAL_MODE"] = "demo"
    secure=os.getenv("SOULBAND_ANDROID_TLS")=="1"
    command=[sys.executable,"-m","uvicorn","app:app","--host","127.0.0.1","--port",str(port)]
    if secure: command += ["--ssl-keyfile","data/tls/server.key","--ssl-certfile","data/tls/server.crt"]
    server=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    scheme="https" if secure else "http"
    base=f"{scheme}://127.0.0.1:{port}"
    context=ssl.create_default_context(cafile=str(ROOT/"data/tls/soulband-ca.crt")) if secure else None
    def request(path,data=None,who="m1"):
        with urllib.request.urlopen(urllib.request.Request(base+"/api"+path,data=None if data is None else json.dumps(data).encode(),headers={"Content-Type":"application/json","X-Member-Id":who}),timeout=10,context=context) as r:return json.load(r)
    checks=[]
    def shot(name):
        result=subprocess.run([str(ADB),"-s",DEVICE,"exec-out","screencap","-p"],capture_output=True,check=True,timeout=30)
        (OUT/(name+".png")).write_bytes(result.stdout);checks.append(name)
    try:
        for _ in range(80):
            try:request("/health");break
            except OSError:time.sleep(.1)
        code=request("/mobile/pair-code",{})["code"]
        adb("shell","am","force-stop","cn.soulband.app")
        adb("shell","am","start","-f","0x10008000","-n","cn.soulband.app/.MainActivity")
        time.sleep(2)
        enter(0,f"{scheme}://10.0.2.2:{port}")
        box=find("允许局域网 HTTP")
        if box.attrib.get("checked")!="true":tap_node(box)
        enter(1,code)
        click("使用配对码绑定这台手机")
        for _ in range(10):
            try:find("已绑定：小林");break
            except AssertionError:time.sleep(1)
        else:raise AssertionError("Pairing did not finish")
        shot("01-native-pairing")
        adb("shell", "appops", "set", "cn.soulband.app", "GET_USAGE_STATS", "allow")
        adb("shell", "pm", "grant", "cn.soulband.app", "android.permission.POST_NOTIFICATIONS")
        click("开始采集并接收提醒", True)
        for _ in range(20):
            phone=request("/state")["members"][0]["devices"][1]
            if phone.get("source")=="android_live" and phone.get("expires_at",0)>time.time():break
            time.sleep(1)
        else:raise AssertionError("Native service did not upload a fresh sample")
        assert phone.get("usage_access"),phone
        shot("02-native-service-sampling")
        def put(path,data):
            with urllib.request.urlopen(urllib.request.Request(base+"/api"+path,method="PUT",data=json.dumps(data).encode(),headers={"Content-Type":"application/json","X-Member-Id":"m1"}),timeout=10,context=context) as r:return json.load(r)
        put("/notification-preference",{"strategy":"all"})
        for _ in range(4):
            adb("shell","input","swipe","500","400","500","2100","250")
        click("进入公约、协商与公共事务")
        find("小林的寝室");shot("02-native-overview")
        page("诉求与公约")
        click("综合公开需求生成公约草案",True)
        time.sleep(1)
        click("本人确认此版本",True)
        proposal=request("/state")["proposals"][-1]
        for who in ("m2","m3","m4"):request(f"/proposals/{proposal['id']}/approve",{},who)
        for _ in range(40):
            reminders=request("/state")["reminders"]
            if any(r.get("delivered",{}).get("phone") for r in reminders):break
            time.sleep(1)
        else:raise AssertionError("Native collector did not receive and acknowledge a reminder")
        notifications=adb("shell","dumpsys","notification","--noredact")
        assert any("cn.soulband.app" in line and "soulband-" in line for line in notifications.splitlines()),"Native notification record missing"
        checks.append("native_reminder_receipt_and_system_notification")
        adb("shell","input","swipe","500","450","500","2100","250")
        click("刷新共享记录")
        shot("03-native-covenant")
        page("公共事务")
        click("创建公共任务")
        click("小林")
        enter(0,"native task")
        # The default date is retained; only title and standard are edited.
        enter(2,"clean floor")
        click("确认")
        time.sleep(1)
        assert any(t["title"]=="native task" for t in request("/state")["tasks"])
        shot("04-native-task-created")
        page("临时安排");find("全员批准后");shot("05-native-adjustments")
        page("反馈协商");find("其他异议");shot("06-native-feedback")
        page("模型助手");click("查询公约 / 值日 / 费用")
        enter(0,"tasks")
        click("确认");time.sleep(1)
        find("工具结果");shot("07-native-tool")
        click("知道了")
        page("私密表达");find("原文仅用于本次整理");shot("08-native-private")
        adb("shell","input","keyevent","4")
        click("暂停采集", True)
        for _ in range(15):
            phone=request("/state")["members"][0]["devices"][1]
            if phone.get("signal")=="unknown" and "暂停" in phone.get("error",""):break
            time.sleep(1)
        else:raise AssertionError("Native pause did not invalidate evidence")
        checks.append("native_pause_invalidates_sample")
        crashes=adb("logcat","-b","crash","-d")
        assert "cn.soulband.app" not in crashes,crashes
        result={"device":DEVICE,"android_api":35,"hardware_phone":False,"transport":scheme,"checks":checks,"count":len(checks),"crashes":False}
        (OUT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        adb("shell","am","force-stop","cn.soulband.app")
        server.terminate();server.wait(timeout=10)


if __name__=="__main__":main()
