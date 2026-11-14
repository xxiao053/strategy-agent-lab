import {useEffect,useRef,useState} from 'react';
import CredentialRenewal from './CredentialRenewal';

type Obj=Record<string,any>;
type Translate=(zh:string,en:string)=>string;
type API=(path:string,body?:Obj,method?:string)=>Promise<any>;

function ImageInputPolicy({connection:c,t,api,onSaved,onError}:{connection:Obj;t:Translate;api:API;onSaved:()=>Promise<void>;onError:(s:string)=>void}){
  const [confirmed,setConfirmed]=useState(false),[saving,setSaving]=useState(false);
  const supported=['openai','anthropic','gemini'].includes(c.provider);
  async function save(){setSaving(true);onError('');try{await api(`/connections/${c.id}/images`,{enabled:!c.image_inputs,billing_profile:c.image_inputs?null:'token-v1'});setConfirmed(false);await onSaved()}catch(e:any){onError(e.message)}finally{setSaving(false)}}
  return <div className="bw-image-policy"><p>{c.image_inputs?t('图片输入已启用','Image inputs enabled'):t('图片输入未启用','Image inputs disabled')}</p>
    {supported?<><p className="bw-caption">{t('仅支持按 token 计费的图片输入；不支持按张收费或自定义计费。按像素及编码量保守预留预算，可能明显高于实际费用。启用本身不调用模型；使用当前已保存密钥。','Only token-billed image input is supported, not per-image or custom billing. Pixel/encoded-size reservations are deliberately conservative and may greatly exceed actual cost. Enabling makes no model call and uses the saved key.')}</p>
      {!c.image_inputs&&<label><input type="checkbox" checked={confirmed} disabled={saving} onChange={e=>setConfirmed(e.target.checked)}/>{t('我确认此所选模型接受图片，并按已配置的输入单价将图片输入计为 tokens。','I confirm this selected model accepts images and bills image input as tokens at the configured input rate.')}</label>}
      <button type="button" disabled={saving||(!c.image_inputs&&!confirmed)} onClick={save}>{c.image_inputs?t('停用图片输入','Disable image inputs'):t('启用图片输入','Enable image inputs')}</button>
    </>:<p>{t('此适配器没有受支持的图片计费配置。请选择 OpenAI、Anthropic 或 Gemini 的兼容模型。','This adapter has no supported image billing profile. Choose a compatible OpenAI, Anthropic or Gemini model.')}</p>}
  </div>;
}

export function ProjectModelRoles({roles,connections,t,disabled,pending,onChange,onSave,onConfigure}:{roles:Obj,connections:Obj[],t:Translate,disabled:boolean,pending:boolean,onChange:(roles:Obj)=>void,onSave:()=>void,onConfigure:()=>void}){
  const unavailable=(id:string)=>!connections.some(c=>c.id===id&&c.configured);
  return <div className="bw-model-roles">
    {(['builder','execution'] as const).map(role=>{
      const label=role==='builder'?t('构建模型','Builder model'):t('执行模型（可选）','Execution model (optional)');
      const id=roles[role]||'';
      return <label key={role}>{label}<select aria-label={label} value={id} disabled={disabled} onChange={e=>onChange({...roles,[role]:e.target.value||null})}>
        <option value="">{role==='builder'?t('选择构建模型','Select a builder model'):t('无执行模型（纯程序可运行）','No execution model (code-only methods)')}</option>
        {id&&unavailable(id)&&<option value={id}>{t('连接已移除或凭据未配置，请重新选择','Connection missing or unconfigured; choose again')}</option>}
        {connections.filter(c=>c.configured).map(c=><option key={c.id} value={c.id}>{c.name} · {c.model}</option>)}
      </select></label>
    })}
    <p className="bw-caption">{t('构建模型用于对话和代码构建；执行模型独立用于已确认方法要求的历史判断。图片能力需在所选连接上另行启用。','The builder handles conversation and construction; the independent execution model handles approved historical judgments. Image inputs must be enabled on the selected connection.')}</p>
    {pending&&<p role="status" className="bw-caption">{t('模型分工尚未保存。保存后请重新授权模型调用。','Model role changes are not saved. Save, then authorize model calls again.')}</p>}
    <button type="button" className="bw-secondary" disabled={disabled||!pending} onClick={onSave}>{t('保存模型分工','Save model roles')}</button>
    <button type="button" className="bw-secondary" disabled={disabled} onClick={onConfigure}>{t('配置模型','Configure models')}</button>
  </div>;
}

export default function ConnectionSettings({connections,providers,t,onSaved,onError,api}:{connections:Obj[],providers:Obj[],t:Translate,onSaved:()=>Promise<void>,onError:(s:string)=>void,api:API}){
  const [persistent,setPersistent]=useState(false);
  useEffect(()=>{let live=true;api('/credential-capability').then(r=>{if(live)setPersistent(r.persistent===true)}).catch(()=>{});return()=>{live=false}},[]);
  const [form,setForm]=useState({name:'',provider:'openai',model:'',key:'',input_price:'',output_price:'',cached_input_price:'',cache_write_price:'',remember:false,use_environment:false,reasoning_effort:''});
  const [saving,setSaving]=useState(false),[loading,setLoading]=useState(false),[note,setNote]=useState('');
  const [catalog,setCatalog]=useState<string[]>([]),[search,setSearch]=useState(''),[catalogState,setCatalogState]=useState('');
  const generation=useRef(0);
  useEffect(()=>()=>{generation.current++},[]);
  function invalidate(){generation.current++;setCatalog([]);setSearch('');setCatalogState('');setLoading(false)}
  function set(key:string,value:any){
    if(['provider','key','use_environment'].includes(key))invalidate();
    setForm(f=>key==='provider'?{...f,provider:value,model:'',key:'',input_price:'',output_price:'',cached_input_price:'',cache_write_price:'',use_environment:false,reasoning_effort:''}:{...f,[key]:value});
  }
  async function load(){
    const token=++generation.current;setLoading(true);setCatalog([]);setCatalogState('');
    try{
      const r=await api('/connections/catalog',{provider:form.provider,key:form.key,use_environment:form.use_environment});
      if(token!==generation.current)return;
      setCatalog(r.models);setCatalogState('available');setSearch('');
    }catch{
      if(token===generation.current)setCatalogState('failed');
    }finally{if(token===generation.current)setLoading(false)}
  }
  async function save(e:React.FormEvent){
    e.preventDefault();setSaving(true);onError('');
    try{
      const {cached_input_price,cache_write_price,...base}=form;
      await api('/connections',{...base,input_price:Number(form.input_price),output_price:Number(form.output_price),...(cached_input_price!==''?{cached_input_price:Number(cached_input_price)}:{}),...(cache_write_price!==''?{cache_write_price:Number(cache_write_price)}:{})});
      invalidate();setForm(f=>({...f,key:'',name:''}));
      setNote(t('连接已保存。保存本身没有调用模型。','Connection saved. Saving does not call the model.'));await onSaved();
    }catch(e:any){onError(e.message)}finally{setSaving(false)}
  }
  async function inspect(c:Obj){
    setSaving(true);onError('');
    try{
      const r=await api(`/connections/${c.id}/check`,{});
      setNote(r.selected_listed?t('目录包含所选模型；尚未发起推理。','Selected model is listed; no inference requested.'):t('目录未包含所选模型，请核对 ID 和账户权限。','Selected model is not listed; check ID and account access.'));
      await onSaved();
    }catch(e:any){onError(e.message)}finally{setSaving(false)}
  }
  const filtered=catalog.filter(m=>m.toLowerCase().includes(search.trim().toLowerCase()));
  return <section className="bw-settings"><div className="bw-eyebrow">YOUR MODELS</div><h1>{t('选你想用的模型。','Choose the models you use.')}</h1>
    <p className="bw-lead">{t('先选择供应商并提供凭据，读取目录后选择模型，也可手动填写 ID。每个项目独立设置构建和执行分工。','Choose a provider and credentials, then fetch and select a model or enter its ID manually. Projects have independent builder and execution assignments.')}</p>
    <div className="bw-settings-grid"><form className="bw-paper" onSubmit={save}><h2>{t('添加连接','Add connection')}</h2>
      <label>{t('供应商','Provider')}<select value={form.provider} onChange={e=>set('provider',e.target.value)}>{providers.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
      <label>API Key<input type="password" autoComplete="new-password" value={form.key} onChange={e=>set('key',e.target.value)} disabled={form.use_environment} required={!form.use_environment}/></label>
      {providers.find(p=>p.id===form.provider)?.environment_available&&<label className="bw-checkbox"><input type="checkbox" checked={form.use_environment} onChange={e=>set('use_environment',e.target.checked)}/>{t('明确使用本机已配置的此供应商 API Key','Use this provider’s key already configured on this computer')}</label>}
      <button type="button" className="bw-secondary" disabled={loading||(!form.use_environment&&!form.key.trim())} onClick={load}>{loading?t('正在读取目录…','Reading catalog…'):t('读取模型目录','Fetch model catalog')}</button>
      {catalogState==='failed'&&<p role="status" className="bw-notice">{t('目录暂不可用，可手动填写模型 ID 并保存连接；未发起推理。','Catalog unavailable. Enter a model ID manually and save; no inference requested.')}</p>}
      {catalogState==='available'&&<div className="bw-catalog"><label>{t('搜索模型','Search models')}<input type="search" value={search} onChange={e=>setSearch(e.target.value)}/></label>
        <label>{t('目录中的模型','Catalog models')}<select value={filtered.includes(form.model)?form.model:''} onChange={e=>set('model',e.target.value)}><option value="">{t('选择模型','Select a model')}</option>{filtered.map(m=><option key={m} value={m}>{m}</option>)}</select></label>
        <p className="bw-caption">{filtered.length} / {catalog.length}</p></div>}
      <label>{t('模型 ID','Model ID')}<input value={form.model} onChange={e=>set('model',e.target.value)} placeholder={t('可手动填写你有权使用的模型 ID','You can enter a model ID manually')} required/></label>
      <label>{t('连接名称','Connection name')}<input value={form.name} onChange={e=>set('name',e.target.value)} placeholder={t('例如：我的研究模型','e.g. My research model')} maxLength={80} required/></label>
      {persistent&&<label className="bw-checkbox"><input type="checkbox" checked={form.remember} onChange={e=>set('remember',e.target.checked)}/>{t('使用 Windows 账户保护并保存在本机','Save locally, protected by my Windows account')}</label>}
      {!persistent&&<p className="bw-notice">{t('此环境只支持会话密钥。后端重启后，使用已保存连接的“重新填写密钥”恢复，不必重新绑定项目。','This environment supports session-only keys. After backend restart, use Re-enter key on the saved connection; project bindings remain intact.')}</p>}
      <p className="bw-caption">{t('不勾选则只保留到后端重启。密钥不会进入项目文件或浏览器存储。','Otherwise the key lasts until the backend restarts. Keys are excluded from project files and browser storage.')}</p>
      <div className="bw-rate-grid"><label>{t('输入价格 / 百万 tokens（美元）','Input USD / million tokens')}<input type="number" min="0.000001" step="any" value={form.input_price} onChange={e=>set('input_price',e.target.value)} required/></label><label>{t('输出价格 / 百万 tokens（美元）','Output USD / million tokens')}<input type="number" min="0.000001" step="any" value={form.output_price} onChange={e=>set('output_price',e.target.value)} required/></label></div>
      <details><summary>{t('缓存计价（可选）','Cache pricing (optional)')}</summary><div className="bw-rate-grid"><label>{t('缓存读取价格 / 百万 tokens（美元）','Cache read USD / million tokens')}<input type="number" min="0" max="10000" step="any" value={form.cached_input_price} onChange={e=>set('cached_input_price',e.target.value)}/></label><label>{t('缓存写入价格 / 百万 tokens（美元）','Cache write USD / million tokens')}<input type="number" min="0" max="10000" step="any" value={form.cache_write_price} onChange={e=>set('cache_write_price',e.target.value)}/></label></div><p className="bw-caption">{t('请填写所选模型的实际单价；留空不代表免费。未知缓存价格会保留预留，不生成不完整的费用。','Use your selected model’s rates; blank does not mean free. Unknown cache pricing retains the reservation instead of producing an incomplete cost.')}</p></details>
      {form.provider==='openai'&&<label>{t('推理强度','Reasoning effort')}<select value={form.reasoning_effort} onChange={e=>set('reasoning_effort',e.target.value)}><option value="">{t('使用模型默认值','Model default')}</option>{['none','low','medium','high'].map(v=><option key={v}>{v}</option>)}</select></label>}
      <p className="bw-caption">{t('请使用供应商公布的当前单价。模型需支持结构化输出；推理选项需该模型支持。','Use the provider’s current rates. The model must support structured output and any reasoning option selected.')}</p><button className="bw-primary" disabled={saving}>{t('保存连接','Save connection')}</button>
    </form><div><h2>{t('已保存的连接','Saved connections')}</h2>{note&&<p className="bw-notice" role="status">{note}</p>}
      {connections.map(c=><article className="bw-paper" key={c.id}><div className="bw-eyebrow">{c.provider}</div><h3>{c.name}</h3><p>{c.model}</p>
        <small>{c.configured?t('凭据已配置','Credentials configured'):t('请重新填写凭据','Re-enter credentials')} · {c.storage==='os-protected'?t('本机加密保存','OS-protected'):t('当前会话','Session only')}</small>
        <CredentialRenewal connection={c} persistent={persistent} environment={!!providers.find(p=>p.id===c.provider)?.environment_available} t={t} api={api} onSaved={onSaved} onError={onError}/>
        <ImageInputPolicy connection={c} t={t} api={api} onSaved={onSaved} onError={onError}/>
        <div className="bw-actions"><button type="button" className="bw-secondary" disabled={saving||!c.configured} onClick={()=>inspect(c)}>{t('检查连接','Check connection')}</button><button type="button" className="bw-secondary" disabled={saving} onClick={async()=>{try{await api('/connections/'+c.id,{},'DELETE');await onSaved()}catch(e:any){onError(e.message)}}}>{t('移除连接','Remove connection')}</button></div>
      </article>)}{!connections.length&&<p className="bw-muted">{t('添加第一个连接，然后回到项目选择角色。','Add your first connection, then assign its project role.')}</p>}
      <p className="bw-caption">{t('检查连接会读取供应商的模型目录，不调用模型。','Checking a connection reads the provider’s model catalog without calling the model.')}</p>
    </div></div>
  </section>;
}
