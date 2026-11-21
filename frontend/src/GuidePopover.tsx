import { useEffect, useRef, useState } from "react";
import { HelpCircle, X } from "lucide-react";
import { fmt, type Dashboard } from "./types";

type Curve = Dashboard["curve"] | undefined;

/** 顶部美债收益率看板的可点击二级解读卡片 */
export function MacroStripWithGuide({ curve }: { curve: Curve }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const updatePos = () => {
      const rect = btnRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(540, window.innerWidth - 24);
      const centerLeft = rect.left + rect.width / 2 - width / 2;
      const left = Math.max(12, Math.min(centerLeft, window.innerWidth - width - 12));
      setPos({ top: Math.round(rect.bottom + 8), left: Math.round(left) });
    };
    updatePos();
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("resize", updatePos);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", updatePos);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const spread = curve?.spread_bp;
  const chg21 = curve?.ten_change_bp;
  const liveSummary = (() => {
    const parts: string[] = [];
    if (spread != null) {
      parts.push(
        spread < 0
          ? `10Y-2Y 为 ${fmt(spread, 0)}bp（曲线倒挂，短端资金偏紧，需留意宏观放缓风险）`
          : `10Y-2Y 为 +${fmt(spread, 0)}bp（利率曲线为正，未倒挂）`,
      );
    }
    if (chg21 != null) {
      if (chg21 <= -10) {
        parts.push(
          `近 21 日 10Y 下行 ${fmt(Math.abs(chg21), 0)}bp，长端利率回落，通常对美股成长股估值偏友好`,
        );
      } else if (chg21 >= 10) {
        parts.push(
          `近 21 日 10Y 上行 +${fmt(chg21, 0)}bp，长端利率走高，高估值成长股往往承压`,
        );
      } else {
        parts.push(
          `近 21 日 10Y 变动 ${chg21 >= 0 ? "+" : ""}${fmt(chg21, 0)}bp，利率整体平稳`,
        );
      }
    }
    return parts.length
      ? parts.join("；") + "。"
      : "正在等待美国财政部最新日度国债收益率数据。";
  })();

  return (
    <div className="macro-wrap" ref={wrapRef}>
      <button
        ref={btnRef}
        type="button"
        className={`macro-strip ${open ? "active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="查看美债收益率看板含义说明"
        title={`点击查看美债利率解读 · 来源：${curve?.source ?? "等待数据"} · 观察日：${curve?.as_of ?? "暂无"}`}
      >
        <span>
          美债2Y <b>{fmt(curve?.two_year, 2)}%</b>
        </span>
        <span>
          10Y <b>{fmt(curve?.ten_year, 2)}%</b>
        </span>
        <span>
          10Y-2Y{" "}
          <b>
            {curve?.spread_bp != null && curve.spread_bp >= 0 ? "+" : ""}
            {fmt(curve?.spread_bp, 0)}bp
          </b>
        </span>
        <span>
          10Y近21日{" "}
          <b>
            {curve?.ten_change_bp != null && curve.ten_change_bp >= 0
              ? "+"
              : ""}
            {fmt(curve?.ten_change_bp, 0)}bp
          </b>
        </span>
        {(curve?.refresh_failed || (curve?.as_of && !curve.fresh)) && (
          <em className="macro-warn">
            {curve?.refresh_failed ? "更新失败" : "利率已过期"}
          </em>
        )}
        <HelpCircle size={13} className="macro-help-ico" />
      </button>

      {open && pos && (
        <div
          className="guide-popover macro-popover"
          style={{ top: pos.top, left: pos.left }}
          role="region"
          aria-label="美债收益率看板解读"
        >
          <div className="guide-pop-head">
            <div>
              <b>美债收益率看板怎么看</b>
              <small>
                来源：{curve?.source ?? "美国财政部"} · 观察日：
                {curve?.as_of ?? "待更新"}（100bp = 1%）
              </small>
            </div>
            <button
              type="button"
              className="legend-close-btn"
              onClick={() => setOpen(false)}
              aria-label="关闭美债解读"
            >
              <X size={15} />
            </button>
          </div>

          <p className="guide-live-note">{liveSummary}</p>

          <div className="guide-grid">
            <div className="guide-item">
              <div className="guide-item-head">
                <b>美债 2Y（2年期收益率）</b>
                <em>当前 {fmt(curve?.two_year, 2)}%</em>
              </div>
              <p>
                反映市场对美联储<strong>短期政策利率与降息/加息</strong>的预期。2Y 走低通常代表降息预期升温，走高代表短期资金偏紧。
              </p>
            </div>
            <div className="guide-item">
              <div className="guide-item-head">
                <b>美债 10Y（10年期收益率）</b>
                <em>当前 {fmt(curve?.ten_year, 2)}%</em>
              </div>
              <p>
                全球资产的<strong>“无风险利率锚”</strong>。10Y 走低利好科技/成长股估值扩张；页面中的「股债利差」即 <code>盈利收益率(100/PE) − 10Y</code>。
              </p>
            </div>
            <div className="guide-item">
              <div className="guide-item-head">
                <b>10Y-2Y（期限利差）</b>
                <em>
                  {spread != null && spread >= 0 ? "+" : ""}
                  {fmt(spread, 0)}bp
                </em>
              </div>
              <p>
                长债减短债。正常应为正值；若变为负数（<strong>倒挂</strong>），说明短端利率高于长端，历史上常预示信贷收紧或经济放缓担忧。
              </p>
            </div>
            <div className="guide-item">
              <div className="guide-item-head">
                <b>10Y 近21日变动</b>
                <em>
                  {chg21 != null && chg21 >= 0 ? "+" : ""}
                  {fmt(chg21, 0)}bp
                </em>
              </div>
              <p>
                近约 1 个月长端利率的变化幅度。<strong>负数</strong>表示利率回落、美股估值压力减轻；<strong>大正数</strong>表示利率急升、容易压制高 PE 标的。
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type IndicatorTab = "ma" | "momentum" | "wave" | "quant";

const INDICATOR_TABS: { id: IndicatorTab; label: string }[] = [
  { id: "ma", label: "均线与布林" },
  { id: "momentum", label: "MACD与RSI" },
  { id: "wave", label: "波浪与趋势" },
  { id: "quant", label: "点位与评分" },
];

const INDICATOR_GUIDES: Record<
  IndicatorTab,
  { name: string; tag: string; desc: string }[]
> = {
  ma: [
    {
      name: "MA20（20日均线）",
      tag: "橙线 · 短线",
      desc: "近 1 个月平均持仓成本。股价站稳 MA20 上方且均线向上说明短线偏强，跌破常意味着短线走弱。",
    },
    {
      name: "MA50（50日均线）",
      tag: "蓝线 · 中期",
      desc: "波段多空分水岭。机构常用 MA50 观察中期趋势强弱，上升趋势中回踩 MA50 往往是关键支撑位。",
    },
    {
      name: "MA200（200日年线）",
      tag: "灰线 · 牛熊线",
      desc: "长期牛熊分界线。价格位于 MA200 上方且 MA20 > MA50 > MA200（多头排列）代表长期趋势最健康。",
    },
    {
      name: "BOLL（布林带）",
      tag: "上 / 中 / 下轨",
      desc: "中轨看方向，上轨看短线超买/压力，下轨看回踩支撑；带宽收口代表蓄势，开口放大代表变盘波动加剧。",
    },
  ],
  momentum: [
    {
      name: "MACD 柱与快慢线",
      tag: "动能强弱",
      desc: "柱状图在零轴上方放大表示多头动能加速，零轴下方放大表示空头占优；快线（橙）上穿慢线（蓝）为金叉偏多，下穿为死叉偏弱。",
    },
    {
      name: "RSI(14) 相对强弱",
      tag: "0–100 · 默认关闭",
      desc: "衡量涨跌节奏是否过热：> 70 为超买警戒区（不宜追高），< 30 为超卖区（留意企稳反弹），50 为多空强弱中轴。",
    },
    {
      name: "成交量与 RVOL 量比",
      tag: "量价配合",
      desc: "RVOL = 当日成交量 ÷ 近 20 日均量。上涨伴随 RVOL ≥ 1.5（放量）更可靠；缩量（< 0.7）突破需防假突破。",
    },
  ],
  wave: [
    {
      name: "平行趋势通道",
      tag: "绿升 / 红降 / 蓝震荡",
      desc: "由近 90 日收盘回归拟合。顺势交易重在上升通道下轨附近低吸、上轨不追高；下降通道内以观望防守为主。",
    },
    {
      name: "波浪胶囊（起 / 1–5浪 / A–C浪）",
      tag: "因果识别",
      desc: "1/3/5 浪为顺势推动（第 3 浪通常动能最强），2/4 浪为回调蓄势，A-B-C 为三浪调整；虚线与 * 号表示当前波段仍在运行、尚未反转确认。",
    },
    {
      name: "道氏高低结构",
      tag: "高抬 / 低抬 / 高低 / 低低",
      desc: "高点抬高 + 低点抬高 = 健康多头结构；高点降低 + 低点降低 = 空头结构；「结构防守」即前低支撑，跌破代表趋势破坏。",
    },
    {
      name: "斐波那契波浪测算",
      tag: "0.618 / 1.0 / 1.618",
      desc: "2 浪常回撤 1 浪的 0.382–0.618 区间；3 浪主升常见 1.618 倍扩展；C 浪调整常见与 A 浪 1.0 倍等长支撑。",
    },
  ],
  quant: [
    {
      name: "参考买点 / 卖点 / 止损",
      tag: "右侧卡片 & 左侧虚线",
      desc: "结合均线、布林、20/60 日高低点、枢轴与 ATR14 因果测算的计划参考区，点击「采纳计划价」可快速预填个人计划。",
    },
    {
      name: "盈亏比（如 1.8:1）",
      tag: "赔率性价比",
      desc: "（第一卖点 − 现价）÷（现价 − 参考止损）。盈亏比越高越划算，通常 ≥ 1.5:1 代表潜在空间相对回撤风险更占优。",
    },
    {
      name: "日线结构评分（0–100）",
      tag: "趋势40% 动量30% 量价30%",
      desc: "≥ 70 分判定结构偏强，≤ 30 分判定偏弱，中间为中性。若近期缺交易日或样本不足 200 根日线会诚实显示待确认。",
    },
    {
      name: "ATR14 / Z-score / 时序排名 / 量价相关",
      tag: "辅助风控算子",
      desc: "ATR14 为近 14 日平均波幅（衡量正常震荡幅度）；Z-score 衡量偏离 20 日均线的标准差倍数；时序排名反映 20 日内所处高低分位；量价相关衡量近 20 日放量是否同步上涨。",
    },
  ],
};

/** K 线工具栏右侧的技术指标二级分类说明菜单 */
export function IndicatorGuideMenu() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<IndicatorTab>("ma");
  const [pos, setPos] = useState<{
    top: number;
    right: number;
    maxHeight: number;
  } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const updatePos = () => {
      const rect = btnRef.current?.getBoundingClientRect();
      if (!rect) return;
      const right = Math.max(12, window.innerWidth - rect.right);
      const preferredTop = rect.bottom + 6;
      const estimatedHeight = 472;
      const maxTop = Math.max(72, window.innerHeight - estimatedHeight - 16);
      const top = Math.min(preferredTop, maxTop);
      const maxHeight = Math.max(240, window.innerHeight - top - 16);
      setPos({
        top: Math.round(top),
        right: Math.round(right),
        maxHeight: Math.round(maxHeight),
      });
    };
    updatePos();
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("resize", updatePos);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", updatePos);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="indicator-guide-wrap" ref={wrapRef}>
      <button
        ref={btnRef}
        type="button"
        className={`toolbar-help-btn ${open ? "active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="查看K线与技术指标说明"
        title="查看均线、MACD、RSI、波浪与趋势指标怎么看"
      >
        <HelpCircle size={13} />
        <span>指标</span>
      </button>

      {open && pos && (
        <div
          className="guide-popover indicator-popover"
          style={{ top: pos.top, right: pos.right, maxHeight: pos.maxHeight }}
          role="region"
          aria-label="技术指标看盘说明"
        >
          <div className="guide-pop-head">
            <b>技术指标怎么看</b>
            <button
              type="button"
              className="legend-close-btn"
              onClick={() => setOpen(false)}
              aria-label="关闭指标说明"
            >
              <X size={15} />
            </button>
          </div>

          <div className="guide-subtabs" role="tablist" aria-label="指标分类">
            {INDICATOR_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={tab === t.id ? "active" : ""}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="guide-list">
            {INDICATOR_GUIDES[tab].map((item) => (
              <div className="guide-row" key={item.name}>
                <div className="guide-item-head">
                  <b>{item.name}</b>
                  <em>{item.tag}</em>
                </div>
                <p>{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
