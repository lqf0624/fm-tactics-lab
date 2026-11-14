'use strict';
let saveOpponentRequest=0,careerLeague='',careerTwoRounds=true,careerRetest=100;
function careerClubs(){
 return (saveInfo?.clubs||[]).filter(c=>!careerLeague||c.league_key===careerLeague);
}
function careerLeagueControls(){
 const leagues=saveInfo?.leagues||[];
 return '<label>联赛<select id="career-league"><option value="">全部五大联赛／执教球队</option>'+
 leagues.map(l=>'<option value="'+esc(l.key||'missing-'+l.database_id)+'" '+(l.key===careerLeague?'selected':'')+' '+(!l.available?'disabled':'')+'>'+esc(l.name)+(l.available?'（'+l.club_uids.length+'队）':' · 存档未加载')+'</option>').join('')+'</select></label>';
}
function careerRoundControls(){
 return '<div class="save-team-controls"><label><input id="career-two-rounds" type="checkbox" '+(careerTwoRounds?'checked':'')+'>两轮测试：筛选 → 新种子复测</label>'+
 '<label>第二轮每队场数<input id="career-retest" type="number" min="2" max="10000" step="2" value="'+careerRetest+'" '+(!careerTwoRounds?'disabled':'')+'></label></div>'+
 (careerTwoRounds?'<p class="tiny muted">第一轮场数沿用底部设置。启用对照可比较 A／B 两套方案，第二轮保持同一对手、主客场与方案，用新种子复测。仅一套方案时为重复验证。两轮双方针对性指令与指定盯人强制关闭。</p>':'');
}
function bindCareerTesting(){
 if($('#career-league'))$('#career-league').onchange=async e=>{
  if(activeJob){e.target.value=careerLeague;return toast('请等待当前实验结束');}
  careerLeague=e.target.value;saveClub=careerClubs()[0]?.uid??null;
  clearCareerSelection();drawSaveMode();if(saveClub!=null)await readSaveClub();
 };
 if($('#career-two-rounds'))$('#career-two-rounds').onchange=e=>{careerTwoRounds=e.target.checked;drawSaveMode();};
 if($('#career-retest'))$('#career-retest').oninput=e=>{careerRetest=Number(e.target.value);updateSaveTotal();};
}
function clearCareerSelection(){
 clearTimeout(saveTimer);saveOpponentRequest++;
 saveRoster=null;saveLoaded=null;saveChosen.clear();saveOpponents=[];reference=null;
 localStorage.removeItem('fm27-career-original');
}
function careerRoundLeader(r,g){
 const entries=Object.entries(r.metrics).filter(([,m])=>m);
 if(!r.complete||entries.length<2)return '';
 const best=r.metrics[r.ranking[0]];
 const equal=entries.filter(([,m])=>m.win_rate===best.win_rate&&m.points===best.points&&m.goals_for-m.goals_against===best.goals_for-best.goals_against);
 if(!equal.some(([key])=>key===g))return '';
 return equal.length>1?'并列':'本轮实测领先';
}
function careerRoundResults(j){
 if(!j.test_rounds?.length)return '';
 const rows=Object.values(j.round_results||{}).flatMap(r=>Object.entries(r.metrics).map(([g,m])=>
  '<tr><td>'+esc(r.name)+'</td><td>'+(g==='A'?'对照 A':'本次 B')+'</td><td>'+(m?.n||0)+'</td><td>'+(m?pct(m.win_rate):'—')+'</td><td>'+(m?m.wins+' / '+m.draws+' / '+m.losses:'—')+'</td><td>'+r.seed_first+'–'+r.seed_last+'</td><td>'+(careerRoundLeader(r,g))+'</td></tr>'));
 return '<section class="card"><div class="card-head"><h3>两轮独立结果</h3></div><p class="tiny muted">主胜率卡片显示第二轮已完成结果（第二轮未开始时显示第一轮）。下方逐对手和主客场统计为两轮合计。小样本领先不代表稳定提升；两轮双方针对性指令已关闭。</p><div class="table-scroll"><table><thead><tr><th>轮次</th><th>方案</th><th>场数</th><th>胜率</th><th>胜／平／负</th><th>种子范围</th><th>排名</th></tr></thead><tbody>'+rows.join('')+'</tbody></table></div></section>';
}
