import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import ProjectRuns from './ProjectRuns';
afterEach(cleanup);
const t=(_:string,en:string)=>en;
const build=(model=false)=>({id:'b1',version:1,status:'completed',execution_hash:'sealed',artifacts:[{name:'execution.json',text:JSON.stringify({schema:'strategy-v1',judgment:model?{criteria:'rising'}:null})}]});
const project=(model=false)=>({id:'p1',builds:[build(model)],busy:false,model_roles:{builder:null,execution:model?'execution':null},records:[]});
test('approved managed commission is selected and cannot be silently overridden',async()=>{
  const p=project();p.builds[0].artifacts[0].text=JSON.stringify({schema:'strategy-v1',judgment:null,account:{mode:'risk-managed',commission:.0005}});
  render(<ProjectRuns project={p} connections={[]} budget={2} rolesPending={false} api={async()=>[]} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  const fee=await screen.findByLabelText('Fee per side');
  await waitFor(()=>expect((fee as HTMLInputElement).value).toBe('0.05'));
  expect((fee as HTMLInputElement).disabled).toBe(true);
});

test('new project explains build-first without an older-build migration warning',async()=>{
  const p=project();p.builds=[];
  const api=vi.fn(async()=>[]);
  render(<ProjectRuns project={p} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  expect(await screen.findByText('Approve your method, then build and validate it before starting a historical run.')).toBeTruthy();
  expect(screen.queryByText(/Older builds/)).toBeNull();
  expect((screen.getByRole('button',{name:'Start historical run'}) as HTMLButtonElement).disabled).toBe(true);
});

test('visual execution requires image-enabled execution connection and offers configuration action',async()=>{
  const p=project(true);p.builds[0].artifacts[0].text=JSON.stringify({schema:'strategy-v1',judgment:{criteria:'visual',input_mode:'chart_and_text'}});
  const configure=vi.fn();const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:[];
  render(<ProjectRuns project={p} connections={[{id:'execution',configured:true,provider:'openai'}]} budget={10} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}} onConfigure={configure}/>);
  await screen.findByText('No historical runs yet.');
  fireEvent.change(screen.getByLabelText('Start session'),{target:{value:'2024-01-03'}});fireEvent.change(screen.getByLabelText('End session'),{target:{value:'2024-01-05'}});
  fireEvent.click(screen.getByLabelText('Authorize execution model spending'));
  expect((screen.getByRole('button',{name:'Start historical run'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Configure execution image inputs'}));expect(configure).toHaveBeenCalled();
});
function result(id:string){return {id,build_id:'b1',version:1,status:'completed',completed_sessions:3,total_sessions:3,
  frozen:{assumptions:{start:'2024-01-03',end:'2024-01-05',symbols:['SPY'],initial_cash:100,fee_rate:0},build_hash:'build-hash',market_hash:'market-hash',run_hash:'run-hash',price_basis:'Frozen prices',model:null},
  curve:[{date:'2024-01-03',equity:100},{date:'2024-01-05',equity:88}],positions:{SPY:3},orders:[],
  trades:[{id:'d1-order',decision_id:'d1',date:'2024-01-04',symbol:'SPY',action:'buy',quantity:3,price:20,fee:0,reason:'next_session_open'}],
  decisions:[{id:'d1',cutoff:'2024-01-03',status:'ordered',proposal:{symbol:'SPY',action:'buy',sizing:{shares:3},explanation:'Approved entry R1'},
    rule:'Approved entry R1',input_hash:'input-hash',account:{cash:100,positions:{}},evidence:{SPY:[{date:'2024-01-03',open:12,high:14,low:11,close:13,volume:100}]},model:null}]};}

test.each(['en','zh-CN'])('saved run shows frozen-capital return and peak-to-trough drawdown in %s',async language=>{
  const saved=result('metrics-run');
  saved.curve=[90,120,90,110].map((equity,index)=>({date:`2024-01-0${index+2}`,equity}));
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:path.endsWith('/runs')?[saved]:saved;
  const translate=(zh:string,en:string)=>language==='en'?en:zh;
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={translate} onQuote={()=>{}} onChanged={async()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/metrics-run/}));
  const summary=await screen.findByRole('group',{name:translate('运行表现','Run performance')});
  expect(within(summary).getByText('$110.00')).toBeTruthy();
  expect(within(summary).getByText(translate('累计收益率','Total return'))).toBeTruthy();
  expect(within(summary).getByText('10%')).toBeTruthy();
  expect(within(summary).getByText(translate('最大回撤（日收盘）','Maximum drawdown (daily close)'))).toBeTruthy();
  expect(within(summary).getByText('25%')).toBeTruthy();
  fireEvent.change(screen.getByLabelText(translate('初始现金','Initial cash')),{target:{value:'1000'}});
  expect(within(summary).getByText('10%')).toBeTruthy();
});

test('switching saved runs updates return and counts first-session loss from initial capital',async()=>{
  const gain=result('gain-run'),loss=result('loss-run');
  gain.curve=[{date:'2024-01-03',equity:100},{date:'2024-01-05',equity:110}];
  loss.curve=[{date:'2024-01-03',equity:80},{date:'2024-01-05',equity:90}];
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:path.endsWith('/runs')?[gain,loss]:path.endsWith('/gain-run')?gain:loss;
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/gain-run/}));
  let summary=await screen.findByRole('group',{name:'Run performance'});
  expect(within(summary).getByText('10%')).toBeTruthy();
  expect(within(summary).getByText('0%')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:/loss-run/}));
  await waitFor(()=>expect(within(summary).getByText('-10%')).toBeTruthy());
  expect(within(summary).getByText('20%')).toBeTruthy();
});

test('missing frozen capital does not invent return or drawdown for an existing equity curve',async()=>{
  const saved:any=result('legacy-run');delete saved.frozen;
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:path.endsWith('/runs')?[saved]:saved;
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/legacy-run/}));
  const summary=await screen.findByRole('group',{name:'Run performance'});
  expect(within(summary).getByText('$88.00')).toBeTruthy();
  expect(within(summary).queryByText('Total return')).toBeNull();
  expect(within(summary).queryByText('Maximum drawdown (daily close)')).toBeNull();
});

test('code-only run starts without any model authorization or connection',async()=>{
  const requests:any[]=[];
  const api=async(path:string,body?:any)=>{
    requests.push({path,body});
    if(path==='/execution-catalog')return {symbols:['SPY','QQQ']};
    if(body)return {id:'new-run',status:'running'};
    if(path.endsWith('/runs'))return [];
    if(path.endsWith('/status'))return {id:'new-run',status:'running'};
    return result('new-run');
  };
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  await screen.findByText('No historical runs yet.');
  expect(screen.queryByLabelText('Authorize execution model spending')).toBeNull();
  fireEvent.change(screen.getByLabelText('Start session'),{target:{value:'2024-01-03'}});
  fireEvent.change(screen.getByLabelText('End session'),{target:{value:'2024-01-05'}});
  fireEvent.click(screen.getByRole('button',{name:'Start historical run'}));
  await waitFor(()=>expect(requests.some(r=>r.body?.build_id==='b1')).toBe(true));
  const sent=requests.find(r=>r.body?.build_id==='b1').body;
  expect(sent.authorized).toBe(false);expect(sent.connection_id).toBeNull();
  expect(requests.some(r=>/messages|build$/.test(r.path))).toBe(false);
});

test('saved run trade selection exposes dated evidence and quotes into project conversation',async()=>{
  const quote=vi.fn();
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:path.endsWith('/runs')?[result('run-a'),result('run-b')]:result(path.split('/').at(-1)!);
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={quote} onChanged={async()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/run-b/}));
  fireEvent.click(await screen.findByRole('button',{name:'buy 3 SPY · 2024-01-04'}));
  expect(await screen.findByText('Approved entry R1')).toBeTruthy();
  expect(screen.getByText('input-hash')).toBeTruthy();
  expect(screen.getByText(/next_session_open/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Quote decision in conversation'}));
  expect(quote.mock.calls[0][0]).toContain('run-b');expect(quote.mock.calls[0][0]).toContain('d1');
  expect(quote.mock.calls[0][0]).toContain('2024-01-03');
  expect(quote.mock.calls[0][1]).toEqual({run_id:'run-b',decision_id:'d1'});
});

test('cross-symbol inspector exposes actual cutoff inputs rubric and tool arguments/results',async()=>{
  const saved:any=result('cross-symbol');
  saved.inputs={'2024-01-03':{cutoff:'2024-01-03',state:{anchor:42},account:{cash:100,positions:{}},previous_orders:[],
    bars:{SPY:saved.decisions[0].evidence.SPY,QQQ:[{date:'2024-01-03',open:401,high:410,low:399,close:407,volume:999}]}}};
  saved.frozen.manifest={judgment:{criteria:'Require SPY and QQQ agreement',trigger:'entry',tools:['price_facts'],uncertainty:'stop'}};
  saved.decisions[0].model={verdict:'pass',reason:'QQQ confirms',evidence:[{symbol:'QQQ',date:'2024-01-03'}],request_ids:['request-cross'],
    tools:[{name:'price_facts',arguments:{symbol:'QQQ',start_date:'2024-01-03',end_date:'2024-01-03'},result:{last_close:407,average_volume:999}}]};
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY','QQQ']}:path.endsWith('/runs')?[saved]:saved;
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/cross-symbol/}));
  fireEvent.click(await screen.findByRole('button',{name:'buy 3 SPY · 2024-01-04'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect QQQ'}));
  expect(screen.getByRole('cell',{name:'407'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Approved judgment rubric'}));
  expect(screen.getByText(/Require SPY and QQQ agreement/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Model tool calls and results'}));
  expect(screen.getByText(/average_volume/)).toBeTruthy();
  expect(screen.getByText(/start_date/)).toBeTruthy();
});

test('compact market references show every input symbol but no future bars',async()=>{
  const saved:any=result('compact');
  saved.inputs={'2024-01-03':{cutoff:'2024-01-03',state:{},account:{cash:100},previous_orders:[],
    bars_ref:{schema:'cutoff-bars-v1',history_bars:2,symbols:['SPY','QQQ']}}};
  saved.market={SPY:saved.decisions[0].evidence.SPY,QQQ:[
    {date:'2024-01-02',open:400,high:410,low:390,close:406,volume:900},
    {date:'2024-01-03',open:401,high:410,low:399,close:407,volume:999},
    {date:'2024-01-04',open:900,high:910,low:890,close:909,volume:999}]};
  saved.frozen.manifest={history_bars:2};
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY','QQQ']}:path.endsWith('/runs')?[saved]:saved;
  render(<ProjectRuns project={project()} connections={[]} budget={2} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/compact/}));
  fireEvent.click(await screen.findByRole('button',{name:'buy 3 SPY · 2024-01-04'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect QQQ'}));
  expect(screen.getByRole('cell',{name:'407'})).toBeTruthy();
  expect(screen.queryByRole('cell',{name:'909'})).toBeNull();
});

test('model runs require saved roles and distinct authorization that resets on settings change',async()=>{
  const api=async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:[];
  const props={project:project(true),connections:[{id:'execution',configured:true}],budget:2,rolesPending:false,api,t,onQuote:()=>{},onChanged:async()=>{}};
  const {rerender}=render(<ProjectRuns {...props}/>);
  const checkbox=await screen.findByLabelText('Authorize execution model spending');
  fireEvent.change(screen.getByLabelText('Start session'),{target:{value:'2024-01-03'}});
  fireEvent.change(screen.getByLabelText('End session'),{target:{value:'2024-01-05'}});
  expect((screen.getByRole('button',{name:'Start historical run'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(checkbox);
  expect((screen.getByRole('button',{name:'Start historical run'}) as HTMLButtonElement).disabled).toBe(false);
  rerender(<ProjectRuns {...props} rolesPending={true}/>);
  expect((checkbox as HTMLInputElement).checked).toBe(false);
  expect((screen.getByRole('button',{name:'Start historical run'}) as HTMLButtonElement).disabled).toBe(true);
});

test('legacy builds remain selectable elsewhere but cannot start a historical run',async()=>{
  const p=project();delete (p.builds[0] as any).execution_hash;
  render(<ProjectRuns project={p} connections={[]} budget={2} rolesPending={false} api={async()=>[]} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
  expect(await screen.findByText(/Rebuild an approved method/)).toBeTruthy();
  expect((screen.getByRole('button',{name:'Start historical run'}) as HTMLButtonElement).disabled).toBe(true);
});
