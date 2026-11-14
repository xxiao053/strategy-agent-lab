import {readFileSync,readdirSync,lstatSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';

export function validateSavedExampleAssets(root:string){
  const manifest=join(root,'project.json'),directory=join(root,'images');
  if(lstatSync(manifest).isSymbolicLink()||lstatSync(directory).isSymbolicLink())throw Error('Unreviewed example link.');
  const example=JSON.parse(readFileSync(manifest,'utf8'));
  const expected=new Set<string>();
  for(const run of example.runs)for(const decision of run.decisions)for(const image of decision.images){
    if(typeof image.sha256!=='string'||!/^[a-f0-9]{64}$/.test(image.sha256))throw Error('Invalid example image identity.');
    expected.add(image.sha256+'.png');
  }
  const entries=readdirSync(directory,{withFileTypes:true});
  if(entries.some(entry=>!entry.isFile()||!expected.has(entry.name)))throw Error('Unreviewed example image: distribution blocked.');
  if(entries.length!==expected.size)throw Error('Missing reviewed example image.');
  for(const name of expected){
    const path=join(directory,name);
    if(lstatSync(path).size>2_000_000||createHash('sha256').update(readFileSync(path)).digest('hex')!==name.slice(0,-4))throw Error('Example image integrity mismatch.');
  }
}

export function showcaseSettings(mode:string,repositoryUrl:string,hasExample:boolean){
  const staticMode=mode==='showcase'||mode==='showcase-preview';
  if(repositoryUrl&&!/^https:\/\/github\.com\/[A-Za-z0-9][A-Za-z0-9-]*\/[A-Za-z0-9_.-]+$/.test(repositoryUrl))throw Error('Invalid GitHub repository URL.');
  if(mode==='showcase'&&!repositoryUrl)throw Error('Set VITE_SHOWCASE_REPOSITORY to the approved public repository URL.');
  if(mode==='showcase'&&!hasExample)throw Error('A reviewed genuine builder example is required for the release showcase.');
  return {staticMode,repositoryUrl,outDir:mode==='showcase'?'dist-showcase':mode==='showcase-preview'?'dist-showcase-preview':'dist',base:'./'};
}
