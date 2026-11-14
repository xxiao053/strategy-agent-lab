import {useEffect,useState} from 'react';
type Obj=Record<string,any>;
type Props={pid:string;api:(path:string)=>Promise<any>;t:(zh:string,en:string)=>string;disabled:boolean;onQuote:(refs:Obj[])=>void};
export default function ProjectMaterials({pid,api,t,disabled,onQuote}:Props){
  const [items,setItems]=useState<Obj[]>([]),[preview,setPreview]=useState<Obj|null>(null);
  const [selected,setSelected]=useState<string[]>([]),[page,setPage]=useState(0),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  function localError(message:string){
    const explanations:[RegExp,string][]=[
      [/No text could be extracted/,'未能提取文字。扫描件或纯图片 PDF 暂不支持 OCR，请上传可提取文字的版本。'],
      [/encrypted/,'PDF 已加密，请先导出未加密的副本。'],
      [/PDF exceeds/,'PDF 超过 100 页，请拆分后导入。'],
      [/Invalid PDF|could not be parsed/,'材料无法解析，请检查格式或重新导出；加密、损坏或复杂版面可能不受支持。'],
      [/UTF-8|Binary content/,'请导出为 UTF-8 编码的文字或 CSV 文件。'],
      [/CSV exceeds/,'CSV 超过 1,000 条记录或 50 列，请拆分文件。'],
      [/Text exceeds|Extracted text exceeds/,'材料超过 100,000 字符或 10,000 文本行，请拆分文件。'],
      [/filename/,'请使用不含文件夹或特殊路径字符的文件名。'],
      [/Image /,'图片须为单帧 PNG/JPEG，最大 2,000,000 字节及 16,000,000 像素。请缩小或重新导出静态图片；规范化结果最多 512,000 字节，不会裁剪。'],
      [/File type|Supported formats|format/,'支持 TXT、Markdown、CSV、可提取文字的 PDF 和静态 PNG/JPEG，请确保类型与扩展名一致。'],
      [/20 materials/,'每个项目最多支持 20 个材料。'],
      [/Request too large|512,000/,'文件不能超过 512,000 字节。'],
      [/time|resource|limit/,'解析达到时间或资源限制，请使用更小的文件。'],
      [/Another material|active project/,'已有任务正在处理，请稍后再导入。'],
      [/integrity|Material unavailable/,'材料无法读取或完整性检查失败，请作为新材料重新导入。'],
      [/Record not found/,'项目或材料不存在，请刷新项目。'],
      [/No readable/,'材料中没有可读取的文字。'],
    ];
    return t(explanations.find(([pattern])=>pattern.test(message))?.[1]||'材料操作失败，请检查文件并重试。',message);
  }
  useEffect(()=>{let live=true;api(`/projects/${pid}/materials`).then(data=>{if(live)setItems(data)}).catch(e=>{if(live)setError(localError(e.message))});return()=>{live=false}},[pid]);
  async function open(item:Obj){setError('');setLoading(true);try{setPreview(await api(`/projects/${pid}/materials/${item.id}`));setSelected([]);setPage(0)}catch(e:any){setError(localError(e.message))}finally{setLoading(false)}}
  async function upload(file?:File){
    if(!file)return;setError('');setNotice('');
    const image=/\.(png|jpe?g)$/i.test(file.name),limit=image?2000000:512000;
    if(file.size>limit){setError(image?t('图片不能超过 2,000,000 字节。','Images must be at most 2,000,000 bytes.'):t('文件不能超过 512,000 字节。','Files must be at most 512,000 bytes.'));return}
    setLoading(true);
    try{
      const extension=file.name.split('.').at(-1)?.toLowerCase()||'';
      const types:Record<string,string>={txt:'text/plain',md:'text/markdown',csv:'text/csv',pdf:'application/pdf',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg'};
      const r=await fetch(`/api/workspace/projects/${pid}/materials`,{method:'POST',headers:{'X-Lab-Request':'1','X-Material-Name':encodeURIComponent(file.name),'Content-Type':file.type||types[extension]||'application/octet-stream'},body:file});
      const data=await r.json();if(!r.ok)throw new Error(data.detail||t('导入失败，请检查文件格式。','Import failed. Check the file format.'));
      setItems(await api(`/projects/${pid}/materials`));setNotice('imported');
    }catch(e:any){setError(localError(e.message))}finally{setLoading(false)}
  }
  return <section className="bw-paper bw-materials"><h2>{t('项目材料','Project materials')}</h2>
    <p>{t('导入笔记、方法或交易记录，检查原始位置后引用到对话。导入和预览不会调用模型；只有你授权发送时才会发送选定内容。','Import notes, methods or trade records, review their source locations, then reference them in chat. Import and preview make no model request; selected content is sent only with your authorized message.')}</p>
    <p className="bw-caption">{t('支持 UTF-8 TXT、Markdown、CSV、可提取文字的 PDF（各 512,000 字节）及静态 PNG/JPEG（2,000,000 字节、16,000,000 像素）。每项目最多 20 个文件，当前方法最多保留 2 张图片。图片按比例缩至最长边 1024，移除元数据；请检查实际发送的预览。材料私密保存，扫描 PDF 不支持 OCR。','UTF-8 TXT, Markdown, CSV and text-extractable PDF (512,000 bytes each), plus still PNG/JPEG (2,000,000 bytes, 16,000,000 pixels). Up to 20 files per project and 2 retained images per active method. Images are proportionally resized to a 1024-pixel maximum edge with metadata removed; review the actual send preview. Materials stay private. Scanned PDFs have no OCR support.')}</p>
    <label>{t('导入材料','Import material')}<input type="file" aria-label={t('导入材料','Import material')} accept=".txt,.md,.csv,.pdf,.png,.jpg,.jpeg" disabled={disabled||loading} onChange={e=>{upload(e.target.files?.[0]);e.target.value=''}}/></label>
    {loading&&<p role="status">{t('正在读取材料……','Reading material…')}</p>}{error&&<p role="alert">{error}</p>}{notice==='imported'&&<p role="status">{t('已导入。请先检查预览，再引用材料。','Imported. Review the preview before referencing it.')}</p>}
    {!items.length&&!loading&&<p>{t('添加方法笔记、走势图或交易 CSV。先检查预览，再选择要讨论的图片、行、页面或记录。','Add method notes, chart images or a trading CSV. Review the preview, then select the images, lines, pages or records you want to discuss.')}</p>}
    <ul>{items.map(item=><li key={item.id}><button disabled={loading} onClick={()=>open(item)}>{item.name}</button><small> {item.locations} {t('处原始位置','source locations')}</small></li>)}</ul>
    {preview&&<div><h3>{preview.name}</h3>{preview.source_kind==='example_excerpt'&&<p>{t('来自原始案例的资料节选。','Material excerpt from the source example.')}</p>}
      <details><summary>{t('来源详情','Source details')}</summary><small>{t('材料 ID','Material ID')}: {preview.id}<br/>SHA-256: {preview.sha256}</small>{preview.image&&<p className="bw-caption">{t('图片已按比例缩放并移除元数据；未进行 OCR。发送版本 SHA-256：','Image resized proportionally with metadata removed; no OCR performed. Send-version SHA-256: ')}{preview.image.sha256}</p>}</details>
      <div className="bw-material-actions"><button disabled={disabled||preview.units.length>1000} onClick={()=>setSelected(preview.units.map((u:Obj)=>u.location))}>{t('选择全部位置','Select all locations')}</button> <button disabled={disabled||!selected.length} onClick={()=>setSelected([])}>{t('清空选择','Clear selection')}</button> <small>{selected.length} {t('处已选择','locations selected')}</small> <button disabled={disabled||!selected.length} onClick={()=>onQuote([{id:preview.id,sha256:preview.sha256,name:preview.name,locations:selected}])}>{t('在对话中引用选定位置','Reference selected locations in chat')}</button></div>
      {preview.image&&<figure className="bw-image-evidence"><img src={`/api/workspace/projects/${pid}/materials/${preview.id}/images/${preview.image.sha256}`} alt={t('规范化图片：','Normalized image: ')+preview.name}/><figcaption>{preview.name} · {preview.image.width} × {preview.image.height} · I1<br/>{t('这就是授权发送时模型会收到的图片。','This is the image the model receives when you authorize sending.')}</figcaption></figure>}
      <p className="bw-caption">{t('L = 原始行，P = PDF 页，R = CSV 记录（C = 列，方括号内为表头）。日期、代码和数量均按原文显示，不自动推断交易含义。选择的材料是证据，不是权限或已确认规则。','L = original line, P = PDF page, R = CSV record (C = column, header in brackets). Dates, tickers and quantities are shown literally, without inferred trading semantics. Selected material is evidence, not permission or an approved rule.')}</p>
      <div className="bw-material-preview">{preview.units.slice(page*100,(page+1)*100).map((unit:Obj)=><div key={unit.location}><label><input type="checkbox" aria-label={unit.location} checked={selected.includes(unit.location)} disabled={disabled} onChange={e=>setSelected(old=>e.target.checked?[...old,unit.location]:old.filter(x=>x!==unit.location))}/>{unit.location}</label><pre>{unit.text||' '}</pre></div>)}</div>
      {preview.units.length>100&&<div><button disabled={!page} onClick={()=>setPage(page-1)}>{t('上一组','Previous')}</button> {page+1}/{Math.ceil(preview.units.length/100)} <button disabled={(page+1)*100>=preview.units.length} onClick={()=>setPage(page+1)}>{t('下一组','Next')}</button></div>}
      <p className="bw-caption">{t('每次选取及当前方法累计材料上下文最多 128 KiB；过长时请减少位置或拆分材料。','Selected and retained method material context is limited to 128 KiB. Select fewer locations or split long material.')}</p>
    </div>}
  </section>;
}
