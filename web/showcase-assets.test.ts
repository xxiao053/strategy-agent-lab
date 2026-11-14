// @vitest-environment node
import {afterEach,expect,test} from 'vitest';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {validateSavedExampleAssets} from './showcase-config';

const folders:string[]=[];
afterEach(()=>{for(const folder of folders.splice(0))rmSync(folder,{recursive:true,force:true})});
function fixture(){
  const root=mkdtempSync(join(tmpdir(),'saved-example-assets-'));folders.push(root);mkdirSync(join(root,'images'));
  const bytes=Buffer.from('reviewed fixture'),sha=createHash('sha256').update(bytes).digest('hex');
  writeFileSync(join(root,'project.json'),JSON.stringify({runs:[{decisions:[{images:[{sha256:sha}]}]}]}));
  writeFileSync(join(root,'images',sha+'.png'),bytes);return {root,sha};
}
test('a complete reviewed asset closure is accepted',()=>{const {root}=fixture();expect(()=>validateSavedExampleAssets(root)).not.toThrow()});
test('unreferenced PNG siblings cannot enter local or static distributions',()=>{
  const {root}=fixture();writeFileSync(join(root,'images','0'.repeat(64)+'.png'),'private-canary');
  expect(()=>validateSavedExampleAssets(root)).toThrow(/unreviewed/i);
});
test('a missing or modified referenced image fails closed',()=>{
  const {root,sha}=fixture();writeFileSync(join(root,'images',sha+'.png'),'changed');
  expect(()=>validateSavedExampleAssets(root)).toThrow(/integrity/i);
  rmSync(join(root,'images',sha+'.png'));expect(()=>validateSavedExampleAssets(root)).toThrow(/missing/i);
});
