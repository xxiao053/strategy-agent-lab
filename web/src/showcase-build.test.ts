// @vitest-environment node
import {expect,test} from 'vitest';
import {build} from 'vite';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';

test('static artifact shares the workbench entry and uses relative assets',async()=>{
  const output=await build({root:fileURLToPath(new URL('..',import.meta.url)),mode:'showcase-preview',logLevel:'silent',build:{write:false}});
  const files=(Array.isArray(output)?output[0]:output) as {output:any[]};
  const entry=files.output.find(item=>item.type==='chunk'&&item.isEntry);
  const modules=Object.keys(entry.modules).map(name=>name.replaceAll('\\','/'));
  expect(modules.some(name=>name.endsWith('/Workspace.tsx'))).toBe(true);
  expect(modules.some(name=>name.endsWith('/Showcase.tsx'))).toBe(false);
  const html=String(files.output.find(item=>item.fileName==='index.html').source);
  expect(html).toMatch(/src="\.\/assets\//);expect(html).not.toMatch(/src="\/assets\//);
},20000);

test.each(['production','showcase-preview'])('%s distribution retains complete license and data notices',async(mode)=>{
  const output=await build({root:fileURLToPath(new URL('..',import.meta.url)),mode,logLevel:'silent',build:{write:false}});
  const files=(Array.isArray(output)?output[0]:output) as {output:any[]};
  for(const [source,name] of [['LICENSE','LICENSE'],['THIRD_PARTY_NOTICES.txt','THIRD_PARTY_NOTICES.txt'],['DATA_NOTICE.md','DATA_NOTICE.md'],['DATA_NOTICE.zh-CN.md','DATA_NOTICE.zh-CN.md']]){
    const asset=files.output.find(item=>item.fileName===name);
    expect(asset,`Missing ${name} in ${mode}`).toBeDefined();
    expect(String(asset.source)).toBe(readFileSync(fileURLToPath(new URL('../../'+source,import.meta.url)),'utf8'));
  }
},20000);
