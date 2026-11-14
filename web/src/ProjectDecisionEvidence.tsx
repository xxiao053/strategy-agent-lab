import {useState} from 'react';
type Obj=Record<string,any>;
type Translate=(zh:string,en:string)=>string;

function ExpandableJSON({label,value,t}:{label:string;value:any;t:Translate}){
  const [open,setOpen]=useState(false),[page,setPage]=useState(0);
  const text=JSON.stringify(value??null,null,2),pages=Math.max(1,Math.ceil(text.length/12000));
  return <div className="bw-evidence-section"><button aria-expanded={open} onClick={()=>setOpen(!open)}>{label}</button>{open&&<>
    <pre>{text.slice(page*12000,(page+1)*12000)}</pre>
    {pages>1&&<div><button disabled={page===0} onClick={()=>setPage(page-1)}>{t('上一段','Previous section')}</button><span> {page+1}/{pages} </span><button disabled={page+1>=pages} onClick={()=>setPage(page+1)}>{t('下一段','Next section')}</button></div>}
  </>}</div>;
}

export default function ProjectDecisionEvidence({pid,run,decision,t}:{pid?:string;run:Obj;decision:Obj;t:Translate}){
  const input=run.inputs?.[decision.cutoff],ref=input?.bars_ref;
  const referenced=ref?.schema==='cutoff-bars-v1'&&ref.history_bars===run.frozen?.manifest?.history_bars
    ?Object.fromEntries(ref.symbols.map((symbol:string)=>[symbol,(run.market?.[symbol]||[]).filter((b:Obj)=>b.date<=decision.cutoff).slice(-ref.history_bars)])):null;
  const bars=input?.bars||referenced||decision.evidence||{},symbols=Object.keys(bars);
  const [selected,setSelected]=useState(symbols.includes(decision.proposal.symbol)?decision.proposal.symbol:symbols[0]),[page,setPage]=useState(0);
  const rows:Obj[]=bars[selected]||[],pages=Math.max(1,Math.ceil(rows.length/40));
  return <div>
    {!!decision.images?.length&&<section><h4>{t('保存的判断图表','Saved judgment charts')}</h4>{decision.images.map((image:Obj)=><figure key={image.sha256} className="bw-image-evidence">
      {pid&&<img src={`/api/workspace/projects/${pid}/runs/${run.id}/images/${image.sha256}`} alt={t('保存的判断图表：','Saved judgment chart: ')+image.source.symbol+t('，截至 ', ', as of ')+image.source.cutoff}/>}
      <figcaption>{image.source.symbol} · {image.source.start} — {image.source.end} · {image.source.bar_count} {t('根行情','bars')}<br/>SHA-256: {image.sha256}</figcaption>
      <ExpandableJSON label={t('图表来源与渲染范围','Chart source and rendering bounds')} value={image.source} t={t}/>
    </figure>)}<p className="bw-caption">{t('引用到对话只包含图表身份与来源，图片像素不会随此引用发送。浏览不会调用模型。','Quoting includes chart identity and provenance; pixels are not sent with this handoff. Browsing makes no model request.')}</p></section>}
    {!input&&<p className="bw-caption">{t('旧运行没有完整截止输入；仅显示当时保存的决策证据。','This older run has no complete cutoff input; only its saved decision evidence is available.')}</p>}
    <ExpandableJSON label={t('账户、策略状态与已知成交','Account, strategy state and known fills')} value={{account:input?.account||decision.account,state:input?.state??null,previous_orders:input?.previous_orders||decision.previous_orders||[]}} t={t}/>
    {run.frozen?.manifest?.judgment&&<ExpandableJSON label={t('已确认判断标准','Approved judgment rubric')} value={run.frozen.manifest.judgment} t={t}/>}
    {decision.model&&<ExpandableJSON label={t('模型工具调用与结果','Model tool calls and results')} value={decision.model.tools||[]} t={t}/>}
    {decision.model?.assessments&&<ExpandableJSON label={t('候选判断与条件复核','Candidate assessments and conditional review')} value={{primary:decision.model.primary,review:decision.model.review,final:decision.model.assessments,selected_candidate_id:decision.model.selected_candidate_id}} t={t}/>}
    <h4>{t('全部可见行情输入','All visible market inputs')}</h4>
    <div className="bw-evidence-symbols">{symbols.map(symbol=><button key={symbol} aria-pressed={selected===symbol} onClick={()=>{setSelected(symbol);setPage(0)}}>{t('检查 ','Inspect ')+symbol}</button>)}</div>
    {selected&&<><p>{selected} · {rows.length} {t('根已保存行情','saved bars')}</p><div className="bw-table"><table><thead><tr>{['Date','Open','High','Low','Close','Volume'].map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.slice(page*40,(page+1)*40).map(b=><tr key={b.date}>{['date','open','high','low','close','volume'].map(k=><td key={k}>{b[k]}</td>)}</tr>)}</tbody></table></div>
      {pages>1&&<div><button disabled={page===0} onClick={()=>setPage(page-1)}>{t('上一页行情','Previous bars')}</button><span> {page+1}/{pages} </span><button disabled={page+1>=pages} onClick={()=>setPage(page+1)}>{t('下一页行情','Next bars')}</button></div>}
    </>}
  </div>;
}
