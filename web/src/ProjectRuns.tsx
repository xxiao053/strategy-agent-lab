import {useEffect,useRef,useState} from 'react';
import {Curve} from './App';
import {runMetrics} from './run-metrics';
import ProjectDecisionEvidence from './ProjectDecisionEvidence';
type Obj=Record<string,any>;
type Props={project:Obj;connections:Obj[];budget:number;rolesPending:boolean;api:(path:string,body?:Obj)=>Promise<any>;t:(zh:string,en:string)=>string;onQuote:(text:string,reference:{run_id:string;decision_id:string})=>void;onChanged:()=>Promise<void>;onConfigure?:()=>void};
const money=(n:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n||0);
const percent=(n:number)=>new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:2}).format(n);
function contract(build:Obj|undefined){try{return JSON.parse(build?.artifacts?.find((f:Obj)=>f.name==='execution.json')?.text||'null')}catch{return null}}

export default function ProjectRuns({project,connections,budget,rolesPending,api,t,onQuote,onChanged,onConfigure}:Props){
  const builds=(project.builds||[]).filter((b:Obj)=>b.status==='completed'&&b.execution_hash&&contract(b)?.schema==='strategy-v1');
  const [buildId,setBuildId]=useState(builds.at(-1)?.id||'');
  const [symbols,setSymbols]=useState('SPY'),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const [cash,setCash]=useState('10000'),[fee,setFee]=useState('0.1'),[authorized,setAuthorized]=useState(false);
  const [catalog,setCatalog]=useState<string[]>([]),[runs,setRuns]=useState<Obj[]>([]),[selected,setSelected]=useState<Obj|null>(null);
  const [decisionId,setDecisionId]=useState(''),[error,setError]=useState(''),[working,setWorking]=useState(false);
  const [preparation,setPreparation]=useState<Obj|null>(project.data_preparation||null);
  const generation=useRef(0),selection=useRef(0);
  const base=`/projects/${project.id}/runs`,build=builds.find((b:Obj)=>b.id===buildId),needsModel=!!contract(build)?.judgment;
  const execution=connections.find(c=>c.id===project.model_roles?.execution&&c.configured);
  const needsImages=contract(build)?.judgment?.input_mode==='chart_and_text';
  const imageReady=!needsImages||!!(execution?.image_inputs&&['openai','anthropic','gemini'].includes(execution.provider));
  const accountPolicy=contract(build)?.account;
  const status=(s:string)=>({running:t('运行中','Running'),completed:t('已完成','Completed'),failed:t('失败','Failed'),cancelled:t('已取消','Cancelled'),interrupted:t('已中断','Interrupted')}[s]||s);
  useEffect(()=>{
    const token=++generation.current;selection.current++;setSelected(null);setRuns([]);setDecisionId('');setError('');setAuthorized(false);
    Promise.all([api(base),api('/execution-catalog')]).then(([rows,available])=>{if(generation.current===token){setRuns(rows);setCatalog(available.symbols||[])}}).catch(e=>{if(generation.current===token)setError(e.message)});
    return()=>{generation.current++;selection.current++};
  },[project.id]);
  useEffect(()=>{setAuthorized(false)},[budget,rolesPending,project.model_roles?.execution,buildId,symbols,start,end,cash,fee]);
  useEffect(()=>{if(accountPolicy)setFee(String(accountPolicy.commission*100))},[buildId,accountPolicy?.commission]);
  useEffect(()=>{setPreparation(project.data_preparation||null)},[project.id,project.data_preparation]);
  useEffect(()=>{
    if(preparation?.status!=='running')return;
    let live=true;const timer=setInterval(async()=>{try{const state=await api(`/projects/${project.id}/prepare-data`);if(live){setPreparation(state);if(state?.status!=='running')await onChanged()}}catch(e:any){if(live)setError(e.message)}},1500);
    return()=>{live=false;clearInterval(timer)};
  },[preparation?.status,project.id]);
  async function prepareData(){
    setWorking(true);setError('');try{const result=await api(`/projects/${project.id}/prepare-data`,{build_id:buildId,symbols:symbols.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean),start,end});setPreparation(result);await onChanged()}catch(e:any){setError(e.message)}finally{setWorking(false)}
  }
  useEffect(()=>{
    if(selected?.status!=='running')return;
    let live=true;
    const timer=setInterval(async()=>{
      try{
        const summary=await api(`${base}/${selected.id}/status`);
        if(!live)return;
        setRuns(rows=>rows.map(r=>r.id===summary.id?summary:r));
        if(summary.status==='running')setSelected(r=>r?{...r,...summary}:r);
        else{const detail=await api(`${base}/${selected.id}`);if(live){setSelected(detail);await onChanged()}}
      }catch(e:any){if(live)setError(e.message)}
    },1500);
    return()=>{live=false;clearInterval(timer)};
  },[selected?.id,selected?.status,project.id]);
  async function inspect(r:Obj){const token=++selection.current;setError('');setDecisionId('');try{const detail=await api(`${base}/${r.id}`);if(token===selection.current)setSelected(detail)}catch(e:any){if(token===selection.current)setError(e.message)}}
  const disabled=working||project.busy||rolesPending||!build||!start||!end||!imageReady||(needsModel&&(!execution||!authorized));
  async function launch(){
    if(disabled)return;setWorking(true);setError('');
    try{
      const summary=await api(base,{build_id:buildId,symbols:symbols.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean),start,end,
        initial_cash:Number(cash),fee_rate:Number(fee)/100,budget,authorized:needsModel&&authorized,connection_id:needsModel?execution?.id:null});
      setRuns(rows=>[summary,...rows]);setSelected(summary);setDecisionId('');setAuthorized(false);await onChanged();
    }catch(e:any){setError(e.message)}finally{setWorking(false)}
  }
  const decision=selected?.decisions?.find((d:Obj)=>d.id===decisionId);
  const fills=selected?.trades?.filter((o:Obj)=>o.decision_id===decisionId)||[];
  const metrics=selected&&runMetrics({assumptions:selected.frozen?.assumptions,curve:selected.curve});
  return <section className="bw-runs" aria-label={t('运行与结果','Runs & results')}>
    <div className="bw-paper"><h2>{t('历史运行','Historical run')}</h2><p>{t('运行已确认方法的生成代码。行情来自本地冻结的美股与 ETF 数据；不会自动下载。','Execute generated code for an approved method against locally frozen US stock/ETF data. No automatic downloads.')}</p>
      {!builds.length&&<p className="bw-caption">{project.builds?.length?t('请重新构建已确认方法，生成 strategy-v1 执行清单。旧构建和结果仍可查看。','Rebuild an approved method to generate a strategy-v1 execution manifest. Older builds and results remain available.'):t('请先确认方法，再构建并验证，之后即可开始历史运行。','Approve your method, then build and validate it before starting a historical run.')}</p>}
      <div className="bw-run-form">
        <label>{t('构建版本','Build version')}<select aria-label={t('构建版本','Build version')} value={buildId} disabled={working||project.busy} onChange={e=>setBuildId(e.target.value)}><option value="">{t('选择已完成构建','Choose completed build')}</option>{builds.map((b:Obj)=><option key={b.id} value={b.id}>v{b.version} · {b.id.slice(0,8)}</option>)}</select></label>
        <label>{t('标的（逗号分隔）','Symbols (comma-separated)')}<input aria-label={t('运行标的','Run symbols')} value={symbols} onChange={e=>setSymbols(e.target.value)}/></label>
        <label>{t('起始交易日','Start session')}<input aria-label={t('起始交易日','Start session')} type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
        <label>{t('结束交易日','End session')}<input aria-label={t('结束交易日','End session')} type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label>
        <label>{t('初始现金 $','Initial cash $')}<input aria-label={t('初始现金','Initial cash')} type="number" min="0.01" value={cash} onChange={e=>setCash(e.target.value)}/></label>
        <label>{t('单边手续费 %','Fee per side %')}<input aria-label={t('单边手续费','Fee per side')} type="number" min="0" max="5" step="0.01" value={fee} disabled={!!accountPolicy} onChange={e=>setFee(e.target.value)}/></label>
      </div>
      <details><summary>{t('支持的标的与执行边界','Supported symbols and execution limits')}</summary><p>{catalog.join(', ')}</p><p>{t('最多 100 标的、756 个交易日。整数股、只做多、下一交易日开盘成交；不足资金的订单取消，期末不强制平仓。','Up to 100 symbols and 756 sessions. Integer shares, long only, next-session-open fills. Unaffordable orders cancel; no forced final liquidation.')}</p></details>
      {needsModel?<><p>{t('此方法需要执行模型；与对话、构建共用项目预算。','This method requires an execution model and shares the project budget with conversation and construction.')} ${budget.toFixed(2)}</p>
        {needsImages&&<div><p>{t('此已确认实现要求图表及文字判断。只发送建议标的的截止行情图，不使用上传示例。','This approved implementation requests chart-and-text judgments. Only the proposal symbol’s cutoff chart is sent, never uploaded examples.')}</p>{!imageReady&&<><p role="status">{t('请启用所选执行连接的图片输入；构建连接的能力不能代替。','Enable image inputs on the selected execution connection; builder capability is not a substitute.')}</p>{onConfigure&&<button onClick={onConfigure}>{t('配置执行模型图片输入','Configure execution image inputs')}</button>}</>}</div>}
        {!execution&&<p className="bw-record-error">{t('请先保存一个可用的执行模型。不会使用构建模型代替。','Save a configured execution model first. The builder model is not a fallback.')}</p>}
        <label className="bw-run-authorization"><input type="checkbox" aria-label={t('授权执行模型费用','Authorize execution model spending')} checked={authorized} disabled={rolesPending||!execution||working||project.busy} onChange={e=>setAuthorized(e.target.checked)}/>{t('允许将本次行情证据和方法判断标准发给已保存的执行模型，并在项目预算内调用。','Send this run’s market evidence and method criteria to the saved execution model within the project budget.')}</label></>:<p className="bw-caption">{t('纯代码运行：不调用模型，不需要模型连接。','Code-only execution: no model requests or model connection required.')}</p>}
      {rolesPending&&<p>{t('请先保存模型分工的修改。','Save pending model-role changes first.')}</p>}
      <button className="bw-primary" disabled={disabled} onClick={launch}>{t('开始历史运行','Start historical run')}</button>
      <button className="bw-secondary" disabled={working||project.busy||!build||!start||!end||preparation?.status==='running'} onClick={prepareData}>{t('准备数据','Prepare data')}</button>
      <p className="bw-caption">{t('准备数据会从固定行情供应商下载所选标的、日期及构建要求的预热数据；保留已有校验快照，不调用模型。','Prepare data explicitly downloads selected symbols, dates and build-required warmup from the fixed market provider. Existing checksummed snapshots are preserved; no model calls.')}</p>
      {preparation&&<div role="status"><p>{t('数据准备','Data preparation')}: {status(preparation.status)} · {preparation.completed}/{preparation.total}</p>{preparation.error&&<p>{preparation.error}</p>}{Object.entries(preparation.results||{}).map(([symbol,result]:[string,any])=><p key={symbol}>{symbol} · {status(result.status)}{result.error?` · ${result.error}`:''}</p>)}</div>}
      {error&&<p role="alert" className="bw-record-error">{error}</p>}
    </div>
    <div className="bw-paper"><h2>{t('已保存运行','Saved runs')}</h2>{!runs.length?<p>{t('还没有历史运行。','No historical runs yet.')}</p>:<div className="bw-run-list">{runs.map(r=><button key={r.id} className={selected?.id===r.id?'active':''} onClick={()=>inspect(r)}>v{r.version} · {r.id.slice(0,12)} · {status(r.status)}</button>)}</div>}</div>
    {selected&&<div className="bw-paper"><h2>{t('运行结果','Run results')} · {selected.id.slice(0,12)}</h2><p role="status">{status(selected.status)} · {selected.completed_sessions||0}/{selected.total_sessions||0} {t('交易日','sessions')}</p>
      {selected.error&&<p role="alert" className="bw-record-error">{selected.error}</p>}
      {selected.status==='running'&&<><progress value={selected.completed_sessions||0} max={selected.total_sessions||1}/><button disabled={selected.cancel_requested} onClick={async()=>{try{const r=await api(`${base}/${selected.id}/cancel`,{});setSelected(s=>s?{...s,...r}:s)}catch(e:any){setError(e.message)}}}>{selected.cancel_requested?t('正在停止…','Stopping…'):t('取消运行','Cancel run')}</button><p className="bw-caption">{t('取消不会抹除已完成证据或费用；正在进行的请求可能完成。','Cancellation preserves completed evidence and spend; an in-flight request may finish.')}</p></>}
      {selected.frozen&&<><p>{selected.frozen.assumptions.symbols.join(', ')} · {selected.frozen.assumptions.start} — {selected.frozen.assumptions.end}</p><p>{t('初始现金','Initial cash')} {money(selected.frozen.assumptions.initial_cash)} · {t('单边费用','Fee per side')} {(selected.frozen.assumptions.fee_rate*100).toFixed(3)}%</p><details><summary>{t('冻结来源与假设','Frozen sources and assumptions')}</summary><p>{selected.frozen.price_basis}</p>{['build_hash','market_hash','run_hash'].map(k=><p className="bw-run-hash" key={k}>{k}: {selected.frozen[k]}</p>)}<p>{selected.frozen.model?`${selected.frozen.model.provider} · ${selected.frozen.model.model}`:t('无执行模型','No execution model')}</p></details></>}
      {!!selected.curve?.length&&<><div className="bw-run-metrics" role="group" aria-label={t('运行表现','Run performance')}>
        <div className="bw-run-equity"><span>{t('最新权益','Latest equity')}</span><strong>{money(selected.curve.at(-1).equity)}</strong></div>
        {metrics&&<><div className="bw-run-equity"><span>{t('累计收益率','Total return')}</span><strong>{percent(metrics.totalReturn)}</strong></div>
          <div className="bw-run-equity"><span>{t('最大回撤（日收盘）','Maximum drawdown (daily close)')}</span><strong>{percent(metrics.maxDrawdown)}</strong></div></>}
      </div><Curve curve={selected.curve}/></>}
      {selected.positions&&<><h3>{t('期末未平仓','Open positions')}</h3>{Object.entries(selected.positions).length?Object.entries(selected.positions).map(([s,q])=><p key={s}>{s} · {String(q)} {t('股','shares')}</p>):<p>{t('无持仓','No positions')}</p>}</>}
      {selected.trades&&<><h3>{t('实际模拟成交','Simulated fills')}</h3>{selected.trades.length?selected.trades.map((o:Obj)=><button className="bw-run-link" key={o.id} onClick={()=>setDecisionId(o.decision_id)}>{o.action} {o.quantity} {o.symbol} · {o.date}</button>):<p>{t('没有成交','No fills')}</p>}</>}
      {selected.orders?.some((o:Obj)=>o.status!=='filled')&&<details><summary>{t('未成交与取消订单','Unfilled and cancelled orders')}</summary>{selected.orders.filter((o:Obj)=>o.status!=='filled').map((o:Obj)=><button className="bw-run-link" key={o.id} onClick={()=>setDecisionId(o.decision_id)}>{o.symbol} · {o.status} · {o.reason}</button>)}</details>}
      {selected.decisions&&<><h3>{t('决策证据','Decision evidence')}</h3><select aria-label={t('选择决策','Select decision')} value={decisionId} onChange={e=>setDecisionId(e.target.value)}><option value="">{t('选择决策查看依据','Choose a decision to inspect')}</option>{selected.decisions.map((d:Obj)=><option key={d.id} value={d.id}>{d.cutoff} · {d.proposal.symbol} · {d.status} · {d.id}</option>)}</select></>}
      {decision&&<section className="bw-run-evidence"><h3>{decision.proposal.symbol} · {decision.cutoff}</h3><p>{decision.rule}</p><p>{t('决策状态','Decision status')}: {decision.status}</p><p className="bw-run-hash">{decision.input_hash}</p><p>{t('决策时现金','Cash at decision')}: {money(decision.account.cash)}</p>
        {decision.error&&<p className="bw-record-error">{decision.error}</p>}
        {fills.map((o:Obj)=><p key={o.id}>{o.date} · {o.quantity} × {money(o.price)} · {t('费用','Fee')} {money(o.fee)} · {o.reason}</p>)}
        {decision.model&&<><h4>{t('模型判断','Model judgment')}</h4><p>{decision.model.verdict} · {decision.model.reason}</p>{decision.model.evidence?.map((e:Obj,i:number)=><p key={i}>{e.symbol} · {e.date}</p>)}<p>{t('模型请求编号','Model request IDs')}: {decision.model.request_ids?.join(', ')}</p></>}
        <ProjectDecisionEvidence key={selected.id+decision.id} pid={project.id} run={selected} decision={decision} t={t}/>
        <button className="bw-primary" onClick={()=>onQuote(`${t('请检查并修正此决策','Please review and correct this decision')}: run=${selected.id}, build=${selected.build_id}, decision=${decision.id}, cutoff=${decision.cutoff}, symbol=${decision.proposal.symbol}. ${decision.rule}`,{run_id:selected.id,decision_id:decision.id})}>{t('引用到项目对话','Quote decision in conversation')}</button>
      </section>}
      <p className="bw-caption">{t('历史模拟不代表未来收益。已保存结果不会自动再次调用模型。','Historical simulation does not predict future returns. Viewing saved results never calls a model.')}</p>
    </div>}
  </section>;
}
