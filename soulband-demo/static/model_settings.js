'use strict';

function modelPanel(firstRun=false){
  if(!ui.state.identity?.local_demo)return `<section class="card panel"><div class="panel-title">模型连接</div><p class="panel-sub">${esc(modelLabel())}。由宿主在本机管理模型连接。</p></section>`;
  const mode=ui.modelChoice??(ui.state.mode==='unconfigured'?'':ui.state.mode);
  const same=mode===ui.state.mode;
  const local=mode==='ollama', external=mode==='external';
  const name=same?ui.state.model:local?'qwen2.5:7b':'';
  return `<section class="card panel model-panel"><div class="panel-title">${icon('spark',17)}模型连接</div>
    <p class="panel-sub">选择本地运行或外部 API。外部 API 不会下载 Ollama 或 Qwen；调用失败会报告错误。</p>
    <div class="model-source-choices" role="group" aria-label="选择模型来源">
      <button type="button" data-model-source="ollama" aria-pressed="${local}">${icon('pc',22)}<strong>本地大模型</strong><small>在本机运行 Ollama + Qwen，保存后才下载</small></button>
      <button type="button" data-model-source="external" aria-pressed="${external}">${icon('shield',22)}<strong>外部大模型 API</strong><small>填写 API 地址、模型名称和密钥，无需下载模型</small></button>
    </div>
    <form id="settings-form" autocomplete="off"><div class="field"><label for="model-mode">模型来源</label><select id="model-mode" required>
      <option value="" disabled ${!mode?'selected':''}>请选择模型来源</option>
      <option value="ollama" ${local?'selected':''}>本地大模型 · Ollama + Qwen</option>
      <option value="external" ${external?'selected':''}>外部大模型 · OpenAI 兼容 API</option>
      ${firstRun?'':`<option value="demo" ${mode==='demo'?'selected':''}>演示模式 · 模拟结果</option>`}</select></div>
    ${external?`<div class="field"><label for="model-base-url">API 地址（Base URL）</label><input id="model-base-url" type="url" required value="${esc(ui.state.api_base_url||'')}" placeholder="例如：https://api.openai.com/v1"></div>`:''}
    ${mode?`<div class="field"><label for="model-name">${external?'模型名称（Model ID，不是网址）':'模型名称'}</label><input id="model-name" value="${esc(name)}" required maxlength="100" ${external?'pattern="(?![Hh][Tt][Tt][Pp][Ss]?://).*" title="这里填写服务商的模型 ID，例如 deepseek-chat，网址请填在 API 地址中。"':''} placeholder="${local?'qwen2.5:7b':external?'例如：deepseek-chat':'演示模型标记'}">${external?'<small class="model-field-help">请从服务商的模型列表复制模型 ID；https:// 开头的网址应填在上面的 API 地址中。</small>':''}</div>`:''}
    ${external?`${/^https?:\/\//i.test(name)?'<div class="notice amber">当前保存的模型名称是网址，请改成服务商提供的模型 ID 后再保存。</div>':''}
      <div class="field"><label for="model-api-key">API Key</label><input id="model-api-key" type="password" autocomplete="new-password" ${ui.state.api_key_saved?'':'required'} placeholder="${ui.state.api_key_saved?'已保存；留空保留该地址的密钥':'填写服务商提供的 API Key'}"></div>
      <div class="notice amber">模型任务所需的诉求、设备摘要和私密表达会发送到你选择的服务商，可能产生 API 费用。密钥仅保存在宿主本机，不回显给成员端。</div>
      <p class="fineprint">支持 OpenAI Chat Completions 兼容接口和 JSON 输出。Base URL 应包含服务商要求的路径（如 /v1）；也可填写完整 /chat/completions 地址。</p>`:''}
    ${local?'<div class="notice">保存后检查并准备 Ollama 和所选模型，缺少时才下载。默认 Qwen2.5 7B 需要数 GB 空间，首次准备可能较久。</div>':''}
    <div class="model-actions"><button class="btn small" type="submit" ${!mode?'disabled':''}>${local?'保存并准备本地模型':'保存模型连接'}</button>
      ${local||external?'<button class="btn small secondary" type="button" data-model-test>测试连接</button>':''}
      ${local&&ui.state.mode==='ollama'?'<button class="btn small secondary" type="button" data-model-prepare>准备 / 重试本地模型</button>':''}</div></form>
    <div id="model-setup-progress" aria-live="polite">${modelSetupProgress()}</div></section>`;
}

function modelLabel(){return ({demo:'演示模式 · 模拟推断',ollama:'Ollama · 真实调用',external:'外部 API · 真实调用',unconfigured:'尚未选择模型'})[ui.state.mode]||'尚未选择模型';}

function modelsPage(){
  return heading('MODEL CONNECTION','模型来源与连接','随时选择本地大模型或外部 API，保存后生效。')+modelPanel();
}

function modelSetupPage(){
  if(!ui.state.identity?.local_demo)return `<main class="model-onboarding"><h1>等待宿主配置模型</h1><p class="panel-sub">请在宿主电脑选择本地模型或外部 API。</p></main>`;
  return `<main class="model-onboarding"><div class="eyebrow">SOULBAND · 首次设置</div><h1>选择你的大模型</h1><p class="panel-sub">先选择模型来源，再开始使用宿伴。此时不会自动下载任何模型。</p>${modelPanel(true)}</main>`;
}

function modelSetupProgress(){
  const s=ui.localSetup;
  if(!s||(!s.running&&!s.error&&!s.ready))return '';
  return `<div class="panel-tip"><strong>${s.running?'本地模型正在准备…':s.ready?'本地模型已准备好':esc(s.error)}</strong><pre class="model-setup-log">${esc(s.output.join('\n'))}</pre></div>`;
}

function modelFormPayload(){
  const get=id=>document.getElementById(id)?.value.trim()||'';
  return {mode:get('model-mode'),model:get('model-name'),api_base_url:get('model-base-url'),api_key:get('model-api-key')||null};
}

document.addEventListener('change',event=>{
  if(event.target.id!=='model-mode')return;
  ui.modelChoice=event.target.value;
  render();
});

document.addEventListener('submit',event=>{
  if(event.target.id!=='settings-form')return;
  event.preventDefault();event.stopImmediatePropagation();
  const payload=modelFormPayload();
  ui.page='models';
  act(async()=>{
    await api('/settings','PUT',payload);
    const input=document.getElementById('model-api-key');if(input)input.value='';
    if(payload.mode==='ollama')ui.localSetup=await api('/settings/local-setup','POST');
  },payload.mode==='ollama'?'已选择本地模型，准备进度见下方。':'模型连接已保存。');
});

document.addEventListener('click',async event=>{
  const source=event.target.closest('[data-model-source]');
  if(source){if(!ui.busy){ui.modelChoice=source.dataset.modelSource;render();}return;}
  const test=event.target.closest('[data-model-test]'), prepare=event.target.closest('[data-model-prepare]');
  if(!test&&!prepare)return;
  event.preventDefault();event.stopImmediatePropagation();
  const button=test||prepare;
  if(ui.busy||button.disabled)return;
  if(test){
    if(!document.getElementById('settings-form').reportValidity())return;
    const payload=modelFormPayload();button.disabled=true;ui.busy=true;
    try{const result=await api('/settings/test','POST',payload);toast(result.message);}
    catch(error){toast(error.message);}
    finally{button.disabled=false;ui.busy=false;}
  }else{
    act(async()=>{ui.localSetup=await api('/settings/local-setup','POST');},'已开始准备本地模型。');
  }
});

setInterval(async()=>{
  if(typeof ui==='undefined'||!ui.state?.identity?.local_demo||ui.state.mode!=='ollama'||!['settings','models'].includes(ui.page)||ui.busy)return;
  try{
    ui.localSetup=await api('/settings/local-setup');
    const progress=document.getElementById('model-setup-progress');if(progress)progress.innerHTML=modelSetupProgress();
  }catch{/* Connection errors are reported by the main room poller. */}
},1500);
