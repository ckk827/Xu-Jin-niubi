/* User-reviewed operations, shared by desktop and the mobile browser. */
function loginView(){
  ui.state=null;
  document.getElementById('app').innerHTML='<main class="content"><section class="card panel" style="max-width:480px;margin:10vh auto"><h1>连接我们的寝室</h1><p>请在宿主电脑「协商与工具」为本人生成一次性登录码。</p><form id="login-form"><div class="field"><label for="login-code">10 位登录码</label><input id="login-code" required minlength="10" maxlength="10" autocomplete="off"></div><button class="btn">配对并登录</button></form><p id="login-error" role="alert"></p></section></main>';
}

function reviewStatus(value){return ({pending:'待审批',approved:'已同意',rejected:'已拒绝'})[value]||value;}
function optionMembers(){return ui.state.members.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');}
function taskOptions(own){return ui.state.tasks.filter(t=>!t.done&&(own?t.owner===ui.member:t.owner!==ui.member)).map(t=>`<option value="${t.id}">${esc(t.title)} · ${esc(person(t.owner).name)} · ${esc(t.due)}</option>`).join('');}
function workflowPage(){
  const s=ui.state,p=active();
  return heading('DISCUSS, REVIEW, ACT','协商与受控工具','所有建议可先预览；公约变更与临时安排必须经过审核。')+`<div class="settings-grid">
  <section class="card panel"><h2>模型助手</h2><p>查询公约、值日和账单；更新本人任务前再次确认。</p><form id="assistant-form"><div class="field"><label for="question">想了解什么？</label><textarea id="question" required maxlength="1500" placeholder="今晚几点需要安静？今天谁值日？"></textarea></div><button class="btn">查询正式记录</button></form>${ui.assistantReply?`<pre class="tool-result">${esc(ui.assistantReply)}</pre>`:''}${ui.confirmTask?button('确认完成建议任务','complete-suggested','secondary'):''}</section>
  <section class="card panel"><h2>整理需求与公开范围</h2><form id="need-prepare-form"><div class="field"><label for="need-raw">我的原始需求</label><textarea id="need-raw" required maxlength="1500"></textarea></div><button class="btn">先整理为需求卡</button></form>${ui.need?`<form id="need-save-form"><div class="field"><label for="need-final">本人检查与修正</label><textarea id="need-final" maxlength="1500" required>${esc(ui.need.text)}</textarea></div><p>${ui.need.questions.map(esc).join('<br>')}</p><div class="field"><label for="need-visibility">公开范围</label><select id="need-visibility"><option value="public">公开并参与公约生成</option><option value="private">仅本人保存，不进入共同公约</option></select></div><button class="btn">确认保存需求卡</button></form>`:''}</section>
  <section class="card panel"><h2>临时调整申请</h2><p>申请时间内暂停一条静音要求，最长 24 小时；全员同意才生效，到期恢复。</p><form id="adjustment-form"><div class="field"><label for="adjust-clause">生效条款</label><select id="adjust-clause">${(p?.clauses||[]).filter(c=>c.kind==='quiet').map(c=>`<option value="${c.id}">${esc(c.title)}</option>`).join('')}</select></div><div class="field"><label for="adjust-reason">原因（公开）</label><input id="adjust-reason" required minlength="2" maxlength="500"></div><div class="field"><label for="adjust-start">开始（业务时钟）</label><input id="adjust-start" type="datetime-local" value="${s.clock.date}T${s.clock.time}" required></div><div class="field"><label for="adjust-end">结束</label><input id="adjust-end" type="datetime-local" required></div><button class="btn" ${p?'':'disabled'}>提交临时安排</button></form>${s.adjustments.map(a=>`<article class="panel-tip"><b>${esc(a.reason)}</b><br>${esc(a.starts)} 至 ${esc(a.ends)}<br>${esc(reviewStatus(a.status))} · ${a.approvals.length}/${s.members.length} 已同意${a.status==='pending'&&!a.approvals.includes(ui.member)?`<br>${button('同意临时安排','adjust-vote','small', '',`data-id="${a.id}" data-approve="true"`)} ${button('拒绝临时安排','adjust-vote','small secondary','',`data-id="${a.id}" data-approve="false"`)}`:''}</article>`).join('')}</section>
  <section class="card panel"><h2>低压力异议与再次协商</h2><form id="opinion-preview-form"><div class="field"><label for="opinion-category">问题类型</label><select id="opinion-category"><option value="quiet">希望安静</option><option value="duties">分工有疑问</option><option value="other">其他共同事项</option></select></div><div class="field"><label for="opinion-raw">原始表达（不会自动公开）</label><textarea id="opinion-raw" maxlength="1500" required></textarea></div><button class="btn">预览中性表达</button></form>${ui.opinion?`<form id="opinion-commit-form"><div class="field"><label for="opinion-neutral">将公开的内容，请检查修改</label><textarea id="opinion-neutral" maxlength="2500">${esc(ui.opinion.neutral)}</textarea></div><button class="btn secondary">确认公开并发起协商</button></form>`:''}${s.negotiations.map(n=>`<article class="panel-tip"><b>${esc(n.title)}</b><p>${esc(n.status)}</p>${n.suggestion?`<p>${esc(n.suggestion)} · ${esc(n.suggestion_source)}</p>`:''}${button('整理待审核协商建议','suggest','small secondary','',`data-id="${n.id}"`)}</article>`).join('')}</section>
  <section class="card panel"><h2>值日排班与任务</h2><form id="task-create-form"><div class="field"><label for="task-title">任务内容</label><input id="task-title" required maxlength="120"></div><div class="field"><label for="task-owner">负责人</label><select id="task-owner">${optionMembers()}</select></div><div class="field"><label for="task-due">到期日期</label><input id="task-due" type="date" value="${s.clock.date}" required></div><button class="btn">创建公共任务</button></form><hr><form id="rota-form"><div class="field"><label for="rota-start">轮值开始日期</label><input id="rota-start" type="date" value="${s.clock.date}" required></div><div class="field"><label for="rota-days">排班天数</label><input id="rota-days" type="number" min="1" max="31" value="7" required></div><button class="btn secondary">按成员顺序生成轮值</button></form><hr><form id="swap-form"><div class="field"><label for="swap-own">我的未完成任务</label><select id="swap-own">${taskOptions(true)}</select></div><div class="field"><label for="swap-other">希望交换的任务</label><select id="swap-other">${taskOptions(false)}</select></div><button class="btn secondary">申请互换</button></form>${s.swaps.map(v=>`<p>${esc(person(v.requester).name)} → ${esc(person(v.target).name)} · ${esc(reviewStatus(v.status))} ${v.target===ui.member&&v.status==='pending'?button('同意交换','swap-vote','small','',`data-id="${v.id}" data-approve="true"`)+button('拒绝交换','swap-vote','small secondary','',`data-id="${v.id}" data-approve="false"`):''}</p>`).join('')}</section>
  <section class="card panel"><h2>我的参与设备与登录</h2><form id="profile-form"><div class="field"><label for="profile-name">我的昵称</label><input id="profile-name" value="${esc(me().name)}" maxlength="20" required></div><button class="btn secondary">保存我的昵称</button></form><p>仅选中的设备参与综合判断；未接入的参与设备仍为未知。</p><form id="participation-form">${me().devices.map(d=>`<label style="display:block;margin:12px 0"><input type="checkbox" name="participant-device" value="${d.id}" ${d.participating===false?'':'checked'}> ${esc(d.label)}</label>`).join('')}<button class="btn secondary">保存参与设备</button></form><hr>${s.identity?.local_demo?`<form id="member-add-form"><div class="field"><label for="new-member-name">添加成员昵称（最多六人，无生效公约时可添加）</label><input id="new-member-name" required maxlength="20"></div><button class="btn secondary">添加寝室成员</button></form><p>宿主本机可为各成员的网页或其他 Windows 客户端生成登录码。</p><div class="field"><label for="access-owner">授权成员</label><select id="access-owner">${optionMembers()}</select></div>${button('生成成员登录码','access-code','secondary')}${button('撤销该成员网页和电脑授权','access-revoke','ghost small')}${ui.accessCode?`<p><strong>一次性登录码：${esc(ui.accessCode)}</strong> · 5 分钟有效</p>`:''}`:button('退出当前设备登录','logout','secondary')}<hr>${button('检查真实模型连接','check-model','secondary')}${ui.modelStatus?`<p>${esc(ui.modelStatus)}</p>`:''}${p?`<hr><p>撤销当前公约需全员分别确认。</p>${button('同意撤销当前公约','revoke-covenant','ghost small')}`:''}</section></div>`;
}

document.addEventListener('submit',async event=>{
  const f=event.target, val=id=>document.getElementById(id).value;
  if(f.id==='login-form'){
    event.preventDefault();
    try{const r=await api('/access/redeem','POST',{code:val('login-code').trim(),platform:'web'});sessionStorage.setItem('soulband-token',r.token);ui.member=r.member_id;await refresh();}catch(e){const error=document.getElementById('login-error');if(error)error.textContent=e.message;}return;
  }
  const operations={
    'profile-form':()=>api('/profile','PUT',{name:val('profile-name')}),
    'member-add-form':()=>api('/members','POST',{name:val('new-member-name')}),
    'assistant-form':async()=>{const r=await api('/assistant','POST',{text:val('question')});ui.assistantReply=r.reply;ui.confirmTask=r.confirm_task_id;},
    'need-prepare-form':async()=>{ui.need=await api('/needs/prepare','POST',{text:val('need-raw')});},
    'need-save-form':async()=>{await api('/needs','POST',{text:val('need-final'),visibility:val('need-visibility')});ui.need=null;},
    'adjustment-form':()=>api('/adjustments','POST',{clause_id:val('adjust-clause'),reason:val('adjust-reason'),starts:val('adjust-start'),ends:val('adjust-end')}),
    'opinion-preview-form':async()=>{const category=val('opinion-category');ui.opinion={...await api('/opinions/preview','POST',{text:val('opinion-raw'),category}),category};},
    'opinion-commit-form':async()=>{await api('/opinions','POST',{category:ui.opinion.category,neutral:val('opinion-neutral')});ui.opinion=null;},
    'task-create-form':()=>api('/tasks','POST',{title:val('task-title'),owner:val('task-owner'),due:val('task-due')}),
    'rota-form':()=>api('/tasks/rota','POST',{start:val('rota-start'),days:Number(val('rota-days')),members:ui.state.members.map(m=>m.id)}),
    'swap-form':()=>api('/swaps','POST',{task_id:val('swap-own'),other_task_id:val('swap-other')}),
    'participation-form':()=>api('/participation','PUT',{devices:[...document.querySelectorAll('[name="participant-device"]:checked')].map(v=>v.value)})
  };
  if(operations[f.id]){event.preventDefault();return act(operations[f.id],'已处理，请检查当前记录。');}
});
document.addEventListener('click',event=>{
  const b=event.target.closest('[data-action]');if(!b||b.disabled)return;
  const action=b.dataset.action,id=b.dataset.id;
  const operations={
    'complete-suggested':async()=>{await api('/tasks/'+ui.confirmTask+'/complete','POST');ui.confirmTask=null;},
    'adjust-vote':()=>api('/adjustments/'+id+'/vote','POST',{approve:b.dataset.approve==='true'}),
    'swap-vote':()=>api('/swaps/'+id+'/vote','POST',{approve:b.dataset.approve==='true'}),
    'suggest':()=>api('/negotiations/'+id+'/suggest','POST'),
    'access-code':async()=>{const r=await api('/access/code','POST',{member_id:document.getElementById('access-owner').value});ui.accessCode=r.code;},
    'access-revoke':()=>api('/access/revoke','POST',{member_id:document.getElementById('access-owner').value}),
    'check-model':async()=>{const r=await api('/models');ui.modelStatus=r.available?'已连接：'+r.models.join('、'):r.message;},
    'revoke-covenant':()=>api('/covenant/revoke-request','POST'),
    'settle':()=>api('/bills/'+id+'/settle','POST')
  };
  if(action==='logout'){api('/access/logout','POST').finally(()=>{sessionStorage.removeItem('soulband-token');loginView();});return;}
  if(operations[action])return act(operations[action],'已处理，请检查当前记录。');
});
