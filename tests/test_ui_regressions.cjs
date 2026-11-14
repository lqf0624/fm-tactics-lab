const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ui=path.join(__dirname,'../src/tactics_ui');
function fragment(file,start,end){const text=fs.readFileSync(path.join(ui,file),'utf8');return text.slice(text.indexOf(start),end?text.indexOf(end,text.indexOf(start)):undefined);}
function context(values){return vm.createContext(values);}
test('opposition button opens the save opponent picker on a DOM click',async()=>{
 const button={};let opened=0;
 const c=context({view:'opposition',$:s=>s==='[data-oi-choose]'?button:null,$$:()=>[],saveOpponentRequest:0,saveInfo:{id:'save'},saveClub:1,saveMode:'save',api:async()=>({status:'complete',opponents:[]}),showSaveOpponents:()=>opened++,toast:assert.fail});
 vm.runInContext(fragment('save-mode.js','async function discoverSaveOpponents','function showSaveOpponents'),c);
 vm.runInContext(fragment('advanced.js','function bindOpposition','function setPiecesView'),c);
 c.bindOpposition();await button.onclick({type:'click'});assert.equal(opened,1);
});
function team(ids,id='save',club=1){return {name:'Club',players:ids.map(source_uid=>({source_uid,name:String(source_uid)})),lineup:ids.map((_,i)=>i),roster_size:ids.length,roster_source:{id,club_uid:club},opposition:{players:ids.map(()=>({press:0,mark:0,tackle:0,foot:0,personal:false})),positions:{GK:{press:2}}},phases:[[{instructions:{14:34},target_player:0}]]};}
async function loadRoster(ids,id='save',automatic=false){
 const old=team([1,2]),other=team([9,10]);other.opposition.players[0]={press:2,mark:1,tackle:0,foot:0,personal:true};
 const loaded=team(ids,id,2),button={dataset:{loadRoster:'1'}};
 const c=context({state:{teams:[other,old]},saveMode:'free',saveClub:null,saveInfo:null,$$:s=>s==='[data-load-roster]'?[button]:[],$:()=>({value:'2'}),refreshPlayerLabels:async()=>{},save(){},saveModeDraft(){},render(){},toast:assert.fail,showActionError:(_,e)=>assert.fail(e),localStorage:{getItem:()=>null,setItem(){}},api:async url=>url.endsWith('board-clubs')?{id,own:null,opponent:2,clubs:[{uid:2,name:'Club'}]}:loaded});
 vm.runInContext(fragment('desktop-workspace.js','let boardRosterSource'),c);
 vm.runInContext("boardRosterSource={id:'save',clubs:[{uid:2}]};",c);
 if(automatic)await c.initializeBoardRoster();else{c.bindBoardRosterControls();await button.onclick();}
 return {other,loaded};
}
test('replacing a club clears player-specific instructions and missing marking targets',async()=>{
 const {other}=await loadRoster([3,4]);assert.equal(other.opposition.players[0].personal,false);assert.equal(other.opposition.players[0].press,0);assert.equal(other.phases[0][0].target_player,255);assert.equal(other.phases[0][0].instructions[14],0);assert.equal(other.opposition.positions.GK.press,2);
});
test('same-save roster reorder follows player identities and match roster order',async()=>{
 const {other}=await loadRoster([2,1]);assert.equal(other.opposition.players[1].personal,true);assert.equal(other.opposition.players[1].press,2);assert.equal(other.phases[0][0].target_player,1);
});
test('automatic save rebinding clears old-save personal targets even with reused UIDs',async()=>{
 const {other}=await loadRoster([1,2],'another-save',true);assert.equal(other.opposition.players[0].personal,false);assert.equal(other.phases[0][0].target_player,255);
});
function paired(second){
 const c=context({isComparison:()=>true,esc:String,fmt:n=>n.toFixed(2)});
 vm.runInContext(fragment('desktop.js','function pairedMatchTable','const desktopResultsPrevious'),c);
 const job={test_rounds:[{number:1,name:'First round',seeds:[1]},{number:2,name:'Retest',seeds:[2]}],runs:[{variant:'A',seed:1,result:{score:[0,0]}},{variant:'B',seed:1,result:{score:[10,0]}}]};
 if(second)job.runs.push({variant:'A',seed:2,result:{score:[2,0]}},{variant:'B',seed:2,result:{score:[0,0]}});
 return c.pairedMatchTable(job);
}
test('paired result uses independent retest scores once retest starts',()=>{const html=paired(true);assert.match(html,/Retest/);assert.match(html,/<td>2.00<\/td><td>0.00<\/td><td>-2.00<\/td><td>1<\/td>/);});
test('paired result keeps first round before retest starts',()=>{const html=paired(false);assert.match(html,/First round/);assert.match(html,/<td>0.00<\/td><td>10.00<\/td><td>\+10.00<\/td><td>1<\/td>/);});

test('opening a legacy real-player draft preserves edits across repeated initialization',async()=>{
 const own=team([1,2]);delete own.roster_source;own.lineup=[1,0];own.players[0].attributes=[99];
 const initial=structuredClone(own),stored=new Map();let reads=0;
 const c=context({state:{teams:[own,team([8,9])]},saveMode:'free',saveClub:null,saveInfo:null,
  localStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)},
  refreshPlayerLabels:async()=>{},save(){stored.set('draft',JSON.stringify(c.state));},showActionError:(_,e)=>assert.fail(e),
  api:async url=>{if(url.endsWith('board-clubs'))return {id:'save',own:1,opponent:null,clubs:[{uid:1,name:'Club'}]};reads++;return team([3,4]);}});
 vm.runInContext(fragment('desktop-workspace.js','let boardRosterSource'),c);
 await c.initializeBoardRoster();await c.initializeBoardRoster();
 assert.deepEqual(c.state.teams[0],initial);assert.equal(reads,0);assert.equal(stored.has('draft'),false);
});

test('loading a different save clears the loaded teams UID overrides',()=>{
 const own=team([1,2],'old-save'),other=team([9,10],'old-save');
 own.opposition.by_player_uid={'999':{press:2,mark:0,tackle:0,foot:0,personal:true}};
 const c=context({state:{teams:[own,other]}});
 vm.runInContext(fragment('desktop-workspace.js','let boardRosterSource'),c);
 const loaded=structuredClone(own);loaded.roster_source.id='new-save';
 c.replaceBoardRoster(c.state,0,loaded);
 assert.equal(c.state.teams[0].opposition.by_player_uid,undefined);
 assert.equal(c.state.teams[0].opposition.positions.GK.press,2);
});

test('same-save roster reload preserves explicit UID overrides',()=>{
 const own=team([1,2]),other=team([9,10]);
 own.opposition.by_player_uid={'999':{press:2,mark:0,tackle:0,foot:0,personal:true}};
 const c=context({state:{teams:[own,other]}});
 vm.runInContext(fragment('desktop-workspace.js','let boardRosterSource'),c);
 c.replaceBoardRoster(c.state,0,structuredClone(own));
 assert.equal(c.state.teams[0].opposition.by_player_uid['999'].press,2);
});
