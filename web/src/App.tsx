import { useEffect, useState } from "react";
import { useLanguage, type Language } from "./i18n";
import { CandidateInspection, PositionTable, ReferenceSources, ExitReason } from './Inspection';
import {
  ArrowUpRight,
  ArrowRight,
  Activity,
  FlaskConical,
  LayoutDashboard,
  Network,
  Plus,
  ShieldCheck,
  Play,
  Pause,
  RotateCcw,
  ChevronRight,
  Check,
  Circle,
  X,
  GitCompareArrows,
  Terminal,
  Eye,
} from "lucide-react";

type Obj = Record<string, any>;
type Page = "home" | "new" | "runs" | "models" | "result";
const names: Obj = {
  baseline: "纯数值对照",
  live: "模型研究",
  replay: "离线回放",
  ready: "等待开始",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  pass: "通过",
  fail: "未通过",
  insufficient_evidence: "证据不足",
};
const usd = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(n || 0);
const pct = (n: number) =>
  `${n >= 0 ? "+" : ""}${((n || 0) * 100).toFixed(2)}%`;
async function api(path: string, body?: Obj) {
  const r = await fetch(
    "/api" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Lab-Request": "1" },
          body: JSON.stringify(body),
        },
  );
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "参数无效，请检查日期、数值及模型配置。",
    );
  return data;
}

export function Curve({
  curve,
  benchmark = [],
}: {
  curve: Obj[];
  benchmark?: Obj[];
}) {
  const { t } = useLanguage();
  if (!curve.length)
    return (
      <div className="empty chart-empty">
        <Activity size={24} />
        <p>{t("运行后，在这里查看真实的账户曲线。")}</p>
      </div>
    );
  const all = [...curve, ...benchmark].map((x) => x.equity),
    low = Math.min(...all) * 0.98,
    high = Math.max(...all) * 1.02;
  const path = (rows: Obj[]) =>
    rows
      .map(
        (p, i) =>
          `${i ? "L" : "M"}${58 + (i / Math.max(1, rows.length - 1)) * 830},${220 - ((p.equity - low) / (high - low)) * 180}`,
      )
      .join(" ");
  return (
    <div className="curve">
      <svg
        viewBox="0 0 920 270"
        role="img"
        aria-label={t("模拟账户与等权价格收益基准曲线")}
      >
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line
              x1="58"
              x2="888"
              y1={40 + i * 60}
              y2={40 + i * 60}
              stroke="#dfe4da"
              strokeDasharray="3 5"
            />
            <text x="0" y={44 + i * 60} fill="#7e887c" fontSize="11">
              {Math.round((high - ((high - low) * i) / 3) / 1000)}k
            </text>
          </g>
        ))}
        {benchmark.length > 0 && (
          <path
            d={path(benchmark)}
            fill="none"
            stroke="#b0b8a4"
            strokeWidth="1.8"
            strokeDasharray="5 4"
          />
        )}
        <path
          d={path(curve)}
          fill="none"
          stroke="#17694f"
          strokeWidth="2.8"
          strokeLinejoin="round"
        />
        <text x="58" y="252" fontSize="11" fill="#7e887c">
          {curve[0].date}
        </text>
        <text x="888" y="252" textAnchor="end" fontSize="11" fill="#7e887c">
          {curve.at(-1)?.date}
        </text>
      </svg>
      <div className="legend">
        <span>
          <i />
          {t("模拟账户")}
        </span>
        {benchmark.length > 0 && (
          <span>
            <i className="benchmark" />
            {t("等权买入持有 · 价格收益、不含股息")}
          </span>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const { language, setLanguage, t } = useLanguage();
  useEffect(() => {
    document.documentElement.lang = language;
    document.title =
      language === "en"
        ? "Strategy Agent Lab · Investment method research"
        : "Strategy Agent Lab · 投资方法研究工作台";
  }, [language]);
  const [page, setPage] = useState<Page>("home"),
    [boot, setBoot] = useState<Obj | null>(null),
    [runs, setRuns] = useState<Obj[]>([]);
  const [config, setConfig] = useState<Obj | null>(null),
    [run, setRun] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [preflight, setPreflight] = useState<Obj | null>(null),
    [selected, setSelected] = useState<Obj | null>(null),
    [context, setContext] = useState<Obj | null>(null),
    [raw, setRaw] = useState<Obj[]>([]);
  const [tab, setTab] = useState("decisions"),
    [compare, setCompare] = useState<string[]>([]),
    [comparison, setComparison] = useState<Obj[]>([]);
  useEffect(() => {
    api("/bootstrap")
      .then((b) => {
        setBoot(b);
        setConfig({ ...b.defaults, approved: false, paid_authorized: false });
        setRuns(b.runs);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (page !== "result" || !run) return;
    let active = true;
    const refresh = async () => {
      try {
        const r = await api("/runs/" + run.id);
        if (active) setRun(r);
      } catch (e) {
        if (active) setError(String(e));
      }
    };
    const timer = setInterval(refresh, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [page, run?.id]);
  useEffect(() => {
    setContext(null);
    if (!run || !selected) return;
    let active = true;
    api(`/runs/${run.id}/context/${selected.symbol}/${selected.date}`)
      .then((c) => {
        if (active) setContext(c);
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [run?.id, selected?.id]);
  async function action(fn: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function openRun(id: string) {
    const r = await api("/runs/" + id);
    setRun(r);
    setPage("result");
    setSelected(r.state?.decisions?.find((d: Obj) => d.order_id) || null);
    setTab("decisions");
  }
  function update(v: Obj) {
    if ("provider" in v || "model" in v) {
      const provider = v.provider ?? config?.provider;
      const model = v.model ?? config?.model;
      const luna = provider === "openai" && model === "gpt-6-luna";
      v = {
        ...v,
        pricing_confirmed: false,
        capabilities_confirmed: false,
        input_rate: luna ? boot?.defaults.input_rate : 0,
        output_rate: luna ? boot?.defaults.output_rate : 0,
        price_note: luna
          ? boot?.defaults.price_note
          : t("请填写账户地区及 USD 等值单价来源"),
      };
    } else {
      if ("input_rate" in v || "output_rate" in v || "price_note" in v)
        v.pricing_confirmed = false;
      if ("use_images" in v || "use_tools" in v)
        v.capabilities_confirmed = false;
    }
    setConfig((c: Obj | null) => ({ ...c, ...v }));
    setPreflight(null);
  }
  function strategy(k: string, v: string | number) {
    setConfig((c: Obj | null) => ({
      ...c,
      strategy: { ...c?.strategy, [k]: v },
      approved: false,
    }));
    setPreflight(null);
  }
  async function refreshRuns() {
    setRuns(await api("/runs"));
  }
  async function navigate(p: Page) {
    setPage(p);
    if (p === "runs") await action(refreshRuns);
  }
  const latest =
      runs.find(
        (r) => r.id === boot?.showcase?.run_id && r.status === "completed" && r.config.mode === "live",
      ),
    account = run?.state?.account,
    decisions: Obj[] = run?.state?.decisions || [];
  const steps = [
    [
      "01",
      t("描述你的方法"),
      t("明确入场、退出与风险条件，保留需要经验判断的部分。"),
    ],
    [
      "02",
      t("交给程序与 AI"),
      t("程序计算数值，模型按你的标准判断形态，共用一个模拟账户。"),
    ],
    [
      "03",
      t("看结果，也看过程"),
      t("从账户曲线回到每一笔交易、判断依据与当时可见的信息。"),
    ],
  ];
  return (
    <div className="app">
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => setPage("home")}
          aria-label={t("返回首页")}
        >
          <span className="brand-icon">
            s<span>∕</span>a
          </span>
          <span>
            strategy
            <br />
            <b>agent lab</b>
          </span>
        </button>
        <div className="nav-label">RESEARCH WORKSPACE</div>
        <nav aria-label={t("主导航")}>
          {(
            [
              ["home", LayoutDashboard, t("概览")],
              ["new", Plus, t("新建研究")],
              ["runs", FlaskConical, t("研究记录")],
              ["models", Network, t("模型连接")],
            ] as const
          ).map(([id, Icon, label]) => (
            <button
              className={page === id ? "active" : ""}
              key={id}
              onClick={() => navigate(id)}
            >
              <Icon size={17} />
              {label}
              {page === id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="local-dot" />
          LOCAL WORKSPACE
          <div>
            {t("仅在这台电脑运行")}
            <br />
            {t("尚未发布 · 未连接实盘")}
          </div>
          <span className="tiny">v0.1 · development preview</span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>
            {t("研究工作台")}
            <ChevronRight size={13} />{" "}
            <b>
              {
                {
                  home: t("概览"),
                  new: t("新建研究"),
                  runs: t("研究记录"),
                  models: t("模型连接"),
                  result: t("研究详情"),
                }[page]
              }
            </b>
          </span>
          <div className="topbar-actions">
            <select
              className="language-select"
              aria-label={t("界面语言")}
              value={language}
              onChange={(e) => setLanguage(e.target.value as Language)}
            >
              <option value="zh-CN">中文</option>
              <option value="en">English</option>
            </select>
            <span className="local-tag">
              <ShieldCheck size={14} />
              {t("本地优先 · 数据由你掌握")}
            </span>
          </div>
        </header>
        <main>
          {error && (
            <div role="alert" className="error">
              <span>{t(error)}</span>
              <button onClick={() => setError("")} aria-label={t("关闭错误")}>
                <X size={16} />
              </button>
            </div>
          )}
          {!boot && !error && (
            <div className="empty">{t("正在连接本地工作台…")}</div>
          )}
          {page === "home" && (
            <>
              <section className="hero">
                <div className="eyebrow">
                  <span /> YOUR RULES. CODE + AI.
                </div>
                <h1>
                  Your method.
                  <br />
                  <em>Made testable.</em>
                </h1>
                <p className="hero-copy">
                  {t("把投资方法，变成可以检验的交易过程。")}
                  <br />
                  {t("让程序处理数值，让 AI 按你的标准判断，")}
                  <br className="mobile-hide" />
                  {t("在历史行情里走完一次完整的模拟。")}
                </p>
                <div className="hero-actions">
                  <button className="primary" onClick={() => setPage("new")}>
                    {t("开始一项研究")}
                    <ArrowUpRight size={18} />
                  </button>
                  <button
                    className="text-button"
                    disabled={busy || !latest}
                    onClick={() =>
                      action(async () => {
                        if (latest) await openRun(latest.id);
                      })
                    }
                  >
                    {t("查看本地示范")}
                    <ArrowRight size={16} />
                  </button>
                </div>
                <div className="hero-note">
                  {latest
                    ? t("读取已完成的真实模型研究，不会重新调用 API")
                    : t("本机尚无已保存的模型示范；可以先新建研究。")}
                </div>
                <div
                  className="hero-art"
                  aria-label={t("人机协同工作流示意，不是回测结果")}
                >
                  <div className="orbit o1" />
                  <div className="orbit o2" />
                  <div className="orbital-caption">
                    METHOD → EVIDENCE → ACTION
                  </div>
                  <div className="method-slip">
                    <span>YOUR METHOD</span>
                    <b>{t("杯柄突破")}</b>
                    <small>{t("量价规则 + 形态判断")}</small>
                    <div className="slip-line" />
                    <div className="slip-line short" />
                  </div>
                  <div className="code-slip">
                    <Terminal size={16} />
                    <span>PROGRAM</span>
                    <b>{t("数值筛选 · 风险控制")}</b>
                    <div className="signal-dots">
                      {[1, 2, 3, 4, 5, 6, 7, 8].map((x) => (
                        <i key={x} style={{ height: 8 + (x % 3) * 10 }} />
                      ))}
                    </div>
                  </div>
                  <div className="ai-slip">
                    <div className="spark">✳</div>
                    <span>AI JUDGMENT</span>
                    <b>{t("按方法判断，而非自由预测")}</b>
                    <small>{t("图表 · 规则 · 可追溯依据")}</small>
                  </div>
                  <div className="artifact-note">
                    {t("工作流示意 · 非模型运行结果")}
                  </div>
                </div>
              </section>
              <section className="workflow">
                <div className="section-heading">
                  <span className="eyebrow">FROM IDEA TO INSPECTION</span>
                  <h2>{t("不只是一条收益曲线。")}</h2>
                  <p>{t("你的方法贯穿始终，每个判断都有来路。")}</p>
                </div>
                <div className="steps">
                  {steps.map(([n, t, c]) => (
                    <article key={n}>
                      <span className="step-no">{n}</span>
                      <h3>{t}</h3>
                      <p>{c}</p>
                    </article>
                  ))}
                </div>
              </section>
              <section className="demo-strip">
                <div>
                  <span className="eyebrow">FIRST METHOD</span>
                  <h2>{t("杯柄突破 / Cup & Handle")}</h2>
                  <p>{t("美股日线 · 主流股票与 ETF · 一个共享模拟账户")}</p>
                  <small>
                    {boot?.showcase
                      ? t(
                            "真实 LLM 示范：从固定候选、模型判断到模拟交易与逐笔复核。",
                        )
                      : t(
                          "面向演示调参，不代表策略泛化或未来投资表现。当前还没有真实 LLM 示范结果。",
                        )}
                  </small>
                </div>
                <button className="outline" onClick={() => setPage("new")}>
                  {t("探索示范方法")}
                  <ArrowUpRight size={17} />
                </button>
              </section>
              <footer>
                <span>STRATEGY AGENT LAB</span>
                <span>Research, not promises.</span>
                <span>{t("本地开发版本 · GitHub 与网站暂未发布")}</span>
              </footer>
            </>
          )}
          {page === "new" && config && (
            <>
              <div className="page-heading">
                <div className="eyebrow">NEW EXPERIMENT</div>
                <h1>{t("让方法开始接受检验。")}</h1>
                <p>{t("先确认规则，再冻结输入。每次运行都保留独立版本。")}</p>
              </div>
              <div className="setup-grid">
                <div>
                  <section className="panel">
                    <div className="panel-title">
                      <span className="number">01</span>
                      <h2>{t("方法与规则")}</h2>
                      <span className="pill">{t("杯柄突破模板")}</span>
                    </div>
                    <label>
                      {t("研究名称")}
                      <input
                        value={config.strategy.name}
                        onChange={(e) => strategy("name", e.target.value)}
                      />
                    </label>
                    <label>
                      {t("交给 AI 的形态判断标准")}
                      <textarea
                        rows={5}
                        value={config.strategy.method}
                        onChange={(e) => strategy("method", e.target.value)}
                      />
                    </label>
                    <p className="help">
                      {t(
                        "这里设置杯柄参考流程的形态判断标准；如需创建或修改策略程序，请使用项目工作台。",
                      )}
                    </p>
                    <div className="responsibilities">
                      <div>
                        <Terminal size={17} />
                        <b>{t("程序负责")}</b>
                        <p>
                          {t(
                            "趋势与放量筛选、价格/位置校验、仓位、风险及账户记账",
                          )}
                        </p>
                      </div>
                      <div>
                        <Eye size={17} />
                        <b>{t("AI 负责")}</b>
                        <p>
                          {t(
                            "圆弧杯体、上沿浅柄、整体连贯性；依据不足可以拒绝判断",
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="fields three">
                      {[
                        ["volume_multiple", t("突破量比")],
                        ["cup_min", t("杯体最短天数")],
                        ["prior_advance", t("前期涨幅下限")],
                      ].map(([k, label]) => (
                        <label key={k}>
                          {label}
                          <input
                            type="number"
                            step="any"
                            value={config.strategy[k] ?? ""}
                            onChange={(e) =>
                              strategy(k, Number(e.target.value))
                            }
                          />
                        </label>
                      ))}
                    </div>
                    <details>
                      <summary>{t("其余交易与风险参数")}</summary>
                      <div className="fields three">
                        {Object.entries(config.strategy)
                          .filter(
                            ([k]) =>
                              ![
                                "name",
                                "version",
                                "entry_priority",
                                "method",
                                "volume_multiple",
                                "cup_min",
                                "prior_advance",
                              ].includes(k),
                          )
                          .map(([k, v]) => (
                            <label key={k}>
                              {{
                                cup_max: t("杯体最长天数"),
                                handle_min: t("柄最短天数"),
                                handle_max: t("柄最长天数"),
                                depth_min: t("杯深下限"),
                                depth_max: t("杯深上限"),
                                risk_fraction: t("每笔计划风险比例"),
                                max_weight: t("单标的入场比例上限"),
                                max_positions: t("最大持仓与待入场数"),
                                history_window: t("可见行情天数"),
                                trend_period: t("趋势均线天数"),
                                trend_slope_sessions: t("均线比较间隔"),
                                trend_buffer:t("收盘相对均线缓冲"),
                                trend_slope_min:t("均线变化下限"),
                                breakout_buffer:t("突破确认缓冲"),
                                breakout_lookback: t("突破回看天数"),
                                volume_lookback: t("均量回看天数"),
                                prior_advance_lookback: t("前期涨幅回看天数"),
                                rim_tolerance: t("杯沿高度差上限"),
                                handle_midpoint_fraction: t("柄低相对杯深下限"),
                                handle_max_drop: t("柄部回撤上限"),
                                max_breakout_extension: t("突破延伸上限"),
                                entry_gap_limit: t("下一开盘买入余量"),
                                max_candidates: t("每次最多形态数"),
                                candidate_overlap: t("去重重叠比例"),
                                bottom_merge_sessions: t("杯底合并间隔"),
                                volatility_period: t("波动单位回看天数"),
                                target_multiple: t("目标位杯体高度倍数"),
                                progress_units: t("有效进展所需波动单位"),
                                stagnation_sessions: t("连续未进展退出天数"),
                                trailing_stop_units:t("跟踪止损波动倍数（0关闭）"),
                                priority_lookback:t("信号优先级回看天数"),
                                commission: t("单边手续费率"),
                                slippage: t("单边滑点率"),
                              }[k] || k}
                              <input
                                type="number"
                                step="any"
                                value={String(v)}
                                onChange={(e) =>
                                  strategy(k, Number(e.target.value))
                                }
                              />
                            </label>
                          ))}
                      </div>
                      <label>{t("同日信号优先级")}<select value={config.strategy.entry_priority||'alphabetical'} onChange={e=>strategy('entry_priority',e.target.value)}>
                        <option value="alphabetical">{t("代码顺序")}</option><option value="momentum">{t("近期动量")}</option><option value="breakout_strength">{t("突破强度")}</option>
                      </select></label>
                      <p className="help">{t("未进展退出天数设为0可关闭；趋势、突破和前期涨幅允许合理负阈值，量比可低于1。")}</p>
                    </details>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={config.approved}
                        onChange={(e) => update({ approved: e.target.checked })}
                      />
                      {t("我确认上述方法与参数，保存为本次研究的策略版本。")}
                    </label>
                  </section>
                  <section className="panel">
                    <div className="panel-title">
                      <span className="number">02</span>
                      <h2>{t("历史数据与账户")}</h2>
                      <span className="pill">{t("已冻结行情")}</span>
                    </div>
                    <button className="outline" onClick={()=>update({symbols:(boot?.universe||[]).map((u:Obj)=>u.symbol)})}>{t("选择全部标的")}</button>
                    <div className="ticker-options">
                      {(boot?.universe?.map((u:Obj)=>u.symbol)||["AAPL", "MSFT", "AMZN", "QQQ", "SPY"]).map((s:string) => (
                        <button
                          key={s}
                          className={config.symbols.includes(s) ? "chosen" : ""}
                          onClick={() =>
                            update({
                              symbols: config.symbols.includes(s)
                                ? config.symbols.filter((x: string) => x !== s)
                                : [...config.symbols, s],
                            })
                          }
                        >
                          {config.symbols.includes(s) && <Check size={12} />}{" "}
                          {s}
                        </button>
                      ))}
                    </div>
                    <div className="fields three">
                      <label>
                        {t("开始日期")}
                        <input
                          type="date"
                          value={config.start}
                          onChange={(e) => update({ start: e.target.value })}
                        />
                      </label>
                      <label>
                        {t("结束日期")}
                        <input
                          type="date"
                          value={config.end}
                          onChange={(e) => update({ end: e.target.value })}
                        />
                      </label>
                      <label>
                        {t("初始资金 / USD")}
                        <input
                          type="number"
                          min="100"
                          value={config.capital}
                          onChange={(e) =>
                            update({ capital: Number(e.target.value) })
                          }
                        />
                      </label>
                    </div>
                    <p className="help">
                      {t(
                        "起止日期需为交易日。日频、只做多、不加仓；次日开盘模拟成交。原始 OHLC 价格收益，不含现金股息；区间内拆股会拒绝运行。数据快照不等于历史时点数据档案。",
                      )}
                    </p>
                  </section>
                  <section className="panel">
                    <div className="panel-title">
                      <span className="number">03</span>
                      <h2>{t("执行方案")}</h2>
                    </div>
                    <div className="mode-options">
                      {[
                        [
                          "baseline",
                          t("纯数值对照"),
                          t("免费 · 不调用模型，仅检验数值规则与账户流程"),
                        ],
                        [
                          "live",
                          t("真实模型研究"),
                          t("按方法判断形态 · 消耗你自己的 API 额度"),
                        ],
                      ].map(([value, title, note]) => (
                        <button
                          className={config.mode === value ? "chosen" : ""}
                          key={value}
                          onClick={() =>
                            update({ mode: value, paid_authorized: false })
                          }
                        >
                          <span>
                            {config.mode === value ? (
                              <Check size={15} />
                            ) : (
                              <Circle size={15} />
                            )}
                            <b>{title}</b>
                          </span>
                          <small>{note}</small>
                        </button>
                      ))}
                    </div>
                    {config.mode === "live" && (
                      <>
                        <div className="fields two">
                          <label>
                            {t("供应商")}
                            <select
                              value={config.provider}
                              onChange={(e) =>
                                update({
                                  provider: e.target.value,
                                  model:
                                    e.target.value === "openai"
                                      ? "gpt-6-luna"
                                      : "",
                                  paid_authorized: false,
                                  price_note:
                                    e.target.value === "openai"
                                      ? boot!.defaults.price_note
                                      : t("请填写账户地区及 USD 等值单价来源"),
                                })
                              }
                            >
                              {boot!.providers.map((p: Obj) => (
                                <option key={p.id} value={p.id}>
                                  {t(p.label)}{" "}
                                  {p.configured
                                    ? t("· 已配置")
                                    : t("· 未配置凭据")}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            {t("模型 / 部署 ID")}
                            <input
                              value={config.model}
                              onChange={(e) =>
                                update({ model: e.target.value })
                              }
                            />
                          </label>
                        </div>
                        <p className="help">
                          {t(
                            "请选择支持所需图片与工具能力的模型；不会自动切换供应商。",
                          )}
                        </p>
                        <div className="fields three">
                          <label>
                            {t("预算估算 / USD")}
                            <input
                              type="number"
                              step=".01"
                              value={config.budget_usd}
                              onChange={(e) =>
                                update({ budget_usd: Number(e.target.value) })
                              }
                            />
                          </label>
                          <label>
                            {t("最多请求次数")}
                            <input
                              type="number"
                              value={config.max_requests}
                              onChange={(e) =>
                                update({ max_requests: Number(e.target.value) })
                              }
                            />
                          </label>
                          <label>
                            {t("单次输出 token 上限")}
                            <input
                              type="number"
                              value={config.max_output_tokens}
                              onChange={(e) =>
                                update({
                                  max_output_tokens: Number(e.target.value),
                                })
                              }
                            />
                          </label>
                        </div>
                        <details>
                          <summary>{t("计价与输入能力")}</summary>
                          <div className="fields two">
                            <label>
                              {t("每百万输入 token / USD")}
                              <input
                                type="number"
                                step="any"
                                value={config.input_rate}
                                onChange={(e) =>
                                  update({ input_rate: Number(e.target.value) })
                                }
                              />
                            </label>
                            <label>
                              {t("每百万输出 token / USD")}
                              <input
                                type="number"
                                step="any"
                                value={config.output_rate}
                                onChange={(e) =>
                                  update({
                                    output_rate: Number(e.target.value),
                                  })
                                }
                              />
                            </label>
                          </div>
                          <label>
                            {t("单价来源 / 币种换算说明")}
                            <input
                              value={config.price_note}
                              onChange={(e) =>
                                update({ price_note: e.target.value })
                              }
                            />
                          </label>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={config.use_images}
                              onChange={(e) =>
                                update({ use_images: e.target.checked })
                              }
                            />
                            {t("发送当时可见的蜡烛图（需要视觉型号）")}
                          </label>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={config.use_tools}
                              onChange={(e) =>
                                update({ use_tools: e.target.checked })
                              }
                            />
                            {t("每阶段允许一次候选局部图 / 行情工具调用")}
                          </label>
                          <label className="checkbox"><input type="checkbox" checked={!!config.review_enabled} onChange={e=>update({review_enabled:e.target.checked})}/>{t("对未通过或证据不足的候选进行一次针对性复核")}</label>
                          <p className="help">{t("主判断与复核各最多两次正常请求加一次修复；每标的日期最多六次，仍受总预算与请求数限制。")}</p>
                        </details>
                        {!(
                          config.provider === "openai" &&
                          config.model === "gpt-6-luna"
                        ) && (
                          <>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={!!config.pricing_confirmed}
                                onChange={(e) =>
                                  update({
                                    pricing_confirmed: e.target.checked,
                                  })
                                }
                              />
                              {t("我已核对所选模型的 USD 等值单价与来源。")}
                            </label>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={!!config.capabilities_confirmed}
                                onChange={(e) =>
                                  update({
                                    capabilities_confirmed: e.target.checked,
                                  })
                                }
                              />
                              {t("我确认该具体型号支持所选的图片及工具能力。")}
                            </label>
                          </>
                        )}
                        <div className="notice">
                          {t(
                            "请求数严格限制；美元预算按保守估算预留，并非供应商账单保证。缓存、区域附加费及各家计费差异需要实测。非 OpenAI 型号请自行确认并填写单价。",
                          )}
                        </div>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={config.paid_authorized}
                            onChange={(e) =>
                              update({ paid_authorized: e.target.checked })
                            }
                          />
                          {t(
                            "我同意本次使用自己的 API 额度；数据和方法将发送给选定供应商。",
                          )}
                        </label>
                      </>
                    )}
                  </section>
                </div>
                <aside className="setup-summary">
                  <div className="eyebrow">RESEARCH SNAPSHOT</div>
                  <h3>{t("一次可复核的实验")}</h3>
                  <dl>
                    <dt>{t("方法")}</dt>
                    <dd>{t("杯柄突破 · 可编辑参数")}</dd>
                    <dt>{t("标的")}</dt>
                    <dd>{config.symbols.join(" / ") || t("请选择标的")}</dd>
                    <dt>{t("区间")}</dt>
                    <dd>
                      {config.start}
                      <br />
                      {config.end}
                    </dd>
                    <dt>{t("账户")}</dt>
                    <dd>
                      {usd(config.capital)} {t("· 共享资金")}
                    </dd>
                    <dt>{t("方案")}</dt>
                    <dd>{t(names[config.mode])}</dd>
                  </dl>
                  <button
                    className="outline"
                    disabled={busy}
                    onClick={() =>
                      action(async () =>
                        setPreflight(await api("/preflight", config)),
                      )
                    }
                  >
                    {t("检查数据与候选机会")}
                    <ArrowRight size={15} />
                  </button>
                  {preflight && (
                    <div className="preflight">
                      <strong>{preflight.numeric_dates}</strong>
                      <span>{t("日期具备数值可行的位置组合")}</span>
                      <small>
                        {t("突破候选")}
                        {preflight.candidates}{" "}
                        {t("个；不是模型通过数或交易数。")}
                      </small>
                      <details>
                        <summary>{t("查看候选日期")}</summary>
                        {preflight.rows.map((r: Obj) => (
                          <div
                            className="candidate-row"
                            key={r.symbol + r.date}
                          >
                            {r.symbol} · {r.date}
                            <b>{r.pairs > 0 ? t("可行") : t("不满足")}</b>
                          </div>
                        ))}
                      </details>
                    </div>
                  )}
                  <button
                    className="primary full"
                    disabled={
                      busy ||
                      !config.approved ||
                      (config.mode === "live" &&
                        (!config.paid_authorized ||
                          (!(
                            config.provider === "openai" &&
                            config.model === "gpt-6-luna"
                          ) &&
                            (!config.pricing_confirmed ||
                              !config.capabilities_confirmed))))
                    }
                    onClick={() =>
                      action(async () => {
                        const r = await api("/runs", config);
                        await openRun(r.id);
                        await refreshRuns();
                      })
                    }
                  >
                    {busy ? t("处理中…") : t("开始本地运行")}
                    <Play size={15} />
                  </button>
                  <p className="help">
                    {t(
                      "没有实盘下单。当前方法由演示需求调参，不构成盈利证明。",
                    )}
                  </p>
                </aside>
              </div>
            </>
          )}
          {page === "models" && (
            <>
              <div className="page-heading">
                <div className="eyebrow">MODEL CONNECTIONS</div>
                <h1>{t("同一套规则，不同的模型。")}</h1>
                <p>
                  {t(
                    "国内外接口独立配置。只在你主动运行研究时调用，不自动切换、不共享密钥。",
                  )}
                </p>
              </div>
              <div className="provider-grid">
                {boot?.providers.map((p: Obj) => (
                  <article className="panel provider" key={p.id}>
                    <div className="provider-top">
                      <span className="provider-mark">
                        {t(p.label).slice(0, 1)}
                      </span>
                      <span
                        className={"pill " + (p.configured ? "positive" : "")}
                      >
                        {p.configured ? t("凭据已配置") : t("未配置凭据")}
                      </span>
                    </div>
                    <h2>{t(p.label)}</h2>
                    <span className="subtle">
                      {p.protocol === "chat"
                        ? "OpenAI-compatible Chat"
                        : p.protocol === "responses"
                          ? "Responses API"
                          : p.protocol === "messages"
                            ? "Messages API"
                            : "generateContent"}
                    </span>
                    <code>{p.env}</code>
                    <div className="provider-cap">
                      {p.images
                        ? t("可构造图片请求 · 需选择视觉型号")
                        : t("当前接口仅文本 · 不静默丢弃图片")}
                    </div>
                  </article>
                ))}
              </div>
              <div className="notice">
                <ShieldCheck size={19} />
                <div>
                  <b>{t("密钥只在本机后端读取。")}</b>
                  <p>
                    {t(
                      "在项目根目录的私有 .env 中配置对应环境变量，再重启服务。浏览器不收集、不保存 API Key，也不会读取旧项目的密钥。请参考 .env.example；千问可设置 QWEN_BASE_URL 为账户控制台中的官方地域地址。",
                    )}
                  </p>
                </div>
              </div>
            </>
          )}
          {page === "runs" && (
            <>
              <div className="page-heading split">
                <div>
                  <div className="eyebrow">EXPERIMENT LIBRARY</div>
                  <h1>{t("每一次研究，都留下依据。")}</h1>
                  <p>
                    {t(
                      "运行版本不会覆盖。选择两次记录，可以并排比较结果与费用。",
                    )}
                  </p>
                </div>
                <button className="primary" onClick={() => setPage("new")}>
                  {t("新建研究")}
                  <Plus size={17} />
                </button>
              </div>
              {!runs.length ? (
                <div className="panel empty">
                  <FlaskConical size={32} />
                  <h3>{t("还没有研究记录")}</h3>
                  <p>
                    {t(
                      "先运行免费纯数值对照，或配置 Luna 后创建真实模型研究。",
                    )}
                  </p>
                  <button className="outline" onClick={() => setPage("new")}>
                    {t("创建第一项研究")}
                  </button>
                </div>
              ) : (
                <>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t("对照")}</th>
                          <th>{t("研究 / 版本")}</th>
                          <th>{t("方案")}</th>
                          <th>{t("区间")}</th>
                          <th>{t("收益")}</th>
                          <th>{t("状态")}</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((r) => (
                          <tr key={r.id}>
                            <td>
                              <input
                                aria-label={`${language === "en" ? "Select for comparison" : "选择对照"} ${r.id}`}
                                type="checkbox"
                                checked={compare.includes(r.id)}
                                onChange={() =>
                                  setCompare(
                                    compare.includes(r.id)
                                      ? compare.filter((x) => x !== r.id)
                                      : [...compare.slice(-1), r.id],
                                  )
                                }
                              />
                            </td>
                            <td>
                              <b>{r.config.strategy.name}</b>
                              <small>
                                {r.id.slice(0, 8)} · {r.strategy_id.slice(0, 8)}
                              </small>
                            </td>
                            <td>{t(names[r.config.mode])}</td>
                            <td>
                              {r.config.start}
                              <br />
                              {r.config.end}
                            </td>
                            <td
                              className={
                                r.summary.total_return >= 0 ? "up" : "down"
                              }
                            >
                              {pct(r.summary.total_return)}
                            </td>
                            <td>
                              <span className="pill">{t(names[r.status])}</span>
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={`${language === "en" ? "Open experiment" : "打开研究"} ${r.id}`}
                                onClick={() => action(() => openRun(r.id))}
                              >
                                <ArrowUpRight size={18} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <button
                    className="outline compare-button"
                    disabled={compare.length !== 2 || busy}
                    onClick={() =>
                      action(async () =>
                        setComparison(
                          await Promise.all(
                            compare.map((id) => api("/runs/" + id)),
                          ),
                        ),
                      )
                    }
                  >
                    <GitCompareArrows size={16} />
                    {t("比较已选记录")}
                  </button>
                </>
              )}
              {comparison.length === 2 && (
                <section className="panel">
                  <h2>{t("实验对照")}</h2>
                  <p className="help">
                    {t(
                      "只有同数据、同方法、同账户规则才能归因于判断方案差异；其他变化均为不同实验。纯数值对照不包含形态语义判断。",
                    )}
                  </p>
                  <div className="comparison-grid">
                    {comparison.map((r) => (
                      <div key={r.id}>
                        <h3>{r.config.strategy.name}</h3>
                        <span className="pill">{t(names[r.config.mode])}</span>
                        <Curve curve={r.state?.account?.curve || []} />
                        <dl>
                          <dt>{t("账户收益")}</dt>
                          <dd>{pct(r.summary.total_return)}</dd>
                          <dt>{t("最大回撤")}</dt>
                          <dd>{pct(r.summary.max_drawdown)}</dd>
                          <dt>{t("已完成交易")}</dt>
                          <dd>{r.summary.trades}</dd>
                          <dt>{t("推理估算费用")}</dt>
                          <dd>{usd(r.summary.estimated_cost)}</dd>
                          <dt>{t("数据 / 策略")}</dt>
                          <dd className="mono">
                            {r.data_id.slice(0, 8)} /{" "}
                            {r.strategy_id.slice(0, 8)}
                          </dd>
                        </dl>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
          {page === "result" && run && (
            <>
              <div className="page-heading split result-heading">
                <div>
                  <div className="eyebrow">
                    EXPERIMENT / {run.id.slice(0, 8)}
                  </div>
                  <h1>{run.config.strategy.name}</h1>
                  <p>
                    {run.config.symbols.join(" · ")}
                    <span className="separator">/</span>
                    {run.config.start} — {run.config.end}
                  </p>
                </div>
                <div className="result-actions">
                  <span
                    className={
                      "pill " + (run.status === "running" ? "positive" : "")
                    }
                  >
                    {t(names[run.status])}
                  </span>
                  {run.status === "running" ? (
                    <button
                      className="outline"
                      onClick={() =>
                        action(async () => {
                          await api(`/runs/${run.id}/pause`, {});
                        })
                      }
                    >
                      <Pause size={15} />
                      {t("暂停")}
                    </button>
                  ) : run.status === "paused" ? (
                    <button
                      className="outline"
                      disabled={busy || run.archived}
                      onClick={() =>
                        action(async () => {
                          await api(`/runs/${run.id}/resume`, {});
                          setRun(await api("/runs/" + run.id));
                        })
                      }
                    >
                      <Play size={15} />
                      {t("继续")}
                    </button>
                  ) : (
                    <button
                      className="outline"
                      disabled={busy || run.status !== "completed"}
                      onClick={() =>
                        action(async () => {
                          const r = await api(`/runs/${run.id}/replay`, {});
                          await openRun(r.id);
                        })
                      }
                    >
                      <RotateCcw size={15} />
                      {run.archived ? t("复制历史归档") : t("离线回放")}
                    </button>
                  )}
                </div>
              </div>
              <div className="run-provenance">
                <ShieldCheck size={16} />
                <span>
                  {t(names[run.config.mode])}
                  {run.archive_replay
                    ? t(" · 归档结果副本，未经重新计算")
                    : run.config.mode === "baseline"
                    ? t(" · 只有数值筛选，没有 LLM 形态判断")
                    : run.config.mode === "replay"
                      ? t(" · 使用保存响应重新校验与记账，不再次付费")
                      : ` · ${run.config.provider} / ${run.config.model}`}
                </span>
                <span>{t("演示调参 · 非投资建议")}</span>
              </div>
              {run.archived && <div className="notice">{t("历史归档：结果按运行时的原始规则保存，后续规则变更不会改写此结果。")}</div>}
              {run.reason && (
                <div className="notice">
                  <div>
                    <b>{t(run.status === 'paused' ? "运行已暂停" : "运行说明")}</b>
                    <p>{run.reason}</p>
                    {run.reason.toLowerCase().includes("unknown") && (
                      <button
                        className="outline"
                        disabled={busy}
                        onClick={() => {
                          if (
                            window.confirm(
                              t(
                                "上次请求可能已经计费。确认接受再次请求可能重复计费？",
                              ),
                            )
                          )
                            action(async () => {
                              await api(
                                `/runs/${run.id}/acknowledge-unknown`,
                                {},
                              );
                              setError(
                                t("已确认风险；点击继续后才会再次请求。"),
                              );
                            });
                        }}
                      >
                        {t("确认未知请求风险")}
                      </button>
                    )}
                  </div>
                </div>
              )}
              <div className="metric-grid">
                <div>
                  <span>{t("账户权益")}</span>
                  <strong>{usd(run.summary.equity)}</strong>
                  <small>
                    {t("初始")}
                    {usd(run.config.capital)}
                  </small>
                </div>
                <div>
                  <span>{t("累计收益")}</span>
                  <strong
                    className={run.summary.total_return >= 0 ? "up" : "down"}
                  >
                    {pct(run.summary.total_return)}
                  </strong>
                  <small>{t("未扣未发生的退出成本")}</small>
                </div>
                <div>
                  <span>{t("最大回撤")}</span>
                  <strong>{pct(run.summary.max_drawdown)}</strong>
                  <small>{t("逐日收盘权益口径")}</small>
                </div>
                <div>
                  <span>{t("已完成交易")}</span>
                  <strong>
                    {run.summary.trades}
                    <small> {t("笔")}</small>
                  </strong>
                  <small>
                    {t("另有")}
                    {Object.keys(account?.positions || {}).length}{" "}
                    {t("个未平仓")}
                  </small>
                </div>
              </div>
              <section className="panel performance">
                <div className="panel-title">
                  <h2>{t("账户表现")}</h2>
                  <span className="subtle">
                    {t("已推进")}
                    {run.state?.day || 0} {t("个交易日")}
                  </span>
                </div>
                <Curve
                  curve={account?.curve || []}
                  benchmark={run.state?.benchmark || []}
                />
              </section>
              <div className="result-meta">
                <span>{t("买入 / 卖出成交")}{run.summary.buy_fills} / {run.summary.sell_fills}</span>
                <span>{t("平均 / 当前仓位")}{(run.summary.mean_exposure*100).toFixed(2)}% / {(run.summary.current_exposure*100).toFixed(2)}%</span>
                <span>{t("有持仓交易日")}{run.summary.active_sessions}</span>
                <span>
                  {t("已实现")}
                  {usd(run.summary.realized_pnl)} {t("/ 浮动")}{" "}
                  {usd(run.summary.unrealized_pnl)}
                </span>
                <span>
                  {t("手续费")}
                  {usd(run.summary.fees)}
                </span>
                <span>
                  {t("请求")}
                  {run.summary.requests} {t("/ 估算")}{" "}
                  {usd(run.summary.estimated_cost)}
                </span>
                <span>
                  {t("模型等待")}
                  {run.summary.elapsed_model_seconds.toFixed(1)}s
                </span>
              </div>
              <section className="panel detail-panel">
                <div className="tabs">
                  {[
                    ["decisions", t("候选与判断")],
                    ["trades", t("交易明细")],
                    ["positions", t("持仓与订单")],
                    ["trace", t("模型记录")],
                    ["config", t("冻结配置")],
                  ].map(([v, label]) => (
                    <button
                      key={v}
                      className={tab === v ? "active" : ""}
                      onClick={() => {
                        setTab(v);
                        if (v === "trace")
                          action(async () =>
                            setRaw(await api(`/runs/${run.id}/requests`)),
                          );
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {tab === "decisions" && (
                  <div className="decision-layout">
                    <div className="decision-list">
                      {!decisions.length ? (
                        <div className="empty">
                          <p>{t("当前还没有已完成日的候选记录。")}</p>
                        </div>
                      ) : (
                        decisions.map((d) => (
                          <button
                            className={selected?.id === d.id ? "selected" : ""}
                            key={d.id}
                            onClick={() => setSelected(d)}
                          >
                            <span>
                              <b>{d.symbol}</b>
                              <small>{d.date}</small>
                            </span>
                            <span
                              className={
                                "decision-verdict " +
                                (d.validation.accepted ? "up" : "subtle")
                              }
                            >
                              {d.execution_precheck?.eligible===false
                                ? (language==='en'?'Model not called':'模型未调用')
                                : d.validation.accepted
                                ? t("数值通过")
                                : d.decision
                                  ? t(names[d.decision.verdict])
                                  : t("未通过预检")}
                              <ChevronRight size={13} />
                            </span>
                          </button>
                        ))
                      )}
                    </div>
                    <div className="decision-detail">
                      {selected ? (
                        <>
                          <div className="split">
                            <h3>
                              {selected.symbol}{" "}
                              <span className="subtle">{selected.date}</span>
                            </h3>
                            <span className="pill">
                              {selected.execution_precheck?.eligible===false
                                ? (language==='en'?'Account precheck':'账户预检')
                                : selected.source === "numeric_baseline"
                                ? t("程序对照")
                                : t("模型判断")}
                            </span>
                          </div>
                          {selected.candidates?.length ? <CandidateInspection runId={run.id} symbol={selected.symbol} day={selected.date} event={selected} /> : <>
                          <img
                            className="candles"
                            alt={
                              language === "en"
                                ? `${selected.symbol} candlesticks through ${selected.date}`
                                : `${selected.symbol} 截至 ${selected.date} 的可见蜡烛图`
                            }
                            src={`/api/runs/${run.id}/chart/${selected.symbol}/${selected.date}`}
                          />
                          <div className="decision-facts">
                            <span>
                              {t("量比")}{" "}
                              <b>{selected.screen.volume_ratio.toFixed(2)}×</b>
                            </span>
                            <span>
                              {t("数值可行组合")}
                              <b>{selected.feasible_pairs}</b>
                            </span>
                            <span>
                              {t("订单")}{" "}
                              <b>
                                {selected.order_id ? t("已创建") : t("未创建")}
                              </b>
                            </span>
                          </div>
                          {selected.decision ? (
                            <>
                              {selected.decision.checks.map((c: Obj) => (
                                <div className="rubric-row" key={c.name}>
                                  <span
                                    className={
                                      c.verdict === "pass" ? "up" : "subtle"
                                    }
                                  >
                                    {c.verdict === "pass" ? (
                                      <Check size={16} />
                                    ) : (
                                      <Circle size={14} />
                                    )}
                                  </span>
                                  <div>
                                    <b>
                                      {
                                        {
                                          cup: t("杯体"),
                                          handle: t("柄部"),
                                          coherence: t("连贯性"),
                                        }[c.name as "cup"]
                                      }
                                    </b>{" "}
                                    · {t(names[c.verdict])}
                                    <p>{c.reason}</p>
                                    <small>
                                      {c.start_date} — {c.end_date}
                                    </small>
                                  </div>
                                </div>
                              ))}
                              <p>{selected.decision.evidence}</p>
                            </>
                          ) : (
                            <div className="notice">
                              {t(
                                "纯数值基线未判断“像不像杯柄”，不能把通过位置条件当成 LLM 形态识别。",
                              )}
                            </div>
                          )}
                          <details>
                            <summary>{t("程序校验与订单依据")}</summary>
                            {!!context?.numeric_checks?.length && (
                              <div className="table-wrap">
                                <table>
                                  <thead>
                                    <tr>
                                      <th>{t("检查项")}</th>
                                      <th>{t("实际值")}</th>
                                      <th>{t("允许范围")}</th>
                                      <th>{t("状态")}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {context.numeric_checks.map((c: Obj) => {
                                      const labels: Obj = {
                                        cup_sessions: "杯体长度",
                                        handle_sessions: "柄部长度",
                                        bottom_internal: "底部位于杯沿之间",
                                        rim_difference: "杯沿高度差",
                                        cup_depth: "杯体深度",
                                        prior_advance: "前期上涨幅度",
                                        handle_above_midpoint:
                                          "柄部低点高于杯体中线",
                                        handle_drop: "柄部回撤",
                                        breakout_extension: "突破幅度",
                                      };
                                      const number = (v: number | null) =>
                                        v === null
                                          ? "—"
                                          : c.unit === "ratio"
                                            ? `${(v * 100).toFixed(2)}%`
                                            : Number(v).toFixed(
                                                c.unit === "sessions" ||
                                                  c.unit === "boolean"
                                                  ? 0
                                                  : 2,
                                              );
                                      return (
                                        <tr key={c.name}>
                                          <td>
                                            {language === "en"
                                              ? c.name
                                              : labels[c.name] || c.name}
                                          </td>
                                          <td>{number(c.value)}</td>
                                          <td>
                                            {c.strict_minimum ? ">" : "≥"}{" "}
                                            {number(c.minimum)}
                                            {c.maximum != null
                                              ? " / ≤ " + number(c.maximum)
                                              : ""}
                                          </td>
                                          <td
                                            className={c.passed ? "up" : "down"}
                                          >
                                            {c.passed ? t("通过") : t("未通过")}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}
                            <pre>
                              {JSON.stringify(selected.validation, null, 2)}
                            </pre>
                          </details>
                          </>}
                          <ReferenceSources pack={context?.references || boot?.references} />
                          <details>
                            <summary>
                              {t("查看当时的模型输入（不含密钥）")}
                            </summary>
                            {context ? (
                              <>
                                <p>{context.original_request?t("保存的原始输入"):t("数值候选参考上下文（未调用模型）")}</p>
                                <pre>{context.system}</pre>
                                <pre>{context.text}</pre>
                              </>
                            ) : (
                              <p>{t("正在重建输入…")}</p>
                            )}
                          </details>
                        </>
                      ) : (
                        <div className="empty">
                          <Eye size={30} />
                          <h3>{t("从一次判断，回到当时的信息。")}</h3>
                          <p>
                            {t(
                              "选择左侧的候选，查看截至该日的图表、规则与订单依据。",
                            )}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {tab === "trades" && (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t("标的")}</th>
                          <th>{t("买入")}</th>
                          <th>{t("卖出")}</th>
                          <th>{t("数量")}</th>
                          <th>{t("损益 / USD")}</th>
                          <th>{t("退出原因")}</th>
                          <th>{t("追溯")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(account?.trades || []).map(
                          (trade: Obj, i: number) => (
                            <tr key={i}>
                              <td>
                                <b>{trade.symbol}</b>
                              </td>
                              <td>
                                {trade.entry_date}
                                <small>{usd(trade.entry_price)}</small>
                              </td>
                              <td>
                                {trade.exit_date}
                                <small>{usd(trade.exit_price)}</small>
                              </td>
                              <td>{trade.quantity}</td>
                              <td className={trade.pnl >= 0 ? "up" : "down"}>
                                {usd(trade.pnl)}
                              </td>
                              <td>
                                <ExitReason reason={trade.reason} />
                              </td>
                              <td>
                                <button
                                  className="icon-button"
                                  aria-label={`${language === "en" ? "Inspect trade" : "追溯交易"} ${i + 1}`}
                                  onClick={() => {
                                    const o = account.orders.find(
                                      (o: Obj) =>
                                        o.symbol === trade.symbol &&
                                        o.side === "buy" &&
                                        o.fill_date === trade.entry_date,
                                    );
                                    setSelected(
                                      decisions.find(
                                        (d) =>
                                          d.id ===
                                          o?.signal_date + ":" + trade.symbol,
                                      ) || null,
                                    );
                                    setTab("decisions");
                                  }}
                                >
                                  <ArrowUpRight size={16} />
                                </button>
                              </td>
                            </tr>
                          ),
                        )}
                      </tbody>
                    </table>
                    {!account?.trades.length && (
                      <div className="empty">
                        {t("没有已平仓交易；未平仓不计为完成交易。")}
                      </div>
                    )}
                  </div>
                )}
                {tab === "positions" && (
                  <>
                    <h3>{t("当前持仓")}</h3>
                    <PositionTable positions={account?.positions || {}} equity={run.summary.equity} strategy={run.config.strategy} />
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>{t("标的")}</th>
                            <th>{t("方向")}</th>
                            <th>{t("信号日期")}</th>
                            <th>{t("成交日期")}</th>
                            <th>{t("数量")}</th>
                            <th>{t("状态")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(account?.orders || []).map((o: Obj) => (
                            <tr key={o.id}>
                              <td>{o.symbol}</td>
                              <td>
                                {o.side === "buy" ? t("买入") : t("卖出")}
                              </td>
                              <td>{o.signal_date}</td>
                              <td>{o.fill_date || t("待下一开盘")}</td>
                              <td>{o.quantity}</td>
                              <td>{o.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
                {tab === "trace" && (
                  <>
                    <p className="help">
                      {t(
                        "原始模型响应保存在本机。回放展示原运行的收据，复用响应标注来源请求；复用与回放不新增模型费用。美元是按冻结单价计算的估算，不是供应商账单。",
                      )}
                    </p>
                    {!raw.length ? (
                      <div className="empty">
                        {t("本次运行没有付费模型请求。")}
                      </div>
                    ) : (
                      raw.map((r) => (
                        <details key={r.id}>
                          <summary>
                            {r.node} · {r.status} · {r.elapsed.toFixed(2)}s
                          </summary>
                          <pre>
                            {JSON.stringify(
                              {
                                status: r.status,
                                source_run_id: r.source_run_id,
                                source_request_id: r.source_request_id,
                                usage: r.usage,
                                request: r.request,
                                raw: r.raw,
                                note: r.note,
                              },
                              null,
                              2,
                            )}
                          </pre>
                        </details>
                      ))
                    )}
                  </>
                )}
                {tab === "config" && (
                  <>
                    <div className="notice">
                      {t("数据 SHA256：")}
                      {run.data_id}
                      <br />
                      {t("策略 SHA256：")}
                      {run.strategy_id}
                    </div>
                    <pre>{JSON.stringify(run.config, null, 2)}</pre>
                  </>
                )}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
