import React from 'react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Workspace from './Workspace';
import savedResult from '../../examples/cup-handle/result.json';
const projects:any[]=[];
const requests:any[]=[];
const connections:any[]=[];
const savedRuns:any[]=[];
const materialRecords:any[]=[];
let catalogResponse:()=>Promise<any>;
let messageStatus='completed';
beforeEach(()=>{
  window.history.replaceState(null,'','#/');
  messageStatus='completed';
  localStorage.clear();projects.length=0;requests.length=0;connections.length=0;savedRuns.length=0;materialRecords.length=0;
  catalogResponse=async()=>({ok:true,json:async()=>({models:['alpha-model','beta-model'],status:'catalog_available'})});
  vi.stubGlobal('fetch',vi.fn(async(url:string,options:any)=>{
    const path=url.replace('/api/workspace','');requests.push({path,options});
    let data:any=[];
    if(path==='/providers')data=[{id:'openai',label:'OpenAI',environment_available:true},{id:'anthropic',label:'Anthropic',environment_available:false}];
    if(path==='/connections/catalog')return catalogResponse();
    if(path==='/connections'){
      if(options?.method==='POST'){data={...JSON.parse(options.body),id:'saved',configured:true};delete data.key;connections.push(data)}
      else data=[...connections];
    }
    if(path==='/projects'&&options?.method==='POST'){
      const body=JSON.parse(options.body);
      data={id:String(projects.length+1),title:body.title,locale:body.locale,revision:0,draft:null,versions:[],records:[],busy:false,model_roles:{builder:null,execution:null},
        messages:[{id:'welcome',role:'assistant',kind:'welcome',text:'先说说你最想实现的那部分吧。'}]};projects.push(data);
    }else if(path==='/projects')data=[...projects];
    else if(path.startsWith('/projects/')){
      data=projects.find(p=>p.id===path.split('/')[2]);
      if(path.endsWith('/models')){
        const roles=JSON.parse(options.body);
        if(Object.values(roles).some(id=>id!==null&&!connections.some(c=>c.id===id&&c.configured)))
          return {ok:false,json:async()=>({detail:'Select a configured model connection.'})};
        data={...data,model_roles:roles};projects[projects.findIndex(p=>p.id===data.id)]=data;
      }
      if(path.endsWith('/messages')){
        data={...data,records:[...data.records,{id:'reply',status:messageStatus,committed_cost:0}]};
        projects[projects.findIndex(p=>p.id===data.id)]=data;
      }
      if(path.includes('/runs'))data=path.endsWith('/runs')?[...savedRuns]:savedRuns.find(r=>r.id===path.split('/').at(-1));
      if(path.includes('/materials'))data=path.endsWith('/materials')?[...materialRecords]:materialRecords.find(m=>m.id===path.split('/').at(-1));
    }
    if(path==='/demo')data={config:{},result:savedResult};
    return {ok:true,json:async()=>data};
  }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
test('model calls separate usage pricing from reserved and legacy budget amounts',async()=>{
  projects.push({id:'costs',title:'Cost project',messages:[],versions:[],records:[
    {id:'priced',model:'test',status:'completed',accounting_version:2,cost_status:'usage_priced',usage_cost:.01,committed_cost:.01},
    {id:'pending',model:'test',status:'unknown',accounting_version:2,committed_cost:.06},
    {id:'old',model:'test',status:'completed',committed_cost:.08}
  ],busy:false});
  render(<Workspace/>);fireEvent.click(await screen.findByRole('button',{name:'Cost project'}));
  expect(await screen.findByText(/预算占用.*0.1500/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'模型调用记录'}));
  expect(await screen.findByText('供应商账单')).toBeTruthy();
  expect(screen.getByText('未接入')).toBeTruthy();
  expect(screen.getByText('1 条已计价记录',{exact:false})).toBeTruthy();
  expect(screen.getByText('待结算预留')).toBeTruthy();
  expect(screen.getAllByText(/历史预算记录（非账单）/).length).toBeGreaterThan(0);
});
test.each([['','',undefined,undefined],['0.02','0.3',.02,.3]])('connection saves optional cache rates without treating blanks as free tokens (%s)',async(cached,write,expectedCached,expectedWrite)=>{
  render(<Workspace/>);fireEvent.click(await screen.findByRole('button',{name:'模型设置'}));
  for(const [label,value] of [['API Key','offline-fixture'],['模型 ID','test-model'],['连接名称','Test'],['输入价格 / 百万 tokens（美元）','0.2'],['输出价格 / 百万 tokens（美元）','0.5'],['缓存读取价格 / 百万 tokens（美元）',cached],['缓存写入价格 / 百万 tokens（美元）',write]])
    fireEvent.change(screen.getByLabelText(label),{target:{value}});
  fireEvent.click(screen.getByRole('button',{name:'保存连接'}));
  await waitFor(()=>expect(connections.length).toBe(1));
  expect(connections[0].cached_input_price).toBe(expectedCached);
  expect(connections[0].cache_write_price).toBe(expectedWrite);
});
test('browser title follows interface language independently of project conversation',async()=>{
  document.title='Previous page';
  render(<Workspace/>);
  await waitFor(()=>expect(document.title).toBe('Strategy Agent Lab · 方法构建工作台'));
  fireEvent.change(screen.getByLabelText('界面语言'),{target:{value:'en'}});
  await waitFor(()=>expect(document.title).toBe('Strategy Agent Lab · Method workbench'));
  expect(requests.some(r=>r.path.endsWith('/messages'))).toBe(false);
});
test('unsupported selected image offers settings action and retains attachment while configuring',async()=>{
  connections.push({id:'builder',name:'Builder',configured:true,provider:'openai',model:'offline'});
  projects.push({id:'visual',title:'Visual',locale:'en',revision:0,draft:null,versions:[],messages:[],records:[],busy:false,model_roles:{builder:'builder',execution:null}});
  materialRecords.push({id:'image',name:'example.png',sha256:'hash',image:{sha256:'normalized',width:30,height:20},locations:1,units:[{location:'I1',text:'Visual source'}]});
  render(<Workspace/>);fireEvent.click(await screen.findByRole('button',{name:'Visual'}));
  fireEvent.click(await screen.findByRole('button',{name:'材料'}));fireEvent.click(await screen.findByRole('button',{name:'example.png'}));
  fireEvent.click(await screen.findByRole('button',{name:'选择全部位置'}));fireEvent.click(screen.getByRole('button',{name:'在对话中引用选定位置'}));
  fireEvent.click(await screen.findByRole('button',{name:'启用或选择兼容的图片连接'}));
  fireEvent.click(await screen.findByRole('button',{name:'返回当前项目'}));
  expect(screen.getByText('example.png · I1')).toBeTruthy();
  expect((screen.getByRole('button',{name:'发送'}) as HTMLButtonElement).disabled).toBe(true);
  expect(requests.some(r=>r.path.endsWith('/messages'))).toBe(false);
});
test('failed authorized image reply retains attachment and requires a new authorization',async()=>{
  messageStatus='unknown';connections.push({id:'builder',name:'Builder',configured:true,provider:'openai',model:'offline',image_inputs:true});
  projects.push({id:'failed-visual',title:'Failed visual',locale:'en',revision:0,draft:null,versions:[],messages:[],records:[],busy:false,model_roles:{builder:'builder',execution:null}});
  materialRecords.push({id:'image',name:'example.png',sha256:'hash',image:{sha256:'normalized',width:30,height:20},locations:1,units:[{location:'I1',text:'Visual source'}]});
  render(<Workspace/>);fireEvent.click(await screen.findByRole('button',{name:'Failed visual'}));
  const authorization=await screen.findByRole('checkbox');
  fireEvent.click(screen.getByRole('button',{name:'材料'}));fireEvent.click(await screen.findByRole('button',{name:'example.png'}));
  fireEvent.click(await screen.findByRole('button',{name:'选择全部位置'}));fireEvent.click(screen.getByRole('button',{name:'在对话中引用选定位置'}));
  fireEvent.click(authorization);fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await screen.findByRole('alert');
  expect(screen.getByText('example.png · I1')).toBeTruthy();
  expect((authorization as HTMLInputElement).checked).toBe(false);
});
test('material attachments require fresh authorization and carry multiple exact source identities',async()=>{
  connections.push({id:'builder',name:'Builder',configured:true,provider:'openai',model:'offline'});
  projects.push({id:'material-project',title:'Material project',locale:'en',revision:0,draft:null,versions:[],messages:[],records:[],busy:false,model_roles:{builder:'builder',execution:null}});
  materialRecords.push({id:'notes',name:'notes.txt',sha256:'notes-hash',locations:1,units:[{location:'L1',text:'method notes'}]}, {id:'helper',name:'helper.txt',sha256:'helper-hash',locations:1,units:[{location:'L1',text:'ratio=0.125'}]});
  render(<Workspace/>);fireEvent.click(await screen.findByRole('button',{name:'Material project'}));
  const approval=await screen.findByRole('checkbox');fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button',{name:'材料'}));
  for(const name of ['notes.txt','helper.txt']){
    fireEvent.click(await screen.findByRole('button',{name}));
    fireEvent.click(await screen.findByRole('button',{name:'选择全部位置'}));
    fireEvent.click(screen.getByRole('button',{name:'在对话中引用选定位置'}));
  }
  expect((approval as HTMLInputElement).checked).toBe(false);
  expect(requests.filter(r=>r.path.endsWith('/messages'))).toHaveLength(0);
  fireEvent.click(approval);fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await waitFor(()=>expect(requests.some(r=>r.path.endsWith('/messages'))).toBe(true));
  expect(JSON.parse(requests.find(r=>r.path.endsWith('/messages')).options.body).material_refs).toEqual([{id:'notes',sha256:'notes-hash',locations:['L1']},{id:'helper',sha256:'helper-hash',locations:['L1']}]);
});
test('execution receipts are labeled separately and preserve run decision references',async()=>{
  projects.push({id:'execution-project',title:'Execution project',locale:'en',revision:0,draft:null,versions:[],messages:[],busy:false,
    model_roles:{builder:null,execution:null},records:[{id:'request-1',kind:'execution',role:'execution',status:'completed',model:'execution-model',committed_cost:.01,created:'2024-01-03',run_id:'run-ref',decision_id:'decision-ref'}]});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Execution project'}));
  fireEvent.click(await screen.findByRole('button',{name:'模型调用记录'}));
  expect(await screen.findByText(/执行判断/)).toBeTruthy();
  expect(screen.getByText(/run-ref.*decision-ref/)).toBeTruthy();
});
test('quoted decision attaches a trusted reference and requires fresh builder authorization',async()=>{
  connections.push({id:'builder',name:'Builder',configured:true,provider:'openai',model:'offline'});
  projects.push({id:'evidence-project',title:'Evidence project',locale:'en',revision:0,draft:null,versions:[],messages:[],records:[],busy:false,
    model_roles:{builder:'builder',execution:null},builds:[]});
  savedRuns.push({id:'saved-run',build_id:'saved-build',version:1,status:'completed',completed_sessions:2,total_sessions:2,
    positions:{SPY:3},trades:[{id:'order',decision_id:'decision-1',date:'2024-01-04',symbol:'SPY',action:'buy',quantity:3,price:20,fee:0,reason:'next_session_open'}],
    decisions:[{id:'decision-1',cutoff:'2024-01-03',proposal:{symbol:'SPY'},rule:'Review the actual gap fill',account:{cash:100},evidence:{},model:null}],curve:[],orders:[]});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Evidence project'}));
  const approval=await screen.findByRole('checkbox');fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button',{name:'运行与结果'}));
  fireEvent.click(await screen.findByRole('button',{name:/saved-run/}));
  fireEvent.click(await screen.findByRole('button',{name:'buy 3 SPY · 2024-01-04'}));
  fireEvent.click(screen.getByRole('button',{name:'引用到项目对话'}));
  expect((approval as HTMLInputElement).checked).toBe(false);
  expect(requests.filter(r=>r.path.endsWith('/messages'))).toHaveLength(0);
  expect(screen.getByRole('button',{name:'移除决策证据'})).toBeTruthy();
  fireEvent.click(approval);fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await waitFor(()=>expect(requests.some(r=>r.path.endsWith('/messages'))).toBe(true));
  const sent=JSON.parse(requests.find(r=>r.path.endsWith('/messages')).options.body);
  expect(sent.evidence_ref).toEqual({run_id:'saved-run',decision_id:'decision-1'});
  expect(sent.connection_id).toBe('builder');expect(sent.authorized).toBe(true);
});
test('creates independent projects and assistant welcomes first',async()=>{
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'新建项目'}));
  fireEvent.change(screen.getByLabelText('项目名称'),{target:{value:'我的方法'}});
  fireEvent.click(screen.getByRole('button',{name:'创建项目'}));
  await screen.findByText(/先说说你最想实现的那部分吧/);
  expect(projects.length).toBe(1);
  fireEvent.click(screen.getByRole('button',{name:'新建项目'}));
  fireEvent.change(screen.getByLabelText('项目名称'),{target:{value:'另一个方法'}});
  fireEvent.click(screen.getByRole('button',{name:'创建项目'}));
  await waitFor(()=>expect(projects.length).toBe(2));
  expect(screen.queryByText(/不是杯柄模板/)).toBeNull();
  expect(screen.queryByRole('button',{name:'重新开始'})).toBeNull();
});
test('model settings has an actionable form and arbitrary supported model ID',async()=>{
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'模型设置'}));
  expect(screen.getByLabelText('模型 ID')).toBeTruthy();
  expect(screen.getByLabelText('API Key')).toBeTruthy();
  expect(screen.getByRole('button',{name:'保存连接'})).toBeTruthy();
  fireEvent.change(screen.getByLabelText('模型 ID'),{target:{value:'my-preferred-model'}});
  expect((screen.getByLabelText('模型 ID') as HTMLInputElement).value).toBe('my-preferred-model');
  expect(localStorage.getItem('API_KEY')).toBeNull();
});

test('compact navigation buttons have names and open settings',async()=>{
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'打开模型设置'}));
  expect(screen.getByLabelText('模型 ID')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'返回项目列表'}));
  expect(screen.getByRole('heading',{name:'你的方法，逐步成形。'})).toBeTruthy();
});
test('packaged project is reachable from the project list without paid requests',async()=>{
  render(<Workspace examples={[{id:'complete',title:'Complete cup',messages:[],versions:[],materials:[],builds:[],runs:[]}]}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Complete cup'}));
  expect(screen.getByRole('tab',{name:'运行与结果'})).toBeTruthy();
  expect(requests.filter(r=>r.options?.method==='POST')).toHaveLength(0);
  expect(screen.queryByRole('link',{name:'已保存示范'})).toBeNull();
});

test('approved project shows actual build action and saved code validation',async()=>{
  projects.push({id:'ready',title:'Ready',locale:'en',revision:1,draft:{scope:'Daily',rules:[],questions:[]},
    messages:[],records:[],busy:false,versions:[{version:1,revision:1,method:{scope:'Daily',rules:[]}}],
    builds:[{id:'b',version:1,status:'completed',events:[],artifacts:[{name:'strategy.py',text:'def signal(): return True'}],
      validation:{tests_passed:true,test_output:'Ran 3 tests\nOK',demo_exit:0,demo_output:'{"synthetic":true}'}}]});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Ready'}));
  expect(await screen.findByRole('button',{name:'构建并验证 v1'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'实现与验证'}));
  expect(await screen.findByText('strategy.py')).toBeTruthy();
  expect(screen.getByText(/Ran 3 tests/)).toBeTruthy();
});

test('construction guidance describes selected isolation and page title follows UI language',async()=>{
  projects.push({id:'ready',title:'Ready',locale:'en',revision:1,draft:{scope:'Daily',rules:[],questions:[]},
    messages:[],records:[],busy:false,builds:[],versions:[{version:1,revision:1,method:{scope:'Daily',rules:[]}}]});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Ready'}));
  expect(await screen.findByText(/代码在当前选定的隔离环境中生成并验证/)).toBeTruthy();
  expect(screen.queryByText(/代码构建目前需要 Windows MXC/)).toBeNull();
  expect(document.title).toBe('Strategy Agent Lab · 方法构建工作台');
  fireEvent.change(screen.getByLabelText('界面语言'),{target:{value:'en'}});
  expect(screen.getByText(/Code is generated and validated in the selected isolated runtime/)).toBeTruthy();
  expect(document.title).toBe('Strategy Agent Lab · Method workbench');
  expect(document.documentElement.lang).toBe('en');
  expect(requests.filter(r=>r.options?.method==='POST')).toHaveLength(0);
});

test('fetches a catalog before other settings, searches and selects without inference',async()=>{
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'模型设置'}));
  fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'private-browser-key'}});
  fireEvent.click(screen.getByRole('button',{name:'读取模型目录'}));
  await screen.findByRole('option',{name:'alpha-model'});
  fireEvent.change(screen.getByLabelText('搜索模型'),{target:{value:'BETA'}});
  expect(screen.queryByRole('option',{name:'alpha-model'})).toBeNull();
  fireEvent.change(screen.getByLabelText('目录中的模型'),{target:{value:'beta-model'}});
  expect((screen.getByLabelText('模型 ID') as HTMLInputElement).value).toBe('beta-model');
  expect(JSON.parse(requests.find(r=>r.path==='/connections/catalog').options.body)).toEqual({provider:'openai',key:'private-browser-key',use_environment:false});
  expect(requests.filter(r=>r.options?.method==='POST').map(r=>r.path)).toEqual(['/connections/catalog']);
  expect(JSON.stringify(localStorage)).not.toContain('private-browser-key');
});

test('provider and credential changes discard old and in-flight catalog results',async()=>{
  let finish!:(data:any)=>void;
  catalogResponse=()=>new Promise(resolve=>{finish=resolve});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'模型设置'}));
  fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'private-browser-key'}});
  fireEvent.click(screen.getByRole('button',{name:'读取模型目录'}));
  fireEvent.change(screen.getByLabelText('供应商'),{target:{value:'anthropic'}});
  finish({ok:true,json:async()=>({models:['wrong-provider-model']})});
  await waitFor(()=>expect(screen.queryByRole('option',{name:'wrong-provider-model'})).toBeNull());
  catalogResponse=async()=>({ok:true,json:async()=>({models:['new-provider-model']})});
  fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'new-private-key'}});
  fireEvent.click(screen.getByRole('button',{name:'读取模型目录'}));
  await screen.findByRole('option',{name:'new-provider-model'});
  fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'changed-private-key'}});
  expect(screen.queryByRole('option',{name:'new-provider-model'})).toBeNull();
});

test('catalog failure preserves manual model entry and connection save',async()=>{
  catalogResponse=async()=>({ok:false,json:async()=>({detail:'Catalog unavailable'})});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'模型设置'}));
  fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'private-browser-key'}});
  fireEvent.change(screen.getByLabelText('模型 ID'),{target:{value:'manual-model'}});
  fireEvent.click(screen.getByRole('button',{name:'读取模型目录'}));
  await screen.findByText(/可手动填写模型 ID/);
  expect((screen.getByLabelText('模型 ID') as HTMLInputElement).value).toBe('manual-model');
  fireEvent.change(screen.getByLabelText('连接名称'),{target:{value:'Manual'}});
  fireEvent.change(screen.getByLabelText('输入价格 / 百万 tokens（美元）'),{target:{value:'1'}});
  fireEvent.change(screen.getByLabelText('输出价格 / 百万 tokens（美元）'),{target:{value:'3'}});
  fireEvent.click(screen.getByRole('button',{name:'保存连接'}));
  await waitFor(()=>expect(connections).toHaveLength(1));
  expect(connections[0].model).toBe('manual-model');
  await waitFor(()=>expect((screen.getByLabelText('API Key') as HTMLInputElement).value).toBe(''));
});

function roleProject(id:string,builder:string|null,execution:string|null){
  return {id,title:id,locale:'en',revision:0,draft:null,versions:[],records:[],messages:[],busy:false,model_roles:{builder,execution}};
}
test('project switching restores independent roles and revokes spending approval',async()=>{
  connections.push({id:'a',name:'Alpha',model:'a-model',configured:true},{id:'b',name:'Beta',model:'b-model',configured:true});
  projects.push(roleProject('One','a',null),roleProject('Two','b','a'));
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'One'}));
  expect((await screen.findByLabelText('构建模型')).getAttribute('value')??(screen.getByLabelText('构建模型') as HTMLSelectElement).value).toBe('a');
  expect((screen.getByLabelText('执行模型（可选）') as HTMLSelectElement).value).toBe('');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Two'}));
  await waitFor(()=>expect((screen.getByLabelText('构建模型') as HTMLSelectElement).value).toBe('b'));
  expect((screen.getByLabelText('执行模型（可选）') as HTMLSelectElement).value).toBe('a');
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  fireEvent.change(screen.getByLabelText('你的方法或补充'),{target:{value:'hello'}});
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await waitFor(()=>expect(requests.find(r=>r.path==='/projects/Two/messages')).toBeTruthy());
  expect(JSON.parse(requests.find(r=>r.path==='/projects/Two/messages').options.body).connection_id).toBe('b');
  await waitFor(()=>expect((screen.getByLabelText('执行模型（可选）') as HTMLSelectElement).disabled).toBe(false));
  fireEvent.change(screen.getByLabelText('执行模型（可选）'),{target:{value:''}});
  expect(requests.filter(r=>r.path==='/projects/Two/models')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button',{name:'保存模型分工'}));
  await waitFor(()=>expect(requests.find(r=>r.path==='/projects/Two/models')).toBeTruthy());
  expect(JSON.parse(requests.find(r=>r.path==='/projects/Two/models').options.body)).toEqual({builder:'b',execution:null});
});

test('missing builder binding stays visible and cannot silently use another connection',async()=>{
  connections.push({id:'other',name:'Other',model:'m',configured:true});
  projects.push(roleProject('Missing','deleted',null));
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Missing'}));
  await screen.findByText(/连接已移除或凭据未配置/);
  expect((screen.getByLabelText('构建模型') as HTMLSelectElement).value).toBe('deleted');
  fireEvent.change(screen.getByLabelText('你的方法或补充'),{target:{value:'hello'}});
  fireEvent.click(screen.getByRole('checkbox'));
  expect((screen.getByRole('button',{name:'发送'}) as HTMLButtonElement).disabled).toBe(true);
});

test.each(['unconfigured','deleted'])('repairs both %s roles atomically and blocks unsaved model calls',async state=>{
  if(state==='unconfigured')connections.push({id:'missing-builder',name:'Old builder',model:'old',configured:false},
    {id:'missing-execution',name:'Old execution',model:'old',configured:false});
  connections.push({id:'replacement',name:'New connection',model:'new-model',configured:true});
  projects.push({...roleProject('Repair','missing-builder','missing-execution'),
    draft:{scope:'Daily',rules:[],questions:[]},versions:[{version:1,revision:0,method:{scope:'Daily',rules:[]}}]});
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Repair'}));
  const builder=await screen.findByLabelText('构建模型') as HTMLSelectElement;
  const execution=screen.getByLabelText('执行模型（可选）') as HTMLSelectElement;
  const approval=screen.getByRole('checkbox') as HTMLInputElement;
  fireEvent.change(screen.getByLabelText('你的方法或补充'),{target:{value:'Continue this project'}});
  fireEvent.click(approval);
  expect(approval.checked).toBe(true);
  fireEvent.change(builder,{target:{value:'replacement'}});
  expect(builder.value).toBe('replacement');
  expect(approval.checked).toBe(false);
  expect(approval.disabled).toBe(true);
  fireEvent.change(execution,{target:{value:''}});
  expect(execution.value).toBe('');
  expect(projects[0].model_roles).toEqual({builder:'missing-builder',execution:'missing-execution'});
  expect(requests.filter(r=>r.path.endsWith('/models'))).toHaveLength(0);
  expect((screen.getByRole('button',{name:'发送'}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button',{name:'构建并验证 v1'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.submit(screen.getByLabelText('你的方法或补充').closest('form')!);
  expect(requests.filter(r=>r.path.endsWith('/messages'))).toHaveLength(0);
  fireEvent.click(screen.getByRole('button',{name:'保存模型分工'}));
  await waitFor(()=>expect(projects[0].model_roles).toEqual({builder:'replacement',execution:null}));
  await waitFor(()=>expect(approval.disabled).toBe(false));
  expect(approval.checked).toBe(false);
  expect(requests.filter(r=>r.path.endsWith('/models')).map(r=>JSON.parse(r.options.body))).toEqual([{builder:'replacement',execution:null}]);
  fireEvent.click(approval);
  expect((screen.getByRole('button',{name:'构建并验证 v1'}) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await waitFor(()=>expect(requests.find(r=>r.path==='/projects/Repair/messages')).toBeTruthy());
  expect(JSON.parse(requests.find(r=>r.path==='/projects/Repair/messages').options.body).connection_id).toBe('replacement');
  await waitFor(()=>expect(builder.disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'项目'}));
  fireEvent.click(screen.getByRole('button',{name:'Repair'}));
  await waitFor(()=>expect((screen.getByLabelText('构建模型') as HTMLSelectElement).value).toBe('replacement'));
  expect((screen.getByLabelText('执行模型（可选）') as HTMLSelectElement).value).toBe('');
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
});
