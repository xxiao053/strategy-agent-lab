import {afterEach,expect,test} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import CupReference from './CupReference';
import result from '../../examples/cup-handle/result.json';
import config from '../../examples/cup-handle/config.json';
afterEach(()=>{cleanup();localStorage.clear()});
test('original saved result stays inspectable and distinct from builder output',()=>{
  localStorage.setItem('sal.language','en');render(<CupReference example={{result,config}}/>);
  expect(screen.getByText(/not a newly generated Builder result/)).toBeTruthy();
  expect(screen.getByText(/40 US stocks/)).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'Trades'}));
  expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
  fireEvent.click(screen.getByRole('tab',{name:'Decisions'}));
  expect(screen.getAllByRole('heading',{level:2}).length).toBeGreaterThan(0);
});
