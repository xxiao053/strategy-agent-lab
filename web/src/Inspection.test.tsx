import { afterEach, expect, test } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { CandidateInspection, PositionTable, ExitReason } from './Inspection';
import { translate } from './i18n';
afterEach(() => { cleanup(); localStorage.clear(); });
const candidate={candidate_id:'fixed-A',rank:1,left_rim:'2024-01-02',right_rim:'2024-04-01',bottom:'2024-02-02',handle_start:'2024-04-02',handle_end:'2024-04-08',stop:92,target:120,volatility_unit:2,cup_sessions:65,handle_sessions:5,numeric_checks:[]};
const assessment=(verdict:string)=>({candidate_id:'fixed-A',verdict,evidence:'Traceable evidence',checks:[{name:'cup',verdict,reason:'Fixed region',start_date:'2024-01-02',end_date:'2024-04-01'}]});

test('inspection shows original, review and final judgment on the same marked geometry',()=>{
 render(<CandidateInspection runId="local" symbol="QQQ" day="2024-04-09" event={{candidates:[candidate],primary_evaluations:[assessment('fail')],review_evaluations:[assessment('pass')],evaluations:[assessment('pass')],validation:{pattern:candidate}}} />);
 expect(screen.getByText('主判断 · 未通过')).toBeTruthy();
 expect(screen.getByText('复核 · 通过')).toBeTruthy();
 expect(screen.getByText('最终判断 · 通过')).toBeTruthy();
 expect(screen.getByRole('img').getAttribute('src')).toContain('candidate_id=fixed-A');
 expect(screen.getByText('已选为订单依据')).toBeTruthy();
});

test('positions expose actual weight, frozen exits and progress instead of total-age exit',()=>{
 render(<PositionTable positions={{QQQ:{candidate_id:'fixed-A',quantity:100,last_close:100,entry_price:95,stop:92,target:120,volatility_unit:2,progress_anchor:101,stagnant_sessions:7}}} equity={100000} strategy={{stagnation_sessions:15,progress_units:1}} />);
 expect(screen.getByText('10.00%')).toBeTruthy();
 expect(screen.getByText('7 / 15')).toBeTruthy();
 expect(screen.getByText('$103.00')).toBeTruthy();
});

test('new exit labels and original decision stages switch to English',()=>{
 localStorage.setItem('sal.language','en');
 render(<><ExitReason reason="target_close"/><ExitReason reason="stagnation"/><ExitReason reason="stop_close"/></>);
 expect(screen.getByText('Target reached at close')).toBeTruthy();
 expect(screen.getByText('No-progress exit')).toBeTruthy();
 expect(screen.getByText('Stop breached at close')).toBeTruthy();
});

test('an accepted shape blocked by account limits clearly says no order and why',()=>{
 render(<CandidateInspection runId="local" symbol="QQQ" day="2024-04-09" event={{candidates:[candidate],evaluations:[assessment('pass')],order_id:null,validation:{pattern:candidate,execution_note:'Slot/cash/risk constraint; no order'}}}/>);
 expect(screen.getByText('未创建订单')).toBeTruthy();
 expect(screen.getByText('Slot/cash/risk constraint; no order')).toBeTruthy();
});

test('archive-copy provenance translates even when the display string starts with a separator',()=>{
 expect(translate(' · 归档结果副本，未经重新计算','en')).toBe(' · Copy of the archived result; not recalculated');
});

test('an account-precheck skip is not presented as a model rejection',()=>{
 render(<CandidateInspection runId="local" symbol="QQQ" day="2024-04-09" event={{candidates:[candidate],execution_precheck:{eligible:false,available_cash:105.21},validation:{reason:'not_executable',execution_note:'raw backend note'}}}/>);
 expect(screen.getByText('未调用模型：资金、仓位或股数限制使本次无法下单。')).toBeTruthy();
 expect(screen.getByText(/模型未调用/)).toBeTruthy();
 expect(screen.queryByText('raw backend note')).toBeNull();
});
