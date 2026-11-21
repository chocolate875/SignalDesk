"""美股证券类型识别与 ETF/指数基金专属因果指标计算。

将宽基指数 ETF、行业/主题 ETF、商品/债基 ETF、杠杆/反向 ETF 以及封闭式基金/组合
与单一上市公司（个股）明确区分，避免把券商接口中失真的基金主体 PE/PB 当作公司盈利分析。
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from .forecast import _contiguous_regular_tail
from .indicators import finite

# 已知高频美股 ETF / 信托 / 基金精确元数据映射表：
# symbol -> (asset_type, type_label, benchmark, leverage, is_inverse)
KNOWN_FUNDS: dict[str, tuple[str, str, str, float | None, bool]] = {
    # 宽基与跨市场指数 ETF
    "QQQ.US": ("broad_etf", "宽基指数 ETF", "追踪纳斯达克 100 指数", None, False),
    "QQQM.US": ("broad_etf", "宽基指数 ETF", "追踪纳斯达克 100 指数（低费率）", None, False),
    "SPY.US": ("broad_etf", "宽基指数 ETF", "追踪标普 500 指数", None, False),
    "VOO.US": ("broad_etf", "宽基指数 ETF", "追踪标普 500 指数", None, False),
    "IVV.US": ("broad_etf", "宽基指数 ETF", "追踪标普 500 指数", None, False),
    "SPLG.US": ("broad_etf", "宽基指数 ETF", "追踪标普 500 指数", None, False),
    "VTI.US": ("broad_etf", "宽基指数 ETF", "追踪美国全市场股票指数", None, False),
    "VT.US": ("broad_etf", "宽基指数 ETF", "追踪全球股票指数", None, False),
    "DIA.US": ("broad_etf", "宽基指数 ETF", "追踪道琼斯工业 30 指数", None, False),
    "IWM.US": ("broad_etf", "宽基指数 ETF", "追踪罗素 2000 小盘股指数", None, False),
    "SCHD.US": ("broad_etf", "红利指数 ETF", "追踪道琼斯美国红利 100 指数", None, False),
    "VUG.US": ("broad_etf", "风格指数 ETF", "追踪美国大盘成长指数", None, False),
    "VTV.US": ("broad_etf", "风格指数 ETF", "追踪美国大盘价值指数", None, False),
    "EWT.US": ("broad_etf", "区域指数 ETF", "追踪 MSCI 台湾指数", None, False),
    "EWY.US": ("broad_etf", "区域指数 ETF", "追踪 MSCI 韩国指数", None, False),
    "EWJ.US": ("broad_etf", "区域指数 ETF", "追踪 MSCI 日本指数", None, False),
    "FXI.US": ("broad_etf", "区域指数 ETF", "追踪富时中国大盘 50 指数", None, False),
    "KWEB.US": ("sector_etf", "行业主题 ETF", "追踪中概互联网指数", None, False),
    "MCHI.US": ("broad_etf", "区域指数 ETF", "追踪 MSCI 中国指数", None, False),
    "EEM.US": ("broad_etf", "区域指数 ETF", "追踪新兴市场指数", None, False),
    "ALLW.US": ("broad_etf", "多资产配置 ETF", "桥水全天候跨资产配置策略", None, False),
    # 行业与主题 ETF
    "SOXX.US": ("sector_etf", "行业主题 ETF", "追踪美国半导体指数", None, False),
    "SMH.US": ("sector_etf", "行业主题 ETF", "追踪全球半导体龙头指数", None, False),
    "XLK.US": ("sector_etf", "行业主题 ETF", "追踪标普科技板块指数", None, False),
    "XLF.US": ("sector_etf", "行业主题 ETF", "追踪标普金融板块指数", None, False),
    "XLE.US": ("sector_etf", "行业主题 ETF", "追踪标普能源板块指数", None, False),
    "XLV.US": ("sector_etf", "行业主题 ETF", "追踪标普医疗保健板块指数", None, False),
    "XLI.US": ("sector_etf", "行业主题 ETF", "追踪标普工业板块指数", None, False),
    "XLY.US": ("sector_etf", "行业主题 ETF", "追踪标普可选消费板块指数", None, False),
    "XLP.US": ("sector_etf", "行业主题 ETF", "追踪标普必选消费板块指数", None, False),
    "XLU.US": ("sector_etf", "行业主题 ETF", "追踪标普公用事业板块指数", None, False),
    "XLC.US": ("sector_etf", "行业主题 ETF", "追踪标普通信服务板块指数", None, False),
    "XLB.US": ("sector_etf", "行业主题 ETF", "追踪标普原材料板块指数", None, False),
    "XLRE.US": ("sector_etf", "行业主题 ETF", "追踪标普房地产板块指数", None, False),
    "XBI.US": ("sector_etf", "行业主题 ETF", "追踪生物科技等权指数", None, False),
    "XME.US": ("sector_etf", "行业主题 ETF", "追踪标普金属与矿业指数", None, False),
    "GDX.US": ("sector_etf", "行业主题 ETF", "追踪黄金矿业股指数", None, False),
    "COPX.US": ("sector_etf", "行业主题 ETF", "追踪全球铜矿企业主题指数", None, False),
    "DRAM.US": ("sector_etf", "行业主题 ETF", "追踪存储芯片产业链主题", None, False),
    "SHLD.US": ("sector_etf", "行业主题 ETF", "追踪全球国防科技主题指数", None, False),
    "ARKK.US": ("sector_etf", "主动主题 ETF", "主动管理颠覆式创新股票篮子", None, False),
    "BOTZ.US": ("sector_etf", "行业主题 ETF", "追踪机器人与人工智能主题", None, False),
    "AIQ.US": ("sector_etf", "行业主题 ETF", "追踪人工智能与科技主题", None, False),
    # 商品、债券与另类资产 ETF
    "GLD.US": ("commodity_etf", "商品 ETF", "追踪现货黄金价格（实物黄金信托）", None, False),
    "IAU.US": ("commodity_etf", "商品 ETF", "追踪现货黄金价格（实物黄金信托）", None, False),
    "GLDM.US": ("commodity_etf", "商品 ETF", "追踪现货黄金价格（低费率黄金信托）", None, False),
    "SLV.US": ("commodity_etf", "商品 ETF", "追踪现货白银价格（实物白银信托）", None, False),
    "USO.US": ("commodity_etf", "商品 ETF", "追踪 WTI 原油期货合约表现", None, False),
    "UNG.US": ("commodity_etf", "商品 ETF", "追踪美国天然气期货合约表现", None, False),
    "TLT.US": ("commodity_etf", "美债 ETF", "追踪 20 年期以上美国国债指数", None, False),
    "IEF.US": ("commodity_etf", "美债 ETF", "追踪 7–10 年期美国国债指数", None, False),
    "SHY.US": ("commodity_etf", "美债 ETF", "追踪 1–3 年期美国国债指数", None, False),
    "SGOV.US": ("commodity_etf", "短债 ETF", "追踪 0–3 个月美国短期国库券", None, False),
    "BND.US": ("commodity_etf", "债券 ETF", "追踪美国综合投资级债券市场", None, False),
    "IBIT.US": ("commodity_etf", "数字资产 ETF", "追踪比特币现货价格表现", None, False),
    "FBTC.US": ("commodity_etf", "数字资产 ETF", "追踪比特币现货价格表现", None, False),
    "ETHA.US": ("commodity_etf", "数字资产 ETF", "追踪以太坊现货价格表现", None, False),
    # 杠杆与反向 ETF（每日再平衡，存在波动损耗）
    "TQQQ.US": ("leveraged_etf", "3X 杠杆 ETF", "每日 3 倍做多纳斯达克 100 指数", 3.0, False),
    "QLD.US": ("leveraged_etf", "2X 杠杆 ETF", "每日 2 倍做多纳斯达克 100 指数", 2.0, False),
    "SQQQ.US": ("leveraged_etf", "3X 反向 ETF", "每日 3 倍做空纳斯达克 100 指数", -3.0, True),
    "QID.US": ("leveraged_etf", "2X 反向 ETF", "每日 2 倍做空纳斯达克 100 指数", -2.0, True),
    "PSQ.US": ("leveraged_etf", "1X 反向 ETF", "每日 1 倍做空纳斯达克 100 指数", -1.0, True),
    "UPRO.US": ("leveraged_etf", "3X 杠杆 ETF", "每日 3 倍做多标普 500 指数", 3.0, False),
    "SSO.US": ("leveraged_etf", "2X 杠杆 ETF", "每日 2 倍做多标普 500 指数", 2.0, False),
    "SPXU.US": ("leveraged_etf", "3X 反向 ETF", "每日 3 倍做空标普 500 指数", -3.0, True),
    "SDS.US": ("leveraged_etf", "2X 反向 ETF", "每日 2 倍做空标普 500 指数", -2.0, True),
    "SH.US": ("leveraged_etf", "1X 反向 ETF", "每日 1 倍做空标普 500 指数", -1.0, True),
    "SOXL.US": ("leveraged_etf", "3X 杠杆 ETF", "每日 3 倍做多美国半导体指数", 3.0, False),
    "SOXS.US": ("leveraged_etf", "3X 反向 ETF", "每日 3 倍做空美国半导体指数", -3.0, True),
    "USD.US": ("leveraged_etf", "2X 杠杆 ETF", "每日 2 倍做多美国半导体指数", 2.0, False),
    "NVDL.US": ("leveraged_etf", "2X 单股杠杆 ETF", "每日 2 倍做多 NVDA 单股表现", 2.0, False),
    "NVDU.US": ("leveraged_etf", "2X 单股杠杆 ETF", "每日 2 倍做多 NVDA 单股表现", 2.0, False),
    "NVDX.US": ("leveraged_etf", "2X 单股杠杆 ETF", "每日 2 倍做多 NVDA 单股表现", 2.0, False),
    "TSLL.US": ("leveraged_etf", "2X 单股杠杆 ETF", "每日 2 倍做多 TSLA 单股表现", 2.0, False),
    "SNXX.US": ("leveraged_etf", "2X 单股杠杆 ETF", "每日 2 倍做多 SNDK 单股表现", 2.0, False),
    "MUU.US": ("leveraged_etf", "2X 单股杠杆 ETF", "每日 2 倍做多 MU 单股表现", 2.0, False),
    "RAM.US": ("leveraged_etf", "2X 杠杆 ETF", "每日 2 倍做多存储芯片主题", 2.0, False),
    "KORU.US": ("leveraged_etf", "3X 杠杆 ETF", "每日 3 倍做多 MSCI 韩国指数", 3.0, False),
    "YINN.US": ("leveraged_etf", "3X 杠杆 ETF", "每日 3 倍做多富时中国 50 指数", 3.0, False),
    "YANG.US": ("leveraged_etf", "3X 反向 ETF", "每日 3 倍做空富时中国 50 指数", -3.0, True),
    "TMF.US": ("leveraged_etf", "3X 杠杆 ETF", "每日 3 倍做多 20 年期以上美债", 3.0, False),
    "TMV.US": ("leveraged_etf", "3X 反向 ETF", "每日 3 倍做空 20 年期以上美债", -3.0, True),
    "UVXY.US": ("leveraged_etf", "波动率杠杆 ETF", "追踪 VIX 短期期货 1.5 倍波动率", 1.5, False),
    "VXX.US": ("commodity_etf", "波动率 ETN", "追踪 VIX 短期波动率期货（含展期损耗）", None, False),
    # 封闭式基金 / 组合产品
    "DXYZ.US": ("fund", "封闭式基金", "持有一篮子未上市科技独角兽股权（关注二级市场折溢价）", None, False),
}

_LEVERAGE_RE = re.compile(
    r"\b([123](?:\.5)?)\s*X\b|ULTRAPRO|\bULTRA\b|两倍|三倍|2倍|3倍|杠杆",
    re.IGNORECASE,
)
_INVERSE_RE = re.compile(r"\b(SHORT|BEAR|INVERSE)\b|反向|做空", re.IGNORECASE)
_ETF_ISSUER_RE = re.compile(
    r"\b(ISHARES|ISHRS|SPDR|INVESCO|VANGUARD|PROSHARES|DIREXION|GLOBAL\s*X|VANECK|ROUNDHILL|GRANITESHARES|WISDOMTREE|KRANESHARES|FIRST\s*TRUST|DEFIANCE|T-REX|SCHWAB|PIMCO|YIELDMAX|GRAYSCALE|BITWISE|AMPLIFY|ARK)\b",
    re.IGNORECASE,
)
_ETF_KEYWORD_RE = re.compile(
    r"\b(ETF|ETN|TRGTETF|TRUST|FUND\s+LP|SHARES\s+TR|SILVER\s+TR|GOLD\s+SHARES|INDEX\s+FUND)\b|指数基金|交易型基金|基金|信托",
    re.IGNORECASE,
)
_BROAD_INDEX_RE = re.compile(
    r"\b(S&P\s*500|NASDAQ|DOW\s+JONES|DJIA|RUSSELL|MSCI|FTSE|TOTAL\s+STOCK|TOTAL\s+MARKET|ALL\s*WORLD|ALL\s*WEATHER)\b|宽基|标普|纳斯达克|纳指|道琼斯|罗素",
    re.IGNORECASE,
)
_COMMODITY_RE = re.compile(
    r"\b(GOLD|SILVER|OIL|CRUDE|NATURAL\s+GAS|TREASURY|BOND|FIXED\s+INCOME|BITCOIN|ETHEREUM|CRYPTO|VIX)\b|黄金|白银|原油|国债|美债|债券|比特币|以太坊",
    re.IGNORECASE,
)
_CONCEPT_SYMBOL_RE = re.compile(r"^CP\d+\.US$")


def _risk_notice(asset_type: str, leverage: float | None, is_inverse: bool) -> str:
    if asset_type == "leveraged_etf":
        if is_inverse:
            mult = f"{abs(leverage):g} 倍" if leverage else ""
            return f"属于{mult}反向做空杠杆工具，按日重置杠杆并存在显著波动复利损耗，仅适合短期波段或对冲，不宜作为长期价值底仓。"
        mult = f"{abs(leverage):g} 倍" if leverage else ""
        return f"属于{mult}杠杆交易型基金，按日再平衡在高波动震荡市中会产生复利损耗，仅适合波段跟踪并须严守止损位。"
    if asset_type == "commodity_etf":
        return "商品/债基/另类资产 ETF 无上市公司盈利与市盈率，核心受宏观利率、供需周期与展期成本驱动。"
    if asset_type == "fund":
        return "属于多标的组合或封闭式基金，需关注底层组合持仓与二级市场折溢价，不适用单一公司 PE/PB 口径。"
    if asset_type in {"broad_etf", "sector_etf"}:
        return "指数/行业 ETF 持有成分股篮子，券商单股口径 PE/PB 易失真；本栏自动改用回撤分位、历史波动率与美债利率环境评估。"
    return ""


def classify_instrument(symbol: str, name: str = "") -> dict:
    """确定性识别美股标的是上市公司个股，还是宽基/行业/商品/杠杆 ETF 或基金。"""
    sym = (symbol or "").strip().upper()
    clean_name = (name or "").strip()

    if sym in KNOWN_FUNDS:
        asset_type, type_label, benchmark, leverage, is_inverse = KNOWN_FUNDS[sym]
        return {
            "asset_type": asset_type,
            "type_label": type_label,
            "benchmark": benchmark,
            "is_fund": True,
            "is_leveraged": asset_type == "leveraged_etf",
            "is_inverse": is_inverse,
            "leverage": leverage,
            "company_valuation_applicable": False,
            "risk_notice": _risk_notice(asset_type, leverage, is_inverse),
        }

    # 长桥概念组合指数（如 CP00084.US）
    if _CONCEPT_SYMBOL_RE.match(sym):
        return {
            "asset_type": "fund",
            "type_label": "主题组合指数",
            "benchmark": f"主题组合篮子（{clean_name or sym}）",
            "is_fund": True,
            "is_leveraged": False,
            "is_inverse": False,
            "leverage": None,
            "company_valuation_applicable": False,
            "risk_notice": _risk_notice("fund", None, False),
        }

    upper_name = clean_name.upper()
    has_etf_word = bool(_ETF_KEYWORD_RE.search(upper_name)) or "ETF" in upper_name
    has_issuer = bool(_ETF_ISSUER_RE.search(upper_name))
    # 排除单一上市银行/金融公司名中含 Trust 的误判（如 Northern Trust）
    is_bank_trust = "TRUST" in upper_name and any(
        w in upper_name for w in ("BANK", "BANCORP", "FINANCIAL", "NORTHERN TRUST", "REALTY")
    )
    looks_like_fund = (has_etf_word and not is_bank_trust) or (
        has_issuer and not any(w in upper_name for w in ("INC", "CORP", "PLC", "LTD"))
    )

    if looks_like_fund:
        lev_match = _LEVERAGE_RE.search(upper_name)
        inv_match = _INVERSE_RE.search(upper_name)
        if lev_match or inv_match:
            mult: float | None = None
            if lev_match:
                if lev_match.group(1):
                    mult = float(lev_match.group(1))
                elif "ULTRAPRO" in upper_name or "三倍" in clean_name or "3倍" in clean_name:
                    mult = 3.0
                elif "ULTRA" in upper_name or "两倍" in clean_name or "2倍" in clean_name:
                    mult = 2.0
            is_inv = bool(inv_match)
            if is_inv and mult is not None:
                mult = -abs(mult)
            elif is_inv:
                mult = -1.0
            mult_prefix = f"{abs(mult):g}X " if mult else ""
            t_label = f"{mult_prefix}反向 ETF" if is_inv else f"{mult_prefix}杠杆 ETF"
            return {
                "asset_type": "leveraged_etf",
                "type_label": t_label,
                "benchmark": f"杠杆/反向交易型基金（{clean_name}）",
                "is_fund": True,
                "is_leveraged": True,
                "is_inverse": is_inv,
                "leverage": mult,
                "company_valuation_applicable": False,
                "risk_notice": _risk_notice("leveraged_etf", mult, is_inv),
            }
        if _COMMODITY_RE.search(upper_name):
            return {
                "asset_type": "commodity_etf",
                "type_label": "商品/债基 ETF",
                "benchmark": f"大宗商品或债券类基金（{clean_name}）",
                "is_fund": True,
                "is_leveraged": False,
                "is_inverse": False,
                "leverage": None,
                "company_valuation_applicable": False,
                "risk_notice": _risk_notice("commodity_etf", None, False),
            }
        if _BROAD_INDEX_RE.search(upper_name):
            return {
                "asset_type": "broad_etf",
                "type_label": "宽基指数 ETF",
                "benchmark": f"宽基/区域指数基金（{clean_name}）",
                "is_fund": True,
                "is_leveraged": False,
                "is_inverse": False,
                "leverage": None,
                "company_valuation_applicable": False,
                "risk_notice": _risk_notice("broad_etf", None, False),
            }
        return {
            "asset_type": "sector_etf",
            "type_label": "指数/主题 ETF",
            "benchmark": f"指数/主题篮子基金（{clean_name}）",
            "is_fund": True,
            "is_leveraged": False,
            "is_inverse": False,
            "leverage": None,
            "company_valuation_applicable": False,
            "risk_notice": _risk_notice("sector_etf", None, False),
        }

    return {
        "asset_type": "stock",
        "type_label": "个股",
        "benchmark": "",
        "is_fund": False,
        "is_leveraged": False,
        "is_inverse": False,
        "leverage": None,
        "company_valuation_applicable": True,
        "risk_notice": "",
    }


def compute_fund_metrics(frame: pd.DataFrame | None, summary: dict) -> dict:
    """严格因果计算 ETF/指数基金核心特征：52周回撤、年内分位、年化波动率与最大回撤。

    仅使用已确认连续常规日线，绝不补零或前向填充；窗口不足的指标诚实返回 None。
    """
    empty = {
        "available": False,
        "window_days": 0,
        "high_52w": None,
        "low_52w": None,
        "drawdown_from_high_pct": None,
        "range_position_pct": None,
        "max_drawdown_pct": None,
        "hv20_pct": None,
        "hv60_pct": None,
        "ma200_gap_pct": None,
        "return_20d_pct": None,
        "return_60d_pct": None,
        "return_252d_pct": None,
    }
    tail = _contiguous_regular_tail(frame)
    if len(tail) < 20:
        return empty

    win = tail.tail(252)
    closes = win["close"].to_numpy(dtype=float)
    highs = win["high"].to_numpy(dtype=float)
    lows = win["low"].to_numpy(dtype=float)
    close_now = finite(closes[-1])
    if close_now is None or close_now <= 0:
        return empty

    high_52w = finite(float(np.max(highs))) if len(win) >= 60 else None
    low_52w = finite(float(np.min(lows))) if len(win) >= 60 else None

    drawdown_from_high_pct = (
        round((close_now / high_52w - 1.0) * 100.0, 2)
        if high_52w is not None and high_52w > 0
        else None
    )
    range_position_pct = (
        round(float(np.clip((close_now - low_52w) / (high_52w - low_52w) * 100.0, 0.0, 100.0)), 1)
        if high_52w is not None and low_52w is not None and high_52w > low_52w
        else None
    )

    # 窗口内最大峰谷回撤（严格因果）
    max_drawdown_pct = None
    if len(win) >= 60:
        running_peak = np.maximum.accumulate(closes)
        dd_series = (closes / running_peak - 1.0) * 100.0
        mdd = finite(float(np.min(dd_series)))
        if mdd is not None:
            max_drawdown_pct = round(mdd, 2)

    # 历史年化波动率（对数收益率标准差 × sqrt(252)）
    log_rets = np.diff(np.log(closes))
    hv20_pct = None
    if len(log_rets) >= 20:
        v20 = finite(float(np.std(log_rets[-20:], ddof=1) * math.sqrt(252.0) * 100.0))
        if v20 is not None:
            hv20_pct = round(v20, 1)
    hv60_pct = None
    if len(log_rets) >= 60:
        v60 = finite(float(np.std(log_rets[-60:], ddof=1) * math.sqrt(252.0) * 100.0))
        if v60 is not None:
            hv60_pct = round(v60, 1)

    indicators = (summary or {}).get("indicators") or {}
    ma200 = finite(indicators.get("ma200"))
    ma200_gap_pct = (
        round((close_now / ma200 - 1.0) * 100.0, 2)
        if ma200 is not None and ma200 > 0
        else None
    )

    def period_return(days: int) -> float | None:
        if len(closes) <= days:
            return None
        base = finite(closes[-1 - days])
        if base is None or base <= 0:
            return None
        return round((close_now / base - 1.0) * 100.0, 2)

    return {
        "available": True,
        "window_days": int(len(win)),
        "high_52w": round(high_52w, 2) if high_52w is not None else None,
        "low_52w": round(low_52w, 2) if low_52w is not None else None,
        "drawdown_from_high_pct": drawdown_from_high_pct,
        "range_position_pct": range_position_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "hv20_pct": hv20_pct,
        "hv60_pct": hv60_pct,
        "ma200_gap_pct": ma200_gap_pct,
        "return_20d_pct": period_return(20),
        "return_60d_pct": period_return(60),
        "return_252d_pct": period_return(251),
    }
