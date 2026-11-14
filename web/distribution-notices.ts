import {readFileSync} from 'node:fs';
import type {Plugin} from 'vite';

/** Keep complete notices in every distributed frontend, independent of minification. */
export function distributionNotices():Plugin {
  return {
    name:'distribution-notices',
    generateBundle(){
      for(const [source,fileName] of [
        ['LICENSE','LICENSE'],
        ['THIRD_PARTY_NOTICES.txt','THIRD_PARTY_NOTICES.txt'],
        ['DATA_NOTICE.md','DATA_NOTICE.md'],
        ['DATA_NOTICE.zh-CN.md','DATA_NOTICE.zh-CN.md'],
      ]){
        this.emitFile({type:'asset',fileName,source:readFileSync(new URL('../'+source,import.meta.url),'utf8')});
      }
    },
  };
}
