import {expect,test} from 'vitest';
import {showcaseSettings} from '../showcase-config';

test('release build needs real repository configuration and a packaged genuine example',()=>{
  expect(()=>showcaseSettings('showcase','',true)).toThrow(/repository/i);
  for(const url of ['http://github.com/a/b','https://evil.example/a/b','https://github.com/a/b?token=private','javascript:alert(1)']){
    expect(()=>showcaseSettings('showcase',url,true)).toThrow(/repository/i);
  }
  expect(()=>showcaseSettings('showcase','https://github.com/a/b',false)).toThrow(/example/i);
  expect(showcaseSettings('showcase','https://github.com/a/b',true)).toEqual({staticMode:true,repositoryUrl:'https://github.com/a/b',outDir:'dist-showcase',base:'./'});
});

test('preview works without publishing configuration and leaves local build separate',()=>{
  expect(showcaseSettings('showcase-preview','',false)).toEqual({staticMode:true,repositoryUrl:'',outDir:'dist-showcase-preview',base:'./'});
  expect(showcaseSettings('production','',false)).toEqual({staticMode:false,repositoryUrl:'',outDir:'dist',base:'./'});
});
