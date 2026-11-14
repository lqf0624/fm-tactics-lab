'use strict';
let matchImportSide=0,matchImportBusy=false;
const workspaceToolbarPrevious=toolbar;
toolbar=function(){
 const base=workspaceToolbarPrevious()+'<p class="tiny muted controlled-state-note">双方全名单开赛体能／比赛状态 100% · 累积疲劳 0 · 士气 20/20 · 球队磨合 80 · 俱乐部磨合 100；比赛中状态正常变化。</p>';if(!['tactics','setpieces'].includes(view))return base;
 const setpiece=view==='setpieces',label=setpiece?spDefinition().label:'比赛战术';
 const sides=editableTeamSides(),singleTeam=sides.length===1;
 const cards=sides.map(s=>{
  const t=state.teams[s],teamLabel=singleTeam?'己方':s?'客队':'主队';
  const edit=singleTeam?'':`<button class="button small" data-edit-team="${s}">${s===side?'正在编辑':'编辑此队'}</button>`;
  const name=setpiece?t.setpieces.routines[spType].map(r=>r.name).join(' ／ '):t.tactic_name||'默认／手动设置';
  const actions=setpiece?'<p class="tiny muted">下方编辑该球队的定位球。</p>':`<div class="team-load-actions"><button class="button" data-match-import="${s}">导入${teamLabel}比赛战术 FMF</button><button class="button small" data-match-export="${s}">导出${teamLabel}比赛战术 FMF</button></div><p class="tiny muted">已加载的比赛战术可继续修改；定位球在定位球页单独导入。</p>`;
  return `<section class="team-load-card ${s===side?'editing':''}" data-loaded-team="${s}"><div class="team-load-heading"><span class="tag">${teamLabel}</span><b>${esc(t.name)}</b>${edit}</div><small>${esc(label)}</small><strong class="loaded-tactic-name">${esc(name)}</strong>${actions}${!singleTeam&&!setpiece?boardRosterControls(s):''}${!setpiece&&state.teams[s].players.some(p=>p.source_uid!=null)?rosterFileButton(s):''}</section>`;
 });
 return base+`<div class="team-load-grid${singleTeam?' single-team':''}">${cards.join('')}</div>`;
};
const workspaceBindPrevious=bind;
bind=function(){workspaceBindPrevious();
 bindBoardRosterControls();bindRosterFiles();
 $$('[data-edit-team]').forEach(b=>b.onclick=()=>{side=+b.dataset.editTeam;slot=player=0;render();});
 $$('[data-match-import]').forEach(b=>{b.disabled=matchImportBusy;b.onclick=()=>{matchImportSide=+b.dataset.matchImport;$('#match-file').click();};});
 $$('[data-match-export]').forEach(b=>b.onclick=async()=>{const target=+b.dataset.matchExport;try{b.disabled=true;b.textContent='写入并核验…';const result=await api('/api/export-fmf',{side:target,scenario:state});downloadBinary(result);toast(`${target?'客队':'主队'}比赛战术已导出`);}catch(e){toast(e.message);}finally{render();}});
};
$('#match-file').onchange=async e=>{
 const file=e.target.files[0],target=matchImportSide;if(!file)return;
 try{clearActionError();if(!/\.fmf$/i.test(file.name))throw Error('请选择比赛战术 FMF 文件');if(file.size>4*1024*1024)throw Error('FMF 文件超过 4 MB');matchImportBusy=true;render();
 const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
 const result=await api('/api/import-fmf',{side:target,scenario:state,file_base64:btoa(binary)});state=result.scenario;side=target;save();toast(`${target?'客队':'主队'}已加载比赛战术：${state.teams[target].tactic_name||file.name}`);
 }catch(e){showActionError('比赛战术导入失败',file.name+' · '+e.message);}finally{matchImportBusy=false;e.target.value='';render();}
};
// Document leases survive navigation/reload without leaving a separate service window.
const desktopPage=crypto.randomUUID();
function desktopPresence(action){const body=JSON.stringify({page:desktopPage,action});if(action==='close')navigator.sendBeacon('/api/desktop-presence',new Blob([body],{type:'application/json'}));else fetch('/api/desktop-presence',{method:'POST',headers:{'Content-Type':'application/json'},body,keepalive:true}).catch(()=>{});}
window.addEventListener('pageshow',()=>desktopPresence('open'));
window.addEventListener('pagehide',()=>desktopPresence('close'));
setInterval(()=>desktopPresence('open'),15000);desktopPresence('open');

let boardRosterSource=null;
let boardRosterBusy=false;
function sampleNames(team,side){
 const pattern=side?/^客队球员\s*\d+$/:/^主队球员\s*\d+$/;
 return team.lineup.every(i=>!team.players[i].source_uid&&pattern.test(team.players[i].name));
}
function boardRosterControls(side){
 if(!boardRosterSource?.clubs.length)return '<button class="button small" data-open-career>从存档载入球员</button>';
 const clubs=boardRosterSource.clubs;
 const current=state.teams[side].roster_source?.club_uid??clubs.find(c=>c.name===state.teams[side].name)?.uid??
  (side?boardRosterSource.opponent:boardRosterSource.own);
 return '<div class="team-load-actions"><label>存档球队 '+select([{id:'',label:'选择球队'},...clubs.map(c=>({id:c.uid,label:c.name+(c.league_name?' · '+c.league_name:'')}))],current??'','data-roster-club="'+side+'"')+
 '</label><button class="button small" data-load-roster="'+side+'">载入球员名单</button></div>';
}
async function fetchBoardTeam(source,side,uid,scenario){
 const team=await api('/api/save/board-roster',{id:source.id,club_uid:uid,side,scenario});
 await refreshPlayerLabels(source.id,false,uid);
 return team;
}
function replaceBoardRoster(scenario,side,loaded){
 const previous=scenario.teams[side],markers=scenario.teams[1-side];
 const sameSave=previous.roster_source?.id&&previous.roster_source.id===loaded.roster_source?.id;
 const uid=(t,i)=>i<(t.roster_size??t.players.length)?t.players[i]?.source_uid:null;
 const prior=new Map();
 if(sameSave)previous.players.forEach((p,i)=>{if(uid(previous,i)!=null)prior.set(p.source_uid,i);});
 const settings=markers.opposition.players;
 markers.opposition.players=settings.map((_,i)=>{
  const old=prior.get(uid(loaded,i));
  return old!=null&&settings[old]?{...settings[old]}:{press:0,mark:0,tackle:0,foot:0,personal:false};
 });
 if(!sameSave)delete markers.opposition.by_player_uid;
 const order=t=>t.lineup.concat(t.players.map((_,i)=>i).filter(i=>!t.lineup.includes(i)));
 const before=order(previous),after=order(loaded);
 for(const cell of markers.phases.flat()){
  if(cell.target_player===255)continue;
  const target=sameSave?uid(previous,before[cell.target_player]):null;
  const next=target==null?-1:after.findIndex(i=>uid(loaded,i)===target);
  cell.target_player=next<0?255:next;
  if(next<0&&cell.instructions['14']===34)cell.instructions['14']=0;
 }
 scenario.teams[side]=loaded;
}
async function initializeBoardRoster(){
 if(!state)return;
 const requested=saveMode==='save'?saveInfo?.id:null,managed=saveClub;
 const mode=saveMode;
 const scenario=state;
 try{
  const source=await api('/api/save/board-clubs',mode==='save'&&saveInfo?.id?{id:saveInfo.id,managed:saveClub}:{});
  if(state!==scenario||saveMode!==mode||mode==='save'&&(saveInfo?.id!==requested||saveClub!==managed))return;
  boardRosterSource=source;
  if(source.id)void refreshPlayerLabels(source.id);
  if(!source.clubs.length)return;
  const sides=mode==='save'?[source.own]:[source.own,source.opponent];
  for(const [side,defaultClub] of sides.entries()){
   const existing=scenario.teams[side],binding=existing.roster_source;
   const oldRoster=existing.players.some(p=>p.source_uid!=null);
   const sameSource=binding?.id===source.id;
   if(sameSource)await refreshPlayerLabels(source.id,false,binding.club_uid);
   if(!sampleNames(existing,side)&&(!oldRoster||sameSource&&(mode==='free'||binding.club_uid===source.own)))continue;
   // Preserve the chosen club when changing seasons if it is available in the new save.
   const previous=mode==='free'&&source.clubs.find(c=>binding?c.uid===binding.club_uid:c.name===existing.name);
   const uid=previous?previous.uid:defaultClub;
   if(uid==null)continue;
   // Attach provenance to an old same-save draft without disturbing manual lineup edits.
   if(!binding&&oldRoster&&previous&&localStorage.getItem('fm27-roster-save-'+mode)===source.id){
    existing.roster_source={id:source.id,club_uid:uid};save();continue;
   }
   const before=JSON.stringify(scenario.teams[side]);
   const team=await fetchBoardTeam(source,side,uid,scenario);
   if(state!==scenario||saveMode!==mode||boardRosterSource!==source||mode==='save'&&(saveInfo?.id!==requested||saveClub!==managed))return;
   if(JSON.stringify(scenario.teams[side])!==before)continue;
   replaceBoardRoster(scenario,side,team);
   save();
  }
  localStorage.setItem('fm27-roster-save-'+mode,source.id);
 }catch(e){showActionError('载入存档球员失败',e.message);}
}
function bindBoardRosterControls(){
 $$('[data-open-career]').forEach(button=>button.onclick=()=>setSaveMode('save'));
 $$('[data-load-roster]').forEach(button=>{
  button.disabled=boardRosterBusy;
  button.onclick=async()=>{
   const target=Number(button.dataset.loadRoster);
   const choice=$('[data-roster-club="'+target+'"]').value;
   if(choice==='')return toast('请选择存档球队');
   const source=boardRosterSource,scenario=state,before=JSON.stringify(scenario.teams[target]);
   try{
    boardRosterBusy=true;button.disabled=true;
    const loaded=await fetchBoardTeam(source,target,Number(choice),scenario);
    await refreshPlayerLabels(source.id);
    if(state!==scenario||saveMode!=='free'||boardRosterSource!==source||JSON.stringify(scenario.teams[target])!==before)return;
    replaceBoardRoster(scenario,target,loaded);side=target;slot=player=0;save();saveModeDraft();
   }catch(e){showActionError('载入存档球员失败',e.message);}
   finally{boardRosterBusy=false;render();}
  };
 });
}
