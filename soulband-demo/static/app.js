'use strict';
const icons = {
  home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-8h6v8"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  chat:'<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5a8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8Z"/><path d="M8 10h8M8 14h5"/>',
  tasks:'<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M9 3h6v4H9ZM8 12l2 2 5-4M8 18h8"/>',
  heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
  settings:'<path d="m9.5 3-.6 2.1-2 .9-2-.5-2.4 4 1.5 1.5v2l-1.5 1.5 2.4 4 2-.5 2 .9.6 2.1h5l.6-2.1 2-.9 2 .5 2.4-4L20 13v-2l1.5-1.5-2.4-4-2 .5-2-.9-.6-2.1Z"/><circle cx="12" cy="12" r="3"/>',
  bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  moon:'<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  pc:'<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  phone:'<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.9M15 3.1a4 4 0 0 1 0 7.8"/><circle cx="9" cy="7" r="4"/>',
  shield:'<path d="m12 3 9 4v6c0 5-9 9-9 9s-9-4-9-9V7Z"/><path d="m8 12 3 3 5-6"/>',
  leaf:'<path d="M20 3C8 1 2 8 6 15s17 2 14-12ZM3 21l12-12"/>',
  edit:'<path d="m16 3 5 5-12 12-6 1 1-6Z"/><path d="m13 6 5 5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  lock:'<rect x="4" y="10" width="16" height="11" rx="3"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  send:'<path d="m22 2-7 20-4-9-9-4Z"/><path d="m22 2-11 11"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2M5 16a8 8 0 0 0 13 2"/>',
  wallet:'<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M3 8V5a2 2 0 0 1 2-2h12m4 8h-6v5h6m-3-2.5h.1"/>',
};
const icon = (name, size=19) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.info}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pages = {overview:['寝室概览','grid'], models:['模型连接','spark'], agreement:['诉求与公约','chat'], affairs:['公共事务','tasks'], workflows:['协商与工具','chat'], private:['私密沟通','heart'], settings:['演示与设置','settings']};
const ui = {page:'overview', member:localStorage.getItem('soulband-member') || 'm1', state:null, busy:false, busyLabel:'', demand:'', privateText:'', privateStyle:'gentle', privateReply:'', proposal:null, inbox:false, error:null};
const deviceType = new URLSearchParams(location.search).get('device') === 'phone' ? 'phone' : 'pc';
let toastTimer, pollInFlight=false, seenNotifications=new Set();
// A full re-render between mousedown and mouseup cancels the browser's click, which
// looked like "the button needs several clicks". Defer paints while a press is open.
let pointerActive=false, pendingPaint=false, flushTimer;

function formatIdle(seconds){if(seconds===null||seconds===undefined)return '不可用';const n=Math.floor(seconds);return n<60?n+' 秒':Math.floor(n/60)+' 分 '+n%60+' 秒';}
function sensorBanner(){const cfg=ui.state.local_sensor;const owner=cfg?.member_id?person(cfg.member_id):null;return `<div class="sensor-banner"><div>${icon('pc',17)}<span><strong>${cfg?.enabled?'Windows 真实采集中 · '+esc(owner.name):'Windows 真实感知已接入'}</strong><small>${cfg?.enabled?'采集的是宿主机这台电脑；手机需安装并配对原生 APK，其他未接入设备为模拟。':'到设置绑定本机和成员后开始采集，未开启前仍使用模拟信号。'}</small></span></div>${button('设备感知设置','to-settings','small secondary','settings')}</div>`;}
function deviceControl(m,d){
  if(['windows_live','android_live'].includes(d.source)){
    return `<div class="device-control live-device" data-live-device="${m.id}:${d.id}" title="${esc(d.error||'原生设备信号')}">${icon(d.id,12)}<span data-live-label>${liveSignalLabel(d)}</span><b>实测</b></div>`;
  }
  return `<label class="device-control" title="${esc(m.name)} ${d.label} 模拟信号">${icon(d.id,12)}<select aria-label="${esc(m.name)} ${d.label} 模拟信号" data-signal-member="${m.id}" data-device="${d.id}">${[['active','活动'],['idle','无操作'],['unknown','未知']].map(([v,l])=>`<option value="${v}" ${d.signal===v?'selected':''}>${l}</option>`).join('')}</select><span class="sim-label">模拟</span></label>`;
}
function mobilePanel(){
  const paired=ui.state.mobile_paired?.includes(ui.member);
  const phone=me().devices.find(d=>d.id==='phone');
  const code=ui.mobileCode?.member===ui.member?ui.mobileCode:null;
  const disabled=deviceType==='phone';
  return `<section class="card panel mobile-panel"><div class="panel-title">${icon('phone',17)}原生 Android 配对与采集<span class="tag ${paired?'green':'gray'}">${paired?'手机已配对':'待配对'}</span></div><p class="panel-sub">先启动局域网联调服务，将 APK 安装到 Android 手机；为当前成员生成一次性配对码，在手机填写宿主局域网地址和配对码。</p><div class="sensor-actions">${button('为'+esc(me().name)+'生成手机配对码','mobile-code','','phone',disabled?'disabled data-fixed-disabled="true"':'')}${button('解除当前成员手机配对','mobile-revoke','secondary','',!paired||disabled?'disabled data-fixed-disabled="true"':'')}${button('当前身份手机切回模拟','simulate-phone','ghost small','',paired?'disabled data-fixed-disabled="true"':'')}</div>${code?`<div class="sensor-reading"><strong>一次性配对码：<code class="pairing-code">${esc(code.code)}</code></strong><p>仅用于 ${esc(me().name)}，5 分钟内有效。请勿把配对码发给无关人员。</p></div>`:''}${phone.source==='android_live'?`<div class="sensor-reading"><strong>Android 原生来源 · ${phone.stale?'暂停 / 数据过期':'近期有采样'}</strong><p>${esc(phone.error||'锁屏：'+(phone.locked?'是':'否')+' · 屏幕交互态：'+(phone.interactive?'亮屏':'熄屏'))}</p></div>`:''}<div class="panel-tip">原生 APK 支持授权、前台采集服务、状态上报和系统提醒。使用情况权限或数据不可用时报告未知；单纯亮屏不认定有明确操作。15 秒尝试上报，90 秒无有效数据转未知；省电机制可能延迟上报。手机收到通知还需开启系统通知权限并在通知偏好中选择手机或两端。</div></section>`;
}
function sensorDetails(m){
  return m.devices.filter(d=>['windows_live','android_live'].includes(d.source)).map(d=>`<div class="sensor-details" data-live-idle="${m.id}:${d.id}">${d.id==='pc'?'电脑':'手机'}实测：${liveDetailText(d)}<br><span>来源：${d.id==='pc'?'Windows API':'Android 原生 APK'}</span></div>`).join('');
}
function sensingPanel(){
  const cfg=ui.state.local_sensor;const owner=cfg.member_id?person(cfg.member_id):null;const pc=owner?.devices.find(d=>d.id==='pc');
  const disabled=!cfg.available||deviceType==='phone';
  return `<section class="card panel sensing-panel"><div class="panel-title">${icon('pc',17)}Windows 真实设备感知<span class="tag ${cfg.enabled?'green':'gray'}">${cfg.enabled?'采集中':'未开启 / 已暂停'}</span></div><p class="panel-sub">绑定的是运行宿主服务的 Windows 当前会话，不是打开此网页的任意设备。切换演示身份不会自动改绑。</p>
  <div class="sensor-reading"><strong>${owner?'当前绑定：'+esc(owner.name):'尚未绑定成员'}</strong><p>${pc?.source==='windows_live'?`电脑信号：${esc(({active:'近期有操作',idle:'持续无操作',away:'暂未操作，尚不足以判断休息',unknown:'未知'})[pc.signal])}<br>输入空闲：${formatIdle(pc.idle_seconds)} · 锁屏：${pc.locked===true?'是':pc.locked===false?'否':'未知'}<br>${pc.error?esc(pc.error):pc.stale?'数据已过期':'已收到真实 Windows API 采样'}`:'开启后会显示实际输入空闲时长与锁屏状态。'}</p></div>
  <div class="inline-fields"><div class="field"><label for="sensor-active-window">近期操作窗口（秒）</label><input id="sensor-active-window" type="number" min="1" max="300" value="${cfg.active_within_seconds}"></div><div class="field"><label for="sensor-rest-window">持续无操作观察时间（秒）</label><input id="sensor-rest-window" type="number" min="30" max="7200" value="${cfg.rest_after_seconds}"></div></div>
  <div class="sensor-actions">${button(cfg.enabled&&cfg.member_id===ui.member?'保存参数并继续采集':'绑定到'+esc(me().name)+'并开始采集','start-sensing','','pc',disabled?'disabled data-fixed-disabled="true"':'')}${button('暂停采集','pause-sensing','secondary','',!cfg.enabled||disabled?'disabled data-fixed-disabled="true"':'')}${button('当前身份电脑切回模拟','simulate-pc','ghost small','',cfg.enabled&&cfg.member_id===ui.member?'disabled data-fixed-disabled="true"':'')}</div>
  <div class="panel-tip">只采集输入空闲、锁屏和会话可用性，不采集按键内容、屏幕或应用明细。每 3 秒采样，15 秒无新数据转未知。刚锁屏不会立即推定休息；手机缺数据时仍可能显示未知。首次绑定会把该成员的模拟手机置为未知。</div>${disabled?'<p class="fineprint" style="margin-top:12px">请在宿主 Windows 的本机页面控制采集；手机入口不能采集 Android 状态。</p>':''}</section>`;
}

function toast(text){const box=document.getElementById('toast');box.textContent=text;box.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.classList.remove('visible'),5000);}
async function api(path, method='GET', data){
  const token=sessionStorage.getItem('soulband-token');
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-Member-Id':ui.member,...(token?{Authorization:'Bearer '+token}:{})},...(data!==undefined?{body:JSON.stringify(data)}:{})});
  if(response.status===401){if(typeof loginView==='function')loginView();throw Error('请使用宿主机生成的登录码登录');}
  let result;try{result=await response.json();}catch{throw Error('服务返回异常，请检查启动窗口。');}
  if(!response.ok){throw Error(typeof result.detail==='string'?result.detail:'输入格式不正确，请检查填写内容。');}return result;
}
function person(id){return ui.state.members.find(m=>m.id===id);}
function me(){return person(ui.member);}
function active(){return ui.state.proposals.find(p=>p.id===ui.state.active_id);}
function latest(){return ui.state.proposals.at(-1);}
function avatar(m,cls=''){return `<div class="avatar ${esc(m.color)} ${cls}">${esc(m.name.slice(-1))}</div>`;}
function modeTag(){return `<span class="mode-tag ${['ollama','external'].includes(ui.state.mode)?'real':''}">${icon(ui.state.mode==='demo'?'spark':'shield',12)}${modelLabel()}</span>`;}
function empty(text,name='leaf'){return `<div class="empty">${icon(name,27)}${text}</div>`;}
function button(text,action,kind='',name='',attrs=''){return `<button type="button" class="btn ${kind}" data-action="${action}" ${attrs} ${ui.busy?'disabled':''}>${name?icon(name,15):''}${text}</button>`;}
function go(page){ui.page=page;ui.inbox=false;render();window.scrollTo({top:0,behavior:'smooth'});}

const busyLabels={analysis:'判断寝室状态并安排提醒',proposal:'综合需求生成公约草案'};
function busyBarText(runtime){
  if(!runtime?.busy)return '';
  return '宿主正在'+(busyLabels[runtime.busy_task]||'处理模型任务')+'，页面可以继续浏览；模型返回后按钮会自动恢复。';
}
function updateRuntimeBar(){
  const text=busyBarText(ui.state?.runtime);
  let bar=document.getElementById('runtime-busy');
  if(!text){if(bar)bar.remove();return;}
  if(!bar){
    const content=document.querySelector('.content');
    if(!content)return;
    bar=document.createElement('div');bar.id='runtime-busy';bar.className='model-state';
    bar.setAttribute('role','status');content.prepend(bar);
  }
  if(bar.dataset.text!==text){bar.dataset.text=text;bar.innerHTML=`<i class="spinner"></i>${esc(text)}`;}
}
function showActionBusy(text){
  if(!text)return;
  const content=document.querySelector('.content');if(!content)return;
  let bar=document.getElementById('action-busy');
  if(!bar){
    bar=document.createElement('div');bar.id='action-busy';bar.className='model-state';
    bar.setAttribute('role','status');content.prepend(bar);
  }
  bar.innerHTML=`<i class="spinner"></i>${esc(text)}`;
}
function hideActionBusy(){document.getElementById('action-busy')?.remove();}
function liveSignalLabel(d){
  if(d.stale)return '已过期 / 已暂停';
  return ({active:'近期有操作',idle:'持续无操作',away:'暂未操作',unknown:'未知'})[d.signal]||'未知';
}
function liveDetailText(d){
  if(d.stale)return '暂停或数据过期';
  if(d.error)return esc(d.error);
  return `无操作 ${formatIdle(d.idle_seconds)} · ${d.locked===true?'已锁屏':d.locked===false?'未锁屏':'锁屏未知'}`;
}
// Poll replies stay "unchanged" for device timestamps only; patch those labels in
// place so the page does not have to be rebuilt every three seconds.
function applyLive(live){
  if(!live)return;
  for(const d of live.devices||[]){
    const key=d.member_id+':'+d.device_id;
    document.querySelectorAll(`[data-live-device="${key}"] [data-live-label]`).forEach(el=>{
      const text=liveSignalLabel(d);if(el.textContent!==text)el.textContent=text;
    });
    document.querySelectorAll(`[data-live-idle="${key}"]`).forEach(el=>{
      const text=`${d.device_id==='pc'?'电脑':'手机'}实测：${liveDetailText(d)}<br><span>来源：${d.device_id==='pc'?'Windows API':'Android 原生 APK'}</span>`;
      if(el.dataset.text!==text){el.dataset.text=text;el.innerHTML=text;}
    });
  }
  if(ui.state&&live.runtime)ui.state.runtime={...(ui.state.runtime||{}),...live.runtime};
  updateRuntimeBar();
}

async function refresh(force=true){
  const previous=ui.state?.revision;
  const previousConnection=JSON.stringify([ui.state?.mode,ui.state?.model,ui.state?.api_base_url,ui.state?.api_key_saved,ui.state?.identity?.local_demo]);
  const previousView=JSON.stringify([ui.state?.clock,ui.state?.members,ui.state?.analysis?.context_key,ui.state?.local_sensor]);
  const role=ui.member;
  const received=await api('/state'+(force||!ui.state?'':`?since=${ui.state.revision}`));
  document.getElementById('connection-error')?.remove();
  ui.error=null;
  if(received.unchanged){
    if(ui.state){
      ui.state.runtime=received.runtime;
      if(received.identity)ui.state.identity={...ui.state.identity,...received.identity};
      applyLive(received.live);
    }
    return;
  }
  if(role!==ui.member)return;
  ui.state=received;ui.member=received.identity?.member_id||ui.member;ui.error=null;
  if(previous===undefined&&ui.state.mode==='external'&&/^https?:\/\//i.test(ui.state.model))ui.page='models';
  for(const n of ui.state.reminders){
    if(!seenNotifications.has(n.id)&&previous!==undefined&&!n.read&&n.devices.includes(deviceType)) toast(n.message);
    seenNotifications.add(n.id);
  }
  // Device sampling and room activity must not replace an open connection form.
  const connectionView=ui.page==='models'||ui.state.mode==='unconfigured';
  const sameConnection=previousConnection===JSON.stringify([ui.state.mode,ui.state.model,ui.state.api_base_url,ui.state.api_key_saved,ui.state.identity?.local_demo]);
  if(!force&&connectionView&&sameConnection)return;
  const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
  const changedView=previousView!==JSON.stringify([ui.state.clock,ui.state.members,ui.state.analysis?.context_key,ui.state.local_sensor]);
  if(force || previous!==ui.state.revision || changedView || ui.state.runtime.busy){
    if(pointerActive||(!force&&(typing||document.getElementById('modal').open||ui.busy||document.body.dataset.selectMenuOpen))){
      // Repaint as soon as the press/caret/modal/busy state clears instead of throwing
      // the update away; otherwise a slow tick could freeze the page visibly.
      pendingPaint=true;
    }else{
      pendingPaint=false;
      render();
    }
  }else{
    applyLive(received.live);
  }
}
async function act(fn, success, busyText){
  if(ui.busy){toast('上一个操作还在处理，请等它结束再点；按钮会自动恢复。');return;}
  ui.busy=true;
  document.querySelectorAll('button[data-action]').forEach(b=>b.disabled=true);
  document.body.setAttribute('aria-busy','true');
  showActionBusy(busyText);
  try{const result=await fn();ui.busy=false;hideActionBusy();await refresh();if(success)toast(typeof success==='function'?success(result):success);return result;}
  catch(error){ui.busy=false;hideActionBusy();toast(error.message);try{await refresh();}catch{ui.error=error.message;render();}}
  finally{ui.busy=false;hideActionBusy();document.body.removeAttribute('aria-busy');document.querySelectorAll('button[data-action]').forEach(b=>{if(b.dataset.fixedDisabled!=='true')b.disabled=false;});}
}

document.addEventListener('pointerdown',()=>{pointerActive=true;},{passive:true});
function flushPendingPaint(){
  pointerActive=false;pendingPaint=false;
  if(!ui.busy&&!document.body.dataset.selectMenuOpen)render();
}
['pointerup','pointercancel'].forEach(name=>document.addEventListener(name,()=>{
  // The click event is dispatched right after pointerup; painting synchronously here
  // would replace the node before the browser sends the click.
  clearTimeout(flushTimer);
  flushTimer=setTimeout(()=>{if(pendingPaint)flushPendingPaint();else pointerActive=false;},250);
},{passive:true}));

const illustration = `<svg class="hero-art" viewBox="0 0 300 240" fill="none" aria-hidden="true">
<ellipse cx="157" cy="198" rx="101" ry="17" fill="#d9cfe9" opacity=".4"/>
<circle cx="166" cy="102" r="77" stroke="#d7c9e8" stroke-width="1" stroke-dasharray="4 7"/>
<path d="m83 107 75-58 75 58v80H83Z" fill="#faf7ff" stroke="#d9c9e9" stroke-width="2"/>
<path d="m70 111 88-70 90 70" stroke="#b9a1d5" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="111" y="113" width="32" height="34" rx="9" fill="#e4daf3"/><path d="M127 114v32m-15-17h30" stroke="#c8b3df" stroke-width="2"/>
<rect x="169" y="137" width="33" height="50" rx="16" fill="#d9c9ee"/>
<path d="M171 102c-7-11 3-20 11-12 7-10 20-1 10 10l-10 11Z" fill="#c8b0df"/>
<rect x="40" y="117" width="57" height="48" rx="15" transform="rotate(-10 40 117)" fill="#f7f1ff"/>
<path d="m57 137 8 7 13-15" stroke="#af95ca" stroke-width="3" stroke-linecap="round"/>
<rect x="214" y="50" width="51" height="42" rx="14" transform="rotate(10 214 50)" fill="#f8f3ff"/>
<path d="M228 69h17m-14 7h10" stroke="#b9a1d2" stroke-width="3" stroke-linecap="round"/>
<path d="M55 73c-9-13 2-23 10-13 9-10 18 2 8 11l-10 9Z" fill="#d0bce3"/>
<path d="M232 161c-2-18 9-27 14-20 3 7-7 16-14 20Zm0 10c12-19 25-16 23-7-2 7-14 8-23 7Z" fill="#b9c9b6"/>
<path d="m233 155-4 33" stroke="#9fb69a" stroke-width="2"/><path d="M218 184h26l-4 17h-18Z" fill="#d0c2e2"/>
<circle cx="105" cy="43" r="3" fill="#c0a5d7"/><circle cx="259" cy="116" r="3" fill="#c6b3dc"/>
<path d="M201 24v10m-5-5h10M32 101v8m-4-4h8" stroke="#b9a0d3" stroke-width="2" stroke-linecap="round"/>
</svg>`;

function render(){
  // Rebuilding innerHTML is the only way this page paints, so keep the parts of
  // the view the user is holding on to: scroll position, focus and text caret.
  const scroller=document.querySelector('.content');
  const scroll=scroller?scroller.scrollTop:0;
  const pageY=window.scrollY;
  const focused=document.activeElement;
  const focusId=focused&&focused.id&&focused!==document.body?focused.id:null;
  const selection=focusId&&typeof focused.selectionStart==='number'?[focused.selectionStart,focused.selectionEnd]:null;
  paint();
  const again=document.querySelector('.content');
  if(again&&scroll)again.scrollTop=scroll;
  if(Math.abs(window.scrollY-pageY)>1)window.scrollTo({top:pageY});
  if(focusId){
    const el=document.getElementById(focusId);
    if(el&&el!==document.activeElement){
      try{el.focus({preventScroll:true});if(selection&&typeof el.setSelectionRange==='function')el.setSelectionRange(selection[0],selection[1]);}catch{}
    }
  }
}

function paint(){
  if(!ui.state){document.getElementById('app').innerHTML=`<div class="boot">${esc(ui.error||'正在连接寝室…')}<br><br><button class="btn" onclick="location.reload()">重新连接</button></div>`;return;}
  if(ui.state.mode==='unconfigured'){document.getElementById('app').innerHTML=modelSetupPage();return;}
  const current=me();const unread=ui.state.reminders.filter(n=>!n.read).length;
  document.getElementById('app').innerHTML=`<div class="layout">
  <aside class="sidebar"><div class="brand"><div class="brand-mark">${icon('home',27)}</div><div class="brand-name">宿伴<small>SOULBAND</small></div></div>
    <div class="side-caption">OUR LITTLE SPACE</div><nav class="nav" aria-label="主导航">${Object.entries(pages).map(([id,[title,name]])=>`<button type="button" data-action="nav" data-page="${id}" class="${ui.page===id&&!ui.inbox?'active':''}" ${ui.page===id?'aria-current="page"':''}>${icon(name,20)}<span>${title}</span></button>`).join('')}</nav>
    <div class="side-bottom"><div class="side-note">${icon('leaf',23)}<strong>一起住，也好好相处。</strong>把小小的在意说出来，<br>让共同生活更舒服一点。</div><div class="room-pill"><div class="room-icon">${icon('home',19)}</div><div><strong>我们的寝室</strong><small>${esc(ui.state.environment||(ui.state.members.length+' 位伙伴 · 示例宿舍'))}</small></div></div></div>
  </aside><main class="main"><header class="topbar"><div class="crumb">我们的寝室 ${icon('chevron',12)} <b>${ui.inbox?'提醒收件箱':pages[ui.page][0]}</b></div>
    <div class="top-actions"><button class="btn small secondary model-connection-shortcut" data-action="to-models">${icon('spark',15)}切换模型来源</button><span class="connected"><i class="dot"></i>本地服务已连接</span>${ui.state.identity?.seat?`<span class="tag" title="这台电脑上的独立演示座位 ${esc(ui.member)}">同机座位 · ${esc(current.name)}</span>`:''}<button class="inbox-button" type="button" data-action="inbox" title="我的提醒" aria-label="我的提醒">${icon('bell',20)}${unread?`<span class="count">${unread}</span>`:''}</button><div class="identity">${avatar(current)}<select id="identity-select" aria-label="切换演示成员身份">${ui.state.members.map(m=>`<option value="${m.id}" ${m.id===ui.member?'selected':''}>${m.name} · 演示身份</option>`).join('')}</select></div></div>
  </header><div class="content">${ui.error?`<div class="error-bar">${esc(ui.error)}</div>`:''}${ui.state.runtime.error?`<div class="error-bar">${esc(ui.state.runtime.error)} ${button('重新判断','analyze','small secondary')}</div>`:''}
  ${ui.inbox?inboxPage():({overview:overviewPage,models:modelsPage,agreement:agreementPage,affairs:affairsPage,workflows:workflowPage,private:privatePage,settings:settingsPage}[ui.page])()}
  <footer class="footer"><span>SOULBAND · 把各自的诉求，变成共同的约定</span><span>可测试版本 v0.5 · ${deviceType==='phone'?'手机适配入口':'桌面入口'} · 支持同机四座位并行演示</span></footer></div></main></div>`;
  if(!ui.state.identity?.local_demo){const picker=document.getElementById('identity-select');picker.disabled=true;picker.options.length=0;picker.add(new Option(current.name+(ui.state.identity?.seat?' · 同机座位':' · 已配对'),current.id));}
  updateRuntimeBar();
}

function heading(eyebrow,title,sub,action=''){return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${sub}</p></div>${action||modeTag()}</div>`;}
function overviewPage(){
  const proposal=active()||latest();const a=ui.state.analysis;const completed=ui.state.tasks.filter(t=>t.done).length;
  return heading('A LITTLE CLOSER, A LITTLE WARMER',`${esc(me().name)}，欢迎回到寝室`, '四个人的小习惯，也可以慢慢变成共同的默契。')+
  `${sensorBanner()}<div class="dashboard-grid"><div><section class="hero"><div class="hero-copy"><div class="hero-kicker">${icon('spark',13)} BETTER TOGETHER</div><h2>让每一份在意，<br>都被温柔接住。</h2><p>说说你的需要，一起定下公约。<br>剩下的小提醒，让宿伴替你记着。</p><div class="hero-actions">${button(proposal?'查看我们的公约':'开始共建公约','to-agreement','light','chat')}${button('体验主动提醒','analyze','secondary','spark')}</div></div>${illustration}</section>
  <div class="section-title"><h2>${icon('users',17)}伙伴此刻</h2><small>${ui.state.clock.mode==='real'?'实际时间':'模拟时间'} ${esc(ui.state.clock.time)} · ${ui.state.members.length} 人</small></div>
  <div class="members">${ui.state.members.map(memberCard).join('')}</div><div class="member-footer"><span class="fineprint">实测与模拟来源分别标注。设备状态不代表真实睡眠或噪声。</span>${button('纠正我的状态','manual','small ghost','edit')}</div>
  ${a?`<div class="panel-tip"><strong>${icon('spark',12)} ${esc(a.source)} · ${a.elapsed}s</strong><br>${esc(a.summary)}${a.blocked.length?'<br>程序拦截：'+esc(a.blocked.join('；')):''}</div>`:''}
  <div class="lower-grid"><section><div class="section-title"><h2>${icon('tasks',16)}一起完成的小事</h2><button class="text-button" data-action="to-affairs">${completed}/${ui.state.tasks.length} 已完成 ${icon('chevron',12)}</button></div><div class="card panel">${taskLines()}</div></section><section><div class="section-title"><h2>${icon('clock',16)}寝室动态</h2><button class="text-button" data-action="to-settings">查看记录 ${icon('chevron',12)}</button></div><div class="card panel">${events(3)}</div></section></div></div>
  <div class="right-col"><section class="card panel"><div class="panel-title">${icon('shield',17)} 我们的共同公约 <span class="tag ${active()?'green':'amber'}">${active()?'已生效':'待共建'}</span></div><p class="panel-sub">每一条约定，都来自大家的需要。</p>${proposal?`<div class="covenant-preview">${proposal.clauses.slice(0,3).map((c,i)=>`<div class="clause-mini"><div class="clause-num">0${i+1}</div><div><h4>${esc(c.title)}</h4><p>${esc(c.text.length>65?c.text.slice(0,65)+'…':c.text)}</p></div></div>`).join('')}</div>${approvalDots(proposal)}`:`${empty('四份诉求已准备好<br>让它们变成第一版共同公约','chat')}`} ${button(proposal?'查看公约与审核':'整理第一版公约','to-agreement','full-width ghost','arrow')}<div class="panel-tip"><strong>小约定，大安心</strong><br>只有经过人工审核的公约，才会成为主动提醒的依据。</div></section>
  <section class="card panel"><div class="panel-title">${icon('heart',17)} 有点在意，不必憋着</div><p class="panel-sub">先整理自己的感受，再决定怎么开口。</p>${button('和宿伴私下说说','to-private','full-width secondary','lock')}<p class="fineprint" style="margin-top:12px">私密输入不保存，也不会自动发给室友。</p></section>
  <section class="card quote-card"><p>“ 好好相处，<br>从让彼此被理解开始。 ”</p><small>一间寝室，几份不同的生活节奏。</small></section></div></div>`;
}

function memberCard(m){
  const state=ui.state.analysis?.states.find(s=>s.member_id===m.id);
  const status=state?.status||'unchecked';const labels={active:'有活动',resting:'可能休息',unknown:'状态未知',unchecked:'等待判断'};
  const name=status==='active'?'sun':status==='resting'?'moon':'info';
  const manual=m.manual&&m.manual.expires>Date.now()/1000?m.manual:null;
  return `<article class="card member-card"><div class="member-top">${avatar(m)}${m.id===ui.member?'<span class="you">我</span>':''}</div><div class="member-name">${esc(m.name)}</div><span class="status ${status}">${icon(name,12)}${labels[status]}</span><p class="member-reason">${esc(manual?'本人设置：'+(manual.activity||labels[manual.status]):state?.reason||'设备摘要已就绪，等待模型综合判断。')}</p>${sensorDetails(m)}<div class="device-row">${m.devices.map(d=>deviceControl(m,d)).join('')}</div></article>`;
}
function approvalDots(p){return `<div class="progress-row">${ui.state.members.map(m=>`<span class="progress-dot ${p.approvals.includes(m.id)?'done':''}" title="${esc(m.name)}">${p.approvals.includes(m.id)?icon('check',12):esc(m.name.slice(-1))}</span>`).join('')}<small class="muted" style="font-size:10px;margin-left:4px">${p.approvals.length}/${ui.state.members.length} 已确认 · v${p.version}</small></div>`;}
function taskLines(){return ui.state.tasks.map(t=>{const m=person(t.owner);return `<div class="task-line"><button class="check ${t.done?'done':''}" data-action="toggle-task" data-id="${t.id}" aria-label="${t.done?'取消完成':'完成'}${esc(t.title)}">${t.done?icon('check',12):''}</button><div class="task-info ${t.done?'completed':''}"><strong>${esc(t.title)}</strong><small>${esc(t.due)} · ${esc(m.name)}负责</small></div>${avatar(m,'task-avatar')}</div>`;}).join('');}
function events(count=100){return ui.state.traces.length?ui.state.traces.slice(0,count).map(t=>`<div class="event"><span class="event-dot"></span><div class="event-body"><strong>${esc(t.action)}</strong><p>${esc(t.detail)}</p><small>${esc(t.at)} · ${esc(t.source)} · 业务 ${esc(t.sim)}</small></div></div>`).join(''):empty('还没有新动态<br>一起生成第一版公约吧','leaf');}

function agreementPage(){
  let p=ui.state.proposals.find(p=>p.id===ui.proposal)||latest();
  const isLatest=p&&p.id===latest()?.id;const isActive=p?.id===ui.state.active_id;
  const disabled=p&&(!isLatest||p.approvals.includes(ui.member)||p.conflicts.length||isActive);
  const modelBusy=Boolean(ui.state.runtime?.busy);
  return heading('SAY IT, SHAPE IT, SHARE IT','每份需要，都值得被听见','先收集诉求，再由大家一起审核共同公约。')+
  `<div class="notice">${icon('info',14)} 当前可切换四个演示身份，分别提交和审核。本机演示模式可以切换身份；局域网成员必须单独配对，授权后不能切换他人身份。</div>
  <div class="two-col"><section class="card panel"><div class="panel-title">${icon('chat',17)} 大家的诉求 <span class="tag">${ui.state.demands.length} 条公开需求</span></div>${ui.state.demands.map(d=>`<article class="demand-card"><div class="demand-head">${avatar(person(d.member_id))}<strong>${esc(person(d.member_id).name)}</strong><span class="tag gray">${d.visibility==='private'?'仅本人保存':'寝室公开'}</span></div><p>${esc(d.text)}</p></article>`).join('')}
  <form id="demand-form" style="margin-top:20px"><div class="field"><label for="demand-text">${esc(me().name)}，你希望怎样一起生活？</label><textarea id="demand-text" maxlength="1500" required placeholder="比如：希望23:30到07:00保持安静，戴耳机玩游戏没关系…">${esc(ui.demand)}</textarea></div><div class="form-footer"><small class="fineprint">提交后在寝室内公开，请勿填写私人原因。</small><button class="btn small" type="submit" ${ui.busy?'disabled':''}>${icon('plus',13)}提交诉求</button></div></form></section>
  <div class="stack"><section class="card panel"><div class="panel-title">${icon('spark',17)} ${p?'共同公约':'准备好，共建第一版公约'} ${p?`<span class="tag ${isActive?'green':'amber'}">${isActive?'生效中':p.status==='archived'?'历史版本':'待审核'}</span>`:''}</div><p class="panel-sub">${ui.state.mode==='demo'?'演示生成器保留原诉求，仅识别明确时间；不会冒充模型生成。':'由所选模型综合需求，生成后仍需成员人工核对。'}</p>
  ${ui.state.proposals.length?`<div class="version-tabs">${ui.state.proposals.map(v=>`<button type="button" data-action="select-proposal" data-id="${v.id}" class="${p?.id===v.id?'selected':''}">v${v.version}${v.id===ui.state.active_id?' · 生效':''}</button>`).join('')}</div>`:''}
  ${p?`<h3 style="font-size:15px;font-weight:550;margin-bottom:15px">${esc(p.title)}</h3>${p.conflicts.length?`<div class="conflict">待协商，暂不能确认：<br>${p.conflicts.map(esc).join('<br>')}</div>`:''}${p.clauses.map((c,i)=>`<div class="clause-block"><h3><span class="clause-num">${String(i+1).padStart(2,'0')}</span>${esc(c.title)}</h3><p>${esc(c.text)}</p>${c.kind==='quiet'?`<small>${icon('moon',12)} 提醒适用时段：${esc(c.start)} — ${esc(c.end)}<br>${esc(scopeLabel(c))}</small>`:''}<small>来源：${c.sources.map(esc).join('、')||'人工补充，待审核'}</small></div>`).join('')}
  <div class="approval-list">${ui.state.members.map(m=>`<span class="approval ${p.approvals.includes(m.id)?'done':''}">${p.approvals.includes(m.id)?icon('check',12):icon('clock',12)}${esc(m.name)} · ${p.approvals.includes(m.id)?'已确认':'待审核'}</span>`).join('')}</div><div class="form-footer">${button('修改为新版本','revise','secondary small','edit',`data-id="${p.id}" ${!isLatest?'disabled data-fixed-disabled="true"':''}`)}<button type="button" class="btn" data-action="approve" data-id="${p.id}" ${disabled?'disabled data-fixed-disabled="true"':''}>${icon('check',15)}${isActive?'已全员确认生效':p.approvals.includes(ui.member)?'你已确认此版本':'以'+esc(me().name)+'身份确认'}</button></div><p class="fineprint" style="margin-top:14px">修改会生成新版本，旧确认不沿用。全员确认前不会产生有效公共规则。</p>`:empty('先看看左边四位伙伴的需要<br>再生成可审核的共同公约','users')}
  <div style="margin-top:20px">${button(modelBusy?'模型正在自动判断，稍候再生成':(p?'重新综合需求生成草案':'综合需求，生成公约草案'),'generate','full-width ghost','spark',modelBusy?'disabled data-fixed-disabled="true"':'')}</div></section>
  <section class="card panel"><div class="panel-title">${icon('heart',17)} 执行反馈与再次协商</div><p class="panel-sub">反馈关联当前静音公约。只表达具体诉求，不判断谁对谁错。</p><div class="feedback-controls"><select id="feedback-target" aria-label="反馈相关成员">${ui.state.members.filter(m=>m.id!==ui.member).map(m=>`<option value="${m.id}" ${m.id==='m2'?'selected':''}>涉及 ${esc(m.name)}</option>`).join('')}</select>${button('已改善','feedback-improved','small secondary','check')}${button('仍希望安静','feedback-still','small ghost','moon')}</div>${ui.state.negotiations.map(n=>`<div class="panel-tip"><strong>${esc(n.title)}</strong><br>关联 v${n.version} · ${esc(n.status)}<br>请相关成员讨论后修订公约，系统不再追加催促。</div>`).join('')}</section></div></div>`;
}

function affairsPage(){return heading('LITTLE THINGS, SHARED TOGETHER','一起分担，轻松一点','公共事务清楚记录，计算交给程序。')+`<div class="two-col"><section class="card panel"><div class="panel-title">${icon('tasks',17)}公共待办<span class="tag">示例任务</span></div><p class="panel-sub">支持完成同步；到「协商与工具」创建任务、生成轮值及审批互换。</p>${taskLines()}<div class="panel-tip">清洁完成标准：清运垃圾、清理公共地面。任务状态由成员主动标记，不由设备活动推断。</div></section><section class="card panel"><div class="panel-title">${icon('wallet',17)}公共费用<span class="tag gray">仅记账，无支付</span></div><p class="panel-sub">按勾选参与者均分，以整数分计算；余数依所选成员顺序分配。</p><form id="bill-form"><div class="field"><label for="bill-title">账单名称</label><input id="bill-title" maxlength="80" placeholder="例如：洗衣液与垃圾袋" required></div><div class="field"><label for="bill-amount">总金额（元）</label><input id="bill-amount" inputmode="decimal" pattern="[0-9]{1,6}([.][0-9]{1,2})?" placeholder="例如：39.90" required></div><div class="field"><label>参与分账成员</label>${ui.state.members.map(m=>`<label style="display:block"><input name="bill-member" type="checkbox" value="${m.id}" checked> ${esc(m.name)}</label>`).join('')}</div><button class="btn small" type="submit">${icon('plus',13)}记一笔公共账单</button></form>${ui.state.bills.length?ui.state.bills.slice().reverse().map(b=>`<article class="bill"><div class="bill-head"><strong>${esc(b.title)}</strong><b>¥ ${(b.total_cents/100).toFixed(2)}</b></div><div class="bill-shares">${b.shares.map(s=>`<span>${esc(person(s.member_id).name)} · ¥ ${(s.cents/100).toFixed(2)}</span>`).join('')}</div>${b.shares.some(v=>v.member_id===ui.member)?button((b.settled||[]).includes(ui.member)?'本人已确认结清':'确认本人已结清','settle','small secondary','',`data-id="${b.id}"`):''}</article>`).join(''):empty('还没有公共账单<br>每一笔，都清清楚楚','wallet')}</section></div>`;}

function privatePage(){return heading('A QUIET CORNER, JUST FOR YOU','有些话，可以先在这里说','整理感受，找到舒服的表达方式。')+`<div class="two-col"><section class="card panel"><div class="panel-title">${icon('lock',17)}你的私密表达空间<span class="tag">不保存原文</span></div><p class="panel-sub">内容不会进入公共公约、动态或提醒。此处生成话术，不替你发送。</p><form id="private-form"><div class="field"><label for="private-text">你想表达什么？</label><textarea id="private-text" maxlength="1500" required style="min-height:180px" placeholder="比如：晚上能听见唱歌，有点影响休息，但我怕直接说会尴尬…">${esc(ui.privateText)}</textarea></div><div class="field"><label for="private-style">希望怎样表达？</label><select id="private-style">${[['gentle','温和商量'],['friendly','轻松友好'],['direct','清晰直接']].map(([v,l])=>`<option value="${v}" ${ui.privateStyle===v?'selected':''}>${l}</option>`).join('')}</select></div><div class="form-footer"><small class="fineprint">${ui.state.mode==='demo'?'当前使用固定话术模板，非模型生成。':ui.state.mode==='external'?'内容会发送给所选外部服务商，本软件不存数据库。':'仅发送给宿主机本地 Ollama，不存数据库。'}</small><button type="submit" class="btn" ${ui.busy?'disabled':''}>${icon('spark',15)}帮我整理表达</button></div></form>${ui.privateReply?`<div class="reply">${esc(ui.privateReply)}</div><p class="fineprint" style="margin-top:12px">只是建议，你可以修改后自行使用。刷新页面即清除。</p>`:''}</section><div class="stack"><section class="card panel"><div class="panel-title">${icon('leaf',18)}把感受说清楚的小提示</div><ul class="check-list"><li>描述你实际遇到的事情。</li><li>说清具体影响和你希望的改变。</li><li>给对方解释与协商的空间。</li><li>避免用“总是”“从来不”评价对方。</li></ul><div class="panel-tip">如果你准备将诉求公开，可以到“诉求与公约”重新填写确认，不会自动转发这里的内容。</div></section><section class="card quote-card"><p>“ 先让自己的感受，<br>被自己认真听见。 ”</p><small>小小的不舒服，也值得被温柔对待。</small></section></div></div>`;}

function settingsPage(){return heading('BEHIND THE LITTLE REMINDERS','演示与设置','看见判断依据，也保留自己的选择。')+`<div class="notice amber">可测试版本 v0.5：Windows 与配对后的原生 Android 支持真实采集；网页手机入口仍不采集。业务时钟可选实际或模拟；提醒由宿主机定时器在静音时段起点触发，页面改为增量同步。四名成员可在同一台电脑上各占一个座位并行演示，座位与会话走同一套授权。原生手机及 Windows 客户端提供系统通知，网页是否弹出通知取决于浏览器授权。</div>${ui.state.identity?.local_demo?`<section class="card panel"><div class="panel-title">${icon('users',17)}同机四座位演示</div><p class="panel-sub">每个座位是独立登录会话，权限与配对设备一致；只能在宿主机本机打开。四个窗口可分别以不同成员身份操作。</p><div style="display:flex;flex-wrap:wrap;gap:8px">${ui.state.members.map(m=>`<a class="btn small secondary" href="/?seat=${esc(m.id)}" target="_blank" rel="noopener">${icon('arrow',13)}${esc(m.name)} · 座位 ${esc(m.id)}</a>`).join('')}</div><p class="fineprint" style="margin-top:10px">当前在线座位可在 <code>/api/demo/seats</code> 查看；关闭窗口后会话保留 7 天。</p></section>`:''}<div class="settings-grid">
${sensingPanel()}${mobilePanel()}${modelPanel()}
<section class="card panel"><div class="panel-title">${icon('clock',17)}业务时钟</div><p class="panel-sub">实际模式按上海时区运行；模拟模式使用下方日期时间。均不修改电脑时间。</p><form id="clock-form"><div class="field"><label for="clock-mode">时钟来源</label><select id="clock-mode"><option value="simulation" ${ui.state.clock.mode!=='real'?'selected':''}>模拟时间 · 手动设置</option><option value="real" ${ui.state.clock.mode==='real'?'selected':''}>实际时间 · Asia/Shanghai</option></select></div><div class="inline-fields"><div class="field"><label for="clock-date">模拟日期</label><input id="clock-date" type="date" value="${esc(ui.state.clock.date)}" required></div><div class="field"><label for="clock-time">模拟时间</label><input id="clock-time" type="time" value="${esc(ui.state.clock.time)}" required></div></div><button class="btn small" type="submit">应用时钟设置</button></form><div class="panel-tip">可以把时间改为 15:00，验证仅有夜间公约时不会扩展午休要求。日期变化可以验证新的静音周期。</div></section>
<section class="card panel"><div class="panel-title">${icon('bell',17)}${esc(me().name)}的通知偏好</div><p class="panel-sub">本 Demo 初始选择“优先活动设备”，是可修改的演示配置。</p><div class="radio-group">${[['active','优先活动设备'],['all','两端均提示'],['pc','主要通知电脑'],['phone','主要通知手机']].map(([id,label])=>`<button data-action="notify-preference" data-value="${id}" class="${me().notify===id?'selected':''}">${label}</button>`).join('')}</div><div class="panel-tip">同一身份在另一端打开页面后，可查看自己的提醒；已读同步采用 Demo 实现方案。此版未实现 Android 后台服务轮询之外的远程推送。</div></section>
<section class="card panel"><div class="panel-title">${icon('users',17)}本人状态与模拟设备</div><p class="panel-sub">人工状态在 Demo 中有效 30 分钟，可随时清除；这是可调整的演示参数。</p>${button('设置或清除我的状态','manual','ghost','edit')}<div class="panel-tip">模拟设备在概览页切换信号，真实电脑在上方绑定。人工状态独立于设备采集，不会让电脑变成真实手机。</div></section>
<section class="card panel"><div class="panel-title">${icon('shield',17)}当前可演示的完整流程</div><div class="flow"><span>需求</span><b>→</b><span>公约</span><b>→</b><span>全员审核</span><b>→</b><span>状态判断</span><b>→</b><span>主动提醒</span></div><p class="fineprint">先生成公约，再切换顶栏的四个演示身份逐一确认。变更设备摘要后，服务端会自动安排判断，也可点击“体验主动提醒”。</p><p class="fineprint" style="margin-top:12px">模型原始判断、程序拦截及实际生成消息分别记录；运行耗时是真实测量，模拟模式耗时不代表模型性能。</p></section>
<section class="card panel"><div class="panel-title">${icon('clock',17)}判断与执行记录<span class="tag gray">最多 100 条</span></div><div class="trace-list">${events(30)}</div></section></div>`;}

function inboxPage(){return heading('GENTLE REMINDERS, JUST ENOUGH','我的提醒','提醒是共同生活的提示，不是对个人的评价。')+`<div class="two-col"><section class="card panel"><div class="panel-title">${icon('bell',17)}${esc(me().name)}的提醒<span class="tag">${ui.state.reminders.length} 条</span></div>${ui.state.reminders.length?ui.state.reminders.slice().reverse().map(n=>`<article class="notification ${n.read?'':'unread'}"><div class="notification-head"><strong>${n.kind==='auto'?'按约预防性提醒':'反馈后的再次提醒'}</strong><span class="tag gray">${esc(n.time)}</span></div><p>${esc(n.message)}</p><div class="notification-meta">依据：${esc(n.reason)}<br>目标终端：${(n.original_devices||n.devices).map(d=>d==='pc'?'电脑':'手机').join('、')} · ${esc(n.source)}<br>状态：${n.read?'成员已读':esc(n.status)} · 应用内消息，不代表系统推送已送达</div>${n.read?'':`<div style="margin-top:10px">${button('我已读到','read','small secondary','check',`data-id="${n.id}"`)}</div>`}</article>`).join(''):empty('还没有给你的提醒<br>安静相处，也是一种默契','bell')}</section><section class="card panel"><div class="panel-title">${icon('shield',17)}提醒有边界</div><ul class="check-list"><li>仅依据已经审核生效的公约。</li><li>设备活动不代表已经制造噪声。</li><li>同一静音时段不因持续活动反复提醒。</li><li>数据不够时，保留“未知”。</li><li>仍有问题时，邀请协商而不是连续催促。</li></ul>${button('查看公约与反馈','to-agreement','full-width ghost','arrow')}</section></div>`;}

function openModal(content){const modal=document.getElementById('modal');modal.innerHTML=content;modal.showModal();}
function closeModal(){document.getElementById('modal').close();}
function manualModal(){const m=me().manual;openModal(`<div class="modal-header"><h2>这是我的真实状态</h2><button class="close" data-action="close-modal" aria-label="关闭">×</button></div><p class="panel-sub">纠正模型推断，或补充正在做的事情。仅更新当前演示身份。</p><form id="manual-form"><div class="field"><label for="manual-status">本人状态</label><select id="manual-status">${[['active','我还在活动 / 还没休息'],['resting','我正在休息'],['unknown','暂不确定'],['clear','清除人工状态，恢复设备判断']].map(([v,l])=>`<option value="${v}" ${m?.status===v?'selected':''}>${l}</option>`).join('')}</select></div><div class="field"><label for="manual-activity">具体活动（选填）</label><input id="manual-activity" maxlength="50" placeholder="例如：戴耳机学习" value="${esc(m?.activity||'')}"></div><p class="fineprint">Demo 设置有效期为 30 分钟，按实际经过时间计算，不随模拟时钟跳变。</p><div class="modal-footer"><button class="btn secondary" type="button" data-action="close-modal">取消</button><button class="btn" type="submit">确认我的状态</button></div></form>`);}
const weekdayNames=['周一','周二','周三','周四','周五','周六','周日'];
function scopeLabel(c){const scope=c.execution_scope;if(scope?.issue)return '仅文字约定，不自动提醒：'+scope.issue;const days=scope?.weekdays||c.weekdays||[0,1,2,3,4,5,6];const ids=scope?.member_ids||c.member_ids||[];return '适用：'+days.map(d=>weekdayNames[d]).join('、')+'；'+(ids.length?ids.map(id=>person(id)?.name||id).join('、'):'全体成员')+'；'+(c.starts_on||'不限开始日期')+' 至 '+(c.ends_on||'不限结束日期')+'（跨夜按起始日）';}
function scopeFields(c){return `<div class="field"><label>适用星期（跨夜按开始日）</label><div>${weekdayNames.map((name,d)=>`<label style="display:inline-block;margin-right:10px"><input class="clause-weekday" type="checkbox" value="${d}" ${(c.weekdays||[0,1,2,3,4,5,6]).includes(d)?'checked':''}>${name}</label>`).join('')}</div></div><div class="field"><label>适用成员</label><div>${ui.state.members.map(m=>`<label style="display:inline-block;margin-right:10px"><input class="clause-member" type="checkbox" value="${m.id}" ${!c.member_ids?.length||c.member_ids.includes(m.id)?'checked':''}>${esc(m.name)}</label>`).join('')}</div></div><div class="inline-fields"><div class="field"><label>开始日期（可空）</label><input class="clause-from" type="date" value="${esc(c.starts_on||'')}"></div><div class="field"><label>结束日期（可空）</label><input class="clause-until" type="date" value="${esc(c.ends_on||'')}"></div></div><div class="field"><label>提醒执行方式</label><select class="clause-automation"><option value="automatic" ${c.automation!=='manual'?'selected':''}>按适用范围自动提醒</option><option value="manual" ${c.automation==='manual'?'selected':''}>仅文字约定，不自动提醒</option></select></div><div class="field"><label>需人工确认的其它例外（每行一条；填写后不自动提醒）</label><textarea class="clause-exceptions">${esc((c.exceptions||[]).join('\n'))}</textarea></div>`;}
function reviseModal(id){const p=ui.state.proposals.find(p=>p.id===id);openModal(`<div class="modal-header"><h2>修订公约 · 新版本需重新审核</h2><button class="close" data-action="close-modal" aria-label="关闭">×</button></div><form id="revise-form" data-id="${p.id}"><div class="field"><label for="revise-title">公约名称</label><input id="revise-title" value="${esc(p.title)}" maxlength="100" required></div><div class="edit-scroll">${p.clauses.map((c,i)=>`<div class="edit-clause" data-clause-index="${i}"><strong>${esc(c.title)}</strong><div class="field"><textarea class="clause-text" required maxlength="1500">${esc(c.text)}</textarea></div>${c.kind==='quiet'?`<div class="inline-fields"><div class="field"><label>开始时间</label><input type="time" class="clause-start" value="${esc(c.start)}" required></div><div class="field"><label>结束时间</label><input type="time" class="clause-end" value="${esc(c.end)}" required></div></div>${scopeFields(c)}`:''}</div>`).join('')}<div class="field"><label for="revise-expiry">公约截止时间（可选，业务时钟；到期不再提醒）</label><input id="revise-expiry" type="datetime-local" value="${esc(p.valid_until||'')}"></div><div class="field"><label for="revise-conflicts">尚未解决的冲突（每行一条；只有实际解决后才清空）</label><textarea id="revise-conflicts">${esc(p.conflicts.join('\n'))}</textarea></div></div><p class="fineprint" style="margin-top:12px">文本和结构化时间需一致，请人工检查；保存仅生成草案，不直接替换当前生效公约。</p><div class="modal-footer"><button class="btn secondary" type="button" data-action="close-modal">取消</button><button class="btn" type="submit">保存为新版本</button></div></form>`);}

document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-action]');if(!b||b.disabled)return;
  const action=b.dataset.action;
  if(action==='nav')return go(b.dataset.page);
  if(action.startsWith('to-'))return go(action.slice(3));
  if(action==='inbox'){ui.inbox=true;render();return;}
  if(action==='close-modal')return closeModal();
  if(action==='manual')return manualModal();
  if(action==='mobile-code'){const owner=ui.member;return act(async()=>{const r=await api('/mobile/pair-code','POST');ui.mobileCode={...r,member:owner};return r;},'一次性配对码已生成，请在原生 APK 中输入。');}
  if(action==='mobile-revoke'){if(!confirm('解除后，这台手机的旧凭据会失效，需要重新配对。是否继续？'))return;return act(()=>api('/mobile/revoke','POST'),'手机配对已解除，设备状态改为未知。');}
  if(action==='simulate-phone')return act(()=>api('/devices/'+ui.member+'/phone','PUT',{signal:'unknown'}),'手机已切回模拟，请在概览页选择信号。');
  if(action==='start-sensing'||action==='pause-sensing'){
    const payload={enabled:action==='start-sensing',active_within_seconds:Number(document.getElementById('sensor-active-window').value),rest_after_seconds:Number(document.getElementById('sensor-rest-window').value)};
    if(payload.enabled&&ui.state.local_sensor.enabled&&ui.state.local_sensor.member_id!==ui.member&&!confirm('这台电脑将从'+person(ui.state.local_sensor.member_id).name+'改绑到'+me().name+'，是否继续？'))return;
    return act(()=>api('/sensing','PUT',payload),payload.enabled?'Windows 真实采集已开启，未接入的手机仍为模拟或未知。':'真实采集已暂停，电脑状态改为未知。');
  }
  if(action==='simulate-pc')return act(()=>api('/devices/'+ui.member+'/pc','PUT',{signal:'unknown'}),'当前身份的电脑已切回模拟，请在概览页选择信号。');
  if(action==='revise')return reviseModal(b.dataset.id);
  if(action==='select-proposal'){ui.proposal=b.dataset.id;render();return;}
  if(action==='generate')return act(async()=>{const p=await api('/proposals/generate','POST');ui.proposal=p.id;return p;},'草案已生成，请逐条核对并分别审核。','正在请求模型综合大家的诉求，最多约两分钟；页面会显示进度，请不要重复点击。');
  if(action==='approve')return act(()=>api('/proposals/'+b.dataset.id+'/approve','POST'),'已确认此版本；全员确认后才会生效。');
  if(action==='analyze')return act(()=>api('/analyze','POST'),'判断已完成。请查看状态、依据和提醒收件箱。','正在请求模型判断寝室状态，最多约两分钟；请不要重复点击。');
  if(action==='toggle-task')return act(()=>api('/tasks/'+b.dataset.id+'/toggle','POST'),'任务状态已同步。');
  if(action==='read')return act(()=>api('/reminders/'+b.dataset.id+'/read','POST'),'已标记为已读。');
  if(action==='notify-preference')return act(()=>api('/notification-preference','PUT',{strategy:b.dataset.value}),'通知偏好已保存。');
  if(action.startsWith('feedback-')){const target=document.getElementById('feedback-target').value;return act(()=>api('/feedback','POST',{target,result:action==='feedback-improved'?'improved':'still'}),r=>r.message);}
});
document.addEventListener('change',async event=>{
  const el=event.target;
  if(el.id==='identity-select'){ui.member=el.value;localStorage.setItem('soulband-member',ui.member);seenNotifications.clear();ui.demand='';ui.privateText='';ui.privateReply='';ui.assistantReply='';ui.confirmTask=null;ui.need=null;ui.opinion=null;ui.accessCode=null;try{await refresh();}catch(error){toast(error.message);}return;}
  if(el.dataset.signalMember)return act(()=>api('/devices/'+el.dataset.signalMember+'/'+el.dataset.device,'PUT',{signal:el.value}),'模拟信号已更新，公约生效时会自动安排判断。');
  if(el.id==='private-style')ui.privateStyle=el.value;
});
document.addEventListener('input',event=>{if(event.target.id==='demand-text')ui.demand=event.target.value;if(event.target.id==='private-text')ui.privateText=event.target.value;});
document.addEventListener('submit',async event=>{
  const form=event.target;event.preventDefault();if(ui.busy)return;
  const value=id=>document.getElementById(id).value;
  if(form.id==='demand-form')return act(async()=>{const r=await api('/demands','POST',{text:value('demand-text')});ui.demand='';return r;},'公开诉求已提交，重新生成草案后可纳入审核。');
  if(form.id==='bill-form'){const payload={title:value('bill-title'),amount:value('bill-amount'),participants:[...form.querySelectorAll('[name="bill-member"]:checked')].map(v=>v.value)};return act(()=>api('/bills','POST',payload),'账单已记录，分摊合计与总额一致。');}
  if(form.id==='clock-form'){const payload={date:value('clock-date'),time:value('clock-time'),mode:value('clock-mode')};return act(()=>api('/clock','PUT',payload),'业务时钟已更新，不会修改操作系统时间。');}
  if(form.id==='manual-form'){const payload={status:value('manual-status'),activity:value('manual-activity')};return act(async()=>{const r=await api('/manual','PUT',payload);closeModal();return r;},'本人状态已更新。');}
  if(form.id==='private-form'){ui.privateText=value('private-text');ui.privateStyle=value('private-style');return act(async()=>{const r=await api('/private','POST',{text:ui.privateText,style:ui.privateStyle});ui.privateReply=r.reply;return r;},'表达建议已整理，没有发送给其他人。');}
  if(form.id==='revise-form'){
    const p=ui.state.proposals.find(p=>p.id===form.dataset.id);
    if([...form.querySelectorAll('[data-clause-index]')].some(row=>row.querySelector('.clause-member')&&!row.querySelector('.clause-member:checked'))){toast('至少选择一位适用成员');return;}
    const clauses=p.clauses.map((c,i)=>{const row=form.querySelector(`[data-clause-index="${i}"]`);const copy={...c,text:row.querySelector('.clause-text').value};if(c.kind==='quiet'){copy.start=row.querySelector('.clause-start').value;copy.end=row.querySelector('.clause-end').value;copy.weekdays=[...row.querySelectorAll('.clause-weekday:checked')].map(v=>Number(v.value));copy.member_ids=[...row.querySelectorAll('.clause-member:checked')].map(v=>v.value);if(!copy.member_ids.length)throw Error('至少选择一位适用成员');copy.starts_on=row.querySelector('.clause-from').value||null;copy.ends_on=row.querySelector('.clause-until').value||null;copy.automation=row.querySelector('.clause-automation').value;copy.exceptions=row.querySelector('.clause-exceptions').value.split('\n').map(v=>v.trim()).filter(Boolean);}return copy;});
    const payload={title:value('revise-title'),valid_until:value('revise-expiry')||null,clauses,conflicts:value('revise-conflicts').split('\n').map(v=>v.trim()).filter(Boolean)};
    return act(async()=>{const r=await api('/proposals/'+p.id+'/revise','POST',payload);ui.proposal=r.id;closeModal();return r;},'新版本已生成，全员需要重新审核。');
  }
});

async function poll(){
  if(pollInFlight||ui.busy)return;
  pollInFlight=true;
  try{await refresh(false);}
  catch{
    if(ui.state){
      ui.error='暂时无法连接宿主服务，请检查启动窗口；恢复后将自动同步。';
      let banner=document.getElementById('connection-error');
      if(!banner){banner=document.createElement('div');banner.id='connection-error';banner.className='error-bar';banner.setAttribute('role','alert');document.querySelector('.content,.model-onboarding')?.prepend(banner);}
      banner.textContent=ui.error;
    }
  }finally{pollInFlight=false;}
}
async function bootstrapSeat(){
  const seat=new URLSearchParams(location.search).get('seat');
  if(!seat)return false;
  try{
    const response=await fetch('/api/demo/seat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:seat})});
    const result=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'同机座位创建失败');
    sessionStorage.setItem('soulband-token',result.token);
    sessionStorage.setItem('soulband-member',result.member_id);
    ui.member=result.member_id;
    return true;
  }catch(error){ui.error=error.message;return false;}
}
(async()=>{await bootstrapSeat();try{await refresh();}catch(error){ui.error=error.message;if(!document.getElementById('login-form'))render();}})();
setInterval(poll,3000);
