import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import App, { Curve } from "./App";
import savedResult from '../../examples/cup-handle/result.json';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

test("a chart without benchmark data does not advertise a benchmark", () => {
  render(<Curve curve={[{ date: "2024-01-02", equity: 100000 }]} />);
  expect(screen.getByText("模拟账户")).toBeTruthy();
  expect(screen.queryByText("等权买入持有 · 价格收益、不含股息")).toBeNull();
});

function mockAPI() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        defaults: {
          symbols: ["AAPL"],
          start: "2024-01-02",
          end: "2026-11-10",
          capital: 100000,
          strategy: {
            name: "Cup",
            method: "Approved rules",
            volume_multiple: 1.2,
          },
          provider: "openai",
          model: "gpt-6-luna",
          mode: "baseline",
        },
        providers: [
          {
            id: "openai",
            label: "OpenAI",
            configured: false,
            env: "OPENAI_API_KEY",
            images: true,
          },
          {
            id: "qwen",
            label: "通义千问 Qwen",
            configured: false,
            env: "DASHSCOPE_API_KEY",
            images: true,
          },
        ],
        runs: [],
      }),
    })),
  );
}

test("home explains product without claiming fake performance", async () => {
  mockAPI();
  render(<App />);
  expect(await screen.findByText(/Your method/)).toBeTruthy();
  expect(screen.getByText(/Made testable/)).toBeTruthy();
  expect(screen.queryByText(/\+32.8%/)).toBeNull();
  expect(screen.getByRole("button", { name: "查看本地示范" }).hasAttribute("disabled")).toBe(true);
  expect(screen.queryByText(/首次查看会运行免费纯数值对照/)).toBeNull();
});

test.each(['zh-CN','en'])('%s model catalog keeps setup and compatibility without internal observation status', async (language) => {
  mockAPI();
  localStorage.setItem('sal.language',language);
  const original=fetch;
  vi.stubGlobal('fetch',vi.fn(async(path:any,options:any)=>{
    const response=await original(path,options);
    const body=await response.json();
    return {...response,json:async()=>({...body,providers:body.providers.map((provider:any)=>({...provider,observed_models:provider.id==='openai'?['internal-observation-model']:[],images:provider.id==='openai'}))})};
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole('button',{name:language==='en'?'Model connections':'模型连接'}));
  expect(await screen.findByText(language==='en'?'Qwen':'通义千问 Qwen')).toBeTruthy();
  expect(screen.getByText("DASHSCOPE_API_KEY")).toBeTruthy();
  expect(document.querySelector('input[type="password"]')).toBeNull();
  expect(screen.getByText(language==='en'?'Image request supported · select a vision model':'可构造图片请求 · 需选择视觉型号')).toBeTruthy();
  expect(screen.getByText(language==='en'?'Text-only adapter · images are never silently dropped':'当前接口仅文本 · 不静默丢弃图片')).toBeTruthy();
  expect(screen.queryByText(/尚未实测|已有真实调用记录|offline tests implemented|provider responses observed|availability unverified/i)).toBeNull();
  expect(screen.queryByText(/internal-observation-model/)).toBeNull();
});

test.each([
  {language:'zh-CN',open:'查看本地示范',notice:'历史归档：结果按运行时的原始规则保存，后续规则变更不会改写此结果。',copy:'复制历史归档',provenance:'归档结果副本，未经重新计算'},
  {language:'en',open:'Explore local demo',notice:'Archived result: saved under the original rules used for this run. Later rule changes do not alter this result.',copy:'Copy archived result',provenance:'Copy of the archived result; not recalculated'},
])('$language archived result explains original rules without development or paid-rerun history',async({language,open,notice,copy,provenance})=>{
  mockAPI();
  const bootstrap=await (await fetch('/api/bootstrap')).json();
  const archived={id:'archive-fixture',status:'completed',archived:true,archive_replay:true,data_id:'saved-data',strategy_id:'saved-strategy',config:{...bootstrap.defaults,mode:'live'},summary:savedResult.summary,state:{day:0,account:{positions:{},curve:[]},decisions:[]}};
  const requests=vi.fn(async(path:string)=>({ok:true,json:async()=>path==='/api/bootstrap'?{...bootstrap,showcase:{run_id:archived.id},runs:[archived]}:archived}));
  vi.stubGlobal('fetch',requests);
  localStorage.setItem('sal.language',language);
  const {container}=render(<App/>);
  fireEvent.click(await screen.findByRole('button',{name:open}));
  expect(await screen.findByText(notice)).toBeTruthy();
  expect(screen.getByRole('button',{name:copy})).toBeTruthy();
  expect(screen.getByText(new RegExp(provenance))).toBeTruthy();
  expect(container.textContent).not.toMatch(/付费重跑|新版验收|新引擎|paid rerun|current-version acceptance|new engine/i);
  expect(requests.mock.calls.map(([path])=>path)).toEqual(['/api/bootstrap','/api/runs/archive-fixture']);
});

test("new run starts as free numeric baseline and requires approval", async () => {
  mockAPI();
  render(<App />);
  await screen.findByText(/Your method/);
  fireEvent.click(screen.getByRole("button", { name: "新建研究" }));
  expect(await screen.findByText(/方法与规则/)).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/尚未实测|离线协议测试|任意策略生成尚未实现/);
  expect(
    screen
      .getByRole("button", { name: /开始本地运行/ })
      .hasAttribute("disabled"),
  ).toBe(true);
});

test("home prefers the designated model showcase rather than a newer baseline", async () => {
  mockAPI();
  const original = fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: any, options: any) => {
      const response = await original(path, options);
      const body = await response.json();
      return {
        ...response,
        json: async () => ({
          ...body,
          showcase: { run_id: "real-demo" },
          numeric_showcase: { run_id: "new-baseline" },
          runs: [
            {
              id: "new-baseline",
              status: "completed",
              config: { mode: "baseline" },
            },
            { id: "real-demo", status: "completed", config: { mode: "live" } },
          ],
        }),
      };
    }),
  );
  render(<App />);
  await screen.findByText(/Your method/);
  expect(
    screen.getByText("读取已完成的真实模型研究，不会重新调用 API"),
  ).toBeTruthy();
  expect(screen.queryByText(/当前还没有真实 LLM 示范结果/)).toBeNull();
  expect(screen.queryByText(/旧版真实 Luna/)).toBeNull();
  expect(screen.queryByText(/尚未进行 LLM 复核/)).toBeNull();
});

test("language switch translates navigation, setup and providers and survives remount", async () => {
  mockAPI();
  const first = render(<App />);
  await screen.findByText(/Your method/);
  fireEvent.change(screen.getByRole("combobox", { name: "界面语言" }), {
    target: { value: "en" },
  });
  expect(
    await screen.findByRole("button", { name: "New research" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Model connections" }));
  expect(await screen.findByText("Qwen")).toBeTruthy();
  expect(screen.getAllByText("Credentials not configured").length).toBe(2);
  expect(document.documentElement.lang).toBe("en");
  first.unmount();
  render(<App />);
  await screen.findByRole("button", { name: "New research" });
  fireEvent.click(screen.getByRole("button", { name: "New research" }));
  expect(await screen.findByText("Method & rules")).toBeTruthy();
  expect(localStorage.getItem("sal.language")).toBe("en");
});

test('setup offers expanded provider-verified instruments rather than a hardcoded five',async()=>{
 mockAPI();const original=fetch;
 vi.stubGlobal('fetch',vi.fn(async(path:any,options:any)=>{const r=await original(path,options);const b=await r.json();return {...r,json:async()=>({...b,universe:[{symbol:'AAPL',name:'Apple',kind:'stock'},{symbol:'NVDA',name:'NVIDIA',kind:'stock'}]})};}));
 render(<App/>);await screen.findByText(/Your method/);
 fireEvent.click(screen.getByRole('button',{name:'新建研究'}));
 expect(await screen.findByRole('button',{name:'NVDA'})).toBeTruthy();
});
