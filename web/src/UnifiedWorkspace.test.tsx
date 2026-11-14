import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import Workspace from './Workspace';
import {referenceExample} from './saved-examples';

const cup={id:'cup-complete',source_project_id:'cup-origin',title:'Cup & handle · 718 sessions',messages:[{id:'m1',role:'user',text:'Use the full method.'}],materials:[],versions:[{number:1,scope:'Forty instruments',rules:[]}],builds:[],runs:[]};
const nvda={...cup,id:'nvda-revision',source_project_id:'nvda-origin',title:'NVDA · position sizing'};
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear();window.history.replaceState(null,'','#/')});

test('local example creates an independent unapproved copy of the selected version',async()=>{
  localStorage.setItem('sal.language','en');
  const copied={id:'new-copy',title:'My cup copy',locale:'en',revision:1,busy:false,messages:[],versions:[],records:[],model_roles:{builder:null,execution:null},draft:{scope:'My method',rules:[{topic:'Rule',rule:'Keep rule',source:'Example'}],questions:[]},example_origin:{id:'cup-complete',version:1},starter_files:[{name:'strategy.py',text:'# starter source'}]};
  let created=false;
  const fetcher=vi.fn(async(url:string,options?:any)=>{
    if(url.endsWith('/examples/cup-complete/copy')){expect(JSON.parse(options.body)).toEqual({version:1,locale:'en'});created=true;return {ok:true,json:async()=>copied}}
    return {ok:true,json:async()=>url.endsWith('/projects')?(created?[copied]:[]):url.endsWith('/new-copy')?copied:[]};
  });vi.stubGlobal('fetch',fetcher);
  render(<Workspace examples={[cup]}/>);
  fireEvent.click(screen.getByRole('button',{name:cup.title}));
  fireEvent.click(await screen.findByRole('button',{name:'Create editable copy'}));
  expect(await screen.findByLabelText('Your method or correction')).toBeTruthy();
  expect(window.location.hash).toBe('#/project/new-copy/method');
  expect(screen.getByRole('link',{name:'View source example'}).getAttribute('href')).toBe('#/project/cup-complete/method');
  expect(within(screen.getByRole('navigation',{name:'My projects'})).getAllByRole('button')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button',{name:'Implementation & validation'}));
  expect(screen.getByText('# starter source')).toBeTruthy();
  expect(screen.getByText('Starter source')).toBeTruthy();
});

test('failed example copying stays on the source and reports the error',async()=>{
  localStorage.setItem('sal.language','en');
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:!url.endsWith('/copy'),json:async()=>url.endsWith('/copy')?{detail:'Example unavailable'}:[]})));
  render(<Workspace examples={[cup]}/>);
  fireEvent.click(screen.getByRole('button',{name:cup.title}));
  fireEvent.click(await screen.findByRole('button',{name:'Create editable copy'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent','Example unavailable');
  expect(window.location.hash).toBe('#/project/cup-complete/method');
  expect(screen.queryByRole('textbox')).toBeNull();
});

test('static project list opens the ordinary split workbench with no live controls or API requests',()=>{
  localStorage.setItem('sal.language','en');const network=vi.fn();vi.stubGlobal('fetch',network);
  render(<Workspace staticMode examples={[cup,nvda]}/>);
  const list=screen.getByRole('navigation',{name:'My projects'});
  expect(within(list).getAllByRole('button')).toHaveLength(2);
  fireEvent.click(within(list).getByRole('button',{name:cup.title}));
  expect(document.querySelector('.bw-project-work .bw-conversation .bw-bubble')?.textContent).toBe('Use the full method.');
  expect(document.querySelector('.bw-project-work .bw-inspector')).toBeTruthy();
  expect(screen.getByRole('tab',{name:'Runs & results'})).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryByRole('button',{name:'Model settings'})).toBeNull();
  expect(screen.queryByRole('button',{name:'Create editable copy'})).toBeNull();
  expect(screen.queryByRole('link',{name:'Saved examples'})).toBeNull();
  expect(network).not.toHaveBeenCalled();
});

test('local origin remains editable once and unrelated same-title project is preserved',async()=>{
  localStorage.setItem('sal.language','en');
  const existing={id:'nvda-origin',title:nvda.title,messages:[],versions:[],records:[],model_roles:{builder:null,execution:null}};
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/projects')?[existing,{...existing,id:'unrelated'}]:url.endsWith('/nvda-origin')?existing:[]})));
  render(<Workspace examples={[cup,nvda]}/>);
  const list=await screen.findByRole('navigation',{name:'My projects'});
  const entries=await within(list).findAllByRole('button',{name:nvda.title});
  expect(entries).toHaveLength(2);
  expect(within(list).getAllByRole('button')).toHaveLength(3);
  fireEvent.click(entries[0]);
  expect(await screen.findByLabelText('Your method or correction')).toBeTruthy();
  fireEvent.click(within(list).getByRole('button',{name:cup.title}));
  expect(await screen.findByText('Use the full method.')).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
});

test('direct project links and browser back select the correct panel without a separate gallery',()=>{
  localStorage.setItem('sal.language','en');vi.stubGlobal('fetch',vi.fn());
  window.history.replaceState(null,'','#/project/cup-complete/results');
  render(<Workspace staticMode examples={[cup,nvda]}/>);
  expect(screen.getByRole('tab',{name:'Runs & results'}).getAttribute('aria-selected')).toBe('true');
  fireEvent.click(screen.getByRole('tab',{name:'Materials'}));
  expect(window.location.hash).toBe('#/project/cup-complete/materials');
  window.history.replaceState(null,'','#/project/nvda-revision/versions');fireEvent(window,new HashChangeEvent('hashchange'));
  expect(screen.getByRole('tab',{name:'Versions'}).getAttribute('aria-selected')).toBe('true');
  expect(within(screen.getByRole('navigation',{name:'My projects'})).getByRole('button',{name:nvda.title}).className).toContain('active');
});

test('returning from a packaged project retains the unsent local message',async()=>{
  localStorage.setItem('sal.language','en');
  const local={id:'local',title:'My draft',messages:[],versions:[],records:[],model_roles:{builder:null,execution:null}};
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/projects')?[local]:url.endsWith('/local')?local:[]})));
  render(<Workspace examples={[cup]}/>);
  fireEvent.click(await screen.findByRole('button',{name:'My draft'}));
  fireEvent.change(await screen.findByLabelText('Your method or correction'),{target:{value:'Keep this unsent correction'}});
  fireEvent.click(screen.getByRole('button',{name:cup.title}));
  fireEvent.click(screen.getByRole('button',{name:'My draft'}));
  expect((await screen.findByLabelText('Your method or correction') as HTMLTextAreaElement).value).toBe('Keep this unsent correction');
});

test('late project loading cannot replace a newer browser navigation',async()=>{
  localStorage.setItem('sal.language','en');
  const local={id:'local',title:'My draft',messages:[],versions:[],records:[],model_roles:{builder:null,execution:null}};
  let finish!:(v:any)=>void;
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:()=>url.endsWith('/local')?new Promise(resolve=>{finish=resolve}):Promise.resolve(url.endsWith('/projects')?[local]:[])})));
  render(<Workspace examples={[cup]}/>);
  fireEvent.click(await screen.findByRole('button',{name:'My draft'}));
  window.history.replaceState(null,'','#/project/cup-complete/results');fireEvent(window,new HashChangeEvent('hashchange'));
  expect(screen.getByText('Use the full method.')).toBeTruthy();
  await vi.waitFor(()=>expect(finish).toBeTypeOf('function'));
  finish(local);
  await vi.waitFor(()=>expect(screen.getByRole('button',{name:cup.title}).hasAttribute('disabled')).toBe(false));
  expect(screen.getByText('Use the full method.')).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
});

test('original execution reference keeps one independent entrance beside the two project entries',()=>{
  localStorage.setItem('sal.language','en');const network=vi.fn();vi.stubGlobal('fetch',network);
  render(<Workspace staticMode examples={[cup,nvda]} referenceExample={referenceExample}/>);
  expect(within(screen.getByRole('navigation',{name:'My projects'})).getAllByRole('button')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button',{name:'Original cup & handle'}));
  expect(screen.getByText('+136.76%')).toBeTruthy();
  expect(screen.getByRole('tab',{name:'Trades'})).toBeTruthy();
  expect(network).not.toHaveBeenCalled();
});

test('static compact header keeps the local guide, repository link and readonly state available',()=>{
  localStorage.setItem('sal.language','en');vi.stubGlobal('fetch',vi.fn());
  render(<Workspace staticMode examples={[cup]} repositoryUrl="https://github.com/owner/repo"/>);
  const header=document.querySelector('.bw-top-actions')!;
  expect(within(header as HTMLElement).getByRole('link',{name:'Run locally'})).toBeTruthy();
  expect(within(header as HTMLElement).getByRole('link',{name:'Source on GitHub'}).getAttribute('href')).toBe('https://github.com/owner/repo');
  expect(within(header as HTMLElement).getByText('Read-only preview')).toBeTruthy();
});

test('refreshing a native project link loads the editable project after the index arrives',async()=>{
  localStorage.setItem('sal.language','en');
  const local={id:'local',title:'My native project',messages:[],versions:[],records:[],model_roles:{builder:null,execution:null}};
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/projects')?[local]:url.endsWith('/local')?local:[]})));
  window.history.replaceState(null,'','#/project/local/records');
  render(<Workspace examples={[cup]}/>);
  expect(await screen.findByLabelText('Your method or correction')).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Model calls'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Materials'}));
  expect(window.location.hash).toBe('#/project/local/materials');
});

test('native English conversation retains inspectable original text without rewriting the message',async()=>{
  localStorage.setItem('sal.language','en');
  const message={id:'original-1',role:'user',text:'原始规则'};
  const local={id:'cup-origin',title:'Cup',messages:[message],versions:[],records:[],model_roles:{builder:null,execution:null}};
  const displayed={...cup,presentation:{translations:{m:{source_message_id:'original-1',source_text:'原始规则',text:'Original rule'}}}};
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/projects')?[local]:url.endsWith('/cup-origin')?local:[]})));
  window.history.replaceState(null,'','#/project/cup-complete/method');
  render(<Workspace examples={[displayed]}/>);
  await screen.findByLabelText('Your method or correction');
  expect(document.querySelector('.bw-bubble')?.textContent).toBe('Original rule');
  const provenance=screen.getByText('Conversation source').closest('details')!;
  expect(provenance.open).toBe(false);
  expect(within(provenance).getByText('原始规则')).toBeTruthy();
  expect(message.text).toBe('原始规则');
});

test('creating a project from an existing aliased project does not return to the old project',async()=>{
  localStorage.setItem('sal.language','en');
  const existing={id:'cup-origin',title:'Original full project',messages:[],versions:[],records:[],model_roles:{builder:null,execution:null}};
  const created={...existing,id:'new-project',title:'My new strategy'};
  let added=false;
  vi.stubGlobal('fetch',vi.fn(async(url:string,options:any)=>({ok:true,json:async()=>{
    if(url.endsWith('/projects')&&options?.method==='POST'){added=true;return created}
    return url.endsWith('/projects')?(added?[existing,created]:[existing]):url.endsWith('/cup-origin')?existing:[];
  }})));
  window.history.replaceState(null,'','#/project/cup-complete/method');
  render(<Workspace examples={[cup]}/>);
  await screen.findByLabelText('Your method or correction');
  fireEvent.click(screen.getByRole('button',{name:'New project'}));
  fireEvent.change(screen.getByLabelText('Project name'),{target:{value:'My new strategy'}});
  fireEvent.click(screen.getByRole('button',{name:'Create project'}));
  await screen.findByRole('button',{name:'My new strategy'});
  await vi.waitFor(()=>expect(window.location.hash).toBe('#/project/new-project/method'));
  expect(screen.getByRole('heading',{name:'My new strategy'})).toBeTruthy();
});

test('a late message response cannot replace the next native project or unlock overlapping work',async()=>{
  localStorage.setItem('sal.language','en');
  const a={id:'a',title:'Project A',messages:[],versions:[],records:[],model_roles:{builder:'c',execution:null}};
  const b={...a,id:'b',title:'Project B'};
  let finish!:(value:any)=>void;
  vi.stubGlobal('fetch',vi.fn(async(url:string,options:any)=>({ok:true,json:()=>{
    if(url.endsWith('/messages')&&options?.method==='POST')return new Promise(resolve=>{finish=resolve});
    return Promise.resolve(url.endsWith('/projects')?[a,b]:url.endsWith('/a')?a:url.endsWith('/b')?b:url.endsWith('/connections')?[{id:'c',configured:true,model:'fixture',provider:'openai'}]:[]);
  }})));
  render(<Workspace/>);
  fireEvent.click(await screen.findByRole('button',{name:'Project A'}));
  fireEvent.change(await screen.findByLabelText('Your method or correction'),{target:{value:'Update A'}});
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Send'}));
  await vi.waitFor(()=>expect(finish).toBeTypeOf('function'));
  window.history.replaceState(null,'','#/project/b/method');fireEvent(window,new HashChangeEvent('hashchange'));
  await screen.findByRole('heading',{name:'Project B'});
  expect((screen.getByLabelText('Your method or correction') as HTMLTextAreaElement).disabled).toBe(true);
  finish({...a,records:[{id:'response',status:'completed',committed_cost:0}]});
  await vi.waitFor(()=>expect((screen.getByLabelText('Your method or correction') as HTMLTextAreaElement).disabled).toBe(false));
  expect(screen.getByRole('heading',{name:'Project B'})).toBeTruthy();
  expect(window.location.hash).toBe('#/project/b/method');
});
