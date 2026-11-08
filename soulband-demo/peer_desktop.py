"""Windows member client: pair, collect this session and show native notifications."""
import json
import sys
import time
import ssl
from pathlib import Path
import httpx
from sensing import WindowsSampler, VERSION

CA_FILE = Path(__file__).resolve().parent / "soulband-ca.crt"
if not CA_FILE.exists():
    CA_FILE = Path(__file__).resolve().parent / "data/tls/soulband-ca.crt"


def tls_context():
    context = ssl.create_default_context()
    if CA_FILE.exists(): context.load_verify_locations(str(CA_FILE))
    return context


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--host", default="http://127.0.0.1:8765")
    parser.add_argument("--code", default="")
    args = parser.parse_args()
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    from PySide6.QtCore import QTimer, QUrl, QThread, Signal
    from PySide6.QtGui import QIcon, QPixmap, QColor
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox, QSystemTrayIcon, QMessageBox
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineProfileBuilder, QWebEnginePage
    from PySide6.QtNetwork import QSslCertificate
    app = QApplication(sys.argv)
    window = QWidget(); window.setWindowTitle("宿伴 · 成员 Windows 客户端 v" + VERSION); window.resize(1200, 900)
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("在宿主电脑的「协商与工具」生成本人登录码。其他电脑请填写宿主局域网地址。"))
    host = QLineEdit(args.host); host.setPlaceholderText("https://宿主局域网IP:8766"); layout.addWidget(host)
    code = QLineEdit(); code.setPlaceholderText("一次性 10 位成员登录码"); layout.addWidget(code)
    allow = QCheckBox("允许局域网 HTTP 样例测试；外部网络必须使用 HTTPS"); layout.addWidget(allow)
    collect = QCheckBox("采集这台电脑的粗粒度状态（可随时暂停）"); layout.addWidget(collect)
    connect = QPushButton("配对并打开我的寝室"); layout.addWidget(connect)
    status = QLabel("未连接"); layout.addWidget(status)
    web = QWebEngineView()
    profile_builder = QWebEngineProfileBuilder()
    if CA_FILE.exists(): profile_builder.setAdditionalTrustedCertificates(QSslCertificate.fromPath(str(CA_FILE)))
    profile = profile_builder.createProfile("", window)
    web.setPage(QWebEnginePage(profile, web)); layout.addWidget(web, 1)
    pix = QPixmap(32, 32); pix.fill(QColor("#7b65ce")); tray = QSystemTrayIcon(QIcon(pix), window); tray.setToolTip("宿伴 · 成员提醒"); tray.show()
    account = {}; active = {"job": None}; seen = set()

    class Worker(QThread):
        finished_data = Signal(object)
        failed = Signal(str)
        def __init__(self, task):
            super().__init__(window); self.task = task
        def run(self):
            try: self.finished_data.emit(self.task())
            except Exception as exc: self.failed.emit(str(exc))

    def run(task, done):
        if active["job"]:
            return
        worker = Worker(task); active["job"] = worker
        worker.finished_data.connect(done)
        worker.failed.connect(lambda text: status.setText("操作失败：" + text[:180]))
        def finish():
            active["job"] = None; worker.deleteLater()
        worker.finished.connect(finish); worker.start()

    def request(path, body=None, method=None):
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False, verify=tls_context()) as client:
            response = client.request(method or ("POST" if body is not None else "GET"), account["base"] + "/api" + path, headers={"Authorization": "Bearer " + account["token"]}, json=body)
            if not response.is_success:
                raise RuntimeError(response.json().get("detail", "连接失败"))
            return response.json()

    def paired(value):
        account.update(value, sequence=0); code.clear(); connect.setEnabled(False); host.setEnabled(False)
        script = QWebEngineScript(); script.setName("Soulband paired identity"); script.setInjectionPoint(QWebEngineScript.DocumentCreation); script.setWorldId(QWebEngineScript.MainWorld)
        script.setSourceCode("sessionStorage.setItem('soulband-token'," + json.dumps(account["token"]) + ");localStorage.setItem('soulband-member'," + json.dumps(account["member_id"]) + ");")
        web.page().scripts().insert(script); web.setUrl(QUrl(account["base"])); status.setText("已配对 · " + account["member_name"])

    def pair():
        import ipaddress
        import socket
        from urllib.parse import urlparse
        base = host.text().strip().rstrip("/"); parsed = urlparse(base)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            QMessageBox.warning(window, "地址无效", "请输入 http(s)://宿主地址:端口"); return
        if parsed.scheme == "http":
            try:
                addresses = [ipaddress.ip_address(v[4][0]) for v in socket.getaddrinfo(parsed.hostname, parsed.port or 80)]
                valid = all(a.is_private or a.is_loopback for a in addresses)
            except OSError:
                valid = False
            if not allow.isChecked() or not valid:
                QMessageBox.warning(window, "连接未授权", "HTTP 仅允许明确勾选后的局域网测试"); return
        entered = code.text().strip()
        def perform():
            with httpx.Client(timeout=10, trust_env=False, verify=tls_context()) as client:
                response = client.post(base + "/api/access/redeem", json={"code": entered, "platform": "pc"})
                if not response.is_success: raise RuntimeError(response.json().get("detail", "配对失败"))
                return {**response.json(), "base": base}
        run(perform, paired)
    connect.clicked.connect(pair)

    def tick():
        if not account or active["job"]: return
        sensing_enabled = collect.isChecked()
        def perform():
            if sensing_enabled:
                account["sequence"] += 1
                sample = WindowsSampler().sample()
                request("/pc/heartbeat", {**sample, "sequence": account["sequence"], "sampled_at": time.time()})
                account["was_collecting"] = True
            elif account.pop("was_collecting", False):
                account["sequence"] += 1
                request("/pc/pause", {"sequence": account["sequence"]})
            return request("/state")
        def received(state):
            status.setText("已连接 · " + account["member_name"] + (" · 本机采集中" if sensing_enabled else " · 采集已暂停"))
            for reminder in state["reminders"]:
                if "pc" not in reminder["devices"] or reminder["read"] or reminder["id"] in seen: continue
                seen.add(reminder["id"])
                tray.showMessage("宿伴 · 公约提醒", reminder["message"], QSystemTrayIcon.Information, 10000)
                # Receipt means this client received the record, not that Windows displayed it.
                with httpx.Client(timeout=2, trust_env=False, verify=tls_context()) as client:
                    try: client.post(account["base"] + "/api/reminders/" + reminder["id"] + "/delivered", json={"device": "pc"}, headers={"Authorization": "Bearer " + account["token"]})
                    except httpx.HTTPError: pass
        run(perform, received)
    timer = QTimer(window); timer.timeout.connect(tick); timer.start(3000)
    tray.activated.connect(lambda _: window.showNormal())
    window.show()
    if args.smoke_test:
        allow.setChecked(True); code.setText(args.code); collect.setChecked(True)
        QTimer.singleShot(0, pair)
        def capture():
            def verify(value):
                if value != account.get("member_id") or not value:
                    print("Paired client failed to render its authorized identity", flush=True); app.exit(1); return
                target = Path(__file__).resolve().parent / "screenshots/release-0.4/windows-member.png"
                target.parent.mkdir(parents=True, exist_ok=True); window.grab().save(str(target))
                print("Authorized Windows member UI rendered:", target, flush=True); app.exit(0)
            web.page().runJavaScript("typeof ui !== 'undefined' && ui.state ? ui.state.identity.member_id : ''", verify)
        QTimer.singleShot(15000, capture)
        QTimer.singleShot(30000, lambda: app.exit(1))
    result = app.exec()
    if active["job"]: active["job"].wait(15000)
    if account:
        try:
            account["sequence"] += 1
            request("/pc/pause", {"sequence": account["sequence"]})
        except Exception:
            pass  # Server expiry still changes an unreachable peer to unknown.
    return result


if __name__ == "__main__":
    raise SystemExit(main())
