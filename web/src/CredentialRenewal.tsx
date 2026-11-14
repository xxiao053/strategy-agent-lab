import {useState} from 'react';
type Obj=Record<string,any>;
export default function CredentialRenewal({connection,persistent,environment,t,api,onSaved,onError}:{connection:Obj,persistent:boolean,environment:boolean,t:(zh:string,en:string)=>string,api:(path:string,body?:Obj)=>Promise<any>,onSaved:()=>Promise<void>,onError:(text:string)=>void}){
  const [open,setOpen]=useState(false),[key,setKey]=useState(''),[remember,setRemember]=useState(false),[useEnvironment,setUseEnvironment]=useState(false),[saving,setSaving]=useState(false);
  if(!open)return <button type="button" className="bw-secondary" onClick={()=>setOpen(true)}>{t('重新填写密钥','Re-enter key')}</button>;
  return <form onSubmit={async e=>{e.preventDefault();setSaving(true);onError('');try{await api(`/connections/${connection.id}/credentials`,{key,remember,use_environment:useEnvironment});setKey('');setOpen(false);await onSaved()}catch(e:any){onError(e.message)}finally{setSaving(false)}}}>
    <label>{t('新的 API Key','Replacement API key')}<input type="password" autoComplete="new-password" value={key} required={!useEnvironment} disabled={useEnvironment||saving} onChange={e=>setKey(e.target.value)}/></label>
    {environment&&<label><input type="checkbox" checked={useEnvironment} onChange={e=>setUseEnvironment(e.target.checked)}/>{t('明确使用后端环境中的密钥','Explicitly use the backend environment key')}</label>}
    {persistent&&<label><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/>{t('由 Windows 账户保护保存','Save with Windows account protection')}</label>}
    <p className="bw-caption">{t('保留模型、价格与项目分工。保存不会调用模型。活动任务期间不可更换凭据。','Preserves model, prices and project roles. Saving makes no model request. Credentials cannot be changed during active tasks.')}</p>
    <button disabled={saving}>{t('保存新密钥','Save replacement key')}</button><button type="button" disabled={saving} onClick={()=>{setKey('');setOpen(false)}}>{t('取消','Cancel')}</button>
  </form>;
}
