import {expect,test} from 'vitest';
import {savedExamples} from './saved-examples';
import original from '../../examples/builder/cup-complete/project.json';
import {presentProject} from './ProjectPresentation';

test('full cup conversation is English while original records and execution identities stay intact',()=>{
  const displayed=savedExamples.find(item=>item.id==='cup-complete')!;
  expect(displayed.messages).toHaveLength(5);
  expect(displayed.messages.map((m:any)=>m.text).join(' ')).not.toMatch(/[\u3400-\u9fff]/);
  expect(original.messages[1].text).toContain('全部40个标的');
  expect(displayed.versions).toEqual(original.versions);
  expect(displayed.builds).toEqual(original.builds);
  expect(displayed.runs).toEqual(original.runs);
  expect(displayed.presentation.translated_message_ids).toEqual(['message-2','message-3']);
});

test('a changed original cannot silently inherit a stale presentation translation',()=>{
  expect(()=>presentProject({messages:[{id:'m',text:'Changed rule'}]},
    {translations:{m:{source_text:'Original rule',text:'English rule'}}})).toThrow(/does not match/);
});
