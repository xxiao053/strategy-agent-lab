import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import ProjectMaterials from './ProjectMaterials';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
const t=(_:string,en:string)=>en;
test('previews inert source locations and attaches explicit identities without model calls',async()=>{
  const api=vi.fn(async(path:string)=>path.endsWith('/m1')?{id:'m1',sha256:'hash',name:'notes.md',units:[{location:'L1',text:'<script>alert(1)</script>'},{location:'L2',text:'ratio=0.125'}]}:[{id:'m1',sha256:'hash',name:'notes.md',locations:2}]);
  const quote=vi.fn();const {container}=render(<ProjectMaterials pid="p1" api={api} t={t} disabled={false} onQuote={quote}/>);
  fireEvent.click(await screen.findByRole('button',{name:'notes.md'}));
  expect(await screen.findByText('<script>alert(1)</script>')).toBeTruthy();expect(container.querySelector('script')).toBeNull();
  fireEvent.click(screen.getByRole('checkbox',{name:'L2'}));
  fireEvent.click(screen.getByRole('button',{name:'Reference selected locations in chat'}));
  expect(quote).toHaveBeenCalledWith([{id:'m1',sha256:'hash',name:'notes.md',locations:['L2']}]);
  expect(api.mock.calls.every(([path])=>path.includes('/materials'))).toBe(true);
});
test('empty state explains private supported upload and import sends only bytes',async()=>{
  const api=vi.fn(async()=>[]);const upload=vi.fn(async(_url:string,_options:any)=>({ok:true,json:async()=>({id:'new'})}));vi.stubGlobal('fetch',upload);
  render(<ProjectMaterials pid="p1" api={api} t={t} disabled={false} onQuote={()=>{}}/>);
  expect(await screen.findByText(/Add method notes/)).toBeTruthy();
  const file=new File(['rule'], 'notes.txt',{type:'text/plain'});
  fireEvent.change(screen.getByLabelText('Import material'),{target:{files:[file]}});
  await screen.findByText('Imported. Review the preview before referencing it.');
  expect(upload.mock.calls[0][0]).toBe('/api/workspace/projects/p1/materials');
  expect(upload.mock.calls[0][1].body).toBe(file);
});
test('selects a complete bounded reference and explains OCR failure in Chinese',async()=>{
  const api=vi.fn(async(path:string)=>path.endsWith('/m1')?{id:'m1',sha256:'hash',name:'notes.txt',units:[{location:'L1',text:'a'},{location:'L2',text:'b'}]}:[{id:'m1',sha256:'hash',name:'notes.txt',locations:2}]);
  const quote=vi.fn();vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>({detail:'No text could be extracted. Scanned/image-only PDF OCR is not supported.'})})));
  render(<ProjectMaterials pid="p1" api={api} t={(zh)=>zh} disabled={false} onQuote={quote}/>);
  fireEvent.click(await screen.findByRole('button',{name:'notes.txt'}));
  fireEvent.click(await screen.findByRole('button',{name:'选择全部位置'}));
  fireEvent.click(screen.getByRole('button',{name:'在对话中引用选定位置'}));
  expect(quote).toHaveBeenCalledWith([{id:'m1',sha256:'hash',name:'notes.txt',locations:['L1','L2']}]);
  fireEvent.change(screen.getByLabelText('导入材料'),{target:{files:[new File(['x'],'scan.pdf',{type:'application/pdf'})]}});
  expect(await screen.findByRole('alert')).toHaveProperty('textContent','未能提取文字。扫描件或纯图片 PDF 暂不支持 OCR，请上传可提取文字的版本。');
});

test('import notice follows language changes without another upload',async()=>{
  const api=vi.fn(async()=>[]);const upload=vi.fn(async()=>({ok:true,json:async()=>({id:'new'})}));vi.stubGlobal('fetch',upload);
  const props={pid:'p1',api,disabled:false,onQuote:()=>{}};
  const {rerender}=render(<ProjectMaterials {...props} t={(zh)=>zh}/>);
  fireEvent.change(screen.getByLabelText('导入材料'),{target:{files:[new File(['rule'],'notes.txt',{type:'text/plain'})]}});
  await screen.findByText('已导入。请先检查预览，再引用材料。');
  rerender(<ProjectMaterials {...props} t={t}/>);
  expect(await screen.findByText('Imported. Review the preview before referencing it.')).toBeTruthy();
  expect(upload).toHaveBeenCalledTimes(1);
});
