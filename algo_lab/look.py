"""A quick look at any ticker: its price, how much trades, how wild it is, and how much history exists.

This is a check before a trade, not a signal. Nothing is saved and no setting changes.
"""

from __future__ import annotations

import re
import time as clock
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from .config import Config, LookConfig
from .data import (DataError, Downloader, Move, SetupError, clean_bars, download_yahoo, drop_unfinished,
                   find_extreme_moves, move_words, normalize_frame, plural, short_error, utc_now)

SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,11}$")


@dataclass
class Look:
    symbol: str
    problem: Optional[str] = None  # why nothing could be shown
    bars: int = 0
    first: Optional[date] = None
    last: Optional[date] = None
    age_days: Optional[int] = None
    last_close: Optional[float] = None
    change_5: Optional[float] = None  # percent over the last 5 bars, a rise is positive
    change_20: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    range_bars_used: int = 0
    dollar_volume: Optional[float] = None  # average dollars traded per day
    volume_bars_used: int = 0
    zero_volume_days: int = 0
    wild_moves: List[Move] = field(default_factory=list)
    flags: List[Tuple[str, str]] = field(default_factory=list)  # (name, plain sentence)
    notes: List[str] = field(default_factory=list)


def dollars(amount: float) -> str:
    if amount >= 1e9:
        return f"${amount / 1e9:.1f} billion"
    if amount >= 1e6:
        return f"${amount / 1e6:.1f} million"
    if amount >= 1e3:
        return f"${amount / 1e3:.0f} thousand"
    return f"${amount:.2f}"


def price(amount: float) -> str:
    return f"${amount:.2f}" if amount >= 1 else f"${amount:.4f}"


def percent_over(close: pd.Series, bars: int) -> Optional[float]:
    if len(close) <= bars:
        return None
    return float((close.iloc[-1] / close.iloc[-1 - bars] - 1.0) * 100.0)


def look_at(symbol: str, frame: pd.DataFrame, now: datetime, cfg: LookConfig) -> Look:
    """Measure one asset from cleaned, finished daily bars."""
    look = Look(symbol=symbol, bars=len(frame))
    if len(frame) == 0:
        look.problem = "No finished daily bars came back."
        return look
    now = utc_now(now)
    close = frame["close"]
    look.first, look.last = frame.index[0].date(), frame.index[-1].date()
    look.age_days = (now.date() - look.last).days
    look.last_close = float(close.iloc[-1])
    look.change_5, look.change_20 = percent_over(close, 5), percent_over(close, 20)
    year = frame.tail(cfg.range_bars)
    look.low, look.high, look.range_bars_used = float(year["low"].min()), float(year["high"].max()), len(year)
    recent = frame.tail(cfg.volume_bars)
    look.dollar_volume, look.volume_bars_used = float((recent["close"] * recent["volume"]).mean()), len(recent)
    window = frame.tail(cfg.move_bars + 1)
    look.zero_volume_days = int((window["volume"].tail(cfg.move_bars) == 0).sum())
    look.wild_moves = find_extreme_moves(window, cfg.wild_move_pct)

    if look.last_close < cfg.penny_price:
        look.flags.append(("PENNY", f"the price is under {cfg.penny_price:g} dollars. Penny stocks swing wildly, "
                                    "are easy to hype, and often get reverse splits that squash the share count."))
    if look.dollar_volume < cfg.thin_dollar_volume:
        look.flags.append(("THIN", f"only about {dollars(look.dollar_volume)} trades on an average day, under "
                                   f"{dollars(cfg.thin_dollar_volume)}. With few buyers and sellers the price "
                                   "jumps around and getting out can be hard."))
    if len(frame) < cfg.new_listing_bars:
        look.flags.append(("NEW", f"only {plural(len(frame), 'bar')} of history, fewer than {cfg.new_listing_bars}. "
                                  "The 200 bar average and the regime model cannot work yet, so nothing can be "
                                  "measured."))
    if look.wild_moves:
        look.flags.append(("WILD", f"{plural(len(look.wild_moves), 'one day move')} bigger than "
                                   f"{cfg.wild_move_pct:g} percent in the last {cfg.move_bars} bars."))
    if look.zero_volume_days:
        look.flags.append(("ZERO", f"{plural(look.zero_volume_days, 'day')} with zero volume in the last "
                                   f"{cfg.move_bars} bars. Some days nobody traded it."))
    return look


def look_symbol(cfg: Config, raw_symbol: str, now: datetime, downloader: Downloader) -> Look:
    symbol = raw_symbol.strip().upper()
    if not SYMBOL_RE.match(symbol):
        return Look(symbol=raw_symbol.strip(),
                    problem="That does not look like a ticker. Use letters and digits, like AAPL or BRK-B.")
    start = (now - timedelta(days=int(cfg.look.history_years * 365.25))).date()
    try:
        try:
            raw = downloader(symbol, start, cfg.data.adjusted)
        except DataError:
            raise
        except Exception as error:  # the outside world failed in a way the downloader did not expect
            raise DataError(f"Could not download {symbol}: {short_error(error)}") from error
        frame = normalize_frame(raw)
    except SetupError:
        raise
    except DataError as error:
        return Look(symbol=symbol, problem=str(error))
    frame, removed = clean_bars(frame, cfg.data.ohlc_tolerance_pct)
    market = "crypto" if symbol.endswith("-USD") else "us"
    frame, unfinished = drop_unfinished(frame, market, now, cfg.data.confirm_delay_minutes)
    look = look_at(symbol, frame, now, cfg.look)
    if removed:
        look.notes.append(f"Removed {plural(len(removed), 'broken row')} from the download.")
    if unfinished:
        look.notes.append("Ignored the unfinished bar for " + ", ".join(d.isoformat() for d in unfinished) + ".")
    return look


def look_up(cfg: Config, symbols: Sequence[str], now: Optional[datetime] = None,
            downloader: Optional[Downloader] = None, pause: float = 1.0) -> List[Look]:
    """Look at each ticker in turn. A ticker that fails is reported and the rest carry on."""
    now = utc_now(now)
    downloader = downloader or download_yahoo
    looks = []
    for number, symbol in enumerate(symbols):
        if number and pause:
            clock.sleep(pause)  # be polite to a free service
        looks.append(look_symbol(cfg, symbol, now, downloader))
    return looks


def render_look(look: Look, cfg: LookConfig) -> str:
    if look.problem:
        return f"{look.symbol}\n  Could not look at it: {look.problem}"
    lines = [
        look.symbol,
        f"  History: {plural(look.bars, 'daily bar')}, from {look.first.isoformat()} to {look.last.isoformat()}"
        f" (the newest finished bar is {plural(look.age_days, 'day')} old)",
        f"  Last close: {price(look.last_close)}",
    ]
    changes = [f"{bars} bars {move_words(value)}" for bars, value in ((5, look.change_5), (20, look.change_20))
               if value is not None]
    if changes:
        lines.append("  Change: " + "; ".join(changes))
    lines.append(f"  Range over the last {look.range_bars_used} bars: low {price(look.low)}, high {price(look.high)}")
    lines.append(f"  Traded per day (average of the last {look.volume_bars_used} bars): {dollars(look.dollar_volume)}")
    window = min(cfg.move_bars, look.bars)
    lines.append(f"  Days with zero volume (last {window} bars): {look.zero_volume_days}")
    if look.wild_moves:
        biggest = max(look.wild_moves, key=lambda m: abs(m.change_pct))
        lines.append(f"  Big moves (last {window} bars): {len(look.wild_moves)}, the biggest was on "
                     f"{biggest.day.isoformat()} when it {move_words(biggest.change_pct)}")
    else:
        lines.append(f"  Big moves (last {window} bars): none bigger than {cfg.wild_move_pct:g} percent")
    if look.flags:
        lines.append("  Warning signs:")
        lines += [f"    {name}: {text}" for name, text in look.flags]
    else:
        lines.append("  Warning signs: none of the ones this check looks for")
    lines += [f"  note: {text}" for text in look.notes]
    return "\n".join(lines)


FOOTER = ("Prices are adjusted for splits and dividends, so after a reverse split the past looks far more expensive "
          "than it was. This is a quick look, not advice, and Yahoo numbers can be late or wrong.")
