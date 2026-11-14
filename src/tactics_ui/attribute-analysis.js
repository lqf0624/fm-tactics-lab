'use strict';

function attributeRoleLabel(assignment) {
 const {position, role} = assignment;
 return `${position} · ${roles()[role]?.label || role}`;
}

function attributeCheckedSlots(container) {
 return [...container.querySelectorAll('[data-screen-slot]:checked')].map(input => Number(input.value));
}

async function openAttributeScreen() {
 const dialog = document.createElement('dialog');
 dialog.className = 'save-dialog attribute-dialog';
 dialog.setAttribute('aria-labelledby','attribute-dialog-title');
 const career=saveMode==='save';
 const saveId=saveInfo?.id, clubId=saveClub;
 let selected=career?saveOpponents.filter(row=>saveChosen.has(row.key)&&row.available):[];
 if(career&&(!saveLoaded||saveLoaded.save_id!==saveInfo?.id||saveLoaded.club_uid!==saveClub)){
  toast('请先将所选球队载入战术板');return;
 }
 const sides = editableTeamSides();
 const initialSide=sides.includes(side)?side:sides[0];
 dialog.innerHTML = `<h2 id="attribute-dialog-title">属性实验室</h2>
  <p>逐项调整属性，用同种子比赛比较，再用新种子复测。</p>
  <form class="attribute-form">
   <label class="attribute-team-picker">分析球队 ${select(sides.map(id => ({id, label: state.teams[id].name})), initialSide, 'data-screen-side')}</label>
   <fieldset class="attribute-slot-picker"><legend>分析范围</legend>
    <label class="attribute-slot-all"><input type="checkbox" data-screen-all>全选 11 个首发位置</label>
    <div class="attribute-slot-grid" data-screen-slots></div>
   </fieldset>
   <div class="attribute-options">
   <label>属性范围 <select data-screen-scope><option value="roles">角色候选（快速试跑）</option><option value="broad">广泛筛选：外场 30 项，门将 39 项</option></select></label>
   <label>属性提升点数 <input data-screen-increase type="number" min="1" max="19" step="1" value="3" required></label>
   </div>
   ${career?`<div class="save-team-controls"><button class="button small" type="button" data-screen-pick>选择存档对手</button><span class="tiny" data-screen-opponent-count aria-live="polite"></span></div><details data-screen-opponent-list hidden><summary>已选球队</summary><p class="tiny muted" data-screen-opponent-names translate="no"></p></details>`:`<label>对手范围 <select data-screen-opponents><option value="current">当前固定对手</option><option value="pool">客队战术池全部战术（2–8 套，仅分析主队）</option></select></label>`}
   <div class="attribute-options">
   <label>探索配对场数 <input data-screen-discovery type="number" min="4" max="100" step="1" value="4" required></label>
   <label>独立验证配对场数 <input data-screen-count type="number" min="2" max="200" step="1" value="4" required></label>
   </div>
   <details class="attribute-advanced"><summary>高级设置</summary>
   <div class="attribute-options">
   <label hidden>起始种子 <input data-screen-seed type="number" min="0" max="4294967295" step="1" value="${esc($('#seed').value)}" required></label>
   <label>验证运行方式 <select data-screen-validation-mode><option value="two_stage">只复测入选候选</option><option value="full">全部属性完整验证（耗时更长）</option></select></label>
   <label>评估对象 <select data-screen-profile-mode><option value="current">当前球员实际属性</option><option value="standard">单属性档位敏感度（同一球员）</option></select></label>
   <label data-screen-levels-row hidden>标准属性档位 <input data-screen-levels value="8,12,16" pattern="[0-9,， ]+" required></label>
   <p class="tiny muted">标准档位会分别测试 8、12、16 等基准值，可修改为最多 3 个 1–19 的整数；比赛量会相应增加。</p>
   <label>稳定推荐参考配对数 <input data-screen-stable-min type="number" min="2" max="200" step="1" value="8" required></label>
   <p class="tiny muted">参考配对数只影响证据等级，不增加比赛量。较少场次仍可获得初步关注或一般推荐。</p>
   <label>候选收益线 <input data-screen-threshold type="number" min="0" max="1" step="0.005" value="0.02" required></label>
   <label>强候选收益线 <input data-screen-strong type="number" min="0" max="1" step="0.005" value="0.05" required></label>
   <label>每位置每榜候选上限 <input data-screen-candidates type="number" min="1" max="15" step="1" value="5" required></label>
   <label>总览最多推荐 <input data-screen-recommendations type="number" min="1" max="5" step="1" value="3" required></label>
   <p class="tiny muted">总收益榜和每点榜各取候选后去重。收益线作用于实际总收益；每点筛选线为收益线除以计划提升点数。每点效果仅代表本次测试区间。</p>
   </div></details>
   <p data-screen-estimate class="tiny muted"></p><p data-screen-status role="status"></p>
   <div class="dialog-actions"><button type="button" class="button" data-screen-close>关闭</button>
    <button type="submit" class="button primary">开始分析</button></div>
  </form>`;
 const get = name => dialog.querySelector(`[data-screen-${name}]`);
 const submit=dialog.querySelector('button[type="submit"]');
 const slotInputs = () => [...get('slots').querySelectorAll('[data-screen-slot]')];
 const selectedSlots = () => attributeCheckedSlots(get('slots'));
 const syncAllSlots = () => {
  const inputs=slotInputs(),selected=inputs.filter(input=>input.checked).length;
  get('all').checked=selected===inputs.length;get('all').indeterminate=selected>0&&selected<inputs.length;
 };
 const renderSlots = (team, selected=[slot]) => {
  const chosen=new Set(selected);
  get('slots').innerHTML=team.lineup.map((index,slot)=>`<label class="attribute-slot-option">
   <input type="checkbox" data-screen-slot value="${slot}" ${chosen.has(slot)?'checked':''}>
   <span>${slot+1}. ${esc(displayName(team.players[index]))} · ${esc(team.phases[0][slot].position)}</span></label>`).join('');
  slotInputs().forEach(input=>input.onchange=()=>{syncAllSlots();estimate();});syncAllSlots();
 };
 renderSlots(state.teams[initialSide]);
 const randomSeeds=$('#seed-mode').value==='random';
 get('seed').closest('label').hidden=randomSeeds;
 get('seed').disabled=randomSeeds;
 const poolEntries=state.away_tactic_pool?.entries || [];
 const poolOption=get('opponents')?.querySelector('option[value="pool"]');
 if(poolOption)poolOption.disabled=initialSide!==0 || poolEntries.length<2 || poolEntries.length>8 || !state.away_tactic_pool?.uniform?.enabled;
 const estimate = () => {
  const team = state.teams[Number(get('side').value)];
  const slots = selectedSlots();
  submit.disabled=!slots.length || (career&&!selected.length);
  if (!slots.length) {get('estimate').textContent='请至少勾选一个首发位置。';return;}
  if (career&&!selected.length) {get('estimate').textContent='请选择存档对手';return;}
  const attributeCounts=slots.map(slot=>get('scope').value==='roles'?4:team.phases[0][slot].position==='GK'?39:30);
  const attributes = attributeCounts.reduce((sum,value)=>sum+value,0);
  const opponents = career ? selected.length : get('opponents').value==='pool' ? poolEntries.length : 1;
  const standard=get('profile-mode').value==='standard';
  const levels=standard?get('levels').value.split(/[,， ]+/).filter(Boolean).length:1;
  const explorationVariants=(standard?2*attributes*levels:1+attributes)*opponents;
  const candidateCount=attributeCounts.reduce((sum,value)=>sum+Math.min(2*(Number(get('candidates').value)||0),value),0);
  const validationVariants=(standard?2*candidateCount*levels:1+candidateCount)*opponents;
  const total=get('validation-mode').value==='two_stage'
   ? explorationVariants*Number(get('discovery').value)+validationVariants*Number(get('count').value)
   : explorationVariants*(Number(get('discovery').value)+Number(get('count').value));
  get('estimate').textContent = `最多预计 ${total} 场完整比赛。已达到 20 的属性会跳过；每项属性以同种子配对。`;
 };
 get('side').onchange = () => {
  const team = state.teams[Number(get('side').value)];
  const away = Number(get('side').value) !== 0;
  if(poolOption){
   poolOption.disabled=away||poolEntries.length<2||poolEntries.length>8||!state.away_tactic_pool?.uniform?.enabled;
   if(poolOption.disabled)get('opponents').value='current';
  }
  renderSlots(team,selectedSlots());
  estimate();
 };
 get('all').onchange=()=>{slotInputs().forEach(input=>input.checked=get('all').checked);syncAllSlots();estimate();};
 get('count').oninput = estimate;
 get('scope').onchange = get('discovery').oninput = estimate;
 if(!career)get('opponents').onchange=estimate;
 else{
  const refresh=()=>{
   get('opponent-count').textContent=`已选 ${selected.length} 队`;
   get('opponent-list').hidden=!selected.length;
   get('opponent-names').textContent=selected.map(row=>row.name).join('、');
   estimate();
  };
  get('pick').onclick=async()=>{
   const button=get('pick');
   button.disabled=true;
   get('status').textContent='';
   try{
    let report;
    do{
     report=await api('/api/save/opponents',{id:saveId,club_uid:clubId});
     if(!dialog.open||saveMode!=='save'||saveId!==saveInfo?.id||clubId!==saveClub)return;
     if(report.status==='error')throw Error(report.stage);
     if(report.status==='reading'){
      get('status').textContent=report.stage||'正在读取存档对手';
      await new Promise(resolve=>setTimeout(resolve,1200));
     }
    }while(report.status==='reading');
    get('status').textContent='';
    showSaveOpponents(report,{initial:new Set(selected.map(row=>row.key)),scope:'all',
     onAccept:keys=>{
      selected=report.opponents.filter(row=>row.available&&keys.has(row.key));
      refresh();
     }});
   }catch(error){get('status').textContent=error.message;}
   finally{button.disabled=false;}
  };
  refresh();
 }
 get('validation-mode').onchange=get('levels').oninput=estimate;
 get('profile-mode').onchange=()=>{get('levels-row').hidden=get('profile-mode').value!=='standard';estimate();};
 get('candidates').oninput = () => { get('recommendations').max=get('candidates').value; estimate(); };
 get('close').onclick = () => dialog.close();
 dialog.addEventListener('close', () => dialog.remove(), {once: true});
 dialog.querySelector('form').onsubmit = async event => {
  event.preventDefault();
  if(career&&(!selected.length||saveMode!=='save'||saveId!==saveInfo?.id||clubId!==saveClub))return;
  const discovery = Number(get('discovery').value);
  const count = discovery + Number(get('count').value);
  const first = Number(get('seed').value);
  if (!randomSeeds&&(!Number.isInteger(first)||first+count-1>0xffffffff)) {
   get('status').textContent = '种子范围无效';
   return;
  }
  const slots = selectedSlots();
  if (!slots.length) {get('status').textContent='请至少勾选一个首发位置';return;}
  const standardLevels=get('levels').value.split(/[,， ]+/).filter(Boolean).map(Number);
  const button = dialog.querySelector('[type="submit"]');
  button.disabled = true;
  try {
   const response = await api('/api/run-attribute-screen', {
    scenario: clone(state), side: Number(get('side').value), slots,
    exploration_count: discovery, attribute_scope: get('scope').value,
    ...(career?{save_id:saveId,club_uid:clubId,opponents:selected.map(o=>o.key)}:{opponents:get('opponents').value}),
    attribute_increase: Number(get('increase').value),
    validation_mode:get('validation-mode').value,profile_mode:get('profile-mode').value,
    standard_levels:standardLevels,
    candidate_threshold: Number(get('threshold').value), strong_threshold: Number(get('strong').value),
    candidate_limit: Number(get('candidates').value), recommendation_limit: Number(get('recommendations').value),
    stable_min_pairs: Number(get('stable-min').value),
    ...(randomSeeds?{seed_mode:'random',count}:{seeds:Array.from({length:count},(_,index)=>first+index)}),
    workers: Number($('#workers').value), event_details: false,
   });
   dialog.close();
   activeJob = response.id;
   polledJob = selectedJob = null;
   view = 'results';
   await poll();
  } catch (error) {
   get('status').textContent = error.message;
   button.disabled = false;
  }
 };
 document.body.append(dialog);
 dialog.showModal();
 estimate();
}

function attributeResearchReport(job) {
 const settings = job.attribute_screen;
 const rows = job.attribute_report || [];
 const number = value => value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(3)}`;
 const label = row => esc(catalog.attributes[row.attribute].label);
 const candidateThreshold = settings.candidate_threshold ?? .02;
 const strongThreshold = settings.strong_threshold ?? .05;
 const recommendationLimit = settings.recommendation_limit ?? 3;
 const attributeIncrease = settings.attribute_increase ?? 3;
 const validationMode = settings.validation_mode ?? 'full';
 const dual = settings.selection_policy === 'dual_v1';
 const statusNotice=job.status==='complete'?'':`<div class="results-error">本任务${job.status==='error'?'运行失败':job.status==='cancelled'?'已取消':'尚未完成'}，当前内容不是最终推荐。已完成 ${job.completed} / ${job.total} 场${job.error?'；'+esc(job.error):''}</div>`;
 const testedRange = row => settings.profile_mode==='standard'
  ? settings.standard_levels.map(level=>`${level} → ${Math.min(20,level+attributeIncrease)}`).join('；')
  : `${row.before/5} → ${row.after/5}（实际 +${row.actual_increase ?? Math.abs(row.after-row.before)/5}）`;
 const validationCount = settings.validation_seeds?.length ?? settings.seed_count;
 const impactSort = (a,b) => {
  const aComplete = a.n === validationCount && a.xg_difference_per_three != null;
  const bComplete = b.n === validationCount && b.xg_difference_per_three != null;
  if (aComplete !== bComplete) return aComplete ? -1 : 1;
  if (aComplete && a.xg_difference_per_three !== b.xg_difference_per_three)
   return b.xg_difference_per_three - a.xg_difference_per_three;
  return (b.exploration.metrics.xg_difference.delta ?? -Infinity) - (a.exploration.metrics.xg_difference.delta ?? -Infinity);
 };
 const conclusion = row => row.recommended
  ? ({stable:'稳定推荐',recommended:'一般推荐',preliminary:'初步关注'}[row.recommendation_tier] || '初步关注')
  : row.n !== validationCount ? (row.selected ? '候选：验证未完成' : '未入选验证候选')
  : row.recommendation_tier === 'strong_candidate' ? '强候选：复测未转正'
  : row.selected || (dual && validationMode==='full') ? '候选：复测未转正' : '未入选验证候选';
 const evidence = row => `${conclusion(row)} · ${row.n}/${validationCount} 对 · ${(row.evidence_warnings || []).map(esc).join('；')}`;
 const overview = settings.tested_slots.map(slot => {
  const all = rows.filter(row => row.slot === slot);
  const context = all[0] || settings.cases.find(row=>row.slot===slot);
  const passed = all.filter(row=>row.recommended).sort((a,b)=>b.xg_difference_per_three-a.xg_difference_per_three).slice(0,recommendationLimit);
  const sensitive = all.filter(row=>row.recommended).sort((a,b)=>(b.xg_difference_per_point??-Infinity)-(a.xg_difference_per_point??-Infinity)).slice(0,recommendationLimit);
  const candidates = all.filter(row=>row.selected).sort((a,b)=>b.exploration.metrics.xg_difference.delta-a.exploration.metrics.xg_difference.delta);
  const explored=all.filter(row=>row.exploration.n===settings.exploration_seeds.length).length;
  const validationTargets=validationMode==='full'?all:candidates;
  const validated=validationTargets.filter(row=>row.n===validationCount).length;
  return `<tr><td>${slot+1}. <span translate="no">${esc(context?.player)}</span><br>${(context?.phases||[]).map(attributeRoleLabel).map(esc).join('<br>')}</td>
   <td>${passed.length ? passed.map(row=>`<strong>${label(row)}（${number(row.xg_difference_per_three)}）</strong><br><small>${evidence(row)}</small>`).join('<br>') : '暂无独立复测为正的推荐'}</td>
   <td>${sensitive.length ? sensitive.map(row=>`${label(row)}（每点 ${number(row.xg_difference_per_point)}）<br><small>${evidence(row)}</small>`).join('<br>') : '暂无每点敏感度结果'}</td>
   <td>${candidates.length ? candidates.map(row=>`${label(row)}（${number(row.exploration.metrics.xg_difference.delta)}）`).join('、') : `没有达到 +${candidateThreshold.toFixed(3)} 的探索候选`}</td>
   <td style="white-space:nowrap">探索 ${explored} / ${settings.expected_attribute_counts?.[String(slot)] ?? all.length}<br>验证 ${validated} / ${validationTargets.length}</td></tr>`;
 }).join('');
 const detail = settings.tested_slots.map(slot => {
  const all = rows.filter(row=>row.slot===slot).sort(impactSort);
  if (!all.length) return '';
  const sensitivityOrder=all.filter(row=>row.n===validationCount && row.xg_difference_per_point!=null).sort((a,b)=>b.xg_difference_per_point-a.xg_difference_per_point);
  const sensitivityRank=new Map(sensitivityOrder.map((row,index)=>[row.attribute,index+1]));
  const position=all[0].phases[0].position;
  const roleKeys=position==='GK'||position.startsWith('DC')||['DL','DR','WBL','WBR','DM'].includes(position)
   ? [['xga','xGA'],['opponent_shots','对手射门'],['opponent_shots_on_target','对手射正'],['goals_against','失球']]
   : position.startsWith('MC')||['ML','MR'].includes(position)
   ? [['possession','控球'],['pass_completion','传球成功率'],['passes','传球次数'],['xg','xG']]
   : [['xg','xG'],['shots','射门'],['shots_on_target','射正'],['goals_for','进球']];
  return `<details><summary>${slot+1}. <span translate="no">${esc(all[0].player)}</span> · ${all.length} 项属性</summary>
   <div class="table-scroll"><table><thead><tr><th>实际收益排名</th><th>每点敏感度排名</th><th>候选属性</th><th>原值 → 测试值</th><th>探索 xG 差变化</th><th>验证总影响</th><th>每点敏感度</th><th>保守误差区间</th><th>探索／验证配对</th><th>证据等级</th></tr></thead><tbody>
   ${all.map((row,index)=>`<tr><td>${row.n===validationCount&&row.xg_difference_per_three!=null?index+1:'—'}</td><td>${sensitivityRank.get(row.attribute)??'—'}</td><td>${label(row)}</td><td>${testedRange(row)}</td><td>${number(row.exploration.metrics.xg_difference.delta)}</td><td>${number(row.xg_difference_per_three)}</td><td>${number(row.xg_difference_per_point)}</td><td>${number(row.lower)} ～ ${number(row.upper)}</td><td>${row.exploration.n} / ${row.n}</td><td>${conclusion(row)}</td></tr>
    <tr><td colspan="10"><small>角色相关球队指标：${roleKeys.map(([key,name])=>`${name} ${number(row.metrics[key]?.delta)}`).join(' / ')}；正种子 ${row.positive_seed_rate==null?'—':`${(100*row.positive_seed_rate).toFixed(0)}%`}<br>${evidence(row)}<br>
     ${row.opponents.map(op=>`<span translate="no">${esc(op.name)}</span>：${number(op.delta)}，${op.n} 对`).join('；')}</small></td></tr>`).join('')}
   </tbody></table></div></details>`;
 }).join('');
 return `<section class="card match-statistics" id="attribute-recommendations"><div class="card-head"><h3>关键属性推荐总览</h3><button class="button" id="export-attribute-report">导出独立报告</button></div>
  <div class="card-body">${statusNotice}<p>探索与独立验证 · ${job.completed} / ${job.total} 场 · 实验 ${esc(job.id)}</p>
  <p>对手：${settings.opponent_names.map(name=>`<span translate="no">${esc(name)}</span>`).join('、')}。等权汇总，先在同一种子内平均各对手变化，再计算误差。</p>
  <p>本次设置：${validationMode==='full'?'全部属性完整验证':'真正两阶段验证'}；${settings.profile_mode==='standard'?`标准属性档位 ${settings.standard_levels.join('、')}`:'当前球员属性'}；属性计划提升 ${attributeIncrease} 点（封顶 20）。探索 ${settings.exploration_seeds.length} 对、验证 ${settings.validation_seeds.length} 对；${dual?'每位置每榜候选上限':'每位置最多'} ${settings.candidate_limit ?? 5} 项。</p>
  ${dual?`<p>双榜候选去重后验证。完整验证模式评估全部属性，不受候选上限限制。验证为正是初步关注；探索和验证总收益均达到 +${candidateThreshold.toFixed(3)}，或每点收益均达到 +${(candidateThreshold/attributeIncrease).toFixed(4)}，是一般推荐。</p>
  <p>稳定推荐还要求探索与验证总收益均达到 +${strongThreshold.toFixed(3)}、验证至少 ${settings.stable_min_pairs??8} 对、至少 60% 种子和三分之二对手／档位为正，且四倍标准误区间下界为正。这是本次设置的证据分级，不是准确率保证。</p>`:
  `<p>历史实验沿用原有筛选与分级规则。</p>`}
  <p class="tiny muted">这里只按你本次设置给出实用推荐，不强制 20 对或固定对手数量。验证批次须完成；单套对手允许出现负值，以全部对手等权后的验证均值为准。误差区间仍显示为均值加减四倍标准误，用于提示波动风险，不再作为硬性淘汰门槛。接近 20 的属性实际提升可能小于计划值，报告会逐项标明；对手种类与球员配置仍限制结论适用范围。</p>
  <div class="table-scroll"><table><thead><tr><th>首发球员与角色</th><th>实际可获得收益榜</th><th>每点属性敏感度榜</th><th>探索入选候选</th><th>属性验证进度</th></tr></thead><tbody>${overview}</tbody></table></div>
  <p>以下明细在每个球员角色内部按独立验证 xG 差影响从高到低排列；验证未完成的项目放在后面，并按探索收益排序。定位球专项、位置熟练度、惯用脚和稳定性不在本轮范围内。</p>${detail}</div></section>`;
}

function attributeScreenReport(job) {
 if (!job.attribute_screen) return '';
 if (!Array.isArray(job.attribute_report)) return `<section class="card match-statistics" id="attribute-recommendations">
  <div class="card-head"><h3>关键属性报告尚未生成</h3></div><div class="card-body">
  <div class="results-error">实验 ${esc(job.id)} ${job.status==='error'?'运行失败':job.status==='cancelled'?'已取消':'仍在运行'}：已完成 ${job.completed} / ${job.total} 场${job.error?'；'+esc(job.error):''}</div>
  <p>探索阶段尚未完整结束，不能把“没有报告”解释为“没有推荐”。修复运行问题后，可使用“继续未完成场次”保留已完成结果。</p></div></section>`;
 return attributeResearchReport(job);
}

const screenResultsPrevious = resultsView;
resultsView = function () {
 const html = screenResultsPrevious();
 return selectedJob?.attribute_screen ? attributeScreenReport(selectedJob) + html : html;
};

const screenBindPrevious = bind;
bind = function () {
 screenBindPrevious();
 const button = $('#run-attribute-screen');
 if (button) button.onclick = openAttributeScreen;
 const exportButton = $('#export-attribute-report');
 if (exportButton) exportButton.onclick = () => {
  const content = attributeScreenReport(selectedJob).replace(/<button[^>]*id="export-attribute-report"[^>]*>.*?<\/button>/, '');
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>关键属性分析报告</title>
   <style>body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 24px;color:#172033;background:#f4f6fa}h3{margin:0}section{background:white;border:1px solid #dce1ea;border-radius:10px;margin:20px 0;padding:20px}.card-head{display:flex;justify-content:space-between;gap:20px}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;text-align:left;border-bottom:1px solid #dde2ea}th{background:#edf1fa}.muted,.tiny{color:#536079;font-size:14px}summary{cursor:pointer;padding:16px}button{display:none}@media print{body{background:white;max-width:none;padding:0}section{break-inside:avoid}}</style>
   <h1>战术角色关键属性分析报告</h1><p>${esc(selectedJob.name || '')} · ${esc(selectedJob.id)} · ${selectedJob.completed} / ${selectedJob.total}</p>${content}</html>`;
  const doc=new DOMParser().parseFromString(html,'text/html');
  doc.documentElement.lang=window.FM27I18n.language;
  const translate=window.FM27I18n.translate;
  const walker=doc.createTreeWalker(doc.documentElement,NodeFilter.SHOW_TEXT);
  for(let node; (node=walker.nextNode());){
   if(!node.parentElement.closest('style,[translate="no"]'))node.data=translate(node.data);
  }
  downloadFile(`attribute-report-${selectedJob.id}.html`,'<!doctype html>'+doc.documentElement.outerHTML,'text/html;charset=utf-8');
 };
};
