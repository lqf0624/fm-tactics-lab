'use strict';
const displayCache=new Map();
function displayKey(){return saveMode==='save'?saveInfo?.id:boardRosterSource?.id;}
function displayRow(p){
 const r=displayCache.get(displayKey())?.rows?.[p?.source_uid??p?.uid];
 return r && (p.name===r.raw || p.name===r.zh) ? r : null;
}
function displayName(p){const r=displayRow(p);return (window.FM27I18n.language==='zh-CN'&&r?.zh)||p.name;}
function kitNumber(p,index){return p.source_uid==null&&p.uid==null?(index==null?'—':index+1):(displayRow(p)?.number??'—');}
function playerCaption(p){
 const r=displayRow(p);
 return [displayName(p),r?.zh&&r.zh!==r.raw?r.raw:'',r?.imported?'游戏导出的阵容表':r?.number_source==='registration'?(r.number==null?'存档未分配球衣号码':'存档注册号码 '+r.number)+' · '+r.as_of:r?.date?'比赛球衣号码 '+r.number+' · '+r.date:''].filter(Boolean).join(' · ');
}
async function refreshPlayerLabels(id, reread=false, club=null){
 if(!id)return;
 const current=displayCache.get(id);
 if(current?.pending){
  if(!await current.request)return false;
  return refreshPlayerLabels(id,reread&&current.club!==club,club);
 }
 if(current&&!reread&&(club==null?current.hasBase:current.clubs.has(club)))return true;
 const entry={rows:current?.rows||{},clubs:new Set(current?.clubs),hasBase:current?.hasBase||false,pending:true,club};
 displayCache.set(id,entry);
 entry.request=api('/api/save/player-display',{id,refresh:reread,club_uid:club}).then(rows=>{
  if(club==null)entry.hasBase=true;
  if(club!=null)entry.clubs.add(club);
  for(const r of Object.values(rows))entry.clubs.add(r.club);
  Object.assign(entry.rows,rows);return true;
 }).catch(e=>{
  if(current)displayCache.set(id,current);else displayCache.delete(id);
  if(displayKey()===id)showActionError('读取球员译名和号码失败',e.message);
  return false;
 }).finally(()=>{
  entry.pending=false;
  if(displayKey()===id&&state)render();
 });
 return entry.request;
}
function rosterFileButton(s){
 const busy=displayCache.get(displayKey())?.pending;
 return '<button class="button small" data-reread-roster="'+s+'" '+(busy?'disabled':'')+'>'+(busy?'正在读取姓名和号码':'重读姓名和号码')+'</button> <button class="button small" data-roster-file="'+s+'" title="请使用当前赛季的球队导出文件">导入游戏阵容表</button>';
}
function rosterTable(html){
 const doc=new DOMParser().parseFromString(html,'text/html');
 const normalize=s=>s.trim().toLowerCase().replace(/[.\s_-]/g,'');
 function column(cells,allowed){return cells.findIndex(cell=>allowed.includes(normalize(cell.textContent)));}
 for(const table of doc.querySelectorAll('table')){
  const rows=Array.from(table.rows);
  for(let i=0;i<Math.min(rows.length,6);i++){
   const cells=Array.from(rows[i].cells);
   const name=column(cells,['姓名','名字','球员姓名','球员','name','player','playername']);
   const number=column(cells,['球衣号码','号码','背号','no','#','sqd','sqdno','squadno','squadnumber','shirtnumber','number']);
   const uid=column(cells,['唯一id','唯一编号','uid','id','uniqueid','球员id']);
   if(name<0||number<0)continue;
   return rows.slice(i+1).map(row=>{
    const value=c=>row.cells[c]?.textContent.trim()||'';
    return {name:value(name),number:value(number),uid:value(uid)};
   }).filter(p=>p.name);
  }
 }
 throw Error('阵容表需要姓名和球衣号码两列');
}
function bindRosterFiles(){
 $$('[data-reread-roster]').forEach(button=>button.onclick=async()=>{
  const target=state.teams[Number(button.dataset.rereadRoster)],id=displayKey();
  if(!id||target.roster_source&&target.roster_source.id!==id)return toast('请先载入存档球队');
  button.disabled=true;button.textContent='正在读取姓名和号码';
  if(await refreshPlayerLabels(id,true,target.roster_source?.club_uid??null)&&displayKey()===id)toast('已重新读取姓名和号码');
 });
 $$('[data-roster-file]').forEach(button=>button.onclick=()=>{
  const s=Number(button.dataset.rosterFile),t=state.teams[s],id=displayKey();
  if(!id)return toast('请先载入存档球队');
  const club=t.roster_source?.id===id?t.roster_source.club_uid:saveMode==='save'?saveClub:boardRosterSource?.clubs.find(c=>c.name===t.name)?.uid;
  if(club==null)return toast('请先载入存档球队');
  const input=document.createElement('input');input.type='file';input.accept='.fmf,.html,.htm';
  input.onchange=async()=>{
   const f=input.files[0];if(!f)return;
   try{
    if(f.size>2*1024*1024)throw Error('阵容文件超过 2 MB');
    let payload;
    if(/\.fmf$/i.test(f.name)){
     const bytes=new Uint8Array(await f.arrayBuffer());let binary='';
     for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
     payload={file_base64:btoa(binary)};
    }else{
     const bytes=new Uint8Array(await f.arrayBuffer());
     const encoding=bytes[0]===255&&bytes[1]===254?'utf-16le':bytes[0]===254&&bytes[1]===255?'utf-16be':'utf-8';
     payload={rows:rosterTable(new TextDecoder(encoding).decode(bytes))};
    }
    await refreshPlayerLabels(id);
    const result=await api('/api/save/import-player-display',{id,club_uid:club,...payload});
    const cache=displayCache.get(id);cache?.clubs.delete(club);await refreshPlayerLabels(id,false,club);toast('已匹配球员 '+result.matched+' / '+result.total);
   }catch(e){showActionError('阵容表导入失败',f.name+' · '+e.message);}
  };
  input.click();
 });
}
