import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import ConnectionSettings from './ModelSettings';
import ProjectRuns from './ProjectRuns';
import RuntimeStatus from './RuntimeStatus';
const t=(_:string,en:string)=>en;

describe('portable local workflows',()=>{
  it('shows unavailable Docker without suggesting a host fallback',async()=>{
    render(<RuntimeStatus api={async()=>({backend:'docker',available:false,detail:'Start Docker Desktop.'})} t={t}/>);
    await waitFor(()=>expect(screen.getByText('Start Docker Desktop.')).toBeTruthy());
    expect(screen.getByText('Unavailable')).toBeTruthy();
  });
  it('renews a saved connection without exposing a secret or replacing roles',async()=>{
    const api=vi.fn(async(path:string)=>path==='/credential-capability'?{persistent:false}:{});
    render(<ConnectionSettings connections={[{id:'c1',name:'Saved',model:'model',configured:false,storage:'session'}]} providers={[]} t={t} api={api} onSaved={async()=>{}} onError={()=>{}}/>);
    await waitFor(()=>expect(screen.queryByText('Save locally, protected by my Windows account')).toBeNull());
    fireEvent.click(screen.getByRole('button',{name:'Re-enter key'}));
    const key=screen.getByLabelText('Replacement API key') as HTMLInputElement;expect(key.value).toBe('');
    fireEvent.change(key,{target:{value:'new-test-key'}});
    fireEvent.click(screen.getByRole('button',{name:'Save replacement key'}));
    await waitFor(()=>expect(api).toHaveBeenCalledWith('/connections/c1/credentials',{key:'new-test-key',remember:false,use_environment:false}));
    expect(api.mock.calls.some(([p])=>p==='/connections')).toBe(false);
  });
  it('prepares selected historical inputs only after explicit action',async()=>{
    const api=vi.fn(async(path:string)=>path==='/execution-catalog'?{symbols:['SPY']}:path.endsWith('/prepare-data')?{status:'completed',completed:1,total:1}:[]);
    const project={id:'p1',busy:false,model_roles:{},builds:[{id:'b1',status:'completed',execution_hash:'hash',version:1,artifacts:[{name:'execution.json',text:'{"schema":"strategy-v1","judgment":null}'}]}]};
    render(<ProjectRuns project={project} connections={[]} budget={1} rolesPending={false} api={api} t={t} onQuote={()=>{}} onChanged={async()=>{}}/>);
    fireEvent.change(screen.getByLabelText('Start session'),{target:{value:'2024-01-02'}});
    fireEvent.change(screen.getByLabelText('End session'),{target:{value:'2024-01-05'}});
    expect(api.mock.calls.some(([p])=>p.endsWith('/prepare-data'))).toBe(false);
    fireEvent.click(screen.getByRole('button',{name:'Prepare data'}));
    await waitFor(()=>expect(api).toHaveBeenCalledWith('/projects/p1/prepare-data',{build_id:'b1',symbols:['SPY'],start:'2024-01-02',end:'2024-01-05'}));
    expect(api.mock.calls.some((args:any[])=>args[1]?.authorized)).toBe(false);
  });
});
