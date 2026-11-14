type Obj=Record<string,any>;

// Only an explicit source identity can replace a packaged entry. Names are not identities.
export function projectLibrary(local:Obj[],packaged:Obj[]):Obj[]{
  return [...local.map(project=>({...project,title:packaged.find(item=>item.source_project_id===project.id)?.title||project.title,packaged:false})),
    ...packaged.filter(item=>!local.some(project=>project.id===item.source_project_id))
      .map(item=>({...item,packaged:true}))];
}

export const projectPanels=['method','materials','implementation','results','versions'];
export function projectRoute(hash:string){
  const match=/^#\/project\/([a-zA-Z0-9-]+)\/([a-z]+)$/.exec(hash);
  return match&&(projectPanels.includes(match[2])||['conversation','records'].includes(match[2]))?
    {id:match[1],panel:match[2]==='conversation'?'method':match[2]}:null;
}
