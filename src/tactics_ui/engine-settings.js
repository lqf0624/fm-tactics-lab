'use strict';
// Keep diagnostics outside the rerendered tactic workspace. No storage access.
function showEngineStatus(status){
 const e=status.engine_compatibility||status;
 document.querySelector('#engine-summary').textContent=e.can_simulate?(e.compatible?'本地引擎：关键接口检查通过':'本地引擎：尚未验证，可试运行'):'本地引擎：需要设置，战术编辑可正常使用';
 document.querySelector('#engine-message').textContent=e.message||'';
 document.querySelector('#engine-path').value=e.selected_game_root||'';
 document.querySelector('#engine-diagnostics').textContent=JSON.stringify({adapter:e.adapter,adapter_version:e.adapter_version,reason:e.reason,diagnostics:e.diagnostics,diagnostic_error:e.diagnostic_error,missing_files:e.missing_files},null,2);
 document.querySelector('#engine-details').open=!e.compatible;
 if(typeof updateExecutionAvailability==='function')updateExecutionAvailability(status.execution_available===true);
}
window.addEventListener('DOMContentLoaded',async()=>{
 if(desktopInvoke){
  const section=document.querySelector('#data-settings');
  const path=document.querySelector('#data-path');
  const button=document.querySelector('#change-data-directory');
  const notice=document.querySelector('#data-status');
  section.hidden=false;
  try{path.value=await desktopInvoke('editor_data_directory');button.disabled=false;}
  catch(e){notice.textContent=String(e?.message||e);}
  button.onclick=async()=>{
   button.disabled=true;
   notice.textContent='如需复制，时间取决于数据大小。更改完成后工具会退出。';
   try{
    const storage=Object.fromEntries(Object.entries(localStorage).filter(([key])=>key.startsWith('fm27-')));
    await desktopInvoke('editor_change_data_directory',{storage});
    notice.textContent='';
   }catch(e){notice.textContent=String(e?.message||e);}
   finally{button.disabled=false;}
  };
 }
 try{showEngineStatus(await api('/api/status'));}catch(e){document.querySelector('#engine-summary').textContent='引擎诊断读取失败：'+e.message;}
 document.querySelector('#engine-check').onclick=async()=>{
  const button=document.querySelector('#engine-check');button.disabled=true;
  try{showEngineStatus(await api('/api/engine/select',{path:document.querySelector('#engine-path').value}));}
  catch(e){document.querySelector('#engine-message').textContent=e.message;}
  finally{button.disabled=false;}
 };
});
