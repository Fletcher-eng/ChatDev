"""Core Arena tests: indicators, data parsing, settlement edge cases, and the no peeking guarantee."""

import re

import pytest

from trading_arena import data as D
from trading_arena import indicators as I
from trading_arena.scenario import Params, Setup, build_scenarios, pick_indices, snapshot_text
from trading_arena.settle import LOSS, TIMEOUT, WIN, bet_payoff, settle

DASH = re.compile(r"[\-‐-―−]")


def candle(t, o, h, low, c, v=1.0):
    return D.Candle(t, o, h, low, c, v)


def setup(ref=100.0, stop=95.0, rr=2.0, horizon=5, fee=0.001, slip=0.0):
    target = ref + rr * (ref - stop)
    return Setup(ref, stop, target, 3.0, rr, horizon, fee, slip)


# ------------------------------------------------------------------ indicators

def test_sma_and_roc():
    assert I.sma([1, 2, 3, 4], 2) == 3.5
    assert I.sma([1, 2], 10) == 1.5
    assert I.roc([100, 110], 1) == pytest.approx(10.0)
    assert I.roc([100], 5) == 0.0


def test_atr_of_constant_range_candles():
    candles = [candle(i, 100, 101, 99, 100) for i in range(40)]
    assert I.atr(candles, 14) == pytest.approx(2.0)


def test_rsi_extremes():
    assert I.rsi([float(i) for i in range(1, 40)]) == 100.0
    assert I.rsi([float(40 - i) for i in range(40)]) == pytest.approx(0.0)
    assert I.rsi([5.0] * 30) == 50.0


def test_swing_reports_how_long_ago():
    candles = [candle(i, 10, 10 + (5 if i == 3 else 0), 9, 10) for i in range(10)]
    hh, ll, since_hh, since_ll = I.swing(candles, 10)
    assert hh == 15 and since_hh == 6 and ll == 9


# ------------------------------------------------------------------ settlement

def test_clean_win_and_r_values():
    s = setup()
    future = [candle(1, 100, 104, 98, 103), candle(2, 103, 112, 102, 111)]
    out = settle(s, future)
    assert out.result == WIN and out.k == 1 and out.bars == 2
    assert out.r_gross == pytest.approx(2.0)
    assert out.r_net < out.r_gross


def test_clean_loss():
    out = settle(setup(), [candle(1, 100, 101, 96, 97), candle(2, 97, 98, 94, 95)])
    assert out.result == LOSS and out.k == 1
    assert out.r_gross == pytest.approx(-1.0)


def test_same_candle_touching_both_counts_as_loss():
    out = settle(setup(), [candle(1, 100, 111, 94, 100)])
    assert out.result == LOSS


def test_timeout_exits_at_last_close():
    future = [candle(i, 100, 101, 99, 100.5) for i in range(1, 8)]
    out = settle(setup(horizon=5), future)
    assert out.result == TIMEOUT and out.k == 4
    assert out.exit == pytest.approx(100.5)


def test_target_after_the_horizon_does_not_count():
    future = [candle(i, 100, 101, 99, 100) for i in range(1, 5)] + [candle(5, 100, 120, 99, 118)]
    out = settle(setup(horizon=4), future)
    assert out.result == TIMEOUT


def test_target_on_the_last_allowed_candle_counts():
    future = [candle(i, 100, 101, 99, 100) for i in range(1, 4)] + [candle(4, 100, 120, 99, 118)]
    assert settle(setup(horizon=4), future).result == WIN


def test_gap_down_through_the_stop_on_a_later_candle_is_worse_than_one_r():
    out = settle(setup(), [candle(1, 100, 101, 98, 99), candle(2, 90, 91, 88, 89)])
    assert out.result == LOSS and out.k == 1
    assert out.exit == pytest.approx(90.0)  # filled at the open, below the stop
    assert out.r_gross == pytest.approx(-2.0)


def test_opening_below_the_stop_at_entry_costs_only_fees():
    # We enter at that same open, so there is nothing left to lose except costs.
    out = settle(setup(), [candle(1, 90, 91, 88, 89)])
    assert out.result == LOSS and out.k == 0
    assert out.r_gross == pytest.approx(0.0) and out.r_net < 0


def test_gap_up_through_the_target_is_a_win():
    out = settle(setup(), [candle(1, 112, 115, 111, 114)])
    assert out.result == WIN and out.k == 0


def test_slippage_makes_entry_and_stop_exit_worse():
    s = setup(slip=0.001)
    out = settle(s, [candle(1, 100, 101, 94, 95)])
    assert out.entry == pytest.approx(100.1)
    assert out.exit == pytest.approx(95 * 0.999)


def test_settle_needs_future_candles():
    with pytest.raises(ValueError):
        settle(setup(), [])


# ------------------------------------------------------------------ payoffs

def test_payoffs_are_zero_sum_between_bull_and_bear():
    s = setup()
    for future in (
        [candle(1, 100, 112, 99, 111)],
        [candle(1, 100, 101, 94, 95)],
        [candle(i, 100, 101, 99, 100.8) for i in range(1, 6)],
    ):
        out = settle(s, future)
        assert bet_payoff("bull", 1.5, out, 2.0) == pytest.approx(-bet_payoff("bear", 1.5, out, 2.0))


def test_payoff_values():
    s = setup()
    win = settle(s, [candle(1, 100, 112, 99, 111)])
    loss = settle(s, [candle(1, 100, 101, 94, 95)])
    assert bet_payoff("bull", 2.0, win, 2.0) == pytest.approx(4.0)
    assert bet_payoff("bear", 2.0, win, 2.0) == pytest.approx(-4.0)
    assert bet_payoff("bull", 2.0, loss, 2.0) == pytest.approx(-2.0)
    assert bet_payoff("bear", 2.0, loss, 2.0) == pytest.approx(2.0)


# ------------------------------------------------------------------ setup maths

def test_base_rate_and_breakeven_with_costs():
    s = setup(ref=100, stop=95, fee=0.001, slip=0.0005)
    assert s.base_rate == pytest.approx(1 / 3)
    assert s.cost_r == pytest.approx((2 * 0.001 + 2 * 0.0005) * 100 / 5)
    assert s.breakeven_p == pytest.approx((1 + s.cost_r) / 3)
    assert s.breakeven_p > s.base_rate


# ------------------------------------------------------------------ scenarios and no peeking

def test_scenarios_are_spaced_and_deterministic():
    ds = D.synthetic(1500, seed=3)
    params = Params.for_interval(ds.interval_s)
    a = pick_indices(len(ds.candles), 30, params, seed=5)
    assert a == pick_indices(len(ds.candles), 30, params, seed=5)
    assert all(b - x >= params.horizon + 1 for x, b in zip(a, a[1:]))
    assert min(a) >= params.warmup and max(a) + params.horizon < len(ds.candles)


def test_scenario_shape():
    ds = D.synthetic(1200, seed=4)
    params = Params.for_interval(ds.interval_s)
    scenarios = build_scenarios(ds, 10, params, seed=2)
    assert len(scenarios) == 10
    for sc in scenarios:
        assert sc.window[-1] is ds.candles[sc.index]
        assert len(sc.reveal()) == params.horizon
        assert sc.reveal()[0].t == ds.candles[sc.index + 1].t
        assert sc.setup.rr == pytest.approx(2.0)
        assert sc.setup.stop < sc.setup.ref_price < sc.setup.target


def test_snapshot_never_contains_the_future():
    ds = D.synthetic(1200, seed=9)
    params = Params.for_interval(ds.interval_s)
    scenarios = build_scenarios(ds, 6, params, seed=1)
    for sc in scenarios:
        # poison the hidden future with an absurd sentinel price and volume
        sc._future = [D.Candle(c.t, 987654.0, 987655.0, 987653.0, 987654.0, 555555.0) for c in sc._future]
        text = snapshot_text(sc)
        assert "987654" not in text and "987655" not in text and "555555" not in text


def test_snapshot_depends_only_on_the_visible_window_and_setup():
    ds = D.synthetic(1200, seed=11)
    params = Params.for_interval(ds.interval_s)
    sc = build_scenarios(ds, 1, params, seed=1)[0]
    before = snapshot_text(sc)
    sc._future = list(reversed(sc._future))
    assert snapshot_text(sc) == before


def test_snapshot_hides_identity_and_has_no_dashes():
    ds = D.synthetic(1200, seed=12)
    ds.label = "BTCUSD daily"
    params = Params.for_interval(ds.interval_s)
    for sc in build_scenarios(ds, 8, params, seed=3):
        text = snapshot_text(sc)
        assert not DASH.search(text), [ln for ln in text.splitlines() if DASH.search(ln)][:3]
        assert "$" not in text
        assert "BTC" not in text.upper().replace("BACK", "")
        assert not re.search(r"\b(19|20)\d{2}\b", text)  # no calendar years
        assert "latest close is 100" in text and "TARGET" in text and "STOP" in text


# ------------------------------------------------------------------ data

def test_clean_candles_sorts_dedupes_and_repairs():
    rows = [candle(3, 10, 11, 9, 10), candle(1, 10, 9, 11, 10), candle(1, 10, 12, 8, 10),
            candle(2, 0, 1, 1, 1), candle(4, float("nan"), 1, 1, 1)]
    out = D.clean_candles(rows)
    assert [c.t for c in out] == [1, 3]
    assert out[0].h == 12 and out[0].l == 8  # the later duplicate wins


def test_csv_round_trip_and_flexible_headers(tmp_path):
    ds = D.synthetic(200, seed=1)
    path = tmp_path / "x.csv"
    D.save_csv(path, ds.candles)
    loaded = D.load_csv(path)
    assert len(loaded.candles) == 200 and loaded.interval_s == 86400
    assert loaded.candles[10].c == pytest.approx(ds.candles[10].c)

    alt = tmp_path / "tv.csv"
    alt.write_text("Time,Open,High,Low,Close,Volume\n" + "\n".join(
        f"2024-01-{d:02d}T00:00:00Z,{10 + d},{12 + d},{9 + d},{11 + d},5" for d in range(1, 29)
    ) + "\n" + "\n".join(f"2024-02-{d:02d},{40 + d},{42 + d},{39 + d},{41 + d},5" for d in range(1, 29)))
    tv = D.load_csv(alt)
    assert len(tv.candles) == 56 and tv.interval_s == 86400


def test_csv_errors_are_clear(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="time column"):
        D.load_csv(bad)


def test_time_cell_parsing():
    assert D.parse_time_cell("1700000000") == 1700000000
    assert D.parse_time_cell("1700000000000") == 1700000000
    assert D.parse_time_cell("2024-01-01") == 1704067200
    assert D.parse_time_cell("2024-01-01T00:00:00Z") == 1704067200


def test_exchange_parsers_with_documented_shapes():
    bitstamp = {"data": {"pair": "BTC/USD", "ohlc": [
        {"timestamp": "86400", "open": "1.2", "high": "2", "low": "1", "close": "1.5", "volume": "3"}]}}
    assert D.parse_bitstamp(bitstamp) == [D.Candle(86400, 1.2, 2.0, 1.0, 1.5, 3.0)]
    coinbase = [[86400, 1, 2, 1.2, 1.5, 3]]  # time, low, high, open, close, volume
    assert D.parse_coinbase(coinbase) == [D.Candle(86400, 1.2, 2.0, 1.0, 1.5, 3.0)]
    binance = [[86400000, "1.2", "2", "1", "1.5", "3", 0, "0", 0, "0", "0", "0"]]
    assert D.parse_binance(binance) == [D.Candle(86400, 1.2, 2.0, 1.0, 1.5, 3.0)]


def test_pair_helpers():
    assert D.split_pair("btcusd") == ("BTC", "USD")
    assert D.split_pair("BTC-USD") == ("BTC", "USD")
    assert D.split_pair("ETHUSDT") == ("ETH", "USDT")
    assert D.tv_symbol_hint("bitstamp", "btcusd") == "BITSTAMP:BTCUSD"
    assert D.tv_symbol_hint("binance", "BTCUSD") == "BINANCE:BTCUSDT"
    assert D.tv_symbol_hint("coinbase", "BTC-USD") == "COINBASE:BTCUSD"


def test_bitstamp_fetch_paginates_without_a_network():
    step = 86400
    calls = []

    def fake_http(url, params=None, **_):
        calls.append(params["start"])
        start, end = params["start"], params["end"]
        times = [start + i * step for i in range(3) if start + i * step < end]
        return {"data": {"ohlc": [{"timestamp": str(t), "open": "10", "high": "12", "low": "9",
                                   "close": "11", "volume": "1"} for t in times]}}

    out = D.fetch_candles("bitstamp", "btcusd", step, 0, 8 * step, http=fake_http, pause=0)
    assert [c.t for c in out] == [i * step for i in range(8)]
    assert calls == [0, 3 * step, 6 * step]


def test_coinbase_fetch_windows_without_a_network():
    step = 86400
    seen = []

    def fake_http(url, params=None, **_):
        seen.append((url, params["granularity"]))
        return [[1_700_000_000 + len(seen) * step, 1, 2, 1.2, 1.5, 3]]

    out = D.fetch_candles("coinbase", "BTC-USD", step, 0, 700 * step, http=fake_http, pause=0)
    # 700 daily candles at 300 per request means 3 requests
    assert len(seen) == 3 and len(out) == 3
    assert all(u.endswith("/products/BTC-USD/candles") and g == step for u, g in seen)


def test_fetch_rejects_unknown_source_and_interval():
    with pytest.raises(ValueError):
        D.fetch_candles("nowhere", "btcusd", 86400, 0, 10)
    with pytest.raises(ValueError):
        D.fetch_candles("coinbase", "btcusd", 14400, 0, 10)


def test_synthetic_is_deterministic_and_valid():
    a, b = D.synthetic(300, seed=5), D.synthetic(300, seed=5)
    assert a.candles == b.candles
    assert all(c.l <= min(c.o, c.c) and c.h >= max(c.o, c.c) and c.l > 0 for c in a.candles)
    assert D.synthetic(300, seed=6).candles != a.candles


def test_interval_helpers():
    assert D.parse_interval("1d") == 86400 and D.parse_interval("4H") == 14400
    assert D.interval_label(86400) == "1D" and D.interval_label(3600) == "1h"
    with pytest.raises(ValueError):
        D.parse_interval("3d")
