import {useEffect,useRef,useState} from 'react';
import {BookOpen,Folder,MessageSquare,Plus,Settings,Send,ShieldCheck,X,Check,History,FileText} from 'lucide-react';
import {useLanguage} from './i18n';
import ConnectionSettings,{ProjectModelRoles} from './ModelSettings';
import ProjectRuns from './ProjectRuns';
import RuntimeStatus from './RuntimeStatus';
import ProjectMaterials from './ProjectMaterials';
import {CostSummary,RecordCost} from './CostDetails';
import './workspace.css';
import SavedProject from './SavedProject';
import WorkbenchGuide from './WorkbenchGuide';
import CupReference from './CupReference';
import {projectLibrary,projectRoute} from './ProjectLibrary';
import {conversationText} from './ProjectPresentation';

type Obj=Record<string,any>;
export async function workspaceAPI(path:string,body?:Obj,method='POST'){
  const r=await fetch('/api/workspace'+path,body===undefined?{}:{method,headers:{'Content-Type':'application/json','X-Lab-Request':'1'},body:JSON.stringify(body)});
  const data=await r.json();
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request failed.');
  return data;
}

type WorkspaceProps={staticMode?:boolean;examples?:Obj[];referenceExample?:Obj;repositoryUrl?:string;imageURL?:(hash:string)=>string|undefined;media?:React.ReactNode};
const noExamples:Obj[]=[];
export default function Workspace({staticMode=false,examples=noExamples,referenceExample,repositoryUrl,imageURL,media}:WorkspaceProps={}){
  const {language,setLanguage}=useLanguage();
  const t=(zh:string,en:string)=>language==='en'?en:zh;
  const [projects,setProjects]=useState<Obj[]>([]),[connections,setConnections]=useState<Obj[]>([]),[providers,setProviders]=useState<Obj[]>([]);
  const [view,setView]=useState('home'),[project,setProject]=useState<Obj|null>(null);
  const [snapshot,setSnapshot]=useState<Obj|null>(null),[snapshotTab,setSnapshotTab]=useState('method');
  const library=projectLibrary(projects,examples);
  const [newProject,setNewProject]=useState(false),[name,setName]=useState(''),[tab,setTab]=useState('method');
  const [text,setText]=useState(''),[budget,setBudget]=useState('2'),[authorized,setAuthorized]=useState(false);
  const [roleDraft,setRoleDraft]=useState<Obj|null>(null);
  const [evidenceRef,setEvidenceRef]=useState<Obj|null>(null);
  const [materialRefs,setMaterialRefs]=useState<Obj[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const chatEnd=useRef<HTMLDivElement>(null);
  const navigation=useRef(0);
  const pendingOperations=useRef(0);
  const localIndex=useRef<Obj[]>([]),activeProject=useRef<Obj|null>(null);
  activeProject.current=project;
  function displayTitle(p:Obj|null){return examples.find(item=>item.source_project_id===p?.id)?.title||p?.title}
  async function refresh(){
    const [p,c,v]=await Promise.all([workspaceAPI('/projects'),workspaceAPI('/connections'),workspaceAPI('/providers')]);
    localIndex.current=p;setProjects(p);setConnections(c);setProviders(v);
    const route=projectRoute(window.location.hash),origin=route&&(examples.find(item=>item.id===route.id)?.source_project_id||route.id);
    if(origin&&p.some((item:Obj)=>item.id===origin)&&activeProject.current?.id!==origin)await loadNative(origin,route!.panel);
  }
  useEffect(()=>{if(!staticMode)refresh().catch(e=>setError(e.message));else if(!localStorage.getItem('sal.language'))setLanguage('en')},[staticMode]);
  useEffect(()=>{
    function readRoute(){
      navigation.current++;setAuthorized(false);
      const route=projectRoute(window.location.hash);
      if(route){
        const item=examples.find(item=>item.id===route.id);
        const native=localIndex.current.find(p=>p.id===(item?.source_project_id||route.id));
        if(!staticMode&&native){void loadNative(native.id,route.panel);return}
        setSnapshot(item||null);setSnapshotTab(route.panel);setView(item&&route.panel!=='records'?'snapshot':'missing');
      }else if(window.location.hash==='#/guide')setView('guide');
      else if(window.location.hash==='#/reference'&&referenceExample)setView('reference');
      else if(window.location.hash&&window.location.hash!=='#/')setView('missing');
      else setView('home');
    }
    readRoute();window.addEventListener('hashchange',readRoute);window.addEventListener('popstate',readRoute);
    return()=>{window.removeEventListener('hashchange',readRoute);window.removeEventListener('popstate',readRoute)};
  },[examples,referenceExample]);
  function setRoute(path:string){navigation.current++;window.history.pushState(null,'','#'+path)}
  function openSnapshot(item:Obj,panel='method'){setSnapshot(item);setSnapshotTab(panel);setView('snapshot');setError('');setRoute('/project/'+item.id+'/'+panel)}
  function selectNativeTab(next:string){
    setTab(next);
    const id=examples.find(item=>item.source_project_id===activeProject.current?.id)?.id||activeProject.current?.id;
    if(id)setRoute('/project/'+id+'/'+(next==='builds'?'implementation':next==='runs'?'results':next));
  }

  useEffect(()=>{
    if(!project?.busy||view!=='project')return;
    let live=true;
    const timer=setInterval(()=>{workspaceAPI('/projects/'+project.id).then(p=>{if(live)setProject(p)}).catch(e=>{if(live)setError(e.message)})},1500);
    return()=>{live=false;clearInterval(timer)};
  },[project?.id,project?.busy,view]);
  useEffect(()=>{chatEnd.current?.scrollIntoView?.({block:'nearest',behavior:'smooth'})},[project?.messages.length,busy]);
  async function act(fn:()=>Promise<void>,current=()=>true){setError('');pendingOperations.current++;setBusy(true);try{await fn()}catch(e:any){if(current())setError(e.message)}finally{pendingOperations.current--;setBusy(pendingOperations.current>0)}}
  async function updateNative(path:string,body:Obj,after?:(p:Obj)=>void){
    if(!project)return;
    const id=project.id,generation=navigation.current;
    const current=()=>activeProject.current?.id===id;
    await act(async()=>{
      const saved=await workspaceAPI('/projects/'+id+path,body);
      if(current())setProject(saved);
      if(current()&&navigation.current===generation)after?.(saved);
      await refresh();
    },()=>current()&&navigation.current===generation);
  }
  function navigate(next:string){if(busy)return;setView(next);setError('');if(next==='project')selectNativeTab(tab);else setRoute(['guide','reference'].includes(next)?'/'+next:'/')}
  async function open(p:Obj){
    if(busy)return;
    if(p.packaged){openSnapshot(p);return}
    const alias=examples.find(item=>item.source_project_id===p.id)?.id||p.id;
    setRoute('/project/'+alias+'/method');await loadNative(p.id,'method');
  }
  async function loadNative(id:string,panel?:string){
    const generation=++navigation.current;setAuthorized(false);
    const nextTab=panel==='implementation'?'builds':panel==='results'?'runs':panel;
    if(id===activeProject.current?.id){if(nextTab)setTab(nextTab);setView('project');return}
    await act(async()=>{
      const loaded=await workspaceAPI('/projects/'+id);
      if(generation!==navigation.current)return;
      setProject(loaded);setRoleDraft(null);setEvidenceRef(null);setMaterialRefs([]);setText('');setTab(nextTab||'method');setView('project');
    },()=>generation===navigation.current);
  }
  async function create(){const generation=navigation.current;await act(async()=>{const p=await workspaceAPI('/projects',{title:name,locale:language});if(generation===navigation.current){setRoute('/project/'+p.id+'/method');activeProject.current=p;setProject(p);setRoleDraft(null);setEvidenceRef(null);setMaterialRefs([]);setNewProject(false);setName('');setText('');setAuthorized(false);setView('project');setTab('method')}await refresh()},()=>generation===navigation.current)}
  async function copySnapshot(version:number){
    if(!snapshot||staticMode||busy)return;
    const generation=navigation.current,id=snapshot.id;
    await act(async()=>{
      const p=await workspaceAPI('/examples/'+id+'/copy',{version,locale:language});
      if(generation===navigation.current){setRoute('/project/'+p.id+'/method');activeProject.current=p;setProject(p);setRoleDraft(null);setEvidenceRef(null);setMaterialRefs([]);setText('');setAuthorized(false);setView('project');setTab('method')}
      await refresh();
    },()=>generation===navigation.current);
  }
  async function send(){if(!project||rolesPending||!imageReady)return;await updateNative('/messages',{text,connection_id:project.model_roles.builder,authorized,budget:Number(budget),...(evidenceRef?{evidence_ref:evidenceRef}:{}),...(materialRefs.length?{material_refs:materialRefs.map(({id,sha256,locations})=>({id,sha256,locations}))}:{})},p=>{setAuthorized(false);const last=p.records.at(-1);if(last?.status==='completed'){setEvidenceRef(null);setMaterialRefs([]);setText('')}else setError(last?.error||'Request did not complete.')})}
  async function build(){if(!project||rolesPending)return;await updateNative('/build',{version:project.versions.at(-1).version,connection_id:project.model_roles.builder,authorized,budget:Number(budget)},()=>{setAuthorized(false);selectNativeTab('builds')})}
  function editRoles(roles:Obj){setRoleDraft(roles);setAuthorized(false)}
  async function assignRoles(){if(!project||!roleDraft)return;setAuthorized(false);await updateNative('/models',roleDraft,()=>setRoleDraft(null))}
  const savedRoles=project?.model_roles||{builder:null,execution:null};
  const displayedRoles=roleDraft||savedRoles;
  const rolesPending=!!roleDraft&&(roleDraft.builder!==savedRoles.builder||roleDraft.execution!==savedRoles.execution);
  const connection=!rolesPending&&connections.find(c=>c.id===savedRoles.builder&&c.configured)?.id;
  const retainedImages:Obj[]=(project?.draft?.material_sources||[]).filter((s:Obj)=>s.image);
  const imageCount=new Set([...retainedImages.map(s=>s.id),...materialRefs.filter(r=>r.locations.includes('I1')).map(r=>r.id)]).size;
  const imageReady=imageCount===0||(imageCount<=2&&connections.some(c=>c.id===savedRoles.builder&&c.image_inputs&&['openai','anthropic','gemini'].includes(c.provider)));
  const tabs=[['method',t('方法','Method')],['materials',t('材料','Materials')],['builds',t('实现与验证','Implementation & validation')],['runs',t('运行与结果','Runs & results')],['versions',t('版本','Versions')],['records',t('模型调用记录','Model calls')]];
  const total=project?.records.reduce((n:number,r:Obj)=>n+r.committed_cost,0)||0;
  const translatedMessages:Obj[]=(project?.messages||[]).filter((m:Obj)=>conversationText(project!.id,m,examples)!==m.text);
  return <div className="bw-shell">
    <aside className="bw-side"><button className="bw-brand" onClick={()=>navigate('home')}><i>sa</i><span>strategy<br/>agent lab</span></button>
      <span className="bw-eyebrow">METHOD BUILDER</span>
      <nav><button className={view==='home'?'active':''} onClick={()=>navigate('home')}><Folder size={17}/>{t('项目','Projects')}</button>
      {!staticMode&&<><button className={view==='settings'?'active':''} onClick={()=>navigate('settings')}><Settings size={17}/>{t('模型设置','Model settings')}</button>
      <button disabled={busy} onClick={()=>{setName('');setNewProject(true)}}><Plus size={17}/>{t('新建项目','New project')}</button></>}
      {staticMode&&<a className="bw-saved-link" href="#/guide" onClick={e=>{e.preventDefault();navigate('guide')}}><BookOpen size={17}/>{t('本地运行','Run locally')}</a>}</nav>
      <nav className="bw-projects" aria-label={t('我的项目','My projects')}><span className="bw-eyebrow">{t('我的项目','MY PROJECTS')}</span>{library.map(p=><button key={p.id} disabled={busy} className={(view==='project'&&p.id===project?.id)||(view==='snapshot'&&(p.id===snapshot?.id||p.id===snapshot?.source_project_id))?'active':''} onClick={()=>open(p)}><MessageSquare size={14}/><span>{p.title}</span></button>)}
      {!library.length&&<p>{t('从一个想法开始。','Start with an idea.')}</p>}</nav>
      <footer>{referenceExample&&<button disabled={busy} onClick={()=>navigate('reference')}><BookOpen size={15}/>{t('杯柄突破 · 原始示范','Original cup & handle')}</button>}{repositoryUrl&&<a className="bw-saved-link" href={repositoryUrl} target="_blank" rel="noreferrer">{t('GitHub 源码','Source on GitHub')}</a>}<small><ShieldCheck size={12}/> {staticMode?t('只读预览','Read-only preview'):t('本地工作区','Local workspace')}</small></footer>
    </aside>
    <main className="bw-main">{!staticMode&&view==='settings'&&<RuntimeStatus api={workspaceAPI} t={t}/>}<header className="bw-top"><div>{t('工作台','Workspace')}<span>/</span><strong>{view==='reference'?t('杯柄突破','Original cup & handle'):view==='snapshot'?snapshot?.title:view==='guide'?t('本地运行','Run locally'):view==='project'?displayTitle(project):view==='settings'?t('模型设置','Model settings'):t('项目','Projects')}</strong></div>
      <div className="bw-top-actions">{staticMode&&<div className="bw-mobile-preview"><span>{t('只读预览','Read-only preview')}</span><a href="#/guide" onClick={e=>{e.preventDefault();navigate('guide')}}>{t('本地运行','Run locally')}</a>{repositoryUrl&&<a href={repositoryUrl} target="_blank" rel="noreferrer">{t('GitHub 源码','Source on GitHub')}</a>}</div>}{!staticMode&&<button className="bw-mobile-new" onClick={()=>setNewProject(true)}><Plus size={16}/>{t('新建','New')}</button>}<button className="bw-mobile-new" aria-label={t('返回项目列表','Back to projects')} onClick={()=>navigate('home')}><Folder size={16}/></button>{!staticMode&&<button className="bw-mobile-new" aria-label={t('打开模型设置','Open model settings')} onClick={()=>navigate('settings')}><Settings size={16}/></button>}<select aria-label={t('界面语言','Language')} value={language} onChange={e=>setLanguage(e.target.value as any)}><option value="zh-CN">中文</option><option value="en">English</option></select></div></header>
      {error&&<div className="bw-error" role="alert">{error}<button aria-label={t('关闭提示','Dismiss')} onClick={()=>setError('')}><X size={16}/></button></div>}
      {view==='home'&&<section className="bw-home"><div className="bw-eyebrow">FROM EXPERIENCE TO EXECUTION</div><h1>{t('你的方法，逐步成形。','Your method, taking shape.')}</h1>
        <div className="bw-project-grid">{library.map(p=><button key={p.id} onClick={()=>open(p)}><Folder size={20}/><h3>{p.title}</h3><p>{p.packaged?`${p.runs.at(-1)?.assumptions.symbols.length||0} ${t('个标的','instruments')} · ${p.runs.at(-1)?.total_sessions||0} ${t('个交易日','sessions')}`:p.revision?t('方法草稿已保存','Method draft saved'):t('等待你的描述','Ready for your ideas')}</p><span>{t('打开项目','Open project')} →</span></button>)}
        {!staticMode&&<button className="bw-new-card" onClick={()=>setNewProject(true)}><Plus size={23}/><h3>{t('新建项目','New project')}</h3><p>{t('从你的方法开始。','Start with your method.')}</p></button>}</div>
        {media}
      </section>}
      {view==='snapshot'&&snapshot&&<SavedProject key={snapshot.id} example={snapshot} initialTab={snapshotTab} onTab={next=>{setSnapshotTab(next);setRoute('/project/'+snapshot.id+'/'+next)}} imageURL={imageURL} onCopy={staticMode?undefined:copySnapshot} copying={busy}/>}
      {view==='guide'&&<WorkbenchGuide/>}
      {view==='reference'&&referenceExample&&<CupReference example={referenceExample}/>}
      {view==='missing'&&<section className="bw-home"><h1>{t('找不到这个项目。','Project not found.')}</h1><button className="bw-secondary" onClick={()=>navigate('home')}>{t('返回项目','Back to projects')}</button></section>}
      {view==='settings'&&<>{project&&<button onClick={()=>navigate('project')}>{t('返回当前项目','Back to current project')}</button>}<ConnectionSettings connections={connections} providers={providers} t={t} onSaved={refresh} onError={setError} api={workspaceAPI}/></>}
      {view==='project'&&project&&<div className="bw-project-work"><section className="bw-conversation"><div className="bw-conversation-head"><h1>{t('一起，把方法讲清楚。','Make your method explicit.')}</h1><p>{t('你来讲述判断，助手帮你整理与澄清。','Your experience. A shared, explicit understanding.')}</p></div>
        <div className="bw-chat">{project.example_origin&&<p><a href={'#/project/'+project.example_origin.id+'/method'}>{t('查看原始案例','View source example')}</a> · v{project.example_origin.version}</p>}{project.messages.map((m:Obj)=><article className={'bw-message '+m.role} key={m.id}><div className="bw-author">{m.role==='assistant'?<><i>s</i>{t('构建助手','Builder')}</>:t('你','You')}</div><div className="bw-bubble">{m.kind==='welcome'?t('你好，我会帮你把投资方法整理成可以运行、检查和修改的项目。\n\n你可以先讲一次具体的买卖，也可以贴一段笔记，不用一次说完整。我们会逐步明确关注的市场、决策依据、退出和仓位。还没想好的地方先留作问题。\n\n先说说你最想实现的那部分吧。','Hello. I’ll help turn your investment method into a project you can run, inspect and revise.\n\nStart with a concrete trade example or a note; you don’t need a complete specification. We’ll clarify the market, decisions, exits and sizing as we go. Anything undecided can remain an open question.\n\nWhat would you like to build first?'):conversationText(project.id,m,examples)}</div></article>)}
        {!!translatedMessages.length&&<details className="bw-conversation-source"><summary>{t('对话原文','Conversation source')}</summary><p>{t('部分历史消息显示为英文译文，原始消息保留如下。','Some historical messages are displayed in English translation. Their original text is preserved below.')}</p>{translatedMessages.map(m=><details key={m.id}><summary>{m.role==='user'?t('用户原文','User original'):t('助手原文','Builder original')}</summary><p>{m.text}</p></details>)}</details>}
        {(busy||project.busy)&&<div className="bw-thinking" role="status">{t('助手正在整理你的方法……','Your assistant is working through your method…')}</div>}<div ref={chatEnd}/></div>
        <form className="bw-compose" onSubmit={e=>{e.preventDefault();send()}}><ProjectModelRoles roles={displayedRoles} connections={connections} t={t} disabled={busy||project.busy} pending={rolesPending} onChange={editRoles} onSave={assignRoles} onConfigure={()=>navigate('settings')}/>
          <textarea aria-label={t('你的方法或补充','Your method or correction')} placeholder={t('描述想法、粘贴笔记，或指出哪里理解错了……','Describe an idea, paste a note, or correct an interpretation…')} maxLength={12000} value={text} onChange={e=>setText(e.target.value)} disabled={busy||project.busy}/>
          {!!materialRefs.length&&<div className="bw-evidence-attachment"><p>{t('将附带选定的材料原文及来源；此前已纳入方法草稿的材料会保留。','Selected source text and locations will be attached. Material already incorporated in the method draft is retained.')}</p>{materialRefs.map(ref=><small key={ref.id}>{ref.name||t('选定材料','Selected material')} · {ref.locations.join(', ')}</small>)}<button type="button" onClick={()=>{setMaterialRefs([]);setAuthorized(false)}}>{t('移除本次材料引用','Remove material attachment')}</button></div>}
          {!!imageCount&&<div className="bw-evidence-attachment"><p>{imageCount} / 2 {t('张当前选定／保留图片。授权发送时会附带实际规范化像素；代码构建仅使用确认的视觉解释。','selected/retained images. Authorized conversation sends normalized pixels; coding uses only the approved visual interpretation.')}</p>
            {retainedImages.map(source=><small key={source.id}>{t('已保留：','Retained: ')}{source.name} · I1 · {source.image.width} × {source.image.height}</small>)}
            {imageCount>2&&<p role="alert">{t('最多 2 张，请移除本次附件或建立范围更窄的项目；不会静默丢弃图片。','At most 2 images. Remove this attachment or start a narrower project; images are never silently dropped.')}</p>}
            {!imageReady&&imageCount<=2&&<><p>{t('附件已保留。所选构建连接尚未启用受支持的图片输入。','Attachment retained. The selected builder connection does not have supported image input enabled.')}</p><button type="button" onClick={()=>{setAuthorized(false);navigate('settings')}}>{t('启用或选择兼容的图片连接','Enable or choose a compatible image connection')}</button></>}
          </div>}
          {evidenceRef&&<div className="bw-evidence-attachment"><p>{t('将附带此决策的已保存输入、成交、判断及代码节选；超出上下文的内容会明确标注省略。','The selected decision’s saved inputs, fills, judgment and code excerpts will be attached; context omissions are explicitly identified.')} <small>{evidenceRef.run_id} · {evidenceRef.decision_id}</small></p><button type="button" onClick={()=>{setEvidenceRef(null);setAuthorized(false)}}>{t('移除决策证据','Remove decision evidence')}</button></div>}
          <div className="bw-budget"><label>{t('项目累计上限 $','Project total limit $')}<input aria-label={t('项目预算','Project budget')} type="number" min="0.01" max="100" step="0.01" value={budget} onChange={e=>{setBudget(e.target.value);setAuthorized(false)}}/></label><small>{t('预算占用','Budget occupied')} ${total.toFixed(4)}</small></div>
          <div className="bw-send-row"><label><input type="checkbox" disabled={rolesPending||busy||project.busy} checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/>{t('允许将本项目对话发送给所选模型，并在上述预算内调用。','Send this project’s conversation to the selected model within this budget.')}</label><button className="bw-primary" aria-label={t('发送','Send')} disabled={busy||project.busy||!text.trim()||!connection||!authorized||!imageReady}><Send size={17}/></button></div>
        </form></section>
        <aside className="bw-inspector"><div className="bw-inspector-head"><BookOpen size={17}/><h2>{t('正在形成的方法','Your method, taking shape')}</h2><span>{project.versions.length?'v'+project.versions.length:t('草稿','Draft')}</span></div><div className="bw-tabs">{tabs.map(([id,label])=><button key={id} onClick={()=>selectNativeTab(id)} className={tab===id?'active':''}>{label}</button>)}</div>
          <div className="bw-panel">{tab==='method'&&<><div className="bw-paper"><div className="bw-eyebrow">METHOD SPECIFICATION</div><h2>{displayTitle(project)}</h2>{project.draft?<><p>{project.draft.scope}</p>{project.draft.rules.map((r:Obj,i:number)=><div className="bw-rule" key={i}><h3>{r.topic}</h3><p>{r.rule}</p><small>{r.source}</small></div>)}{project.draft.questions.length>0&&<div className="bw-questions"><h3>{t('待确认的问题','Open questions')}</h3>{project.draft.questions.map((q:Obj,i:number)=><p key={i}>{q.question}<small>{q.blocking?t('影响执行','Needed for execution'):t('可后续完善','Can refine later')}</small></p>)}</div>}
          <button className="bw-primary" disabled={busy||project.busy||!project.draft.rules.length||project.draft.questions.some((q:Obj)=>q.blocking)||project.versions.at(-1)?.revision===project.revision} onClick={()=>updateNative('/approve',{revision:project.revision})}><Check size={15}/>{t('确认当前方法','Approve current method')}</button><p className="bw-caption">{t('确认会保存一个独立版本；后续对话只修改草稿。','Approval saves a separate version. Further conversation changes the draft only.')}</p></>:<><p>{t('从左侧的对话开始。你的表达会逐步成为有依据的规则和待确认的问题。','Start the conversation. Your words become grounded rules and questions to resolve.')}</p><div className="bw-ghost"/><div className="bw-ghost short"/></>}</div>
          {project.versions.length>0&&<div className="bw-paper"><h3>{t('构建与验证','Build and validate')}</h3><p>{t('基于已确认版本生成 Python 项目、运行测试和合成数据演示。使用项目构建模型和同一项目预算。','Generate a Python project from the approved version, run tests and a synthetic-data demonstration. Uses the project builder model and the same project budget.')}</p><button className="bw-primary" disabled={busy||project.busy||!authorized||!connection} onClick={build}>{t('构建并验证 v','Build and validate v')+project.versions.at(-1).version}</button><p className="bw-caption">{t('代码在当前选定的隔离环境中生成并验证；当前编码接口为 OpenAI Responses。历史模拟请在“运行与结果”中单独启动，不涉及实盘交易。','Code is generated and validated in the selected isolated runtime; coding currently uses OpenAI Responses. Start historical simulations separately in Runs & results. No live trading.')}</p></div>}</>}
          {tab==='builds'&&<>{!!project.starter_files?.length&&<section className="bw-paper"><h3>{t('起始代码','Starter source')}</h3><p>{t('来自原项目；确认你的方法后，将以这些文件为起点重新构建。','Copied from the source project. Approve your method to build from these files.')}</p>{project.starter_files.map((f:Obj)=><details key={f.name}><summary>{f.name}</summary><pre>{f.text}</pre></details>)}</section>}<BuildResults builds={project.builds||[]} t={t}/></>}
          {tab==='materials'&&<ProjectMaterials key={project.id} pid={project.id} api={workspaceAPI} t={t} disabled={busy||project.busy} onQuote={refs=>{setMaterialRefs(old=>[...old.filter(x=>!refs.some(r=>r.id===x.id)),...refs]);setAuthorized(false);if(!text.trim())setText(t('请解释选定材料的含义并指出需要澄清的问题。','Explain the selected material and identify any ambiguity.'))}}/>}
          {tab==='runs'&&<ProjectRuns key={project.id} project={project} connections={connections} budget={Number(budget)} rolesPending={rolesPending} api={workspaceAPI} t={t} onConfigure={()=>navigate('settings')} onQuote={(quote,reference)=>{setText(quote);setEvidenceRef(reference);setAuthorized(false)}} onChanged={async()=>{const updated=await workspaceAPI('/projects/'+project.id);if(activeProject.current?.id===project.id)setProject(updated);await refresh()}}/>}
          {tab==='versions'&&<div className="bw-paper"><h2>{t('方法版本','Method versions')}</h2>{project.versions.length?project.versions.map((v:Obj)=><details key={v.version}><summary>v{v.version} · {t('已确认','Approved')}</summary><p>{v.method.scope}</p>{v.method.rules.map((r:Obj,i:number)=><p key={i}><strong>{r.topic}</strong><br/>{r.rule}</p>)}</details>):<p>{t('确认方法后，版本会保存在这里。','Approved method versions will appear here.')}</p>}</div>}
          {tab==='records'&&<div className="bw-paper"><h2>{t('模型调用记录','Model calls')}</h2><CostSummary records={project.records} t={t}/>{project.records.length?project.records.slice().reverse().map((r:Obj)=><div className="bw-record" key={r.id}><strong>{r.model}</strong><span>{r.status==='completed'?t('已完成','Completed'):r.status==='running'?t('处理中','Running'):r.status==='unknown'?t('结果未知','Outcome unknown'):t('未完成','Failed')}</span><p>{r.kind==='execution'?t('执行判断','Execution judgment'):r.kind==='construction'?t('代码构建','Code construction'):t('方法澄清','Method clarification')} · <RecordCost record={r} t={t}/></p>{r.run_id&&<small>{r.run_id} · {r.decision_id}</small>}<small>{new Date(r.created).toLocaleString(language)}</small>{r.usage&&<small>{r.usage.input} input · {r.usage.output} output tokens</small>}{r.error&&<p className="bw-record-error">{r.error}</p>}</div>):<p>{t('还没有发起模型请求。','No model requests yet.')}</p>}</div>}</div>
        </aside></div>}
    </main>
    {newProject&&<div className="bw-overlay"><form className="bw-dialog" role="dialog" aria-modal="true" aria-labelledby="new-title" onSubmit={e=>{e.preventDefault();create()}}><button className="bw-close" type="button" aria-label={t('关闭','Close')} onClick={()=>setNewProject(false)}><X size={19}/></button><div className="bw-eyebrow">NEW PROJECT</div><h2 id="new-title">{t('从你的方法开始。','Start with your method.')}</h2><p>{t('先起一个名字，接下来由助手引导你。','Give it a name. Your assistant will guide the next steps.')}</p><label>{t('项目名称','Project name')}<input autoFocus maxLength={100} value={name} onChange={e=>setName(e.target.value)} required/></label><button className="bw-primary" disabled={!name.trim()||busy}>{t('创建项目','Create project')}</button></form></div>}
  </div>
}

function BuildResults({builds,t}:{builds:Obj[],t:(a:string,b:string)=>string}){
  return <>{!builds.length&&<div className="bw-paper"><p>{t('确认方法后即可构建，成果与验证记录会出现在这里。','Approve a method to build it. Artifacts and validation records will appear here.')}</p></div>}{builds.slice().reverse().map(b=><section className="bw-paper" key={b.id}><div className="bw-eyebrow">v{b.version} · {b.status==='completed'?t('构建完成','BUILD COMPLETE'):b.status==='running'?t('构建中','BUILDING'):t('需要检查','NEEDS ATTENTION')}</div><h2>{t('项目成果','Project artifacts')}</h2>{b.error&&<p className="bw-record-error">{b.error}</p>}{b.status==='running'&&<p role="status">{t('正在生成、测试和验证；离开页面不会停止任务。','Generating, testing and validating. Leaving this page will not stop the task.')}</p>}{b.validation&&<><h3>{t('生成项目自测报告','Generated self-test report')}</h3><p>{t('自测输出来自生成的项目；策略是否符合方法，还需独立案例与运行检查。','Self-tests are reported by the generated project; method fidelity needs independent cases and run checks.')}</p><pre>{b.validation.test_output}</pre><h3>{t('合成数据运行','Synthetic-data run')}</h3><details><summary>{t('查看运行输出','View run output')}</summary><pre>{b.validation.demo_output}{b.validation.demo_error}</pre></details></>}{b.artifacts.map((f:Obj)=><details key={f.name}><summary>{f.name}</summary><pre>{f.text}</pre><button className="bw-secondary" onClick={()=>{const url=URL.createObjectURL(new Blob([f.text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=f.name.split('/').at(-1);a.click();URL.revokeObjectURL(url)}}>{t('下载文件','Download file')}</button></details>)}{b.events?.length>0&&<details><summary>{t('构建过程','Construction activity')}</summary>{b.events.map((e:Obj,i:number)=><pre key={i}>{e.item?.text||e.item?.command||e.type}</pre>)}</details>}</section>)}</>
}

