import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import SavedProject,{runMetrics} from './SavedProject';

afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear()});
const example={id:'actual-example',title:'Complete method',schema:'saved-builder-example-v1',
  messages:[{id:'m1',role:'user',text:'Use my original forty symbols.'},{id:'m2',role:'assistant',text:'The method is ready for approval.'}],
  materials:[{id:'material-1',name:'method.md',sha256:'a'.repeat(64),units:[{location:'L1',text:'Use the confirmed rule.'}]}],
  versions:[{number:1,scope:'Daily US stocks',rules:[{topic:'Entry',rule:'Assess the fixed candidate.',source:'method.md L1',material_refs:[]}]}],
  builds:[{id:'build-v1',version:1,status:'completed',original_build_hash:'b'.repeat(64),files:[{name:'strategy.py',text:'<script>window.HACKED=true</script>',sha256:'b'.repeat(64)}],validation:{tests_passed:true,test_output:'7 tests passed',demo_output:'synthetic only'}}],
  runs:[{id:'run-v1',build_id:'build-v1',version:1,status:'completed',original_run_hash:'c'.repeat(64),completed_sessions:718,total_sessions:718,assumptions:{start:'2024-01-02',end:'2026-11-10',symbols:['SPY'],initial_cash:100000,fee_rate:.0005},
    curve:[{date:'2024-01-02',cash:100000,equity:100000},{date:'2026-11-10',cash:100001,equity:100001}],positions:[],
    trades:[{symbol:'SPY',quantity:3,action:'buy',date:'2024-01-03',price:100,fee:.15,decision_id:'d1'}],
    decisions:[{id:'d1',symbol:'SPY',cutoff:'2024-01-02',status:'ordered',explanation:'Approved numeric conditions passed.',candidates:[],images:[],model:{verdict:'pass',reason:'Shape accepted',primary:{assessments:[{candidate_id:'candidate-1',verdict:'fail',checks:{cup:{reason:'Initial V concern',verdict:'fail',evidence:[{symbol:'SPY',date:'2024-01-02'}]}}}]},review:{assessments:[{candidate_id:'candidate-1',verdict:'pass',checks:{cup:{reason:'Sustained base is visible',verdict:'pass',evidence:[{symbol:'SPY',date:'2024-01-02'}]}}}]}}}],judgment:{criteria:'Inspect the approved shape'},account_policy:{risk_fraction:.25}}]};

test('saved workflow is inspectable without live controls or any API request',()=>{
  localStorage.setItem('sal.language','en');const network=vi.fn(()=>{throw Error('No API permitted')});vi.stubGlobal('fetch',network);
  render(<SavedProject example={example}/>);
  expect(screen.getByText('Use my original forty symbols.')).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();expect(screen.queryByRole('button',{name:/send|build and|new project|authorize/i})).toBeNull();
  fireEvent.click(screen.getByRole('tab',{name:'Method'}));expect(screen.getByText('Assess the fixed candidate.')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'Materials'}));expect(screen.getByText('Use the confirmed rule.')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'Implementation & validation'}));expect(screen.getByText('7 tests passed')).toBeTruthy();
  expect(screen.getByText('<script>window.HACKED=true</script>')).toBeTruthy();expect(document.querySelector('script')).toBeNull();
  expect(network).not.toHaveBeenCalled();
});

test('generated self-test output is not labeled as independent validation',()=>{
  localStorage.setItem('sal.language','en');render(<SavedProject example={example} initialTab="implementation"/>);
  expect(screen.getByText('Generated self-tests: reported pass')).toBeTruthy();
  expect(screen.getByText(/Self-test output comes from the generated project/)).toBeTruthy();
  expect(screen.queryByText('Build tests passed')).toBeNull();
});

test('return and drawdown use initial cash and the full daily equity path',()=>{
  expect(runMetrics({assumptions:{initial_cash:100},curve:[{equity:90},{equity:120},{equity:90},{equity:110}]})).toEqual({totalReturn:.1,maxDrawdown:.25});
  expect(runMetrics({assumptions:{initial_cash:100},curve:[]})).toBeNull();
});

test('saved result exposes return, daily close drawdown and independent review separately',()=>{
  localStorage.setItem('sal.language','en');
  const reviewed={...example,independent_checks:{implementation_cases:26,sessions:718,fills:56,images:105,response_repairs:2,
    checks:['Daily equity reconstruction'],build_hash:'b'.repeat(64),run_hash:'c'.repeat(64)}};
  render(<SavedProject example={reviewed} initialTab="results"/>);
  expect(screen.getByText('Total return')).toBeTruthy();expect(screen.getByText('Maximum drawdown (daily close)')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'Implementation & validation'}));
  expect(screen.getByRole('heading',{name:'Independent checks'})).toBeTruthy();
  expect(screen.getByText('Daily equity reconstruction')).toBeTruthy();
});

test('a saved fill opens its real primary and review evidence',()=>{
  localStorage.setItem('sal.language','en');render(<SavedProject example={example} initialTab="results"/>);
  expect(screen.getByText('718 / 718 sessions')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:/SPY.*2024-01-03/}));
  expect(screen.getByText('Initial V concern')).toBeTruthy();expect(screen.getByText('Sustained base is visible')).toBeTruthy();
  expect(screen.getByText('Inspect the approved shape')).toBeTruthy();
});

test('multiple passing candidates identify the selected geometry and final merged judgment',()=>{
  localStorage.setItem('sal.language','en');
  const original=example.runs[0].decisions[0],primary=original.model.primary.assessments[0];
  const final=original.model.review.assessments[0];
  const decision={...original,selected_candidate_id:'candidate-2',candidates:[{candidate_id:'candidate-1',stop:90,target:120},{candidate_id:'candidate-2',stop:91,target:125}],model:{...original.model,
    assessments:[final,{...final,candidate_id:'candidate-2'}],primary:{assessments:[primary,{...final,candidate_id:'candidate-2'}]}}};
  render(<SavedProject example={{...example,runs:[{...example.runs[0],decisions:[decision]}]}} initialTab="results"/>);
  fireEvent.click(screen.getByRole('button',{name:/SPY.*2024-01-03/}));
  const selected=screen.getByRole('region',{name:'Selected candidate'});
  expect(within(selected).getByText('candidate-2')).toBeTruthy();
  expect(within(selected).getByText('$91.00')).toBeTruthy();expect(within(selected).getByText('$125.00')).toBeTruthy();
  const merged=screen.getByRole('region',{name:'Final assessments'});
  expect(within(merged).getByText('candidate-1 · Pass')).toBeTruthy();
  expect(within(merged).getByText('candidate-2 · Pass')).toBeTruthy();
  expect(screen.getByText('Initial V concern')).toBeTruthy();
});

test('run and method selectors keep the displayed version relationship consistent',()=>{
  localStorage.setItem('sal.language','en');
  const versions=[...example.versions,{...example.versions[0],number:2},{...example.versions[0],number:3}];
  const runs=[example.runs[0],{...example.runs[0],id:'run-v2',version:2}];
  render(<SavedProject example={{...example,versions,runs}} initialTab="results"/>);
  fireEvent.change(screen.getByLabelText('Select run'),{target:{value:'run-v1'}});
  expect((screen.getByLabelText('Method version') as HTMLSelectElement).value).toBe('1');
  fireEvent.change(screen.getByLabelText('Method version'),{target:{value:'2'}});
  expect((screen.getByLabelText('Select run') as HTMLSelectElement).value).toBe('run-v2');
  fireEvent.change(screen.getByLabelText('Method version'),{target:{value:'3'}});
  expect(screen.getByText('No saved historical run for this method version.')).toBeTruthy();
});

test('incomplete history remains visibly failed and Chinese tabs work',()=>{
  const failed={...example,runs:[{...example.runs[0],status:'failed',completed_sessions:4}]};
  render(<SavedProject example={failed} initialTab="results"/>);
  expect(screen.getByText('未完成')).toBeTruthy();expect(screen.getByText('4 / 718 个交易日')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'版本'}));expect(screen.getByText('Daily US stocks')).toBeTruthy();
});
