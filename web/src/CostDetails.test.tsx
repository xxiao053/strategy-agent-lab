import {afterEach,expect,test} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {CostSummary,RecordCost} from './CostDetails';
afterEach(cleanup);
const t=(_zh:string,en:string)=>en;
test('usage charges, unknown reservations and legacy ledger are separate, never an invoice',()=>{
  render(<CostSummary t={t} records={[
    {accounting_version:2,status:'completed',usage_cost:.125,committed_cost:.125,cost_status:'usage_priced',billed_cost:null},
    {accounting_version:2,status:'unknown',usage_cost:null,committed_cost:.4,reserved_cost:.4},
    {status:'completed',committed_cost:2},
  ]}/>);
  expect(screen.getByText('Provider bill')).toBeTruthy();expect(screen.getByText('Not connected')).toBeTruthy();
  expect(screen.getByText('Usage-priced amount (no margin)')).toBeTruthy();expect(screen.getByText('$0.1250')).toBeTruthy();
  expect(screen.getByText('Pending reservations')).toBeTruthy();expect(screen.getByText('$0.4000')).toBeTruthy();
  expect(screen.getByText('Legacy budget ledger (not a bill)')).toBeTruthy();expect(screen.getByText('$2.0000')).toBeTruthy();
  expect(screen.queryByText(/spent|paid|actual cost/i)).toBeNull();
});
test('a finished call does not display its original reservation as cost',()=>{
  render(<RecordCost t={t} record={{accounting_version:2,status:'completed',usage_cost:.0002,reserved_cost:1,committed_cost:.0002,cost_status:'usage_priced'}}/>);
  expect(screen.getByText(/Usage-priced amount.*\$0.0002/)).toBeTruthy();
  expect(screen.queryByText(/\$1.0000/)).toBeNull();
});
test('missing usage is pending instead of free or a fake bill',()=>{
  render(<RecordCost t={(zh)=>zh} record={{accounting_version:2,status:'completed',usage_cost:null,committed_cost:.1,cost_status:'usage_unpriced'}}/>);
  expect(screen.getByText(/用量或计价信息不足/)).toBeTruthy();
  expect(screen.queryByText(/已花费|实际费用|\$0.0000/)).toBeNull();
});
