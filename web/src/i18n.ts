import { useEffect, useSyncExternalStore } from "react";

export type Language = "zh-CN" | "en";
const storageKey = "sal.language";
let memory: Language = "zh-CN";
function current(): Language {
  try {
    return localStorage.getItem(storageKey) === "en" ? "en" : "zh-CN";
  } catch {
    return memory;
  }
}
function subscribe(callback: () => void) {
  window.addEventListener("sal-language", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("sal-language", callback);
    window.removeEventListener("storage", callback);
  };
}
export function useLanguage() {
  const language = useSyncExternalStore(
    subscribe,
    current,
    () => "zh-CN" as Language,
  );
  useEffect(() => {
    document.documentElement.lang = language;
    document.title = language === 'en'
      ? 'Strategy Agent Lab · Method workbench'
      : 'Strategy Agent Lab · 方法构建工作台';
  }, [language]);
  const setLanguage = (value: Language) => {
    memory = value;
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      /* No secrets in preference storage. */
    }
    window.dispatchEvent(new Event("sal-language"));
  };
  return {
    language,
    setLanguage,
    t: (value: string) => translate(value, language),
  };
}
export function translate(value: string, language: Language) {
  return language === "en" ? (en[value] ?? en[value.trim()] ?? value) : value;
}
const en: Record<string, string> = {
  "本机尚无已保存的模型示范；可以先新建研究。": "No saved model demonstration on this installation. Start a new research run first.",
  "真实 LLM 示范：从固定候选、模型判断到模拟交易与逐笔复核。": "A real LLM workflow: fixed candidates, model judgments, simulated trades and inspectable decisions.",
  "收盘相对均线缓冲":"Close versus SMA buffer",
  "均线变化下限":"Minimum SMA change",
  "突破确认缓冲":"Breakout confirmation buffer",
  "跟踪止损波动倍数（0关闭）":"Trailing-stop volatility units (0 off)",
  "信号优先级回看天数":"Signal priority lookback",
  "同日信号优先级":"Same-day signal priority",
  "代码顺序":"Ticker order",
  "近期动量":"Recent momentum",
  "突破强度":"Breakout strength",
  "选择全部标的":"Select all instruments",
  "美股日线 · 主流股票与 ETF · 一个共享模拟账户":"US daily bars · Mainstream stocks & ETFs · One shared account",
  "未进展退出天数设为0可关闭；趋势、突破和前期涨幅允许合理负阈值，量比可低于1。":"Set no-progress sessions to0 to disable it. Trend, breakout and prior-advance thresholds may be negative; volume ratio may be below1.",
  "目标位杯体高度倍数":"Target cup-height multiple",
  "可见行情天数":"Visible history sessions",
  "趋势均线天数":"Trend SMA sessions",
  "均线比较间隔":"SMA comparison lag",
  "突破回看天数":"Breakout lookback",
  "均量回看天数":"Volume lookback",
  "前期涨幅回看天数":"Prior advance lookback",
  "杯沿高度差上限":"Rim-height difference limit",
  "柄低相对杯深下限":"Handle-low cup-height fraction",
  "柄部回撤上限":"Handle drawdown limit",
  "突破延伸上限":"Breakout extension limit",
  "下一开盘买入余量":"Next-open entry allowance",
  "每次最多形态数":"Max patterns per node",
  "去重重叠比例":"Deduplication overlap",
  "杯底合并间隔":"Bottom merge distance",
  "波动单位回看天数":"Volatility lookback",
  "有效进展所需波动单位":"Progress volatility units",
  "连续未进展退出天数":"No-progress exit sessions",
  "每阶段允许一次候选局部图 / 行情工具调用":"One candidate zoom / bars tool call per stage",
  "对未通过或证据不足的候选进行一次针对性复核":"Targeted review of failed or insufficient-evidence candidates",
  "主判断与复核各最多两次正常请求加一次修复；每标的日期最多六次，仍受总预算与请求数限制。":"Primary and review each allow two normal requests plus one repair: at most six per symbol/date, within total cost and request limits.",
  "历史归档：结果按运行时的原始规则保存，后续规则变更不会改写此结果。":"Archived result: saved under the original rules used for this run. Later rule changes do not alter this result.",
  "复制历史归档":"Copy archived result",
  " · 归档结果副本，未经重新计算":" · Copy of the archived result; not recalculated",
  "运行说明":"Run note",
  "买入 / 卖出成交":"Buy / sell fills ",
  "平均 / 当前仓位":"Mean / current exposure ",
  "有持仓交易日":"Sessions holding positions ",
  "保存的原始输入":"Saved original input",
  "数值候选参考上下文（未调用模型）":"Numeric candidate reference context (no model called)",
  "原始模型响应保存在本机。回放展示原运行的收据，复用响应标注来源请求；复用与回放不新增模型费用。美元是按冻结单价计算的估算，不是供应商账单。":
    "Original responses stay local. Replay displays source-run receipts; reused responses identify their source request. Neither reuse nor replay creates new inference charges. USD costs are estimates from frozen rates, not provider invoices.",
  "读取已完成的真实模型研究，不会重新调用 API":
    "Opens a completed real model run. No new API calls.",
  "已有真实 Luna 研究、同方法程序对照与免费回放。示范经过调参，不代表未来收益。":
    "Explore real Luna research, the matched numeric baseline and free replay. Demo-tuned, not evidence of future returns.",
  程序逐项检查: "Program checks",
  检查项: "Check",
  实际值: "Observed",
  允许范围: "Allowed range",
  验收与对照: "Verification & comparison",
  查看同方法对照: "Compare the same method",
  回放一致: "Replay matches",
  恢复一致: "Recovery matches",
  回放未验证: "Replay not verified",
  恢复未验证: "Recovery not verified",
  模型判定分布: "Model verdicts",
  模型延迟中位数: "Median model latency",
  "模型响应与参考信息保留原语言。":
    "Model responses and reference material retain their original language.",
  界面语言: "Interface language",
  纯数值对照: "Numeric baseline",
  模型研究: "Model research",
  离线回放: "Offline replay",
  等待开始: "Ready",
  运行中: "Running",
  已暂停: "Paused",
  已完成: "Completed",
  通过: "Pass",
  未通过: "Fail",
  证据不足: "Insufficient evidence",
  "参数无效，请检查日期、数值及模型配置。":
    "Invalid settings. Check dates, numbers and model configuration.",
  "运行后，在这里查看真实的账户曲线。":
    "Run an experiment to see its actual account curve.",
  模拟账户与等权价格收益基准曲线:
    "Simulated account and equal-weight price-return benchmark",
  模拟账户: "Simulated account",
  "等权买入持有 · 价格收益、不含股息":
    "Equal-weight buy & hold · price return, no dividends",
  描述你的方法: "Describe your method",
  "明确入场、退出与风险条件，保留需要经验判断的部分。":
    "Define entry, exit and risk rules. Identify where judgment is needed.",
  "交给程序与 AI": "Let code and AI execute",
  "程序计算数值，模型按你的标准判断形态，共用一个模拟账户。":
    "Code calculates the signals. AI applies your criteria. One shared simulated account.",
  "看结果，也看过程": "Inspect results and reasoning",
  "从账户曲线回到每一笔交易、判断依据与当时可见的信息。":
    "Trace the account curve back to trades, evidence and information available at the time.",
  返回首页: "Home",
  主导航: "Main navigation",
  概览: "Overview",
  新建研究: "New research",
  研究记录: "Experiments",
  模型连接: "Model connections",
  仅在这台电脑运行: "Runs on this computer only",
  "尚未发布 · 未连接实盘": "Unpublished · no live brokerage",
  研究工作台: "Research workspace",
  研究详情: "Experiment details",
  "本地优先 · 数据由你掌握": "Local first · your data stays in your control",
  关闭错误: "Dismiss error",
  "正在连接本地工作台…": "Connecting to the local workspace…",
  "把投资方法，变成可以检验的交易过程。":
    "Turn your investment method into a testable process. ",
  "让程序处理数值，让 AI 按你的标准判断，":
    "Code handles the numbers. AI applies your judgment criteria. ",
  "在历史行情里走完一次完整的模拟。":
    "Simulate the complete process on historical market data.",
  开始一项研究: "Start a research run",
  查看本地示范: "Explore local demo",
  打开已保存的真实模拟记录: "Opens an actual saved simulation",
  "首次查看会运行免费纯数值对照；不调用 LLM":
    "First visit runs a free numeric baseline. No LLM calls.",
  "人机协同工作流示意，不是回测结果":
    "Human–AI workflow illustration, not backtest results",
  杯柄突破: "Cup & Handle breakout",
  "量价规则 + 形态判断": "Price / volume rules + pattern judgment",
  "数值筛选 · 风险控制": "Numeric screening · risk controls",
  "按方法判断，而非自由预测": "Apply a method, not an unconstrained forecast",
  "图表 · 规则 · 可追溯依据": "Charts · rules · traceable evidence",
  "工作流示意 · 非模型运行结果": "Workflow illustration · not a model result",
  "不只是一条收益曲线。": "More than a return curve.",
  "你的方法贯穿始终，每个判断都有来路。":
    "Your method, end to end. Every decision leaves a trail.",
  "杯柄突破 / Cup & Handle": "Cup & Handle breakout",
  "美股日线 · 五个知名标的 · 一个共享模拟账户":
    "US daily bars · five familiar instruments · one shared account",
  "面向演示调参，不代表策略泛化或未来投资表现。当前还没有真实 LLM 示范结果。":
    "Tuned for demonstration, not evidence of generalization or future returns. No real LLM demonstration run is available yet.",
  探索示范方法: "Explore the example method",
  "本地开发版本 · GitHub 与网站暂未发布":
    "Local development preview · not published to GitHub or the web",
  "让方法开始接受检验。": "Put your method to the test.",
  "先确认规则，再冻结输入。每次运行都保留独立版本。":
    "Approve the rules, then freeze the inputs. Every experiment keeps its own version.",
  方法与规则: "Method & rules",
  杯柄突破模板: "Cup & Handle template",
  研究名称: "Experiment name",
  "交给 AI 的形态判断标准": "Pattern judgment criteria for AI",
  "这里设置杯柄参考流程的形态判断标准；如需创建或修改策略程序，请使用项目工作台。":
    "Set pattern criteria for the cup reference workflow here. Use the project workbench to create or revise a strategy program.",
  程序负责: "Code handles",
  "趋势与放量筛选、价格/位置校验、仓位、风险及账户记账":
    "Trend / volume screening, price / anchor validation, sizing, risk and accounting",
  "AI 负责": "AI handles",
  "圆弧杯体、上沿浅柄、整体连贯性；依据不足可以拒绝判断":
    "Rounded cup, shallow upper handle and coherence. Insufficient evidence is a valid outcome.",
  突破量比: "Breakout volume ratio",
  杯体最短天数: "Minimum cup sessions",
  前期涨幅下限: "Minimum prior advance",
  其余交易与风险参数: "More execution and risk parameters",
  杯体最长天数: "Maximum cup sessions",
  柄最短天数: "Minimum handle sessions",
  柄最长天数: "Maximum handle sessions",
  杯深下限: "Minimum depth",
  杯深上限: "Maximum depth",
  每笔计划风险比例: "Planned risk / trade",
  单标的入场比例上限: "Entry weight cap",
  最大持仓与待入场数: "Position + pending cap",
  最长持有天数: "Maximum holding sessions",
  单边手续费率: "Commission / side",
  单边滑点率: "Slippage / side",
  "我确认上述方法与参数，保存为本次研究的策略版本。":
    "I approve these rules and parameters as the strategy version for this run.",
  历史数据与账户: "Historical data & account",
  已冻结行情: "Frozen data",
  开始日期: "Start date",
  结束日期: "End date",
  "初始资金 / USD": "Initial capital / USD",
  "起止日期需为交易日。日频、只做多、不加仓；次日开盘模拟成交。原始 OHLC 价格收益，不含现金股息；区间内拆股会拒绝运行。数据快照不等于历史时点数据档案。":
    "Dates must be trading sessions. Daily, long-only, no pyramiding; simulated next-open fills. Raw OHLC price returns, no cash dividends. Splits are rejected. A downloaded snapshot is not a point-in-time archive.",
  执行方案: "Execution mode",
  "免费 · 不调用模型，仅检验数值规则与账户流程":
    "Free · no model calls; numeric rules and account execution only",
  真实模型研究: "Live model research",
  "按方法判断形态 · 消耗你自己的 API 额度":
    "Apply the method to patterns · uses your API credits",
  供应商: "Provider",
  "请填写账户地区及 USD 等值单价来源":
    "Enter account region and USD-equivalent rate source",
  "· 已配置": " · configured",
  "· 未配置凭据": " · credentials missing",
  "模型 / 部署 ID": "Model / deployment ID",
  "请选择支持所需图片与工具能力的模型；不会自动切换供应商。":
    "Choose a model supporting the images and tools you need. Providers are never switched automatically.",
  "预算估算 / USD": "Estimated budget / USD",
  最多请求次数: "Maximum requests",
  "单次输出 token 上限": "Max output tokens / request",
  计价与输入能力: "Pricing & input capabilities",
  "每百万输入 token / USD": "Input / million tokens, USD",
  "每百万输出 token / USD": "Output / million tokens, USD",
  "单价来源 / 币种换算说明": "Rate source / currency conversion",
  "发送当时可见的蜡烛图（需要视觉型号）":
    "Send cutoff-limited candlestick charts (vision model required)",
  "允许一次有界 read_bars 工具调用": "Allow one bounded read_bars tool call",
  "请求数严格限制；美元预算按保守估算预留，并非供应商账单保证。缓存、区域附加费及各家计费差异需要实测。非 OpenAI 型号请自行确认并填写单价。":
    "Request count is strictly limited. Budget reservations are conservative estimates, not a billing guarantee. Check caching, regional premiums and provider-specific billing. Confirm rates for the selected model.",
  "我同意本次使用自己的 API 额度；数据和方法将发送给选定供应商。":
    "I authorize API spending for this run. Market data and method text will be sent to the selected provider.",
  一次可复核的实验: "An inspectable experiment",
  方法: "Method",
  "杯柄突破 · 可编辑参数": "Cup & Handle · editable parameters",
  标的: "Instruments",
  请选择标的: "Choose instruments",
  区间: "Period",
  账户: "Account",
  "· 共享资金": " · shared cash",
  方案: "Mode",
  检查数据与候选机会: "Check data & candidates",
  日期具备数值可行的位置组合: "dates have numerically feasible anchors",
  突破候选: "Breakout candidates: ",
  "个；不是模型通过数或交易数。": " dates; not model acceptances or trades.",
  查看候选日期: "View candidate dates",
  可行: "Feasible",
  不满足: "Not feasible",
  "处理中…": "Working…",
  开始本地运行: "Start local run",
  "没有实盘下单。当前方法由演示需求调参，不构成盈利证明。":
    "No live orders. Parameters are tuned for demonstration, not proof of profitability.",
  "同一套规则，不同的模型。": "Same rules. Different models.",
  "国内外接口独立配置。只在你主动运行研究时调用，不自动切换、不共享密钥。":
    "Configure each provider independently. Requests happen only when you start a model run. No automatic fallback or shared keys.",
  "通义千问 Qwen": "Qwen",
  "智谱 GLM": "GLM / Zhipu",
  "豆包 / 火山方舟": "Doubao / Volcano Ark",
  凭据已配置: "Credentials configured",
  未配置凭据: "Credentials not configured",
  "可构造图片请求 · 需选择视觉型号":
    "Image request supported · select a vision model",
  "当前接口仅文本 · 不静默丢弃图片":
    "Text-only adapter · images are never silently dropped",
  "密钥只在本机后端读取。": "Credentials are read by the local backend only.",
  "在项目根目录的私有 .env 中配置对应环境变量，再重启服务。浏览器不收集、不保存 API Key，也不会读取旧项目的密钥。请参考 .env.example；千问可设置 QWEN_BASE_URL 为账户控制台中的官方地域地址。":
    "Set the relevant variable in a private .env in the project root, then restart. The browser never collects or stores keys. Old project credentials are not accessed. See .env.example. Qwen supports an official regional / workspace QWEN_BASE_URL.",
  "每一次研究，都留下依据。": "Every experiment leaves evidence.",
  "运行版本不会覆盖。选择两次记录，可以并排比较结果与费用。":
    "Versions are never overwritten. Select two runs to compare results and costs.",
  还没有研究记录: "No experiments yet",
  "先运行免费纯数值对照，或配置 Luna 后创建真实模型研究。":
    "Start with a free numeric baseline, or configure Luna for a model run.",
  创建第一项研究: "Create your first experiment",
  对照: "Compare",
  "研究 / 版本": "Experiment / version",
  收益: "Return",
  状态: "Status",
  比较已选记录: "Compare selected runs",
  实验对照: "Experiment comparison",
  "只有同数据、同方法、同账户规则才能归因于判断方案差异；其他变化均为不同实验。纯数值对照不包含形态语义判断。":
    "Only runs sharing data, method and execution can isolate judgment differences. Other changes are separate experiments. The numeric baseline does not judge pattern semantics.",
  账户收益: "Account return",
  最大回撤: "Max drawdown",
  已完成交易: "Closed trades",
  推理估算费用: "Estimated inference cost",
  "数据 / 策略": "Data / strategy",
  暂停: "Pause",
  继续: "Resume",
  "· 只有数值筛选，没有 LLM 形态判断":
    " · numeric screening only; no LLM pattern judgment",
  "· 使用保存响应重新校验与记账，不再次付费":
    " · validates and accounts from saved responses; no new inference",
  "演示调参 · 非投资建议": "Demo-tuned · not investment advice",
  运行已暂停: "Run paused",
  "上次请求可能已经计费。确认接受再次请求可能重复计费？":
    "The previous request may already have been billed. Accept possible duplicate billing if retried?",
  "已确认风险；点击继续后才会再次请求。":
    "Risk acknowledged. A new request happens only after Resume.",
  确认未知请求风险: "Acknowledge unknown request outcome",
  账户权益: "Account equity",
  初始: "Initial ",
  累计收益: "Total return",
  未扣未发生的退出成本: "Excludes exit costs not yet incurred",
  逐日收盘权益口径: "Daily closing equity basis",
  笔: " trades",
  另有: "Plus ",
  个未平仓: " open positions",
  账户表现: "Account performance",
  已推进: "Processed ",
  个交易日: " sessions",
  已实现: "Realized ",
  "/ 浮动": " / unrealized ",
  手续费: "Fees ",
  请求: "Requests ",
  "/ 估算": " / estimate ",
  模型等待: "Model wait ",
  候选与判断: "Candidates & judgments",
  交易明细: "Trades",
  持仓与订单: "Positions & orders",
  模型记录: "Model records",
  冻结配置: "Frozen configuration",
  "当前还没有已完成日的候选记录。":
    "No candidate records from completed sessions yet.",
  数值通过: "Numeric pass",
  未通过预检: "Prefilter rejected",
  程序对照: "Numeric baseline",
  模型判断: "Model judgment",
  量比: "Volume ratio ",
  数值可行组合: "Feasible pairs ",
  订单: "Order ",
  已创建: "Created",
  未创建: "Not created",
  杯体: "Cup",
  柄部: "Handle",
  连贯性: "Coherence",
  "纯数值基线未判断“像不像杯柄”，不能把通过位置条件当成 LLM 形态识别。":
    "The numeric baseline does not assess whether the chart resembles a cup and handle. Feasible anchors are not LLM pattern recognition.",
  程序校验与订单依据: "Program validation & order basis",
  "查看当时的模型输入（不含密钥）":
    "Inspect cutoff-limited model input (no credentials)",
  "正在重建输入…": "Reconstructing input…",
  "从一次判断，回到当时的信息。": "Go from a decision back to its information.",
  "选择左侧的候选，查看截至该日的图表、规则与订单依据。":
    "Select a candidate to inspect its cutoff-limited chart, rules and order basis.",
  买入: "Entry",
  卖出: "Exit",
  数量: "Quantity",
  "损益 / USD": "P&L / USD",
  退出原因: "Exit reason",
  追溯: "Inspect",
  持有到期: "Holding limit",
  收盘止损: "Close-triggered stop",
  "没有已平仓交易；未平仓不计为完成交易。":
    "No closed trades. Open positions are not counted as completed trades.",
  当前持仓: "Current positions",
  方向: "Side",
  信号日期: "Signal date",
  成交日期: "Fill date",
  待下一开盘: "Pending next open",
  "原始模型响应保存在本机。回放模式的响应来自原运行；当前列表只展示本次运行自己的请求收据。美元是按冻结单价计算的估算，不是供应商账单。":
    "Original responses stay local. Replays use their source run. This list shows request receipts for this run only. USD costs are estimates from frozen rates, not provider invoices.",
  "本次运行没有付费模型请求。": "This run made no paid model requests.",
  "数据 SHA256：": "Data SHA256: ",
  "策略 SHA256：": "Strategy SHA256: ",
  "我已核对所选模型的 USD 等值单价与来源。":
    "I have checked the selected model’s USD-equivalent prices and source.",
  "我确认该具体型号支持所选的图片及工具能力。":
    "I confirm this specific model supports the selected image and tool capabilities.",
};
