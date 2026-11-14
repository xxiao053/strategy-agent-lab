import {useState} from 'react';
import {useLanguage} from './i18n';
import {Curve} from './App';
import './workspace.css';
type Obj=Record<string,any>;
const money=(n:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n||0);
const percent=(n:number)=>`${n>=0?'+':''}${(n*100).toFixed(2)}%`;
export default function CupReference({example}:{example:Obj}){
  const {language}=useLanguage(),t=(zh:string,en:string)=>language==='en'?en:zh;
  const [tab,setTab]=useState('overview'),{result,config}=example;
  return <section className="bw-demo-view"><div className="bw-eyebrow">SAVED EXECUTION REFERENCE</div><h1>{t('杯柄突破 · 原始运行示范','Cup & handle · original execution example')}</h1>
    <p className="bw-lead">{result.symbols.length} {t('支美股与 ETF','US stocks & ETFs')} · {result.start} — {result.end}</p>
    <p className="bw-caption">{t('这是保留的原始执行示范，不是本次构建助手新生成的结果。经过选择和调参的历史示范不代表未来收益；浏览不调用模型。','This is the preserved original execution example, not a newly generated Builder result. It is a selected, tuned historical demonstration, not a promise of future returns. Browsing makes no model calls.')}</p>
    <div className="bw-metrics">{[[t('期末权益','Ending equity'),money(result.summary.equity)],[t('累计收益','Total return'),percent(result.summary.total_return)],[t('最大回撤','Max drawdown'),percent(result.summary.max_drawdown)],[t('已平仓交易','Closed trades'),result.summary.trades]].map(([k,v])=><div key={k}><span>{k}</span><strong>{v}</strong></div>)}</div>
    <div className="bw-tabs" role="tablist">{[['overview',t('账户表现','Performance')],['trades',t('交易记录','Trades')],['decisions',t('判断案例','Decisions')],['method',t('方法配置','Method')]].map(([id,label])=><button role="tab" aria-selected={tab===id} key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}</button>)}</div>
    {tab==='overview'&&<div className="bw-paper bw-chart"><Curve curve={result.curve}/><p>{t('买入成交','Buy fills')} {result.summary.buy_fills} · {t('已平仓','Closed')} {result.summary.trades}</p></div>}
    {tab==='trades'&&<div className="bw-paper bw-table"><table><thead><tr>{[t('标的','Symbol'),t('买入日期','Entry'),t('卖出日期','Exit'),t('股数','Shares'),t('盈亏','P&L')].map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{result.trades.map((r:Obj,i:number)=><tr key={i}><td>{r.symbol}</td><td>{r.entry_date}</td><td>{r.exit_date}</td><td>{r.quantity}</td><td>{money(r.pnl)}</td></tr>)}</tbody></table></div>}
    {tab==='decisions'&&<div className="bw-decision-grid">{result.examples.map((x:Obj,i:number)=><article className="bw-paper" key={i}><div className="bw-eyebrow">{x.date}</div><h2>{x.symbol}</h2><p>{x.kind}</p>{(x.assessments||[]).map((e:Obj,j:number)=><details key={j}><summary>{e.verdict} · {e.candidate_id}</summary><p>{e.evidence}</p>{(e.checks||[]).map((c:Obj,k:number)=><p key={k}><strong>{c.name} · {c.verdict}</strong><br/>{c.reason}</p>)}</details>)}</article>)}</div>}
    {tab==='method'&&<div className="bw-paper"><h2>{t('保存的方法配置','Saved method configuration')}</h2><pre>{JSON.stringify(config,null,2)}</pre></div>}
  </section>;
}
