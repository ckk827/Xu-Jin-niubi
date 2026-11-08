"""Pairing UI and native API contract with constructed packets, not Android hardware."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=os.environ.copy()
    env['SOULBAND_DB']=str(ROOT/'tests'/'.data'/('mobile-ui-'+uuid.uuid4().hex+'.sqlite3'))
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    base=f'http://127.0.0.1:{port}'
    errors=[]
    checks=[]
    try:
        for _ in range(100):
            try:urllib.request.urlopen(base+'/api/health',timeout=1).close();break
            except OSError:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base)
            page.get_by_role('button',name='演示与设置',exact=True).click()
            page.get_by_role('button',name='为小林生成手机配对码',exact=True).click()
            expect(page.locator('.pairing-code')).to_have_text(__import__('re').compile(r'^[A-F0-9]{10}$'))
            code=page.locator('.pairing-code').inner_text()
            checks.append('desktop_pairing_code_ui')
            response=page.request.post(base+'/api/mobile/pair',data={'code':code,'installation_id':str(uuid.uuid4())})
            assert response.ok,response.text()
            token=response.json()['token']
            headers={'Authorization':'Bearer '+token}
            packet={'sequence':1,'sampled_at_ms':int(time.time()*1000),'interactive':True,'locked':False,'usage_access':True,'interaction_age_seconds':0,'inactive_seconds':0}
            assert page.request.post(base+'/api/mobile/heartbeat',headers=headers,data=packet).ok
            page.get_by_role('button',name='寝室概览',exact=True).click()
            page.wait_for_function("document.body.innerText.includes('Android 原生 APK')")
            assert page.get_by_label('小林 Android 模拟信号').count()==0
            checks.append('constructed_native_packet_source_and_no_simulation_override')
            page.get_by_role('button',name='演示与设置',exact=True).click()
            page.once('dialog',lambda dialog:dialog.accept())
            page.get_by_role('button',name='解除当前成员手机配对',exact=True).click()
            expect(page.get_by_role('button',name='解除当前成员手机配对',exact=True)).to_be_disabled()
            assert page.request.get(base+'/api/mobile/inbox',headers=headers).status==401
            checks.append('revoke_ui_invalidates_old_credential')
            page.get_by_role('button',name='当前身份手机切回模拟',exact=True).click()
            page.get_by_role('button',name='寝室概览',exact=True).click()
            expect(page.get_by_label('小林 Android 模拟信号')).to_be_visible()
            checks.append('explicit_phone_return_to_simulation')
            phone=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            phone.goto(base+'/?device=phone')
            phone.get_by_role('button',name='演示与设置',exact=True).click()
            expect(phone.get_by_role('button',name='为小林生成手机配对码',exact=True)).to_be_disabled()
            assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth')
            checks.append('mobile_settings_no_overflow_and_no_host_pair_code_control')
            browser.close()
        assert not errors,errors
        report={'checks':checks,'count':len(checks),'errors':errors,'packets':'constructed API contract data','android_hardware_tested':False}
        (ROOT/'screenshots'/'mobile-ui-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        server.terminate();server.wait(timeout=10)


if __name__=='__main__':main()
