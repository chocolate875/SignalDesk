import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Compass,
  ShieldAlert,
  X,
} from "lucide-react";
import { fmt, type MacroPillar, type MacroRegime } from "./types";

type ModalTab = "overview" | "methodology";

const QUADRANT_SHORT: Record<string, string> = {
  tailwind: "顺风",
  divergence: "背离",
  repair: "修复",
  headwind: "逆风",
  unavailable: "待补齐",
};

const QUADRANT_CELLS: {
  code: string;
  title: string;
  axis: string;
  hint: string;
  tone: string;
}[] = [
  {
    code: "repair",
    title: "修复 · 观察见底",
    axis: "流动性平稳/宽松 × 指数承压",
    hint: "宏观未恶化但大盘弱势，耐心等待右侧企稳",
    tone: "neutral",
  },
  {
    code: "tailwind",
    title: "顺风",
    axis: "流动性平稳/宽松 × 指数多头",
    hint: "环境友好，按个股计划与纪律正常跟踪",
    tone: "positive",
  },
  {
    code: "headwind",
    title: "逆风",
    axis: "流动性偏紧 × 指数承压",
    hint: "下行尾部风险偏高，严守仓位与止损纪律",
    tone: "danger",
  },
  {
    code: "divergence",
    title: "背离 · 警惕见顶",
    axis: "流动性偏紧 × 指数多头",
    hint: "指数强但水位转紧，警惕高位背离与追高",
    tone: "warning",
  },
];

const LIGHT_TONE: Record<string, string> = {
  green: "positive",
  yellow: "warning",
  red: "danger",
  unavailable: "muted",
};

const PILLAR_NUM = ["①", "②", "③", "④", "⑤", "⑥"];

/** 顶栏紧凑「市场大势」触发胶囊：不占用 K 线纵向高度，点击展开全景弹窗 */
export function MacroRegimeTrigger({
  macro,
  open,
  onOpen,
}: {
  macro: MacroRegime | undefined;
  open: boolean;
  onOpen: () => void;
}) {
  const q = macro?.quadrant;
  const rg = macro?.risk_gauge;
  const tone = q?.tone ?? "muted";
  const shortLabel = QUADRANT_SHORT[q?.code ?? "unavailable"] ?? "待补齐";
  const redCount = rg?.red_count ?? 0;
  const totalCount = rg?.total_count ?? 6;
  const redBadgeTone =
    !macro?.available
      ? "muted"
      : redCount >= 3
        ? "danger"
        : redCount >= 1
          ? "warning"
          : "positive";

  return (
    <button
      type="button"
      className={`macro-regime-trigger tone-${tone} ${open ? "active" : ""}`}
      onClick={onOpen}
      aria-expanded={open}
      aria-label="打开市场大势与宏观流动性全景面板"
      title={
        q
          ? `市场大势：${q.label}（${q.liquidity_label} × ${q.trend_label}）· 红灯 ${redCount}/${totalCount} · 点击展开全景面板`
          : "点击查看市场大势与宏观流动性全景面板"
      }
    >
      <span className={`mr-dot tone-${tone}`} />
      <span className="mr-trigger-name">大势·{shortLabel}</span>
      <span className={`mr-red-pill tone-${redBadgeTone}`}>
        {macro?.available ? `红灯 ${redCount}/${totalCount}` : "同步中"}
      </span>
    </button>
  );
}

/** 六分项单卡 */
function PillarCard({ pillar }: { pillar: MacroPillar }) {
  const tone = LIGHT_TONE[pillar.light] ?? "muted";
  const badgeNo = PILLAR_NUM[(pillar.index ?? 1) - 1] ?? `${pillar.index}`;
  const pct = pillar.percentile_10y;

  return (
    <article className={`mr-pillar-card tone-${tone}`}>
      <div className="mr-pillar-head">
        <div className="mr-pillar-title">
          <span className="mr-pillar-num">{badgeNo}</span>
          <h4>{pillar.label}</h4>
        </div>
        <span className={`verdict-chip tone-${tone}`}>
          {pillar.light_label}
        </span>
      </div>

      <div className="mr-pillar-metric-row">
        <strong className="mr-pillar-primary">{pillar.primary_metric}</strong>
        <span className="mr-pillar-chg">{pillar.change_13w_text}</span>
      </div>

      <div className="mr-pct-row">
        <span className="mr-pct-label">10年因果分位</span>
        {pct != null ? (
          <>
            <div className="mr-pct-track" aria-hidden="true">
              <div
                className={`mr-pct-fill tone-${tone}`}
                style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
              />
            </div>
            <b className="mr-pct-val">{fmt(pct, 1)}%</b>
          </>
        ) : (
          <span className="mr-pct-empty">样本不足或待补齐</span>
        )}
      </div>

      <p className="mr-pillar-summary">{pillar.summary}</p>

      {pillar.details?.length > 0 && (
        <dl className="mr-pillar-kv">
          {pillar.details.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mr-pillar-foot">
        <span>
          {pillar.source}
          {pillar.as_of ? ` · 观测 ${pillar.as_of}` : ""}
          {pillar.as_of && !pillar.fresh ? "（已滞后）" : ""}
        </span>
      </div>
      {pillar.caveat && <p className="mr-pillar-caveat">{pillar.caveat}</p>}
    </article>
  );
}

/** 居中全屏门户弹窗：市场大势四象限 + 下行风险水位 + 六分项指示灯 + 口径与学术依据 */
export function MacroRegimeModal({
  macro,
  onClose,
}: {
  macro: MacroRegime | undefined;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<ModalTab>("overview");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const q = macro?.quadrant;
  const rg = macro?.risk_gauge;
  const pillars = macro?.pillars ?? [];
  const alerts = macro?.alerts ?? [];
  const partialErrCount = Object.keys(macro?.partial_errors ?? {}).length;

  return createPortal(
    <div
      className="modal-shade"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="small-modal macro-modal"
        role="dialog"
        aria-modal="true"
        aria-label="市场大势与宏观流动性全景"
      >
        <header className="modal-header">
          <div>
            <h2>市场大势与宏观流动性全景</h2>
            <p className="wt-modal-sub">
              来源：{macro?.source ?? "等待同步"} · 最新观测：
              {macro?.as_of ?? "待更新"} · 规则 {macro?.rule_version ?? "macro-1.0.0"}
              {macro?.refresh_failed
                ? " · 最近一次外部宏观拉取失败（沿用本机缓存）"
                : partialErrCount > 0
                  ? ` · ${partialErrCount} 个序列沿用缓存`
                  : ""}
            </p>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="关闭市场大势面板"
          >
            <X size={20} />
          </button>
        </header>

        <div className="wt-modal-tabs" role="tablist" aria-label="市场大势分页">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "overview"}
            className={tab === "overview" ? "active" : ""}
            onClick={() => setTab("overview")}
          >
            <Compass size={14} />
            大势全景与六分项
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "methodology"}
            className={tab === "methodology" ? "active" : ""}
            onClick={() => setTab("methodology")}
          >
            <BookOpen size={14} />
            口径与学术依据
          </button>
        </div>

        <div className="macro-modal-body">
          {tab === "overview" && (
            <>
              <div className="mr-hero-grid">
                {/* 左侧：流动性方向 × 指数趋势 四象限矩阵 */}
                <section className="mr-hero-card">
                  <div className="mr-hero-card-head">
                    <h3>
                      <Activity size={15} />
                      流动性方向 × 指数趋势四象限
                    </h3>
                    <span className={`verdict-chip tone-${q?.tone ?? "muted"}`}>
                      {q?.label ?? "待补齐"}
                    </span>
                  </div>

                  <div className="mr-quad-matrix" role="grid" aria-label="市场大势四象限">
                    {QUADRANT_CELLS.map((cell) => {
                      const active = q?.code === cell.code;
                      return (
                        <div
                          key={cell.code}
                          className={`mr-quad-cell tone-${cell.tone} ${active ? "active" : ""}`}
                        >
                          <div className="mr-quad-top">
                            <b>{cell.title}</b>
                            {active && <em>当前所处</em>}
                          </div>
                          <small className="mr-quad-axis">{cell.axis}</small>
                          <p>{cell.hint}</p>
                        </div>
                      );
                    })}
                  </div>

                  <p className="mr-hero-desc">
                    {q?.description ??
                      "等待 FRED 宏观数据与基准 ETF 日线同步完成后自动合成四象限。"}
                  </p>
                </section>

                {/* 右侧：下行风险水位（红灯计数 / 6） */}
                <section className="mr-hero-card mr-gauge-card">
                  <div className="mr-hero-card-head">
                    <h3>
                      <ShieldAlert size={15} />
                      下行风险水位
                    </h3>
                    <span className={`verdict-chip tone-${rg?.tone ?? "muted"}`}>
                      {rg?.label ?? "等待数据"}
                    </span>
                  </div>

                  <div className="mr-gauge-score-row">
                    <div className={`mr-gauge-big tone-text-${rg?.tone ?? "muted"}`}>
                      <strong>{rg?.red_count ?? 0}</strong>
                      <span>/ {rg?.total_count ?? 6} 红灯</span>
                    </div>
                    <div className="mr-gauge-counts">
                      <span className="tone-positive">绿灯 {rg?.green_count ?? 0}</span>
                      <span className="tone-warning">黄灯 {rg?.yellow_count ?? 0}</span>
                      <span className="tone-danger">红灯 {rg?.red_count ?? 0}</span>
                    </div>
                  </div>

                  <div className="mr-light-strip" aria-label="六分项红黄绿分布">
                    {pillars.map((p) => (
                      <div
                        key={p.key}
                        className={`mr-light-seg light-${p.light}`}
                        title={`${p.label}：${p.light_label}（${p.primary_metric}）`}
                      >
                        <span>{PILLAR_NUM[(p.index ?? 1) - 1] ?? p.index}</span>
                        <small>{p.label.replace("（NFCI）", "")}</small>
                      </div>
                    ))}
                  </div>

                  <div className="mr-axis-summary">
                    <div>
                      <span>流动性轴（①+②+③）</span>
                      <b>{q?.liquidity_label ?? "待确认"}</b>
                    </div>
                    <div>
                      <span>趋势轴（⑤ SPY/QQQ）</span>
                      <b>{q?.trend_label ?? "待确认"}</b>
                    </div>
                    <div>
                      <span>10Y 实际利率（DFII10）</span>
                      <b>
                        {macro?.real_rate?.ten_year_real != null
                          ? `${fmt(macro.real_rate.ten_year_real, 2)}%`
                          : "—"}
                        {macro?.real_rate?.change_21d_bp != null
                          ? `（21日 ${macro.real_rate.change_21d_bp >= 0 ? "+" : ""}${fmt(macro.real_rate.change_21d_bp, 0)}bp）`
                          : ""}
                      </b>
                    </div>
                  </div>

                  <p className="mr-scope-note">
                    不做 0–100 黑箱大势总分，也不自动覆盖个股评级；红灯越多表示宏观左尾风险越高，应优先严守仓位与止损纪律。
                  </p>
                </section>
              </div>

              {alerts.length > 0 && (
                <div className="mr-alerts-box" role="note" aria-label="宏观联动风险提示">
                  {alerts.map((text, idx) => (
                    <div className="mr-alert-row" key={idx}>
                      <AlertTriangle size={15} />
                      <span>{text}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="mr-pillars-grid">
                {pillars.map((p) => (
                  <PillarCard key={p.key} pillar={p} />
                ))}
              </div>
            </>
          )}

          {tab === "methodology" && (
            <div className="mr-method-wrap">
              <div className="wt-explain-section">
                <h4>一、为什么展示「四象限 + 六分项红灯」而不做 0–100 大势总分？</h4>
                <div className="wt-compare-list">
                  <div className="wt-compare-item">
                    <b>拒绝黑箱加权，只刻画下行风险分布（Growth-at-Risk）</b>
                    <p>
                      Welch &amp; Goyal (2008) 证实单一宏观指标很难稳定跑赢样本外择时；而 Adrian, Boyarchenko &amp; Giannone (2019, AER) 表明，金融条件与信用利差收紧对<strong>市场下行左尾风险（暴跌/深回撤概率）</strong>有显著解释力。因此本面板定位为“风险环境底色”，用 6 个独立指示灯和红灯计数代替黑箱总分。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>严格按真实发布时间对齐 + 因果历史分位</b>
                    <p>
                      所有 FRED 宏观序列均按官方发布时刻截断（如联储 H.4.1 周三数据于周四 16:30 ET 才可见，芝加哥联储 NFCI 周五数据于次周三 09:30 ET 才可见），10 年历史分位仅使用截至当日的历史窗口、缺失值绝不前向填充，杜绝未来函数。
                    </p>
                  </div>
                </div>
              </div>

              <div className="wt-explain-section">
                <h4>二、各分项关键口径与反直觉风险点</h4>
                <div className="wt-compare-list">
                  <div className="wt-compare-item">
                    <b>① 净流动性（WALCL − TGA − ON RRP）与管道压力</b>
                    <p>
                      净流动性属于从业者经验口径（用于衡量美联储扩表/缩表与财政部发债吸水的净效应），必须配合银行准备金（WRESBAL）与货币市场管道利差（<code>SOFR − IORB</code>）交叉验证。当 <code>SOFR &gt; IORB</code> 时意味着隔夜融资成本突破准备金利率，属于最直接的短期资金管道紧绷信号。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>③ 为什么信用利差处于 10 年极低分位（&lt; 10%）反而标黄？</b>
                    <p>
                      Gilchrist &amp; Zakrajšek (2012, AER) 与 López-Salido et al. (2017, QJE) 发现：当信用利差极度压缩至历史 10% 以下时，往往意味着信贷定价过于乐观、风险补偿过薄，随后 1–2 年反而容易出现信用反转与增长放缓，因此低分位提示“过热谨慎”而非标绿。同时因 FRED 的 ICE 高收益 OAS 授权窗口仅近 3 年，10 年分位自动采用 40 年完整的 Moody&apos;s BAA10Y 口径计算。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>④ 10Y−3M 衰退概率与「倒挂解除 ≠ 风险解除」</b>
                    <p>
                      采用纽约联储单变量 Probit 基准模型 Φ(-0.5333 − 0.6330 × (10Y−3M))（Estrella &amp; Mishkin 1998）。历史上衰退往往发生在收益率曲线<strong>结束倒挂并重新陡峭化（降息初期）</strong>的 6 个月内，因此近 6 个月曾倒挂时仍保持黄灯提醒。另引入 10 年期 TIPS 实际利率（DFII10），回应 Asness (2003) 对纯名义 Fed Model 通胀错配的批评。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>⑤ 全市场基准 ETF 广度与 ⑥ VRP 方差溢价</b>
                    <p>
                      绝不用用户自选池冒充全市场广度，而是独立缓存只读基准 ETF：<code>SPY</code>（标普500）、<code>QQQ</code>（纳指100）、<code>RSP/SPY</code>（等权参与度）、<code>IWM/SPY</code>（小盘风险偏好）、<code>HYG/IEF</code>（高收益债/国债偏好）。方差风险溢价 <code>VRP ≈ VIX² − (SPY 20日年化波动)²</code> 转负代表真实波动击穿期权定价（Bollerslev et al. 2009）；若信用利差与高波动同时亮红灯，将触发流动性螺旋警报（Brunnermeier &amp; Pedersen 2009）。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>刻意不纳入的数据：M2 与 FINRA 融资余额</b>
                    <p>
                      美联储 M2 在 2020 年 5 月更改统计定义产生不可比断点，且与美股中短期相关性极弱；FINRA 融资余额滞后近 1 个月发布，属强滞后指标，故二者均不纳入决策底色。
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <footer className="modal-footer">
          <span>{macro?.disclaimer ?? "仅作市场整体风险环境参考，不构成投资建议。"}</span>
          <button type="button" className="button primary" onClick={onClose}>
            知道了
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
