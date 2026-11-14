import { useLanguage } from './i18n';
type Obj = Record<string, any>;
const dollars=(v:number|undefined)=>v==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(v);
const percent=(v:number)=>`${(v*100).toFixed(2)}%`;
function useLabels(){
 const {language,t}=useLanguage();
 return {l:(zh:string,en:string)=>language==='en'?en:zh,
 verdict:(v:string)=>t(({pass:'通过',fail:'未通过',insufficient_evidence:'证据不足'} as Obj)[v]||v)};
}

export function ExitReason({reason}:{reason:string}){
 const {l}=useLabels();
 const labels:Obj={stop_close:l('收盘止损','Stop breached at close'),target_close:l('收盘达到目标','Target reached at close'),
 stagnation:l('缺乏进展退出','No-progress exit'),trailing_stop:l('跟踪止损','Trailing stop'),holding_limit:l('旧版持有到期','Archived holding-age limit')};
 return <span>{labels[reason]||reason}</span>;
}

function Assessment({label,value}:{label:string;value:Obj|undefined}){
 const {l,verdict}=useLabels();
 return <section className="assessment-stage">
  <h4>{label} · {value?verdict(value.verdict):l('未执行','Not run')}</h4>
  {value&&<><p>{value.evidence}</p>{value.checks.map((c:Obj)=><div className="rubric-row" key={c.name}>
   <span className={c.verdict==='pass'?'up':'subtle'}>{verdict(c.verdict)}</span>
   <div><b>{({cup:l('杯体','Cup'),handle:l('柄部','Handle'),coherence:l('连贯性','Coherence')} as Obj)[c.name]}</b>
    <p>{c.reason}</p><small>{c.start_date} — {c.end_date}</small></div>
  </div>)}{!!value.missing_information?.length&&<p>{l('缺少信息：','Missing information: ')}{value.missing_information.join('; ')}</p>}</>}
 </section>;
}

export function CandidateInspection({runId,symbol,day,event}:{runId:string;symbol:string;day:string;event:Obj}){
 const {l,verdict}=useLabels();
 const skipped=event.execution_precheck?.eligible===false;
 return <div className="candidate-stack"><div className="notice" role="status"><div>
  <b>{event.order_id?l('订单已创建','Order created'):l('未创建订单','No order created')}</b>
  {event.order_id&&<small>{event.order_id}</small>}
  {skipped?<p>{l('未调用模型：资金、仓位或股数限制使本次无法下单。','Model not called: cash, position slots or sizing prevent this entry.')}</p>:event.validation?.execution_note&&<p>{event.validation.execution_note}</p>}
 </div></div>{(event.candidates||[]).map((c:Obj,index:number)=>{
  const find=(key:string)=>(event[key]||[]).find((a:Obj)=>a.candidate_id===c.candidate_id);
  const final=find('evaluations');
  return <details className="candidate-card" key={c.candidate_id} open={index===0}>
   <summary>#{c.rank} · {c.candidate_id} · {final?verdict(final.verdict):skipped?l('模型未调用','Model not called'):l('纯数值候选','Numeric candidate')}</summary>
   {event.validation?.pattern?.candidate_id===c.candidate_id&&<p className="up">{l('已选为订单依据','Selected as order basis')}</p>}
   <img className="candidate-chart" alt={`${c.candidate_id} ${l('固定杯体与柄部','fixed cup and handle')}`}
    src={`/api/runs/${runId}/chart/${symbol}/${day}?candidate_id=${encodeURIComponent(c.candidate_id)}`}/>
   <dl className="candidate-facts">
    <dt>{l('杯体','Cup')}</dt><dd>{c.left_rim} — {c.right_rim} ({c.cup_sessions})</dd>
    <dt>{l('杯底','Bottom')}</dt><dd>{c.bottom}</dd>
    <dt>{l('柄部','Handle')}</dt><dd>{c.handle_start} — {c.handle_end} ({c.handle_sessions})</dd>
    <dt>{l('冻结止损 / 目标','Frozen stop / target')}</dt><dd>{dollars(c.stop)} / {dollars(c.target)}</dd>
    <dt>{l('冻结波动单位 A','Frozen volatility unit A')}</dt><dd>{dollars(c.volatility_unit)}</dd>
   </dl>
   <Assessment label={l('主判断','Primary')} value={find('primary_evaluations')}/>
   <Assessment label={l('复核','Review')} value={find('review_evaluations')}/>
   <Assessment label={l('最终判断','Final')} value={final}/>
   <details><summary>{l('该候选的程序核验事实','Program-verified facts for this candidate')}</summary>
    <div className="table-wrap"><table><thead><tr><th>{l('检查项','Check')}</th><th>{l('实际值','Observed')}</th><th>{l('下限 / 上限','Lower / upper')}</th><th>{l('通过','Pass')}</th></tr></thead>
    <tbody>{c.numeric_checks.map((x:Obj)=>{
     const n=(v:any)=>v==null?'—':x.unit==='ratio'?percent(v):Number(v).toFixed(x.unit==='sessions'||x.unit==='boolean'?0:2);
     return <tr key={x.name}><td>{x.name}</td><td>{n(x.value)}</td><td>{x.strict_minimum?'>':'≥'} {n(x.minimum)} / ≤ {n(x.maximum)}</td><td>{x.passed?'✓':'✕'}</td></tr>;
    })}</tbody></table></div>
   </details>
  </details>;
 })}</div>;
}

export function PositionTable({positions,equity,strategy}:{positions:Obj;equity:number;strategy:Obj}){
 const {l}=useLabels();
 if(!Object.keys(positions).length)return <p className="empty">{l('当前没有未平仓持仓。','No open positions.')}</p>;
 return <div className="table-wrap"><table><thead><tr>
  {[l('标的 / 候选','Symbol / candidate'),l('数量 / 实际仓位','Quantity / actual weight'),l('成本 / 现价','Entry / close'),l('止损 / 目标','Stop / target'),l('波动单位 A','Volatility unit A'),l('进展锚点 / 下次门槛','Progress anchor / next level'),l('未进展天数','No-progress sessions')].map(x=><th key={x}>{x}</th>)}
 </tr></thead><tbody>{Object.entries(positions).map(([symbol,p])=><tr key={symbol}>
  <td><b>{symbol}</b><small>{p.candidate_id||l('旧版无编号','Archived: no ID')}</small></td>
  <td>{p.quantity}<small>{percent(p.quantity*p.last_close/equity)}</small></td>
  <td>{dollars(p.entry_price)}<small>{dollars(p.last_close)}</small></td>
  <td>{dollars(p.stop)}<small>{dollars(p.target)}</small></td><td>{dollars(p.volatility_unit)}</td>
  <td>{dollars(p.progress_anchor)}<small>{dollars(p.progress_anchor==null?undefined:p.progress_anchor+strategy.progress_units*p.volatility_unit)}</small></td>
  <td>{strategy.stagnation_sessions===0?l('已关闭','Disabled'):p.stagnant_sessions==null?'—':`${p.stagnant_sessions} / ${strategy.stagnation_sessions}`}</td>
 </tr>)}</tbody></table></div>;
}

export function ReferenceSources({pack}:{pack:Obj}){
 const {l}=useLabels();
 if(!pack?.cases)return null;
 return <details className="reference-pack"><summary>{l('判断参考：来源、正例与边界','Judgment references: sources, examples and boundaries')}</summary>
  <p className="help">{l('以下为教学摘要与本项目绘制的示意图，不是经标注的行情测试集。原资料保留英文。','Teaching summaries and project-made schematics, not a labeled market test set. Source material stays in English.')}</p>
  <p>{pack.limitations}</p>{pack.cases.map((c:Obj)=><article key={c.id}><h4><a href={c.source_url} target="_blank" rel="noreferrer">{c.id}</a> · {c.label}</h4><p>{c.lesson}</p><small>{c.provenance}</small></article>)}
 </details>;
}
