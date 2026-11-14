type Obj=Record<string,any>;
type Translate=(zh:string,en:string)=>string;
const usd=(value:number)=>`$${value.toFixed(4)}`;
const priced=(record:Obj)=>record.accounting_version===2&&record.cost_status==='usage_priced'&&typeof record.usage_cost==='number';

export function RecordCost({record:r,t}:{record:Obj;t:Translate}){
  if(priced(r))return <span>{t('用量计价（无预留系数）','Usage-priced amount (no margin)')} · {usd(r.usage_cost)}</span>;
  if(r.status==='running'||r.status==='unknown')return <span>{t('待结算预留（非扣费）','Pending reservation (not a charge)')} · {usd(r.committed_cost||0)}</span>;
  if(r.accounting_version===2)return <span>{t('用量或计价信息不足；预留尚未释放','Usage or pricing incomplete; reservation retained')} · {usd(r.committed_cost||0)}</span>;
  return <span>{t('历史预算记录（非账单）','Legacy budget ledger (not a bill)')} · {usd(r.committed_cost||0)}</span>;
}

export function CostSummary({records,t}:{records:Obj[];t:Translate}){
  const usage=records.filter(priced),pending=records.filter(r=>!priced(r)&&(r.status==='running'||r.status==='unknown'||r.accounting_version===2));
  const legacy=records.filter(r=>r.accounting_version!==2&&r.status!=='running'&&r.status!=='unknown');
  const sum=(items:Obj[],key:string)=>items.reduce((total,r)=>total+(r[key]||0),0);
  return <section className="bw-cost-summary" aria-label={t('调用费用分类','Call cost categories')}>
    <p><strong>{t('供应商账单','Provider bill')}</strong> · <span>{t('未接入','Not connected')}</span></p>
    <p><strong>{t('用量计价（无预留系数）','Usage-priced amount (no margin)')}</strong> · <span>{usd(sum(usage,'usage_cost'))}</span> · {usage.length} {t('条已计价记录','priced records')}</p>
    <p><strong>{t('待结算预留','Pending reservations')}</strong> · <span>{usd(sum(pending,'committed_cost'))}</span></p>
    {!!legacy.length&&<details><summary>{t('历史预算记录（非账单）','Legacy budget ledger (not a bill)')}</summary><span>{usd(sum(legacy,'committed_cost'))}</span><p>{t('旧记录保留原值，未重新计价，不计入以上用量金额。','Original values are retained without repricing and excluded from the usage-priced amount above.')}</p></details>}
    <p className="bw-caption">{t('用量计价依据返回的 tokens 与保存的单价，不包含 1.5 倍预留余量；实际扣费请以供应商账单为准。结果未知的请求保留预留，不自动重试。','Token pricing uses reported usage and saved rates without the 1.5× reservation margin. Provider bills determine actual charges. Unknown outcomes retain reservations and are not retried automatically.')}</p>
  </section>;
}
