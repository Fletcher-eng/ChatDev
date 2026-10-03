"""Tests for the Data Bot: cleaning, confirmed bars, health checks, saved files, failures and made up data."""

import json
import shutil
import sys
import types
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from algo_lab import data as D
from algo_lab.config import ConfigError, load_config
from algo_lab.synthetic import make_series, make_universe, write_demo

NOW = datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc)  # a Saturday
FIRST = D.OK, D.WARN, D.STOP


@pytest.fixture()
def cfg(tmp_path):
    base = load_config()
    return replace(base, data=replace(base.data, folder=tmp_path / "real", demo_folder=tmp_path / "demo"))


def us_frame(n=500, end=date(2026, 10, 2), seed=1):
    return make_series(n, "us", end, seed)[0]


def crypto_frame(n=500, end=date(2026, 10, 2), seed=1):
    return make_series(n, "crypto", end, seed, vol_scale=2.0)[0]


def yahoo_like(frame, tz):
    """What yfinance returns: capitalised columns, extra columns and a time zone aware index."""
    raw = frame.rename(columns=str.capitalize).copy()
    raw["Dividends"] = 0.0
    raw["Stock Splits"] = 0.0
    raw.index = raw.index.tz_localize(tz)
    raw.index.name = "Date"
    return raw


def broken(frame, row, **cells):
    out = frame.copy()
    for name, value in cells.items():
        out.iloc[row, out.columns.get_loc(name)] = value
    return out


def fake_downloader(calls):
    def download(yahoo_symbol, start, adjusted):
        calls.append((yahoo_symbol, start, adjusted))
        if yahoo_symbol.endswith("-USD"):
            return yahoo_like(crypto_frame(800, end=date(2026, 10, 3)), "UTC")  # includes today's unfinished bar
        return yahoo_like(us_frame(800), "America/New_York")
    return download


def prepared(cfg, frame, symbol="SPY", now=NOW):
    return D.prepare(frame, cfg.asset(symbol), cfg, now, "yahoo")


def assert_no_dashes(text):
    assert "—" not in text and "–" not in text
    assert " - " not in text and " -- " not in text


def test_the_test_clock_is_a_saturday():
    assert NOW.weekday() == 5


# ---------------------------------------------------------------- normalize

def test_normalize_handles_a_yahoo_shaped_frame():
    base = us_frame(30)
    out = D.normalize_frame(yahoo_like(base, "America/New_York"))
    assert list(out.columns) == D.COLUMNS
    assert out.index.tz is None and out.index.name == "date"
    assert list(out.index.date) == list(base.index.date)
    np.testing.assert_allclose(out.to_numpy(), base.to_numpy())


def test_normalize_keeps_the_utc_date_for_crypto():
    base = crypto_frame(30)
    out = D.normalize_frame(yahoo_like(base, "UTC"))
    assert list(out.index.date) == list(base.index.date)


def test_normalize_flattens_two_level_columns():
    wide = us_frame(10).rename(columns=str.capitalize)
    wide.columns = pd.MultiIndex.from_product([wide.columns, ["SPY"]])
    assert list(D.normalize_frame(wide).columns) == D.COLUMNS


def test_normalize_names_a_missing_column():
    with pytest.raises(D.DataError, match="close"):
        D.normalize_frame(us_frame(10).drop(columns=["close"]))


def test_normalize_turns_text_into_missing_numbers():
    raw = us_frame(10).astype(object)
    raw.iloc[3, raw.columns.get_loc("close")] = "n/a"
    out = D.normalize_frame(raw)
    assert np.isnan(out["close"].iloc[3]) and out["close"].notna().sum() == 9


# ---------------------------------------------------------------- clean

def clean(frame):
    return D.clean_bars(frame, 0.05)


def test_good_data_passes_untouched():
    base = us_frame(100)
    out, removed = clean(base)
    assert removed == []
    pd.testing.assert_frame_equal(out, base, check_freq=False)


@pytest.mark.parametrize("edit, reason", [
    (lambda f: broken(f, 5, close=np.nan), "missing price"),
    (lambda f: broken(f, 5, close=np.inf), "missing price"),
    (lambda f: broken(f, 5, volume=np.nan), "missing volume"),
    (lambda f: broken(f, 5, open=0.0), "price at or below zero"),
    (lambda f: broken(f, 5, low=-1.0), "price at or below zero"),
    (lambda f: broken(f, 5, volume=-5.0), "negative volume"),
    (lambda f: broken(f, 5, high=50.0, low=60.0), "high below low"),
    (lambda f: broken(f, 5, close=f.iloc[5]["high"] * 1.01), "open or close outside the high to low range"),
])
def test_each_kind_of_broken_row_is_removed_with_its_reason(edit, reason):
    base = us_frame(50)
    out, removed = clean(edit(base))
    assert removed == [(base.index[5].date(), reason)]
    pd.testing.assert_frame_equal(out, base.drop(base.index[5]), check_freq=False)


def test_rounding_slack_is_tolerated():
    base = us_frame(50)
    out, removed = clean(broken(base, 5, close=base.iloc[5]["high"] * 1.0003))
    assert removed == [] and len(out) == 50


def test_duplicate_dates_keep_the_last_row():
    base = us_frame(20)
    dup = base.iloc[[7]].copy()
    dup["close"] = dup["close"] * 1.0001
    out, removed = clean(pd.concat([base, dup]))
    assert removed == [(base.index[7].date(), "duplicate date")]
    assert len(out) == 20 and out.loc[base.index[7], "close"] == dup.iloc[0]["close"]


def test_unsorted_input_is_sorted():
    base = us_frame(40)
    out, removed = clean(base.iloc[::-1])
    assert removed == [] and out.index.is_monotonic_increasing
    pd.testing.assert_frame_equal(out, base, check_freq=False)


def test_cleaning_never_changes_a_price():
    base = us_frame(60)
    out, _ = clean(broken(base, 9, close=np.nan))
    kept = base.drop(base.index[9])
    assert out.to_numpy().tobytes() == kept.to_numpy().tobytes()


# ---------------------------------------------------------------- confirmed bars

def test_us_bar_is_final_thirty_minutes_after_the_close_in_summer():
    # New York is on summer time in July, so 16:00 there is 20:00 UTC
    assert D.bar_confirmed_at(date(2026, 7, 15), "us", 30) == datetime(2026, 7, 15, 20, 30, tzinfo=timezone.utc)


def test_us_bar_is_final_thirty_minutes_after_the_close_in_winter():
    assert D.bar_confirmed_at(date(2026, 1, 15), "us", 30) == datetime(2026, 1, 15, 21, 30, tzinfo=timezone.utc)


def test_crypto_bar_is_final_after_midnight_utc():
    assert D.bar_confirmed_at(date(2026, 10, 2), "crypto", 30) == datetime(2026, 10, 3, 0, 30, tzinfo=timezone.utc)


def test_unfinished_us_bar_is_dropped_until_it_is_confirmed():
    frame = us_frame(30, end=date(2026, 7, 15))
    kept, dropped = D.drop_unfinished(frame, "us", datetime(2026, 7, 15, 20, 10, tzinfo=timezone.utc), 30)
    assert dropped == [date(2026, 7, 15)] and kept.index[-1].date() == date(2026, 7, 14)
    kept, dropped = D.drop_unfinished(frame, "us", datetime(2026, 7, 15, 20, 31, tzinfo=timezone.utc), 30)
    assert dropped == [] and len(kept) == 30


def test_todays_crypto_bar_is_unfinished_but_yesterdays_is_final():
    frame = crypto_frame(30, end=date(2026, 10, 3))
    kept, dropped = D.drop_unfinished(frame, "crypto", NOW, 30)
    assert dropped == [date(2026, 10, 3)] and kept.index[-1].date() == date(2026, 10, 2)


def test_bars_dated_in_the_future_are_dropped():
    frame = us_frame(30, end=date(2026, 10, 9))
    kept, dropped = D.drop_unfinished(frame, "us", NOW, 30)
    assert kept.index[-1].date() == date(2026, 10, 2) and len(dropped) == 5


def test_an_empty_frame_has_nothing_to_drop():
    kept, dropped = D.drop_unfinished(us_frame(5).iloc[0:0], "us", NOW, 30)
    assert len(kept) == 0 and dropped == []


def test_the_time_must_carry_a_time_zone():
    with pytest.raises(ValueError, match="time zone"):
        D.utc_now(datetime(2026, 1, 1))


# ---------------------------------------------------------------- health checks

def test_clean_us_data_is_ok(cfg):
    _, health = prepared(cfg, us_frame())
    assert health.status == D.OK and health.bars == 500 and health.age_days == 1
    assert health.last == date(2026, 10, 2) and not health.problems and not health.warnings


def test_too_few_bars_stops(cfg):
    _, health = prepared(cfg, us_frame(300))
    assert health.status == D.STOP and "300" in health.problems[0] and "400" in health.problems[0]


@pytest.mark.parametrize("end, status", [
    (date(2026, 10, 2), D.OK),    # Friday, 1 day old
    (date(2026, 9, 29), D.OK),    # Tuesday, 4 days old: the limit for a long weekend
    (date(2026, 9, 28), D.STOP),  # Monday, 5 days old
])
def test_us_staleness(cfg, end, status):
    _, health = prepared(cfg, us_frame(500, end=end))
    assert health.status == status
    if status == D.STOP:
        assert "stale" in health.problems[0]


@pytest.mark.parametrize("end, status", [
    (date(2026, 10, 2), D.OK),
    (date(2026, 10, 1), D.OK),    # 2 days old, the limit
    (date(2026, 9, 30), D.STOP),  # 3 days old
])
def test_crypto_staleness(cfg, end, status):
    _, health = prepared(cfg, crypto_frame(500, end=end), "QNT")
    assert health.status == status


def test_an_unfinished_bar_is_a_note_not_a_problem(cfg):
    frame, health = prepared(cfg, crypto_frame(500, end=date(2026, 10, 3)), "QNT")
    assert health.status == D.OK and health.age_days == 1
    assert "Ignored the unfinished bar for 2026-10-03" in health.notes[0]
    assert frame.index[-1].date() == date(2026, 10, 2)


def test_a_missing_crypto_day_is_a_gap(cfg):
    base = crypto_frame()
    _, health = prepared(cfg, base.drop(base.index[100]), "QNT")
    assert health.status == D.WARN
    assert "1 gap in the history" in health.warnings[0]
    assert f"{base.index[99].date()} to {base.index[101].date()} (2 days apart)" in health.warnings[0]


def test_a_holiday_weekend_is_not_a_gap(cfg):
    base = us_frame()
    _, health = prepared(cfg, base.drop(pd.Timestamp("2026-09-07")))  # Labor Day: Friday to Tuesday is 4 days
    assert health.status == D.OK


def test_a_week_long_hole_in_us_data_is_a_gap(cfg):
    base = us_frame()
    hole = [pd.Timestamp(d) for d in ("2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10")]
    _, health = prepared(cfg, base.drop(hole))
    assert health.status == D.WARN and "(7 days apart)" in health.warnings[0]


PRICE_COLUMNS = ["open", "high", "low", "close"]


def spike(frame, down=0.53, back=0.9):
    """One bad bar: a day far too low, then back near the old level, like a data glitch."""
    out = frame.copy()
    out.loc[out.index[300:], PRICE_COLUMNS] *= back
    out.loc[out.index[300], PRICE_COLUMNS] *= down / back
    return out


def test_a_huge_one_day_move_is_flagged(cfg):
    base = us_frame()
    base.loc[base.index[300:], PRICE_COLUMNS] *= 1.7
    jump = (base["close"].iloc[300] / base["close"].iloc[299] - 1) * 100
    _, health = prepared(cfg, base)
    assert health.status == D.WARN
    assert f"{base.index[300].date()} rose {jump:.1f} percent" in health.warnings[0]
    assert "1 one day move bigger than 40 percent, 0 undone the next day" in health.warnings[0]


def test_a_spike_that_reverses_is_called_a_bad_bar(cfg):
    base = spike(us_frame())
    moves = D.find_extreme_moves(base, 40)
    assert [m.day for m in moves] == [base.index[300].date(), base.index[301].date()]
    assert moves[0].change_pct < -40 and moves[0].next_change_pct > 40
    assert moves[0].undone_next_day is True and moves[1].undone_next_day is False
    _, health = prepared(cfg, base)
    text = health.warnings[0]
    assert "2 one day moves bigger than 40 percent, 1 undone the next day" in text
    assert "fell" in text and "then rose" in text and "python -m algo_lab moves SPY" in text


def test_a_crash_that_stays_is_not_called_undone():
    base = us_frame()
    base.loc[base.index[300:], PRICE_COLUMNS] *= 0.5
    moves = D.find_extreme_moves(base, 40)
    assert len(moves) == 1 and moves[0].undone_next_day is False


def test_a_move_on_the_last_bar_has_no_next_day():
    base = us_frame()
    base.loc[base.index[-1], PRICE_COLUMNS] *= 0.5
    move = D.find_extreme_moves(base, 40)[-1]
    assert move.next_change_pct is None and move.undone_next_day is False
    assert "then" not in D.describe_move(move)


def test_the_moves_table_lists_each_move_with_a_hint():
    base = spike(us_frame())
    text = D.render_moves("SPY", base, 40)
    lines = text.splitlines()
    assert lines[0] == "MOVES BIGGER THAN 40 PERCENT FOR SPY (500 saved bars)"
    assert str(base.index[300].date()) in lines[2] and "a bad bar (undone)" in lines[2]
    assert str(base.index[301].date()) in lines[3] and "the bounce back from the line above" in lines[3]
    assert "hint, not proof" in text
    assert_no_dashes(text)


def test_a_crash_that_stays_is_listed_as_possibly_real():
    base = us_frame()
    base.loc[base.index[300:], PRICE_COLUMNS] *= 0.5
    lines = D.render_moves("SPY", base, 40).splitlines()
    assert str(base.index[300].date()) in lines[2] and "possibly real (it stayed)" in lines[2]


def test_the_moves_table_says_so_when_nothing_moved():
    assert "None." in D.render_moves("SPY", us_frame(), 40)


def test_zero_volume_bars_are_flagged(cfg):
    base = us_frame()
    base.iloc[10:13, base.columns.get_loc("volume")] = 0.0
    _, health = prepared(cfg, base)
    assert health.status == D.WARN and "3 bars with zero volume" in health.warnings[0]


def test_a_few_broken_rows_warn(cfg):
    base = us_frame()
    base.iloc[[10, 11, 12, 13, 14], base.columns.get_loc("close")] = np.nan
    _, health = prepared(cfg, base)
    assert health.status == D.WARN
    assert "Removed 5 broken rows (5 missing price)" in health.warnings[0]


def test_many_broken_rows_stop(cfg):
    base = us_frame()
    base.iloc[::10, base.columns.get_loc("close")] = np.nan  # 10 percent of the rows
    _, health = prepared(cfg, base)
    assert health.status == D.STOP and "not trusted" in health.problems[0]


def test_one_bad_asset_stops_everything():
    ok = D.AssetHealth("A", "yahoo")
    warn = D.AssetHealth("B", "yahoo", warnings=["care"])
    stop = D.AssetHealth("C", "yahoo", problems=["bad"])
    assert D.overall_status([ok]) == D.OK
    assert D.overall_status([ok, warn]) == D.WARN
    assert D.overall_status([ok, warn, stop]) == D.STOP
    assert D.overall_status([]) == D.STOP


# ---------------------------------------------------------------- fetching and saved files

def test_fetch_saves_clean_data_and_labels_it(cfg):
    calls = []
    results = D.fetch_all(cfg, now=NOW, downloader=fake_downloader(calls), pause=0)
    assert [r.status for r in results] == [D.OK] * 7
    assert [c[0] for c in calls] == ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "JPM", "QNT-USD"]
    assert all(c[1] == date(2016, 10, 3) and c[2] is True for c in calls)  # ten years back, adjusted prices
    for asset in cfg.assets:
        csv_path, meta_path = D.cache_paths(cfg.data.folder, asset.symbol)
        assert csv_path.exists() and meta_path.exists()
    meta = json.loads(D.cache_paths(cfg.data.folder, "QNT")[1].read_text(encoding="utf-8"))
    assert meta["source"] == "yahoo" and meta["interval"] == "1d" and meta["adjusted"] is True
    assert meta["yahoo"] == "QNT-USD" and meta["rows"] == 799 and meta["last_bar"] == "2026-10-02"


def test_saved_bars_come_back_unchanged(cfg):
    D.fetch_all(cfg, ["SPY"], NOW, downloader=fake_downloader([]), pause=0)
    frame, health = D.load_asset(cfg, cfg.asset("SPY"), NOW)
    original = us_frame(800)
    assert health.status == D.OK and list(frame.index.date) == list(original.index.date)
    np.testing.assert_allclose(frame.to_numpy(), original.to_numpy())


def test_saved_data_goes_stale_and_is_caught_on_load(cfg):
    D.fetch_all(cfg, ["SPY"], NOW, downloader=fake_downloader([]), pause=0)
    _, later = D.load_asset(cfg, cfg.asset("SPY"), NOW + timedelta(days=10))
    assert later.status == D.STOP and "stale" in later.problems[0]


def test_a_failed_download_stops_that_asset_and_saves_nothing(cfg):
    good = fake_downloader([])

    def flaky(symbol, start, adjusted):
        if symbol == "NVDA":
            raise ConnectionError("no internet")
        return good(symbol, start, adjusted)

    results = D.fetch_all(cfg, now=NOW, downloader=flaky, pause=0)
    by = {r.symbol: r for r in results}
    assert by["NVDA"].status == D.STOP and "no internet" in by["NVDA"].problems[0]
    assert by["SPY"].status == D.OK
    assert D.overall_status(results) == D.STOP
    assert not any(p.exists() for p in D.cache_paths(cfg.data.folder, "NVDA"))
    with pytest.raises(D.DataError, match="No saved data for NVDA"):
        D.load_asset(cfg, cfg.asset("NVDA"), NOW)


def test_when_everything_fails_nothing_is_made_up(cfg):
    def down(symbol, start, adjusted):
        raise TimeoutError("timed out")

    results = D.fetch_all(cfg, now=NOW, downloader=down, pause=0)
    assert [r.status for r in results] == [D.STOP] * 7
    assert not cfg.data.folder.exists() and not cfg.data.demo_folder.exists()


def test_an_empty_download_is_a_stop(cfg):
    def empty(symbol, start, adjusted):
        return yahoo_like(us_frame(10).iloc[0:0], "America/New_York")

    result = D.fetch_all(cfg, ["SPY"], NOW, downloader=empty, pause=0)[0]
    assert result.status == D.STOP and "no usable bars" in result.problems[0]


def test_bad_data_never_overwrites_good_data(cfg):
    D.fetch_all(cfg, ["SPY"], NOW, downloader=fake_downloader([]), pause=0)
    csv_path, _ = D.cache_paths(cfg.data.folder, "SPY")
    before = csv_path.read_text(encoding="utf-8")

    def stale(symbol, start, adjusted):
        return yahoo_like(us_frame(800, end=date(2026, 9, 1)), "America/New_York")

    result = D.fetch_all(cfg, ["SPY"], NOW, downloader=stale, pause=0)[0]
    assert result.status == D.STOP and "stale" in result.problems[0]
    assert csv_path.read_text(encoding="utf-8") == before


def test_a_setup_problem_aborts_instead_of_repeating_for_every_asset(cfg):
    def no_library(symbol, start, adjusted):
        raise D.SetupError("The yfinance library is not installed.")

    with pytest.raises(D.SetupError):
        D.fetch_all(cfg, now=NOW, downloader=no_library, pause=0)


def test_fetch_reports_progress_and_rejects_unknown_symbols(cfg):
    seen = []
    D.fetch_all(cfg, ["SPY", "QNT"], NOW, downloader=fake_downloader([]), pause=0, progress=seen.append)
    assert [h.symbol for h in seen] == ["SPY", "QNT"]
    with pytest.raises(ConfigError, match="Unknown symbol XYZ"):
        D.fetch_all(cfg, ["XYZ"], NOW, downloader=fake_downloader([]), pause=0)


def test_a_damaged_saved_file_is_not_used(cfg):
    D.fetch_all(cfg, ["SPY"], NOW, downloader=fake_downloader([]), pause=0)
    csv_path, meta_path = D.cache_paths(cfg.data.folder, "SPY")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["rows"] += 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(D.DataError, match="does not match its label"):
        D.load_asset(cfg, cfg.asset("SPY"), NOW)
    csv_path.write_text("this is not a price file", encoding="utf-8")
    with pytest.raises(D.DataError, match="could not be read"):
        D.load_asset(cfg, cfg.asset("SPY"), NOW)


# ---------------------------------------------------------------- the Yahoo adapter

class FakeTicker:
    frame = None
    error = None
    calls = []

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        FakeTicker.calls.append((self.symbol, kwargs))
        if FakeTicker.error:
            raise FakeTicker.error
        return FakeTicker.frame


@pytest.fixture()
def fake_yfinance(monkeypatch):
    FakeTicker.calls, FakeTicker.error = [], None
    FakeTicker.frame = yahoo_like(us_frame(20), "America/New_York")
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=FakeTicker))
    return FakeTicker


def test_yahoo_adapter_asks_for_daily_bars_and_raises_on_errors(fake_yfinance):
    out = D.download_yahoo("QNT-USD", date(2020, 1, 1), True)
    assert len(out) == 20
    symbol, kwargs = fake_yfinance.calls[0]
    assert symbol == "QNT-USD"
    assert kwargs == {"start": "2020-01-01", "interval": "1d", "auto_adjust": True, "actions": False,
                      "raise_errors": True}


def test_yahoo_adapter_turns_every_failure_into_a_plain_data_error(fake_yfinance):
    fake_yfinance.error = RuntimeError("rate limited,\n slow down")
    with pytest.raises(D.DataError, match="did not return QNT-USD: rate limited, slow down"):
        D.download_yahoo("QNT-USD", date(2020, 1, 1), True)
    fake_yfinance.error = None
    fake_yfinance.frame = fake_yfinance.frame.iloc[0:0]
    with pytest.raises(D.DataError, match="returned no rows for QNT-USD"):
        D.download_yahoo("QNT-USD", date(2020, 1, 1), True)


def test_a_missing_yfinance_library_is_a_setup_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", None)
    with pytest.raises(D.SetupError, match="pip install yfinance"):
        D.download_yahoo("SPY", date(2020, 1, 1), True)


# ---------------------------------------------------------------- made up data stays apart

def test_demo_data_is_labelled_and_kept_apart(cfg):
    results = write_demo(cfg, NOW)
    assert [r.status for r in results] == [D.OK] * 7 and {r.source for r in results} == {"SYNTHETIC"}
    meta = json.loads(D.cache_paths(cfg.data.demo_folder, "SPY")[1].read_text(encoding="utf-8"))
    assert meta["source"] == "SYNTHETIC"
    assert not cfg.data.folder.exists()
    frame, health = D.load_asset(cfg, cfg.asset("SPY"), NOW, demo=True)
    assert health.status == D.OK and len(frame) == 1500
    with pytest.raises(D.DataError, match="No saved data for SPY"):
        D.load_asset(cfg, cfg.asset("SPY"), NOW)


def test_demo_data_never_looks_stale_but_it_never_passes_as_real(cfg):
    write_demo(cfg, NOW)
    _, health = D.load_asset(cfg, cfg.asset("QNT"), NOW + timedelta(days=400), demo=True)
    assert health.status == D.OK
    real_csv, real_meta = D.cache_paths(cfg.data.folder, "QNT")
    demo_csv, demo_meta = D.cache_paths(cfg.data.demo_folder, "QNT")
    real_csv.parent.mkdir(parents=True)
    shutil.copy(demo_csv, real_csv)
    shutil.copy(demo_meta, real_meta)
    with pytest.raises(D.DataError, match="made up data in the wrong folder"):
        D.load_asset(cfg, cfg.asset("QNT"), NOW)


def test_real_data_in_the_demo_folder_is_refused(cfg):
    D.fetch_all(cfg, ["SPY"], NOW, downloader=fake_downloader([]), pause=0)
    real_csv, real_meta = D.cache_paths(cfg.data.folder, "SPY")
    demo_csv, demo_meta = D.cache_paths(cfg.data.demo_folder, "SPY")
    demo_csv.parent.mkdir(parents=True)
    shutil.copy(real_csv, demo_csv)
    shutil.copy(real_meta, demo_meta)
    with pytest.raises(D.DataError, match="real data in the wrong folder"):
        D.load_asset(cfg, cfg.asset("SPY"), NOW, demo=True)


def test_synthetic_series_is_valid_repeatable_and_has_regimes():
    a, regimes = make_series(2000, "us", date(2026, 10, 2), seed=3)
    b, _ = make_series(2000, "us", date(2026, 10, 2), seed=3)
    pd.testing.assert_frame_equal(a, b)
    _, removed = D.clean_bars(a, 0.05)
    assert removed == [] and (a.index.dayofweek < 5).all()
    assert set(regimes) == {"bear", "neutral", "bull"}
    switches = int((regimes != regimes.shift()).sum())
    assert 10 < switches < 200  # regimes last a while but do change
    returns = np.log(a["close"]).diff()
    assert returns[regimes == "bear"].std() > 2 * returns[regimes == "bull"].std()


def test_synthetic_crypto_trades_every_day_and_assets_differ(cfg):
    frames = make_universe(cfg, date(2026, 10, 2), bars=300)
    gaps = frames["QNT"].index.to_series().diff().dropna().dt.days
    assert (gaps == 1).all()
    assert not np.allclose(frames["SPY"]["close"].to_numpy(), frames["QQQ"]["close"].to_numpy())


# ---------------------------------------------------------------- the report

def test_report_states_interval_lag_and_every_asset(cfg):
    results = [D.AssetHealth("SPY", "yahoo", bars=500, first=date(2024, 1, 2), last=date(2026, 10, 2), age_days=1)]
    text = D.render_report(results, cfg.data, NOW)
    assert "Interval: daily bars" in text and "Data lag:" in text and "30 minutes" in text
    assert "SPY" in text and "OVERALL: OK" in text and "MADE UP" not in text
    assert_no_dashes(text)


def test_report_for_a_stop_says_nothing_was_guessed(cfg):
    results = [D.AssetHealth("SPY", "yahoo", problems=["Yahoo Finance did not return SPY: no internet"])]
    text = D.render_report(results, cfg.data, NOW)
    assert "STOP: Yahoo Finance did not return SPY" in text and "Nothing was guessed" in text
    assert "none" in text and "n/a" in text
    assert_no_dashes(text)


def test_report_for_made_up_data_starts_with_a_banner(cfg):
    text = D.render_report(write_demo(cfg, NOW), cfg.data, NOW, synthetic=True)
    assert text.startswith("*** MADE UP DATA")
    assert "Data lag: none, this data is made up." in text
    assert_no_dashes(text)


def test_every_kind_of_message_is_dash_free(cfg):
    base = us_frame()
    base.iloc[10:13, base.columns.get_loc("volume")] = 0.0
    base.loc[base.index[300:], ["open", "high", "low", "close"]] *= 1.7
    base = base.drop(pd.Timestamp("2026-09-08"))
    base.iloc[[20, 21], base.columns.get_loc("close")] = np.nan
    _, health = prepared(cfg, base)
    stale = prepared(cfg, us_frame(300, end=date(2026, 9, 1)))[1]
    text = D.render_report([health, stale, D.AssetHealth("QNT", "yahoo", problems=["no internet"])], cfg.data, NOW)
    assert "WARN:" in text and "STOP:" in text
    assert_no_dashes(text)
