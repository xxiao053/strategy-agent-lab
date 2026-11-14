type Obj=Record<string,any>;

export function presentProject(original:Obj,presentation:Obj):Obj{
  const translations=presentation.translations||{};
  for(const [id,translation] of Object.entries(translations) as [string,Obj][]){
    if(original.messages.find((m:Obj)=>m.id===id)?.text!==translation.source_text)
      throw new Error('Conversation translation does not match its source message.');
  }
  return {...original,title:presentation.title||original.title,source_project_id:presentation.source_project_id,
    presentation:{language:presentation.language,translated_message_ids:Object.keys(translations),translations},
    messages:original.messages.map((message:Obj)=>({...message,text:translations[message.id]?.text||message.text}))};
}

export function conversationText(projectId:string,message:Obj,examples:Obj[]):string{
  const presentation=examples.find(item=>item.source_project_id===projectId)?.presentation;
  const translated=Object.values(presentation?.translations||{}).find((item:any)=>item.source_message_id===message.id&&item.source_text===message.text) as Obj|undefined;
  return translated?.text||message.text;
}
