import { useEffect, useRef, useState } from "react";
import { Compass, HelpCircle, X } from "lucide-react";
import { fmt, type ComexGold, type Dashboard } from "./types";

type Curve = Dashboard["curve"] | undefined;

/** 顶部美债收益率与 COMEX 黄金看板的可点击二级解读卡片 */
export function MacroStripWithGuide({
  curve,
  gold,
  onOpenMacroPanel,
}: {
  curve: Curve;
  gold?: ComexGold;
  onOpenMacroPanel?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const updatePos = () => {
      const rect = btnRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(560, window.innerWidth - 24);
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
  const spread103m = curve?.spread_10y_3m_bp;
  const recProb = curve?.recession_prob_12m_pct;
  const real10y = curve?.real_ten_year;
  const chg21 = curve?.ten_change_bp;
  const goldReady = Boolean(gold?.available && gold.price != null);
  const goldChg = gold?.change_pct;
  const goldChg21 = gold?.change_21d_pct;
  const warnReasons: string[] = [];
  if (curve?.refresh_failed) warnReasons.push("美债利率更新失败");
  else if (curve?.as_of && !curve.fresh) warnReasons.push("美债利率已过期");
  if (gold?.refresh_failed) warnReasons.push("COMEX黄金更新失败");
  else if (gold?.as_of && !gold.fresh) warnReasons.push("COMEX黄金行情已过期");

  const liveSummary = (() => {
    const parts: string[] = [];
    if (spread103m != null) {
      parts.push(
        spread103m < 0
          ? `10Y-3M 为 ${fmt(spread103m, 0)}bp（倒挂${recProb != null ? `，NY Fed 12M 衰退概率 ${fmt(recProb, 1)}%` : ""}）`
          : `10Y-3M 为 +${fmt(spread103m, 0)}bp（未倒挂${recProb != null ? `，NY Fed 12M 衰退概率 ${fmt(recProb, 1)}%` : ""}）`,
      );
    } else if (spread != null) {
      parts.push(
        spread < 0
          ? `10Y-2Y 为 ${fmt(spread, 0)}bp（曲线倒挂，短端资金偏紧，需留意宏观放缓风险）`
          : `10Y-2Y 为 +${fmt(spread, 0)}bp（利率曲线为正，未倒挂）`,
      );
    }
    if (real10y != null) {
      parts.push(`10Y 实际利率（TIPS）为 ${fmt(real10y, 2)}%`);
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
    if (goldReady && gold) {
      const chgTxt =
        goldChg != null ? `（日 ${goldChg >= 0 ? "+" : ""}${fmt(goldChg, 2)}%` : "（";
      const chg21Txt =
        goldChg21 != null
          ? `${goldChg != null ? "，" : ""}21日 ${goldChg21 >= 0 ? "+" : ""}${fmt(goldChg21, 1)}%）`
          : goldChg != null
            ? "）"
            : "";
      parts.push(
        `COMEX 黄金主力现报 $${fmt(gold.price, 2)}/盎司${chgTxt}${chg21Txt}${gold.real_rate_linkage ? `，${gold.real_rate_linkage}` : ""}`,
      );
    }
    return parts.length
      ? parts.join("；") + "。"
      : "正在等待美国财政部国债收益率与 COMEX 黄金公开数据。";
  })();

  const goldTitlePart = goldReady
    ? `COMEX黄金 $${fmt(gold?.price, 2)}/oz${goldChg != null ? ` (${goldChg >= 0 ? "+" : ""}${fmt(goldChg, 2)}%)` : ""}`
    : "COMEX黄金待同步";

  return (
    <div className="macro-wrap" ref={wrapRef}>
      <button
        ref={btnRef}
        type="button"
        className={`macro-strip compact ${open ? "active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="查看美债收益率与COMEX黄金看板说明"
        title={`美债2Y ${fmt(curve?.two_year, 2)}% · 10Y ${fmt(curve?.ten_year, 2)}% · ${goldTitlePart} · 点击查看完整利率与黄金联动解读`}
      >
        <span className="macro-strip-seg">
          美债10Y <b>{fmt(curve?.ten_year, 2)}%</b>
        </span>
        <span className="macro-strip-sep" aria-hidden="true">
          ·
        </span>
        <span className="macro-strip-seg macro-strip-gold">
          COMEX金{" "}
          <b>{goldReady ? `$${fmt(gold?.price, 0)}` : "—"}</b>
          {goldReady && goldChg != null && (
            <span
              className={`macro-gold-chg ${goldChg >= 0 ? "quote-up" : "quote-down"}`}
            >
              ({goldChg >= 0 ? "+" : ""}
              {fmt(goldChg, 1)}%)
            </span>
          )}
        </span>
        {warnReasons.length > 0 && (
          <span
            className="macro-warn-dot"
            title={warnReasons.join("；")}
          />
        )}
        <HelpCircle size={13} className="macro-help-ico" aria-hidden="true" />
      </button>

      {open && pos && (
        <div
          className="guide-popover macro-popover"
          style={{ top: pos.top, left: pos.left }}
          role="region"
          aria-label="美债收益率与COMEX黄金看板解读"
        >
          <div className="guide-pop-head">
            <div>
              <b>美债收益率与 COMEX 黄金看板</b>
              <small>
                美债：{curve?.source ?? "美国财政部"}（{curve?.as_of ?? "待更新"}，100bp = 1%）· 期金：
                {gold?.source ?? "COMEX"}（{gold?.as_of ?? "待更新"}）
              </small>
            </div>
            <button
              type="button"
              className="legend-close-btn"
              onClick={() => setOpen(false)}
              aria-label="关闭美债与黄金解读"
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
            <div className="guide-item">
              <div className="guide-item-head">
                <b>10Y-3M 与 NY Fed 衰退概率</b>
                <em>
                  {spread103m != null
                    ? `${spread103m >= 0 ? "+" : ""}${fmt(spread103m, 0)}bp · ${recProb != null ? `${fmt(recProb, 1)}%` : "—"}`
                    : "待更新"}
                </em>
              </div>
              <p>
                相比 10Y-2Y，纽约联储官方模型以 <code>10Y − 3M</code>（当前 3M{" "}
                {fmt(curve?.three_month, 2)}%）估算未来 12 个月衰退概率；注意历史上<strong>倒挂解除≠风险解除</strong>。
              </p>
            </div>
            <div className="guide-item">
              <div className="guide-item-head">
                <b>10Y 实际利率（TIPS DFII10）</b>
                <em>{real10y != null ? `${fmt(real10y, 2)}%` : "待同步"}</em>
              </div>
              <p>
                扣除通胀预期后的真实资金成本。右侧个股卡片同时对照名义与实际利率利差，避免单纯 Fed Model 的通胀错配。
              </p>
            </div>
            <div className="guide-item guide-item-wide gold-guide-card">
              <div className="guide-item-head">
                <b>COMEX 黄金主力与 10Y TIPS 实际利率联动</b>
                <em>
                  {goldReady
                    ? `$${fmt(gold?.price, 2)}/盎司${goldChg != null ? ` (${goldChg >= 0 ? "+" : ""}${fmt(goldChg, 2)}%)` : ""}`
                    : "待同步"}
                </em>
              </div>
              <div className="gold-guide-metrics">
                <span>
                  近21日{" "}
                  <b
                    className={
                      goldChg21 == null
                        ? ""
                        : goldChg21 >= 0
                          ? "quote-up"
                          : "quote-down"
                    }
                  >
                    {goldChg21 != null
                      ? `${goldChg21 >= 0 ? "+" : ""}${fmt(goldChg21, 2)}%`
                      : "—"}
                  </b>
                </span>
                <span>
                  昨收 <b>{gold?.prev_close != null ? `$${fmt(gold.prev_close, 2)}` : "—"}</b>
                </span>
                <span>
                  日内区间{" "}
                  <b>
                    {gold?.day_low != null && gold?.day_high != null
                      ? `$${fmt(gold.day_low, 2)}–$${fmt(gold.day_high, 2)}`
                      : "—"}
                  </b>
                </span>
                {gold?.real_rate_linkage && (
                  <span className="gold-linkage-pill">{gold.real_rate_linkage}</span>
                )}
                {(gold?.refresh_failed || (gold?.as_of && !gold.fresh)) && (
                  <span className="gold-warn-pill">
                    {gold?.refresh_failed ? "刷新失败·展示缓存" : "行情已过期"}
                  </span>
                )}
              </div>
              <p>
                {gold?.real_rate_note ??
                  "黄金为无息避险与抗通胀资产，传统上与 10Y TIPS 实际利率负相关；若在高实际利率下金价仍强势，往往指向央行购金或地缘避险溢价主导。"}
              </p>
            </div>
          </div>

          {onOpenMacroPanel && (
            <div className="guide-pop-foot">
              <button
                type="button"
                className="wt-detail-link"
                onClick={() => {
                  setOpen(false);
                  onOpenMacroPanel();
                }}
              >
                <Compass size={14} aria-hidden="true" />
                <span>打开「市场大势与宏观流动性全景面板」（六分项与四象限）</span>
              </button>
            </div>
          )}
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
      tag: "动能强弱 · 默认关闭",
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
      desc: "由近 126 日（约 6 个月）收盘线性回归拟合，与默认看盘窗口及筹码分布同频。顺势重在上升通道下轨附近低吸、上轨不追高；下降通道内以观望防守为主。",
    },
    {
      name: "波浪胶囊（起 / 1–5浪 / A–C浪）",
      tag: "因果识别",
      desc: "1/3/5 浪为顺势推动（第 3 浪通常动能最强），2/4 浪为回调蓄势，A-B-C 为三浪调整；虚线与 * 号表示当前波段仍在运行、尚未反转确认。",
    },
    {
      name: "道氏高低结构与趋势失效位",
      tag: "前低失效 / 前高反转",
      desc: "上升趋势中，最近一个已确认波段低点（如 2 浪底）即「前低失效位」——收盘有效跌破代表多头结构破坏；下降趋势则看「前高反转位」——站上前高才算空头反转。它衡量的是大趋势结构是否破坏，与按 ATR14 波动测算的左侧「参考止损」维度不同。",
    },
    {
      name: "斐波那契波浪测算",
      tag: "0.618 / 1.0 / 1.618",
      desc: "2 浪常回撤 1 浪的 0.382–0.618 区间；3 浪主升常见 1.618 倍扩展；C 浪调整常见与 A 浪 1.0 倍等长支撑。",
    },
  ],
  quant: [
    {
      name: "主要突破位 / 主要防守位（▲ / ▼）",
      tag: "筹码 × 波浪共振主线",
      desc: "综合 126 日筹码价值区（VAL/VAH）、上下筹码密集峰、波浪前高/前低与 60 日移动保护位提炼的两条核心战线；若多维度在近距重合则标为「共振突破 / 共振防守」，可信度更高。K 线中买卖参考区以半透明色带呈现，减少横线干扰。",
    },
    {
      name: "筹码分布（Volume Profile · POC / 70%价值区）",
      tag: "主图右侧直方图 · 可开关",
      desc: "基于近 126 个交易日前复权量价按典型价三角加权（90日半衰期）估算各价位累计成交厚度。琥珀柱为核心主筹码峰（POC），蓝灰柱为 70% 价值区（VAL–VAH）；下方密集筹码构成真实承接防守，放量越过上方筹码峰或 VAH 则阻力骤减。",
    },
    {
      name: "参考买区 / 卖区 / 盈亏比",
      tag: "色带区间 & 赔率性价比",
      desc: "结合筹码峰、均线、布林、20/60日高低点与 ATR14 因果测算。盈亏比 =（第一卖点 − 现价）÷（现价 − 参考止损），通常 ≥ 1.5:1 代表赔率较占优。",
    },
    {
      name: "结构评分（fusion-2.0.0）与学术因子",
      tag: "趋势45% 动量40% 平滑量价15%",
      desc: "废弃高噪音单日量价重权，改用多周期趋势连续斜率 + 60日动量 + 10日平滑量价，并叠加 vs SPY 残差动量、FIP 连续度（慢牛 vs 脉冲）与 52 周高点锚定（样本不足 200 根或缺日线时诚实显示待确认）。",
    },
    {
      name: "Yang-Zhang 波动 / 下行 Beta / MAX5 / 日夜拉锯",
      tag: "正交尾部与微结构画像",
      desc: "Yang-Zhang 含隔夜跳空计算无偏波动率并映射「参考敞口系数」；MAX5 检测近月单日急涨彩票过热；下行 Beta 衡量大盘下跌时抗跌度；日夜拉锯识别近 20 日「高开低走」派发特征，与盘外跳空预警联动。",
    },
    {
      name: "个股 vs ETF 基金评估差异",
      tag: "自动分流",
      desc: "个股结合 PE 与股债利差评估；QQQ/SOXX/SPY/GLD 等指数或商品 ETF 不套用失真的基金主体 PE，改用 52 周高点回撤、年内分位、年化波动率与美债利率环境评估；杠杆/反向 ETF 额外提示日度再平衡波动损耗。",
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
