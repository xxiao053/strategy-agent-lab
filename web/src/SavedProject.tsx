import {useEffect,useState} from 'react';
import {useLanguage} from './i18n';
import {Curve} from './App';
import {runMetrics} from './run-metrics';
import './workspace.css';
import './saved-project.css';

type Obj=Record<string,any>;
type Props={example:Obj;initialTab?:string;onTab?:(tab:string)=>void;imageURL?:(hash:string)=>string|undefined;onCopy?:(version:number)=>void;copying?:boolean};
const money=(value:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value);
const percent=(value:number)=>new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:2}).format(value);

export default function SavedProject({example,initialTab='method',onTab,imageURL,onCopy,copying=false}:Props){
  const {language}=useLanguage(),t=(zh:string,en:string)=>language==='en'?en:zh;
  const [tab,setTab]=useState(initialTab),[version,setVersion]=useState(example.versions.at(-1)?.number),
    [fileName,setFileName]=useState('strategy.py'),[runId,setRunId]=useState(example.runs.filter((r:Obj)=>r.version===example.versions.at(-1)?.number).at(-1)?.id||''),[decisionId,setDecisionId]=useState('');
  useEffect(()=>{setTab(initialTab)},[initialTab]);
  const method=example.versions.find((v:Obj)=>v.number===version),build=example.builds.filter((b:Obj)=>b.version===version).at(-1);
  const file=build?.files.find((f:Obj)=>f.name===fileName)||build?.files[0];
  const run=example.runs.find((r:Obj)=>r.id===runId),decision=run?.decisions.find((d:Obj)=>d.id===decisionId);
  const selectedCandidate=decision?.candidates?.find((c:Obj)=>c.candidate_id===decision.selected_candidate_id);
  const metrics=run&&runMetrics(run),independent=example.independent_checks;
  const reviewed=independent&&build?.original_build_hash===independent.build_hash&&example.runs.some((r:Obj)=>r.build_id===build.id&&r.original_run_hash===independent.run_hash);
  const checkLabels:Record<string,string>={'Original method configuration':'原始方法配置','Numeric candidates and boundary cases':'数值候选与边界案例','No future input data':'输入不包含未来数据','Next-session fills, fees, cash and holdings':'下一交易日成交、费用、现金与持仓','Daily equity reconstruction':'逐日账户权益复算','Primary and conditional review coverage':'初次判断与条件复核覆盖','Chart and receipt provenance':'图表与请求凭据来源','Original example preserved':'原有示范保持不变'};
  const tabs=[['method',t('方法','Method')],['materials',t('资料','Materials')],
    ['implementation',t('实现与验证','Implementation & validation')],['results',t('运行与结果','Runs & results')],['versions',t('版本','Versions')]];
  const verdict=(value:string)=>({pass:t('通过','Pass'),fail:t('未通过','Fail'),insufficient_evidence:t('证据不足','Insufficient evidence')}[value]||value);
  function choose(next:string){setTab(next);onTab?.(next)}
  function chooseVersion(next:number){setVersion(next);setRunId(example.runs.filter((r:Obj)=>r.version===next).at(-1)?.id||'');setDecisionId('')}
  function stage(value:Obj|undefined,label:string){return value&&<section className="saved-stage" aria-label={label}><h4>{label}</h4>{value.assessments?.map((a:Obj)=><div key={a.candidate_id}>
    <p className="saved-candidate">{a.candidate_id} · {verdict(a.verdict)}</p>{Object.entries(a.checks).map(([name,check]:[string,any])=><div className="saved-check" key={name}>
      <strong>{name} · {verdict(check.verdict)}</strong><p>{check.reason}</p><small>{check.evidence.map((e:Obj)=>`${e.symbol} · ${e.date}`).join(' / ')}</small>
    </div>)}</div>)}</section>}
  return <div className="bw-project-work">
    <section className="bw-conversation"><div className="bw-conversation-head"><h1>{t('对话','Conversation')}</h1>{onCopy&&<button className="bw-secondary" disabled={copying} onClick={()=>onCopy(version)}>{t('创建可编辑副本','Create editable copy')}</button>}</div>
      <div className="bw-chat">{example.messages.map((m:Obj)=><article key={m.id} className={'bw-message '+m.role}>
        <div className="bw-author">{m.role==='user'?t('你','You'):<><i>s</i>{t('构建助手','Builder')}</>}</div><div className="bw-bubble">{m.text}</div>
      </article>)}</div>
      <details className="bw-record-details"><summary>{t('记录详情','Record details')}</summary>
        <p>{t('此项目包含已完成的对话、实现与运行记录，当前以只读方式打开。','This project contains completed conversation, implementation and run records, opened read-only.')}</p>
        {example.presentation?.translated_message_ids?.length>0&&<p>{t('对话以英文呈现；部分消息译自中文。实现与运行数据未经改动。','Conversation presented in English; some messages are translated from Chinese. Implementation and run data are unchanged.')}</p>}
      </details>
    </section>
    <aside className="bw-inspector"><div className="bw-inspector-head"><h2>{t('项目成果','Project artifacts')}</h2>
      <label>{t('方法版本','Method version')} <select aria-label={t('方法版本','Method version')} value={version} onChange={e=>chooseVersion(Number(e.target.value))}>{example.versions.map((v:Obj)=><option key={v.number} value={v.number}>v{v.number}</option>)}</select></label>
    </div>
    <div className="bw-tabs" role="tablist" aria-label={t('项目内容','Project contents')}>{tabs.map(([id,label])=><button role="tab" aria-selected={tab===id} className={tab===id?'active':''} key={id} onClick={()=>choose(id)}>{label}</button>)}</div>
    <div className="bw-panel saved-project"><div className="saved-body" role="tabpanel">
      {tab==='method'&&method&&<section><h2>{t('已确认的方法','Approved method')} · v{version}</h2><p>{method.scope}</p>{method.rules.map((rule:Obj,i:number)=><article className="saved-rule" key={i}>
        <span>{String(i+1).padStart(2,'0')}</span><div><h3>{rule.topic}</h3><p>{rule.rule}</p><details><summary>{t('来源','Source')}</summary><p>{rule.source}</p>{rule.material_refs?.map((ref:Obj,j:number)=><p key={j}>{example.materials.find((m:Obj)=>m.id===ref.id)?.name||ref.id} · {ref.start}–{ref.end}</p>)}</details></div></article>)}</section>}
      {tab==='materials'&&<section><h2>{t('方法资料','Method materials')}</h2>{example.materials.map((m:Obj)=><article className="saved-material" key={m.id}><h3>{m.name}</h3>
        <details><summary>{t('资料完整性','Source integrity')}</summary><code>{m.sha256}</code></details>{m.units.map((u:Obj)=><div className="saved-source-line" key={u.location}><span>{u.location}</span><pre>{u.text}</pre></div>)}</article>)}</section>}
      {tab==='implementation'&&<section><h2>{t('生成实现','Generated implementation')} · v{version}</h2>{build?<>
        <div className="saved-validation"><strong>{build.validation.tests_passed?t('生成项目自测：报告通过','Generated self-tests: reported pass'):t('检查自测报告','Inspect self-test report')}</strong><p>{t('自测输出来自生成的项目，不是独立的策略正确性证明。','Self-test output comes from the generated project; it is not independent proof of strategy correctness.')}</p><pre>{build.validation.test_output}</pre>
          <details><summary>{t('合成软件案例（非历史收益）','Synthetic software example (not historical performance)')}</summary><pre>{build.validation.demo_output}</pre></details></div>
        {reviewed&&<section className="saved-validation"><h3>{t('独立核验','Independent checks')}</h3>
          <p>{independent.implementation_cases} {t('个实现核验案例','implementation cases')} · {independent.sessions} {t('个交易日','sessions')} · {independent.fills} {t('笔成交','fills')} · {independent.images} {t('张证据图','evidence charts')}</p>
          <ul>{independent.checks.map((name:string)=><li key={name}>{t(checkLabels[name]||name,name)}</li>)}</ul>
          <p>{t('核验针对这份保存的实现与运行，不保证所有输入下的策略正确性或未来表现。','Checks cover this saved implementation and run, not strategy correctness for every input or future performance.')}</p>
          <details><summary>{t('对应实现与运行的完整性标识','Implementation and run identities')}</summary><p>SHA-256 · {t('实现','Build')}</p><code>{independent.build_hash}</code><p>SHA-256 · {t('运行','Run')}</p><code>{independent.run_hash}</code></details>
        </section>}
        <div className="saved-code"><nav aria-label={t('生成文件','Generated files')}>{build.files.map((f:Obj)=><button key={f.name} aria-pressed={file?.name===f.name} onClick={()=>setFileName(f.name)}>{f.name}</button>)}</nav>
          <div><h3>{file?.name}</h3><pre>{file?.text}</pre><details><summary>SHA-256</summary><code>{file?.sha256}</code></details></div></div>
      </>:<p>{t('此版本没有已保存实现。','No saved implementation for this version.')}</p>}</section>}
      {tab==='results'&&<section><h2>{t('历史运行与依据','Historical execution & evidence')}</h2>{!example.runs.length?<p>{t('尚无已保存历史运行。','No saved historical runs.')}</p>:<>
        <label>{t('选择运行','Select run')} <select aria-label={t('选择运行','Select run')} value={runId} onChange={e=>{setRunId(e.target.value);setVersion(example.runs.find((r:Obj)=>r.id===e.target.value)?.version);setDecisionId('')}}>{!run&&<option value="">{t('此版本暂无运行','No run for this version')}</option>}{example.runs.map((r:Obj)=><option key={r.id} value={r.id}>v{r.version} · {r.assumptions.start} — {r.assumptions.end}</option>)}</select></label>
        {!run&&<p>{t('此方法版本没有已保存历史运行。','No saved historical run for this method version.')}</p>}
        {run&&<><div className="saved-run-heading"><span className={run.status==='completed'?'saved-complete':'saved-incomplete'}>{run.status==='completed'?t('已完成','Completed'):t('未完成','Not completed')}</span><span>{run.completed_sessions} / {run.total_sessions} {t('个交易日','sessions')}</span><span>{run.assumptions.symbols.length} {t('个标的','instruments')}</span><span>{t('方法','Method')} v{run.version}</span></div>
          <details><summary>{t('标的与执行规则','Instruments and execution rules')}</summary><p>{run.assumptions.symbols.join(', ')}</p><p>{t('初始资金','Initial cash')}: {money(run.assumptions.initial_cash)}</p><p>{run.price_basis}</p><pre>{JSON.stringify(run.account_policy,null,2)}</pre></details>
          {!!run.curve.length&&<><div className="saved-metrics"><div className="saved-equity"><span>{t('模拟账户权益','Simulated account equity')}</span><strong>{money(run.curve.at(-1).equity)}</strong></div>{metrics&&<><div className="saved-equity"><span>{t('累计收益率','Total return')}</span><strong>{percent(metrics.totalReturn)}</strong></div><div className="saved-equity"><span>{t('最大回撤（日收盘）','Maximum drawdown (daily close)')}</span><strong>{percent(metrics.maxDrawdown)}</strong></div></>}</div><Curve curve={run.curve}/></>}
          <h3>{t('模拟成交','Simulated fills')}</h3><div className="saved-fills">{run.trades.map((trade:Obj,i:number)=><button key={i} onClick={()=>setDecisionId(trade.decision_id)}>{trade.symbol} · {trade.date} · {trade.action==='buy'?t('买入','Buy'):t('卖出','Sell')} {trade.quantity} × {money(trade.price)}</button>)}</div>
          {!run.trades.length&&<p>{t('没有成交','No fills')}</p>}<h3>{t('期末持仓','Open positions')}</h3><p>{run.positions.length?run.positions.map((p:Obj)=>`${p.symbol} · ${p.quantity}`).join(' / '):t('无持仓','No positions')}</p>
          <label>{t('检查决策','Inspect decision')} <select aria-label={t('检查决策','Inspect decision')} value={decisionId} onChange={e=>setDecisionId(e.target.value)}><option value="">{t('选择一笔交易或决策','Select a fill or decision')}</option>{run.decisions.map((d:Obj)=><option key={d.id} value={d.id}>{d.cutoff} · {d.symbol} · {verdict(d.model?.verdict||d.status)}</option>)}</select></label>
          {decision&&<section className="saved-evidence"><h3>{decision.symbol} · {decision.cutoff}</h3><p>{decision.explanation}</p><p>{run.judgment?.criteria}</p>
            {selectedCandidate&&<section className="saved-selection" aria-label={t('选中候选','Selected candidate')}><h4>{t('选中候选','Selected candidate')}</h4><code>{selectedCandidate.candidate_id}</code>
              <p>{t('止损价','Stop')}: <strong>{money(selectedCandidate.stop)}</strong> · {t('目标价','Target')}: <strong>{money(selectedCandidate.target)}</strong></p>
              {selectedCandidate.dates&&<p>{Object.entries(selectedCandidate.dates).map(([name,date])=>`${name}: ${date}`).join(' · ')}</p>}</section>}
            {decision.model&&<><p>{verdict(decision.model.verdict)} · {decision.model.reason}</p>{decision.model.assessments&&stage(decision.model,t('最终判断','Final assessments'))}{stage(decision.model.primary,t('初次判断','Primary assessment'))}{stage(decision.model.review,t('条件复核','Conditional review'))}</>}
            {decision.images.map((im:Obj)=>{const url=imageURL?.(im.sha256);return url?<figure key={im.sha256}><img src={url} alt={`${im.symbol} · ${im.start} — ${im.end}`}/><figcaption>{im.symbol} · {im.start} — {im.end}</figcaption></figure>:null})}
            {!!decision.candidates?.length&&<details><summary>{t('固定候选与数值依据','Fixed candidates and numeric facts')}</summary><pre>{JSON.stringify(decision.candidates,null,2)}</pre></details>}
          </section>}<p className="bw-caption">{t('历史模拟不代表未来收益。模型判断具有不确定性。','Historical simulation does not predict future returns. Model judgments are uncertain.')}</p></>}
      </>}</section>}
      {tab==='versions'&&<section><h2>{t('保留每次确认','Every approval, preserved')}</h2>{example.versions.map((v:Obj)=><article className="saved-version" key={v.number}><h3>v{v.number}</h3><p>{v.scope}</p>
        <p>{v.rules.length} {t('条规则','rules')} · {example.builds.filter((b:Obj)=>b.version===v.number).length} {t('份实现','implementations')} · {example.runs.filter((r:Obj)=>r.version===v.number).length} {t('次保存运行','saved runs')}</p>
        <button onClick={()=>{chooseVersion(v.number);choose('method')}}>{t('查看已确认规则','Inspect approved rules')} →</button></article>)}</section>}
    </div></div>
    </aside>
  </div>;
}
