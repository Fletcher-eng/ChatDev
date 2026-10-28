"""Tests for the quick look at any ticker."""

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest
import yaml

from algo_lab import cli
from algo_lab import data as D
from algo_lab.config import DEFAULT_CONFIG_PATH, load_config
from algo_lab.look import FOOTER, dollars, look_at, look_up, percent_over, price, render_look
from algo_lab.synthetic import make_series

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)  # a Wednesday
PRICE_COLUMNS = ["open", "high", "low", "close"]


def frame(n=500, end=date(2026, 10, 27), seed=1):
    return make_series(n, "us", end, seed)[0]


def settings():
    return load_config().look


def names(look):
    return [name for name, _ in look.flags]


def assert_no_dashes(text):
    assert "—" not in text and "–" not in text and " - " not in text and " -- " not in text


def yahoo_like(base, tz="America/New_York"):
    raw = base.rename(columns=str.capitalize).copy()
    raw["Dividends"] = 0.0
    raw.index = raw.index.tz_localize(tz)
    raw.index.name = "Date"
    return raw


def test_a_liquid_stock_has_no_warning_signs():
    base = frame()
    look = look_at("SPY", base, NOW, settings())
    assert look.flags == [] and look.wild_moves == [] and look.zero_volume_days == 0
    assert look.bars == 500 and look.last == date(2026, 10, 27) and look.age_days == 1
    close = base["close"]
    assert look.last_close == pytest.approx(close.iloc[-1])
    assert look.change_5 == pytest.approx((close.iloc[-1] / close.iloc[-6] - 1) * 100)
    assert look.change_20 == pytest.approx((close.iloc[-1] / close.iloc[-21] - 1) * 100)
    assert look.low == pytest.approx(base["low"].tail(252).min())
    assert look.high == pytest.approx(base["high"].tail(252).max())
    assert look.range_bars_used == 252 and look.volume_bars_used == 20
    assert look.vs_fast == pytest.approx((close.iloc[-1] / close.tail(50).mean() - 1) * 100)
    assert look.vs_slow == pytest.approx((close.iloc[-1] / close.tail(200).mean() - 1) * 100)
    assert look.from_high == pytest.approx((close.iloc[-1] / look.high - 1) * 100) and look.from_high <= 0
    expected = (base["close"] * base["volume"]).tail(20).mean()
    assert look.dollar_volume == pytest.approx(expected)


def test_a_penny_price_is_flagged():
    base = frame()
    base[PRICE_COLUMNS] *= 2.0 / base["close"].iloc[-1]
    base["volume"] *= 100  # plenty of volume, so only the price is a problem
    look = look_at("NEXR", base, NOW, settings())
    assert names(look) == ["PENNY"] and "under 5 dollars" in look.flags[0][1]


def test_thin_trading_is_flagged():
    base = frame()
    base["volume"] = 500.0
    look = look_at("THIN", base, NOW, settings())
    assert names(look) == ["THIN"] and "under $5.0 million" in look.flags[0][1]


def test_a_new_listing_is_flagged_and_short_windows_are_skipped():
    look = look_at("AIOK", frame(14), NOW, settings())
    assert "NEW" in names(look) and "only 14 bars of history, fewer than 200" in dict(look.flags)["NEW"]
    assert look.change_5 is not None and look.change_20 is None
    text = render_look(look, settings())
    assert "5 bars" in text and "20 bars" not in text
    assert look.vs_fast is None and look.vs_slow is None
    assert "no 50 bar average yet (only 14 bars)" in text and "no 200 bar average yet (only 14 bars)" in text


def flat(last):
    """Every bar at 100 dollars, then one last bar at `last`."""
    base = frame()
    base[PRICE_COLUMNS] = 100.0
    base.loc[base.index[-1], PRICE_COLUMNS] = last
    return base


def test_the_trend_line_says_above_or_below_and_how_far():
    up = render_look(look_at("UP", flat(130.0), NOW, settings()), settings())
    fast = (130 / ((49 * 100 + 130) / 50) - 1) * 100
    slow = (130 / ((199 * 100 + 130) / 200) - 1) * 100
    assert f"Trend: it is {fast:.1f} percent above its 50 bar average; {slow:.1f} percent above its 200 bar average" in up
    assert "now at the high" in up
    down = render_look(look_at("DOWN", flat(70.0), NOW, settings()), settings())
    assert "percent below its 50 bar average" in down and "percent below its 200 bar average" in down
    assert "now 30.0 percent below the high" in down
    assert_no_dashes(up + down)


def test_a_wild_recent_move_is_flagged_but_an_old_one_is_not():
    recent = frame()
    recent.loc[recent.index[-30:], PRICE_COLUMNS] *= 0.5
    look = look_at("WILD", recent, NOW, settings())
    assert names(look) == ["WILD"] and len(look.wild_moves) == 1 and look.wild_moves[0].change_pct < -20
    old = frame()
    old.loc[old.index[-100:], PRICE_COLUMNS] *= 0.5
    assert look_at("OLD", old, NOW, settings()).flags == []


def test_zero_volume_days_are_counted_inside_the_window_only():
    base = frame()
    base.iloc[[-10, -11], base.columns.get_loc("volume")] = 0.0
    base.iloc[-200, base.columns.get_loc("volume")] = 0.0
    look = look_at("ZERO", base, NOW, settings())
    assert look.zero_volume_days == 2 and "ZERO" in names(look)


def test_an_empty_frame_has_a_problem_not_a_crash():
    look = look_at("NONE", frame().iloc[0:0], NOW, settings())
    assert look.problem == "No finished daily bars came back."
    assert "Could not look at it" in render_look(look, settings())


def test_numbers_are_written_in_words():
    assert dollars(1_234_567) == "$1.2 million"
    assert dollars(2_500_000_000) == "$2.5 billion"
    assert dollars(45_000) == "$45 thousand"
    assert dollars(12.5) == "$12.50"
    assert price(0.5) == "$0.5000" and price(12.3456) == "$12.35"
    assert percent_over(frame(10)["close"], 20) is None
    assert percent_over(frame(20)["close"], 20) is None  # 20 bars give only 19 changes
    assert percent_over(frame(21)["close"], 20) is not None


def test_the_text_is_plain_and_dash_free():
    base = frame(14)
    base[PRICE_COLUMNS] *= 2.0 / base["close"].iloc[-1]
    base.loc[base.index[-5:], PRICE_COLUMNS] *= 0.5
    text = render_look(look_at("AIOK", base, NOW, settings()), settings())
    assert "PENNY:" in text and "NEW:" in text and "Warning signs:" in text and ("fell" in text or "rose" in text)
    assert_no_dashes(text)
    quiet = render_look(look_at("SPY", frame(), NOW, settings()), settings())
    assert "Warning signs: none" in quiet and "Big moves (last 60 bars): none bigger than 20 percent" in quiet
    assert_no_dashes(quiet)
    assert_no_dashes(FOOTER)


# ---------------------------------------------------------------- looking up tickers

@pytest.fixture()
def cfg():
    return load_config()


def test_look_up_asks_yahoo_the_right_way_and_reads_the_answer(cfg):
    calls = []

    def downloader(symbol, start, adjusted):
        calls.append((symbol, start, adjusted))
        return yahoo_like(frame())

    looks = look_up(cfg, ["nexr", " SPY "], NOW, downloader=downloader, pause=0)
    assert [look.symbol for look in looks] == ["NEXR", "SPY"] and all(look.problem is None for look in looks)
    assert calls[0] == ("NEXR", date(2024, 10, 28), True)  # two years back, adjusted prices
    assert looks[0].bars == 500 and looks[0].last == date(2026, 10, 27)


def test_one_failure_does_not_stop_the_others(cfg):
    def downloader(symbol, start, adjusted):
        if symbol == "BAD":
            raise ConnectionError("no internet")
        return yahoo_like(frame())

    looks = look_up(cfg, ["BAD", "SPY"], NOW, downloader=downloader, pause=0)
    assert "no internet" in looks[0].problem and looks[1].problem is None


def test_a_setup_problem_aborts(cfg):
    def no_library(symbol, start, adjusted):
        raise D.SetupError("The yfinance library is not installed.")

    with pytest.raises(D.SetupError):
        look_up(cfg, ["SPY"], NOW, downloader=no_library, pause=0)


def test_a_silly_ticker_is_rejected_before_any_download(cfg):
    calls = []
    looks = look_up(cfg, ["bad symbol!"], NOW, downloader=lambda *a: calls.append(a), pause=0)
    assert "does not look like a ticker" in looks[0].problem and calls == []


def test_an_empty_download_is_reported(cfg):
    looks = look_up(cfg, ["EMPTY"], NOW, downloader=lambda *a: yahoo_like(frame(5)).iloc[0:0], pause=0)
    assert looks[0].problem == "No finished daily bars came back."


def test_todays_unfinished_crypto_bar_is_ignored_but_a_finished_stock_bar_is_kept(cfg):
    evening = datetime(2026, 10, 28, 22, 0, tzinfo=timezone.utc)  # after the US close, before midnight UTC
    crypto = make_series(500, "crypto", date(2026, 10, 28), seed=2)[0]
    look = look_up(cfg, ["QNT-USD"], evening, downloader=lambda *a: yahoo_like(crypto, "UTC"), pause=0)[0]
    assert look.last == date(2026, 10, 27) and "Ignored the unfinished bar for 2026-10-28" in look.notes[0]
    stock = frame(end=date(2026, 10, 28))
    assert look_up(cfg, ["SPY"], evening, downloader=lambda *a: yahoo_like(stock), pause=0)[0].last == date(2026, 10, 28)


def test_broken_rows_are_dropped_and_mentioned(cfg):
    base = frame()
    base.iloc[10, base.columns.get_loc("close")] = np.nan
    look = look_up(cfg, ["SPY"], NOW, downloader=lambda *a: yahoo_like(base), pause=0)[0]
    assert look.bars == 499 and "Removed 1 broken row" in look.notes[0]


# ---------------------------------------------------------------- the command

@pytest.fixture()
def config_file(tmp_path):
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["data"]["folder"] = str(tmp_path / "real")
    raw["data"]["demo_folder"] = str(tmp_path / "demo")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def live_downloader(symbol, start, adjusted):
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    return yahoo_like(make_series(500, "us", end, seed=3)[0])


def test_look_command_prints_each_ticker_and_the_footer(monkeypatch, capsys, config_file):
    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", live_downloader)
    code = cli.main(["look", "NEXR", "AIOK", "--config", str(config_file)])
    out = capsys.readouterr().out
    assert code == 0 and "NEXR" in out and "AIOK" in out and "Last close:" in out and FOOTER in out
    assert_no_dashes(out)


def test_look_command_fails_loudly_when_yahoo_is_down(monkeypatch, capsys, config_file):
    def down(symbol, start, adjusted):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", down)
    code = cli.main(["look", "SPY", "--config", str(config_file)])
    out = capsys.readouterr().out
    assert code == 2 and "Could not look at it" in out and "timed out" in out


def test_look_command_needs_at_least_one_ticker(config_file):
    with pytest.raises(SystemExit) as stop:
        cli.main(["look", "--config", str(config_file)])
    assert stop.value.code == 2
