from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from fastapi.testclient import TestClient

from signaldesk.app import create_app
from signaldesk.calendar import NY
from signaldesk.demo import make_benchmark_bars
from signaldesk.indicators import enrich
from signaldesk.macro import (
    MACRO_BENCHMARK_SYMBOLS,
    _net_liquidity_series,
    causal_percentile,
    compute_macro_regime,
    demo_fred_bundle,
    parse_fred_csv,
    published_series,
    release_datetime,
)
from signaldesk.models import Settings
from signaldesk.research import (
    curve_summary,
    nyfed_recession_prob_pct,
    research_context,
    treasury_curve_observations,
    treasury_observations,
)


def test_parse_fred_csv_skips_missing_without_forward_fill():
    raw = (
        "observation_date,VIXCLS\n"
        "2026-11-16,18.2\n"
        "2026-11-17,.\n"
        "2026-11-18,21.5\n"
        "bad-date,19.0\n"
        "2026-11-19,\n"
        "2026-11-20,24.1\n"
    )
    rows = parse_fred_csv(raw, min_date=date(2026, 11, 17))
    assert rows == [["2026-11-18", 21.5], ["2026-11-20", 24.1]]


def test_release_alignment_blocks_unpublished_h41_and_nfci():
    # H.4.1 周三观测 2026-11-18 应于周四 2026-11-19 16:30 ET 才可见
    rel_walcl = release_datetime("WALCL", date(2026, 11, 18))
    assert rel_walcl == datetime(2026, 11, 19, 16, 30, tzinfo=NY)

    raw_walcl = [["2026-11-11", 6_700_000.0], ["2026-11-18", 6_741_452.0]]
    before_h41 = published_series("WALCL", raw_walcl, datetime(2026, 11, 19, 16, 0, tzinfo=NY))
    after_h41 = published_series("WALCL", raw_walcl, datetime(2026, 11, 19, 16, 30, tzinfo=NY))
    assert [d for d, _, _ in before_h41] == ["2026-11-11"]
    assert [d for d, _, _ in after_h41] == ["2026-11-11", "2026-11-18"]

    # NFCI 周五观测 2026-11-13 应于次周周三 2026-11-18 09:30 ET 才可见
    rel_nfci = release_datetime("NFCI", date(2026, 11, 13))
    assert rel_nfci == datetime(2026, 11, 18, 9, 30, tzinfo=NY)

    raw_nfci = [["2026-11-06", -0.45], ["2026-11-13", -0.48]]
    before_nfci = published_series("NFCI", raw_nfci, datetime(2026, 11, 17, 18, 0, tzinfo=NY))
    after_nfci = published_series("NFCI", raw_nfci, datetime(2026, 11, 18, 9, 30, tzinfo=NY))
    assert [d for d, _, _ in before_nfci] == ["2026-11-06"]
    assert [d for d, _, _ in after_nfci] == ["2026-11-06", "2026-11-13"]


def test_net_liquidity_unit_conversion_and_no_cross_week_ffill():
    now = datetime(2026, 11, 23, 12, 0, tzinfo=NY)
    walcl = published_series("WALCL", [["2026-11-11", 6_700_000.0], ["2026-11-18", 6_741_452.0]], now)
    # 故意缺少 2026-11-11 的 TGA，检验不跨周前向填充
    tga = published_series("WTREGEN", [["2026-11-18", 916_613.0]], now)
    # RRPONTSYD 单位直接是十亿美元（Billions），严禁再除 1000
    rrp = published_series("RRPONTSYD", [["2026-11-18", 0.401]], now)

    net = _net_liquidity_series(walcl, tga, rrp)
    assert len(net) == 1
    assert net[0][0] == "2026-11-18"
    assert abs(net[0][1] - 5824.44) < 0.02


def test_causal_percentile_no_future_leakage_and_min_samples():
    assert causal_percentile([1.0, 2.0, 3.0], lookback=100, min_samples=10) is None
    base = [float(i) for i in range(1, 121)]
    pct_before = causal_percentile(base, lookback=100, min_samples=50)
    assert pct_before is not None
    # 修改历史之外的未来值，不得影响原历史截断点的因果分位
    extended = base + [9999.0] * 30
    pct_hist_slice = causal_percentile(extended[: len(base)], lookback=100, min_samples=50)
    assert pct_hist_slice == pct_before


def test_credit_pillar_falls_back_to_baa10y_and_marks_overheated_yellow():
    now = datetime(2026, 11, 23, 12, 0, tzinfo=NY)
    days = pd.bdate_range(end="2026-11-20", periods=1200)
    # BAA10Y 4 年完整历史，末端跌到极低分位（过热）
    baa_rows = [[d.date().isoformat(), round(2.8 - i * 0.0012, 3)] for i, d in enumerate(days)]
    # BAMLH0A0HYM2 仅 600 条（< 2200，模拟 FRED 3 年授权窗口）
    hy_rows = [[d.date().isoformat(), 3.0] for d in days[-600:]]

    regime = compute_macro_regime(
        {"source": "FRED", "fetched_at": now.isoformat(), "series": {"BAA10Y": baa_rows, "BAMLH0A0HYM2": hy_rows}},
        {},
        {},
        now,
    )
    credit = next(p for p in regime["pillars"] if p["key"] == "credit")
    assert credit["percentile_10y"] is not None and credit["percentile_10y"] < 10.0
    assert credit["light"] == "yellow"
    assert "过热" in credit["summary"]

    # 若 HY OAS 近 13 周内（约 50 个交易日）走阔 >= 100bp，立刻翻红
    hy_widen = [[d.date().isoformat(), 3.0 if i < 550 else 4.35] for i, d in enumerate(days[-600:])]
    regime_red = compute_macro_regime(
        {"source": "FRED", "fetched_at": now.isoformat(), "series": {"BAA10Y": baa_rows, "BAMLH0A0HYM2": hy_widen}},
        {},
        {},
        now,
    )
    credit_red = next(p for p in regime_red["pillars"] if p["key"] == "credit")
    assert credit_red["light"] == "red"


def test_treasury_3m_probit_and_real_yield_gap():
    xml = (
        b'<feed xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
        b'xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">'
        b"<entry><content><m:properties><d:NEW_DATE>2026-11-20T00:00:00</d:NEW_DATE>"
        b"<d:BC_3MONTH>4.30</d:BC_3MONTH><d:BC_2YEAR>4.10</d:BC_2YEAR><d:BC_10YEAR>4.55</d:BC_10YEAR>"
        b"</m:properties></content></entry></feed>"
    )
    # 原二元组函数完全向后兼容
    assert treasury_observations(xml, date(2026, 11, 20)) == {"2026-11-20": (4.1, 4.55)}
    full = treasury_curve_observations(xml, date(2026, 11, 20))
    assert full == {"2026-11-20": (4.1, 4.55, 4.3)}

    summary = curve_summary(full)
    assert summary["three_month"] == 4.3
    assert summary["spread_10y_3m_bp"] == 25.0
    assert summary["recession_prob_12m_pct"] is not None

    # Probit 单调性：倒挂越深衰退概率越高，且 0 利差处约 29.7%
    p_inv = nyfed_recession_prob_pct(-1.5)
    p_zero = nyfed_recession_prob_pct(0.0)
    p_pos = nyfed_recession_prob_pct(1.5)
    assert p_inv is not None and p_zero is not None and p_pos is not None
    assert p_inv > p_zero > p_pos
    assert 29.0 <= p_zero <= 30.5

    now = datetime(2026, 11, 23, 12, 0, tzinfo=NY)
    val = {"pe_ttm": 25.0, "pb": 5.0, "fetched_at": now.isoformat()}
    ctx = research_context(val, summary, now, False, real_ten_year=2.1, real_rate_fresh=True)
    assert ctx["earnings_yield_pct"] == 4.0
    assert abs(ctx["yield_gap_pp"] - (-0.55)) < 1e-9
    assert ctx["real_ten_year"] == 2.1
    assert abs(ctx["real_yield_gap_pp"] - 1.9) < 1e-9

    # 兼容不含 three_month 的旧缓存
    legacy_curve = curve_summary({"2026-11-20": (4.1, 4.55)})
    assert legacy_curve["three_month"] is None
    assert legacy_curve["spread_10y_3m_bp"] is None


def _make_trend_frames(now: datetime, uptrend: bool) -> dict[str, pd.DataFrame]:
    rules = Settings().rules
    frames = {}
    for sym in MACRO_BENCHMARK_SYMBOLS:
        bars = make_benchmark_bars(sym, now)
        if not uptrend and sym in {"SPY.US", "QQQ.US"}:
            # 末端下跌跌破 MA200
            for idx in range(max(0, len(bars) - 65), len(bars)):
                factor = 1.0 - 0.0042 * (idx - (len(bars) - 65))
                bars[idx]["close"] = round(bars[idx]["close"] * factor, 3)
                bars[idx]["open"] = bars[idx]["close"]
                bars[idx]["high"] = bars[idx]["close"] * 1.005
                bars[idx]["low"] = bars[idx]["close"] * 0.995
        frames[sym] = enrich(bars, "day", now, rules)
    return frames


def test_four_quadrants_and_alerts():
    now = datetime(2026, 11, 23, 12, 0, tzinfo=NY)
    easy_fred = demo_fred_bundle(now)
    up_frames = _make_trend_frames(now, uptrend=True)
    down_frames = _make_trend_frames(now, uptrend=False)
    curve = curve_summary({"2026-11-20": (3.8, 4.2, 3.9)})

    # 1. 宽松 + 多头 = 顺风
    r_tail = compute_macro_regime(easy_fred, curve, up_frames, now, demo=True)
    assert r_tail["quadrant"]["code"] == "tailwind"

    # 2. 宽松 + 承压 = 修复
    r_rep = compute_macro_regime(easy_fred, curve, down_frames, now, demo=True)
    assert r_rep["quadrant"]["code"] == "repair"

    # 构造流动性偏紧 + 高波动 + 信用走阔 + 近期刚解除倒挂
    tight_series = {k: [list(pair) for pair in v] for k, v in easy_fred["series"].items()}
    tight_series["SOFR"][-1][1] = tight_series["IORB"][-1][1] + 0.08  # +8bp 管道压力
    tight_series["VIXCLS"][-1][1] = 31.5  # > 25 红灯
    tight_series["BAMLH0A0HYM2"][-1][1] = tight_series["BAMLH0A0HYM2"][-70][1] + 1.5  # 走阔 +150bp 红灯
    # 20 天前曾倒挂，最新刚转正 -> 应标黄且提示「倒挂解除≠风险解除」
    tight_series["T10Y3M"][-25][1] = -0.35
    tight_series["T10Y3M"][-1][1] = 0.15
    tight_fred = {**easy_fred, "series": tight_series}

    # 3. 偏紧 + 多头 = 背离
    r_div = compute_macro_regime(tight_fred, curve, up_frames, now, demo=True)
    assert r_div["quadrant"]["code"] == "divergence"

    # 4. 偏紧 + 承压 = 逆风 + 联动警报
    r_head = compute_macro_regime(tight_fred, curve, down_frames, now, demo=True)
    assert r_head["quadrant"]["code"] == "headwind"
    assert r_head["risk_gauge"]["red_count"] >= 3
    joined_alerts = " ".join(r_head["alerts"])
    assert "流动性螺旋" in joined_alerts
    assert "SOFR" in joined_alerts
    assert "倒挂解除" in joined_alerts


def test_api_macro_bootstrap_privacy_and_no_rating_interference(tmp_path):
    app = create_app(tmp_path, background=False)
    with TestClient(app) as client:
        boot = client.get("/api/bootstrap")
        assert boot.status_code == 200
        payload = boot.json()

        assert "macro" in payload
        macro = payload["macro"]
        assert macro["available"] is True
        assert macro["source"] == "合成宏观数据"
        assert len(macro["pillars"]) == 6
        assert macro["quadrant"]["code"] in {"tailwind", "divergence", "repair", "headwind"}
        assert payload["curve"]["three_month"] is not None
        assert payload["curve"]["real_ten_year"] is not None

        # 确认基准 ETF 不污染用户自选股列表
        user_symbols = {s["symbol"] for s in payload["stocks"]}
        assert "RSP.US" not in user_symbols
        assert "IEF.US" not in user_symbols

        # /api/macro 接口
        res_macro = client.get("/api/macro")
        assert res_macro.status_code == 200
        assert res_macro.json()["rule_version"] == macro["rule_version"]

        # 脱敏预览透传 macro_regime 且不泄露持仓金额/股数/成本
        prev = client.get("/api/analysis/preview/NVDA.US")
        assert prev.status_code == 200
        snap = prev.json()
        assert snap["macro_regime"]["available"] is True
        assert len(snap["macro_regime"]["pillars"]) == 6
        assert snap["research"]["real_ten_year"] is not None
        assert snap["research"]["real_yield_gap_pp"] is not None
        for private_key in ("cost_price", "broker_quantity", "long_quantity", "net_assets"):
            assert private_key not in snap

        # 验证第一阶段市场大势变更不影响个股评级
        monitor = app.state.monitor
        nvda_alloc = next(a for a in monitor.portfolio() if a.symbol == "NVDA.US")
        rating_before = monitor.stock(nvda_alloc)["forecast"]["rating"]["score"]

        # 人为把宏观推向逆风红灯，确认个股评级完全不受干扰
        monitor.demo_fred["series"]["VIXCLS"][-1][1] = 45.0
        monitor.demo_fred["series"]["SOFR"][-1][1] = 6.5
        monitor.macro_cache = None
        rating_after = monitor.stock(nvda_alloc)["forecast"]["rating"]["score"]
        assert rating_after == rating_before
