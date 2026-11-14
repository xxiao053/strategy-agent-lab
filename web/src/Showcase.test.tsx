import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import Showcase from './Showcase';

afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear();window.history.replaceState(null,'','#/')});
const example={id:'cup-complete',title:'Cup & handle · complete method',messages:[{id:'message-1',role:'user',text:'Keep my complete method.'}],
  materials:[],versions:[{number:1,scope:'Forty instruments',rules:[]}],builds:[],runs:[]};

test('saved walkthrough has user-controlled playback, a transcript and the revision clip',()=>{
  const network=vi.fn(()=>{throw Error('Media must be bundled')});vi.stubGlobal('fetch',network);
  render(<Showcase examples={[example]}/>);
  const video=screen.getByLabelText('Workflow video') as HTMLVideoElement;
  expect(video.controls).toBe(true);expect(video.autoplay).toBe(false);
  expect(video.getAttribute('preload')).toBe('none');
  expect(video.getAttribute('src')).toMatch(/walkthrough.*\.mp4/);
  expect(video.getAttribute('poster')).toMatch(/builder-conversation.*\.png/);
  expect(screen.getByRole('link',{name:'English / Chinese captions'}).getAttribute('href')).toMatch(/\.srt/);
  expect(screen.getByRole('link',{name:'Position sizing revision (GIF)'}).getAttribute('href')).toMatch(/revision.*\.gif/);
  fireEvent.change(screen.getByLabelText('Language'),{target:{value:'zh-CN'}});
  expect(screen.getByLabelText('工作流程视频')).toBeTruthy();
  expect(network).not.toHaveBeenCalled();
});

test('example cards summarize saved state instead of repeating stale draft instructions',()=>{
  render(<Showcase examples={[{...example,versions:[{number:1,scope:'Draft awaiting approval; do not build yet',rules:[]}]}]}/>);
  expect(screen.queryByText('Draft awaiting approval; do not build yet')).toBeNull();
  expect(screen.getByRole('navigation',{name:'My projects'})).toBeTruthy();
});

test('visitor inspects saved method, uses direct links and changes language without a backend',()=>{
  const network=vi.fn(()=>{throw Error('Static mode must not use an API')});vi.stubGlobal('fetch',network);
  window.history.replaceState(null,'','#/project/cup-complete/method');
  render(<Showcase examples={[example]}/>);
  expect(screen.getByRole('heading',{name:/Approved method/})).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'Materials'}));
  expect(window.location.hash).toBe('#/project/cup-complete/materials');
  expect(screen.getByText('Keep my complete method.')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Language'),{target:{value:'zh-CN'}});
  expect(screen.getByRole('tab',{name:'方法'})).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();expect(network).not.toHaveBeenCalled();
});

test('preview supplies a working local guide and never invents a repository link',()=>{
  render(<Showcase examples={[example]}/>);
  expect(screen.queryByRole('link',{name:'Source on GitHub'})).toBeNull();
  fireEvent.click(screen.getAllByRole('link',{name:'Run locally'})[0]);
  fireEvent(window,new HashChangeEvent('hashchange'));
  expect(screen.getByRole('heading',{name:'Run locally'})).toBeTruthy();
  expect(screen.getByText('.\\scripts\\start-docker.cmd')).toBeTruthy();
});

test('unknown deep link is recoverable and approved repository link is real',()=>{
  window.history.replaceState(null,'','#/project/absent/results');
  render(<Showcase examples={[example]} repositoryUrl="https://github.com/example-owner/example-repo"/>);
  expect(screen.getByText('Project not found.')).toBeTruthy();
  for(const link of screen.getAllByRole('link',{name:'Source on GitHub'}))expect(link.getAttribute('href')).toBe('https://github.com/example-owner/example-repo');
  fireEvent.click(screen.getAllByRole('button',{name:'Back to projects'}).at(-1)!);
  fireEvent(window,new HashChangeEvent('hashchange'));
  expect(screen.getByRole('heading',{name:'Your method, taking shape.'})).toBeTruthy();
});
