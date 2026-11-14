import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import ConnectionSettings from './ModelSettings';

afterEach(cleanup);
const languages=[
  {locale:'en',t:(_:string,en:string)=>en,enabled:'Image inputs enabled',disabled:'Image inputs disabled',enable:'Enable image inputs',disable:'Disable image inputs',input:'Input USD / million tokens',output:'Output USD / million tokens',fetch:'Fetch model catalog',catalog:'Catalog models',model:'Model ID',unsupported:'This adapter has no supported image billing profile. Choose a compatible OpenAI, Anthropic or Gemini model.'},
  {locale:'zh-CN',t:(zh:string)=>zh,enabled:'图片输入已启用',disabled:'图片输入未启用',enable:'启用图片输入',disable:'停用图片输入',input:'输入价格 / 百万 tokens（美元）',output:'输出价格 / 百万 tokens（美元）',fetch:'读取模型目录',catalog:'目录中的模型',model:'模型 ID',unsupported:'此适配器没有受支持的图片计费配置。请选择 OpenAI、Anthropic 或 Gemini 的兼容模型。'},
];
const connection={id:'c1',name:'My model',provider:'openai',model:'selected-model',configured:true,storage:'session',input_price:1,output_price:3};
const providers=[{id:'openai',label:'OpenAI'},{id:'deepseek',label:'DeepSeek'}];
const diagnostics=/semantic understanding|not verified|not established|capability unknown|observed|observations|guaranteed|Catalog not checked|Model (?:not )?listed in catalog|语义理解|验证|能力未知|观察|不保证|不能证明|目录(?:尚未检查|已列出此模型|未列出此模型)/i;

for(const language of languages){
  for(const observed of [false,true]){
    test(`${language.locale} model settings show configuration without capability diagnostics when observations are ${observed?'present':'absent'}`,async()=>{
      const api=vi.fn(async()=>({persistent:false}));
      const {container}=render(<ConnectionSettings connections={[{...connection,image_inputs:observed,image_billing_profile:observed?'token-v1':null,image_observation:observed?'image_response_observed':'not_observed',verification:observed?'structured_response_observed':'not_tested',construction:observed?'code_construction_observed':'not_observed',catalog_status:observed?'catalog_available':'not_tested',selected_listed:observed}]} providers={providers} t={language.t} onSaved={async()=>{}} onError={()=>{}} api={api}/>);
      await waitFor(()=>expect(api).toHaveBeenCalledWith('/credential-capability'));
      expect(container.textContent).not.toMatch(diagnostics);
      expect(screen.getByText(observed?language.enabled:language.disabled)).toBeTruthy();
      expect((screen.getByRole('button',{name:observed?language.disable:language.enable}) as HTMLButtonElement).disabled).toBe(!observed);
      expect(screen.getByLabelText(language.input)).toBeTruthy();
      expect(screen.getByLabelText(language.output)).toBeTruthy();
      expect(api.mock.calls).toHaveLength(1);
    });
  }

  test(`${language.locale} model catalog remains selectable without capability-validation commentary`,async()=>{
    const api=vi.fn(async(path:string)=>path==='/connections/catalog'?{models:['selected-model','other-model']}:{persistent:false});
    const {container}=render(<ConnectionSettings connections={[]} providers={providers} t={language.t} onSaved={async()=>{}} onError={()=>{}} api={api}/>);
    fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'fixture-key'}});
    fireEvent.click(screen.getByRole('button',{name:language.fetch}));
    await screen.findByRole('option',{name:'selected-model'});
    expect(container.textContent).not.toMatch(diagnostics);
    fireEvent.change(screen.getByLabelText(language.catalog),{target:{value:'selected-model'}});
    expect((screen.getByLabelText(language.model) as HTMLInputElement).value).toBe('selected-model');
    expect(api.mock.calls.map(([path])=>path)).toEqual(['/credential-capability','/connections/catalog']);
  });

  test(`${language.locale} unsupported image adapters keep an actionable limitation`,async()=>{
    const api=vi.fn(async()=>({persistent:false}));
    render(<ConnectionSettings connections={[{...connection,provider:'deepseek',image_inputs:false}]} providers={providers} t={language.t} onSaved={async()=>{}} onError={()=>{}} api={api}/>);
    expect(await screen.findByText(language.unsupported)).toBeTruthy();
    expect(screen.queryByRole('button',{name:language.enable})).toBeNull();
  });

  test(`${language.locale} credential renewal preserves key replacement without internal observation commentary`,async()=>{
    const api=vi.fn(async(_path:string,_body?:Record<string,unknown>)=>({persistent:false}));
    const onSaved=vi.fn(async()=>{});
    const {container}=render(<ConnectionSettings connections={[connection]} providers={providers} t={language.t} onSaved={onSaved} onError={()=>{}} api={api}/>);
    fireEvent.click(screen.getByRole('button',{name:language.t('重新填写密钥','Re-enter key')}));
    expect(container.textContent).not.toMatch(diagnostics);
    fireEvent.change(screen.getByLabelText(language.t('新的 API Key','Replacement API key')),{target:{value:'replacement-fixture-key'}});
    fireEvent.click(screen.getByRole('button',{name:language.t('保存新密钥','Save replacement key')}));
    await waitFor(()=>expect(onSaved).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledWith('/connections/c1/credentials',{key:'replacement-fixture-key',remember:false,use_environment:false});
    expect(screen.queryByLabelText(language.t('新的 API Key','Replacement API key'))).toBeNull();
  });
}

test('image input failures preserve the configuration and surface the actual error',async()=>{
  const onError=vi.fn(),onSaved=vi.fn(async()=>{});
  const api=vi.fn(async(path:string)=>{
    if(path==='/connections/c1/images')throw new Error('Connection is in use by an active project. Wait before changing it.');
    return {persistent:false};
  });
  render(<ConnectionSettings connections={[{...connection,image_inputs:true}]} providers={providers} t={languages[0].t} onSaved={onSaved} onError={onError} api={api}/>);
  fireEvent.click(screen.getByRole('button',{name:'Disable image inputs'}));
  await waitFor(()=>expect(onError).toHaveBeenLastCalledWith('Connection is in use by an active project. Wait before changing it.'));
  expect(screen.getByText('Image inputs enabled')).toBeTruthy();
  expect(onSaved).not.toHaveBeenCalled();
  expect(api).toHaveBeenCalledWith('/connections/c1/images',{enabled:false,billing_profile:null});
});
