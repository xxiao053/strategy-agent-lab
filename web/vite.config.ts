import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {showcaseSettings,validateSavedExampleAssets} from './showcase-config';
import {distributionNotices} from './distribution-notices';
export default defineConfig(({mode})=>{
  const exampleRoot=fileURLToPath(new URL('../examples/builder/cup-complete/',import.meta.url));
  const hasExample=existsSync(exampleRoot+'project.json');
  if(hasExample)validateSavedExampleAssets(exampleRoot);
  const secondaryRoot=fileURLToPath(new URL('../examples/builder/nvda-revision/',import.meta.url));
  if(existsSync(secondaryRoot+'project.json'))validateSavedExampleAssets(secondaryRoot);
  const settings=showcaseSettings(mode,process.env.VITE_SHOWCASE_REPOSITORY||'',hasExample);
  // Vite checks both the file and its ?url request; allow only the public media directory.
  const media=fileURLToPath(new URL('../docs/media/',import.meta.url));
  return {base:settings.base,plugins:[react(),distributionNotices(),...(settings.staticMode?[{name:'static-showcase-entry',transformIndexHtml:{order:'pre' as const,handler(html:string){return html.replace('/src/main.tsx','/src/showcase-main.tsx').replace('lang="zh-CN"','lang="en"').replace('投资方法构建工作台','Method builder workbench')}}}]:[])],
    define:{__SHOWCASE_REPOSITORY__:JSON.stringify(settings.repositoryUrl)},build:{outDir:settings.outDir},
    server:{host:'127.0.0.1',fs:{allow:[fileURLToPath(new URL('./',import.meta.url)),exampleRoot,secondaryRoot,media]},proxy:settings.staticMode?undefined:{'/api':'http://127.0.0.1:8765'}},test:{environment:'jsdom'}};
});
