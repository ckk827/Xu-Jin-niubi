"""Read-only native Windows sensing plus UI binding, on an isolated local demo server.

Does not synthesize input, lock the workstation, or change the real system clock.
"""
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
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    env=os.environ.copy()
    env['SOULBAND_DB']=str(ROOT/'tests'/'.data'/('live-'+uuid.uuid4().hex+'.sqlite3'))
    process=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)],
                             cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    url=f'http://127.0.0.1:{port}'
    results=[]
    errors=[]
    shots=ROOT/'screenshots'
    shots.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url+'/api/health',timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1050})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            page.get_by_role('button',name='设备感知设置',exact=True).click()
            expect(page.locator('.sensing-panel .panel-title')).to_contain_text('Windows 真实设备感知')
            page.get_by_role('button',name='绑定到小林并开始采集',exact=True).click()
            expect(page.get_by_text('当前绑定：小林',exact=True)).to_be_visible()
            def state():
                return page.request.get(url+'/api/state').json()
            first=state()
            pc=first['members'][0]['devices'][0]
            assert first['local_sensor']['enabled']
            assert pc['source']=='windows_live'
            assert pc['error'] is None,pc
            assert isinstance(pc['idle_seconds'],(float,int))
            assert isinstance(pc['locked'],bool)
            results.append('actual_windows_api_sample_and_ui_binding')
            deadline=time.monotonic()+7
            second=pc
            while time.monotonic()<deadline:
                second=state()['members'][0]['devices'][0]
                if second['observed_at']>pc['observed_at']:
                    break
                time.sleep(.2)
            assert second['observed_at']>pc['observed_at']
            results.append('automatic_native_sampling_heartbeat')
            page.screenshot(path=str(shots/'sensing-windows-settings.png'),full_page=True)

            page.locator('#identity-select').select_option('m2')
            expect(page.get_by_text('当前绑定：小林',exact=True)).to_be_visible()
            assert state()['local_sensor']['member_id']=='m1'
            results.append('identity_switch_preserves_binding')

            page.get_by_role('button',name='寝室概览',exact=True).click()
            expect(page.get_by_text('实测',exact=True)).to_be_visible()
            expect(page.get_by_label('阿泽 Windows 模拟信号')).to_be_visible()
            page.screenshot(path=str(shots/'sensing-windows-overview.png'),full_page=True)
            results.append('real_and_simulated_sources_distinguished')

            page.get_by_role('button',name='设备感知设置',exact=True).click()
            page.get_by_role('button',name='暂停采集',exact=True).click()
            expect(page.get_by_text('未开启 / 已暂停',exact=True)).to_be_visible()
            paused=state()['members'][0]['devices'][0]
            assert paused['signal']=='unknown' and paused['source']=='windows_live'
            results.append('pause_changes_device_to_unknown')

            page.locator('#identity-select').select_option('m1')
            page.get_by_role('button',name='当前身份电脑切回模拟',exact=True).click()
            assert state()['members'][0]['devices'][0]['source']=='simulation'
            results.append('explicit_return_to_simulation')

            phone=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            phone.goto(url+'/?device=phone')
            phone.get_by_role('button',name='设备感知设置',exact=True).click()
            expect(phone.get_by_role('button',name='绑定到小林并开始采集',exact=True)).to_be_disabled()
            assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth')
            phone.screenshot(path=str(shots/'sensing-mobile-settings.png'),full_page=True)
            results.append('mobile_does_not_claim_android_native_sensing')
            browser.close()
        assert not errors,errors
        report={'version':'0.2.0','checks':results,'count':len(results),'errors':errors,
                'native_sample':{k:pc[k] for k in ('source','signal','idle_seconds','locked','observed_at')},
                'lock_unlock_transition_tested':False,'android_native_tested':False,'real_ollama_tested':False}
        (shots/'sensing-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__=='__main__':
    main()
