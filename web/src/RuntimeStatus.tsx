import {useEffect,useState} from 'react';
export default function RuntimeStatus({api,t}:{api:(path:string)=>Promise<any>,t:(zh:string,en:string)=>string}){
  const [runtime,setRuntime]=useState<any>(null);
  useEffect(()=>{let live=true;api('/runtime-status').then(r=>{if(live)setRuntime(r)}).catch(()=>{if(live)setRuntime({backend:'',available:false,detail:t('无法读取运行环境状态。','Runtime status unavailable.')})});return()=>{live=false}},[]);
  if(!runtime)return null;
  return <details className="bw-runtime"><summary>{t('隔离运行环境','Isolated runtime')} · {runtime.backend?.toUpperCase()} · <span>{runtime.available?t('可用','Available'):t('不可用','Unavailable')}</span></summary>
    <p>{t('每个任务在执行前检查隔离边界；环境不可用时不会直接在本机执行生成代码。','Each task checks isolation before execution. Unavailable isolation never falls back to running generated code on the host.')}</p><p>{runtime.detail}</p>
  </details>;
}
