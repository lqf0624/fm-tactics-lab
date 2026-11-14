const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

(async () => {
 const metric = {delta:0.005,standard_error:0.001};
 const row = {slot:0,attribute:0,player:'<script>unsafe</script>',before:60,after:75,
  phases:[{position:'ST',role:'Forward'},{position:'ST',role:'Forward'}],
  n:40,selected:true,recommended:false,lower:0.001,upper:0.009,
  xg_difference_per_three:0.005,xg_difference_per_point:0.005/3,standard_error:0.001,
  exploration:{n:16,metrics:{xg_difference:metric}},
  metrics:Object.fromEntries(['goals_for','goals_against','xg','xga','xg_difference'].map(k=>[k,metric])),
  opponents:[{name:'Opponent',delta:0.005,n:40}]};
 const higher={...row,attribute:1,xg_difference_per_three:0.025,xg_difference_per_point:0.025/3};
 const job = {id:'report-test',name:'Test',status:'complete',completed:112,total:112,
  attribute_screen:{schema:2,tested_slots:[0],cases:[row],opponent_names:['Opponent'],seed_count:40,
   exploration_seeds:Array.from({length:16},(_,i)=>i),validation_seeds:Array.from({length:40},(_,i)=>16+i),
   candidate_threshold:0.02,strong_threshold:0.05,candidate_limit:5,recommendation_limit:3},
  attribute_report:[row,higher]};
 let exported;
 const button = {};
 const context = {selectedJob:job,catalog:{attributes:[{label:'Passing'},{label:'Finishing'}]},
  roles:()=>({Forward:{label:'Forward'}}),resultsView:()=>'',tacticsView:()=>'',bind:()=>{},poll:async()=>{},
  esc:s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  $:id=>id==='#export-attribute-report'?button:null,
  DOMParser:class {parseFromString(html){return {documentElement:{outerHTML:html.slice(15)},createTreeWalker:()=>({nextNode:()=>null})};}},
  NodeFilter:{SHOW_TEXT:4},window:{FM27I18n:{language:'zh-CN',translate:s=>s}},
  downloadFile:(name,html)=>{assert.equal(name,'attribute-report-report-test.html');exported=html;}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/tactics_ui/attribute-analysis.js'),'utf8'),context);
 assert.deepEqual([...context.attributeCheckedSlots({querySelectorAll:()=>[
  {checked:true,value:'1'},{checked:true,value:'4'}]} )],[1,4]);
 const html=context.attributeScreenReport(job);
 assert(html.includes('暂无独立复测为正的推荐'));
 assert(html.includes('候选：复测未转正'));
 assert(html.includes('不强制 20 对'));
 assert(html.includes('<th>实际收益排名</th>'));
 assert(html.includes('<th>每点敏感度排名</th>'));
 assert(html.includes('探索 2 / 2<br>验证 2 / 2'));
 assert(!html.includes('探索候选（待验证）'));
 assert(html.includes('<td>1</td><td>Finishing</td>'));
 assert(html.indexOf('<td>1</td><td>Finishing</td>') < html.indexOf('<td>2</td><td>Passing</td>'));
 assert(!html.includes('<script>unsafe'));
 context.bind();button.onclick();
 assert(exported.startsWith('<!doctype html>'));
 assert(!exported.includes('id="export-attribute-report"'));
 assert(exported.includes('保守误差区间'));
 job.attribute_screen.selection_policy='dual_v1';
 higher.recommended=true;higher.recommendation_tier='preliminary';
 higher.evidence_warnings=['验证样本较少'];
 const revised=context.attributeScreenReport(job);
 const overview=revised.slice(0,revised.indexOf('<details>'));
 assert(overview.includes('初步关注'));
 assert(overview.includes('验证样本较少'));
 assert(overview.includes('40/40 对'));
 assert(revised.includes('完整验证模式评估全部属性'));
 higher.n=1;
 assert(context.attributeScreenReport(job).includes('探索 2 / 2<br>验证 1 / 2'));
 assert(context.attributeScreenReport(job).includes('<td>—</td><td>—</td><td>Finishing</td>'));
 higher.n=40;
 const savedReport=job.attribute_report;
 delete job.attribute_report;job.status='error';job.error='marker busy';
 const incomplete=context.attributeScreenReport(job);
 assert(incomplete.includes('关键属性报告尚未生成'));
 assert(incomplete.includes('不能把“没有报告”解释为“没有推荐”'));
 job.attribute_report=savedReport;
 console.log('Research recommendations and standalone export verified');
})().catch(error=>{console.error(error);process.exitCode=1});
