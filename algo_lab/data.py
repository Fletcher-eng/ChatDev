"""Data Bot: downloads daily bars, cleans them, and stops when the data is stale or broken.

The rules come from the briefing. Never invent data. Say which interval and how much lag. Use confirmed bar
closes only. If a source fails, say so and stop. Made up data exists only for tests and the demo, lives in its
own folder, is labelled SYNTHETIC, and is never used as a fallback.
"""

from __future__ import annotations

import json
import logging
import os
import time as clock
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import Asset, Config, DataConfig

COLUMNS = ["open", "high", "low", "close", "volume"]
PRICES = ["open", "high", "low", "close"]
NEW_YORK = ZoneInfo("America/New_York")
OK, WARN, STOP = "OK", "WARN", "STOP"
SYNTHETIC = "SYNTHETIC"
YAHOO = "yahoo"

Downloader = Callable[[str, date, bool], pd.DataFrame]


class DataError(RuntimeError):
    """The data source failed or the data cannot be trusted. The lab must stop and say so, never guess."""


class SetupError(DataError):
    """Something is missing on this computer, such as a library. The data itself may be fine."""


@dataclass
class AssetHealth:
    """What the Data Bot found for one asset."""

    symbol: str
    source: str
    bars: int = 0
    first: Optional[date] = None
    last: Optional[date] = None
    age_days: Optional[int] = None  # days since the newest finished bar
    problems: List[str] = field(default_factory=list)  # reasons to STOP
    warnings: List[str] = field(default_factory=list)  # reasons for care
    notes: List[str] = field(default_factory=list)  # plain information

    @property
    def status(self) -> str:
        if self.problems:
            return STOP
        return WARN if self.warnings else OK


def overall_status(results: Sequence[AssetHealth]) -> str:
    """One bad asset stops everything, as the briefing says."""
    if not results or any(r.status == STOP for r in results):
        return STOP
    return WARN if any(r.status == WARN for r in results) else OK


def _short(error: Exception, limit: int = 160) -> str:
    text = " ".join(str(error).split()) or type(error).__name__
    return text if len(text) <= limit else text[: limit - 3] + "..."


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def utc_now(now: Optional[datetime] = None) -> datetime:
    """The current time in UTC. A time given by a caller must carry its time zone."""
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("The time must carry a time zone.")
    return now.astimezone(timezone.utc)


# ---------------------------------------------------------------- download

def download_yahoo(yahoo_symbol: str, start: date, adjusted: bool) -> pd.DataFrame:
    """Daily bars from Yahoo Finance through the yfinance library. Free, unofficial, and it can break."""
    try:
        import yfinance as yf
    except ImportError as error:
        raise SetupError("The yfinance library is not installed. Run: pip install yfinance") from error
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # failures are reported below in plain words
    try:
        raw = yf.Ticker(yahoo_symbol).history(start=start.isoformat(), interval="1d", auto_adjust=adjusted,
                                              actions=False, raise_errors=True)
    except Exception as error:  # yfinance raises many kinds of errors: no network, rate limit, unknown ticker
        raise DataError(f"Yahoo Finance did not return {yahoo_symbol}: {_short(error)}") from error
    if raw is None or len(raw) == 0:
        raise DataError(f"Yahoo Finance returned no rows for {yahoo_symbol}.")
    return raw


# ---------------------------------------------------------------- cleaning

def normalize_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Lower case names, a plain date index and numbers. No price is changed."""
    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(name).strip().lower() for name in frame.columns]
    missing = [name for name in COLUMNS if name not in frame.columns]
    if missing:
        raise DataError("The data is missing these columns: " + ", ".join(missing) + ".")
    frame = frame[COLUMNS]
    try:
        index = pd.DatetimeIndex(frame.index)
    except (TypeError, ValueError) as error:
        raise DataError(f"The dates could not be read: {_short(error)}") from error
    if index.tz is not None:
        index = index.tz_localize(None)  # keeps the exchange's own calendar date
    frame.index = index.normalize()
    frame.index.name = "date"
    frame = frame.loc[~frame.index.isna()].copy()
    for name in COLUMNS:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame


def clean_bars(frame: pd.DataFrame, tolerance_pct: float) -> Tuple[pd.DataFrame, List[Tuple[date, str]]]:
    """Drop broken rows and say why. Nothing is repaired and nothing is invented."""
    frame = frame.sort_index(kind="stable")
    removed: List[Tuple[date, str]] = []
    duplicate = frame.index.duplicated(keep="last")
    removed += [(stamp.date(), "duplicate date") for stamp in frame.index[duplicate]]
    frame = frame.loc[~duplicate].replace([np.inf, -np.inf], np.nan)
    prices, volume = frame[PRICES], frame["volume"]
    slack = tolerance_pct / 100.0
    above_high = frame[["open", "close"]].gt(frame["high"] * (1 + slack), axis=0)
    below_low = frame[["open", "close"]].lt(frame["low"] * (1 - slack), axis=0)
    checks = [
        ("missing price", prices.isna().any(axis=1)),
        ("missing volume", volume.isna()),
        ("price at or below zero", (prices <= 0).any(axis=1)),
        ("negative volume", volume < 0),
        ("high below low", frame["high"] < frame["low"]),
        ("open or close outside the high to low range", (above_high | below_low).any(axis=1)),
    ]
    reasons = np.full(len(frame), "", dtype=object)
    for text, mask in checks:
        reasons[mask.to_numpy(dtype=bool) & (reasons == "")] = text
    bad = reasons != ""
    removed += [(stamp.date(), why) for stamp, why in zip(frame.index[bad], reasons[bad])]
    return frame.loc[~bad], removed


# ---------------------------------------------------------------- confirmed bars only

def bar_confirmed_at(bar_date: date, market: str, delay_minutes: int) -> datetime:
    """The moment (UTC) after which the daily bar for bar_date is final."""
    if market == "crypto":
        end = datetime.combine(bar_date + timedelta(days=1), time(0, 0), tzinfo=timezone.utc)  # a crypto day ends at midnight UTC
    else:
        end = datetime.combine(bar_date, time(16, 0), tzinfo=NEW_YORK).astimezone(timezone.utc)  # US markets close at 16:00 New York time
    return end + timedelta(minutes=delay_minutes)


def drop_unfinished(frame: pd.DataFrame, market: str, now: datetime,
                    delay_minutes: int) -> Tuple[pd.DataFrame, List[date]]:
    """Confirmed bar closes only: a bar whose session is not over yet is never used."""
    now = utc_now(now)
    dropped: List[date] = []
    while len(frame) and bar_confirmed_at(frame.index[-1].date(), market, delay_minutes) > now:
        dropped.append(frame.index[-1].date())
        frame = frame.iloc[:-1]
    return frame, dropped


# ---------------------------------------------------------------- health checks

def find_gaps(frame: pd.DataFrame, max_gap_days: int) -> List[Tuple[date, date, int]]:
    """Holes in the history: the bar before the hole, the bar after it, and how many days apart they are."""
    gaps = []
    index = frame.index
    for i in range(1, len(index)):
        days = (index[i] - index[i - 1]).days
        if days > max_gap_days:
            gaps.append((index[i - 1].date(), index[i].date(), days))
    return gaps


def find_extreme_moves(frame: pd.DataFrame, limit_pct: float) -> List[Tuple[date, float]]:
    """Close to close moves bigger than the limit, in percent (a rise is positive)."""
    change = (frame["close"] / frame["close"].shift(1) - 1.0) * 100.0
    big = change[change.abs() > limit_pct]
    return [(stamp.date(), float(value)) for stamp, value in big.items()]


def evaluate(asset: Asset, frame: pd.DataFrame, now: datetime, cfg: DataConfig, source: str,
             removed: Sequence[Tuple[date, str]] = (), unfinished: Sequence[date] = ()) -> AssetHealth:
    """Judge one asset's bars. STOP means do not use them, WARN means use them with care."""
    now = utc_now(now)
    health = AssetHealth(symbol=asset.symbol, source=source, bars=len(frame))
    if unfinished:
        days = ", ".join(d.isoformat() for d in unfinished)
        health.notes.append(f"Ignored the unfinished bar for {days} (that session is not over yet).")
    if removed:
        counts = Counter(why for _, why in removed)
        detail = ", ".join(f"{n} {why}" for why, n in counts.most_common())
        text = (f"Removed {plural(len(removed), 'broken row')} ({detail}). "
                f"The first was on {min(d for d, _ in removed).isoformat()}.")
        share = 100.0 * len(removed) / (len(frame) + len(removed))
        if share > cfg.bad_rows_stop_pct:
            health.problems.append(f"{text} That is {share:.1f} percent of the rows, more than the "
                                   f"{cfg.bad_rows_stop_pct:g} percent allowed, so this source is not trusted.")
        else:
            health.warnings.append(text)
    if len(frame) == 0:
        health.problems.append("There are no usable bars.")
        return health
    health.first, health.last = frame.index[0].date(), frame.index[-1].date()
    health.age_days = (now.date() - health.last).days
    if len(frame) < cfg.min_bars:
        health.problems.append(f"Only {len(frame)} usable bars, at least {cfg.min_bars} are needed.")
    limit = cfg.stale_after_days[asset.market]
    if health.age_days > limit:
        health.problems.append(f"The newest finished bar is {health.age_days} days old, the limit is {limit}. "
                               "The data is stale.")
    gaps = find_gaps(frame, cfg.max_gap_days[asset.market])
    if gaps:
        shown = "; ".join(f"{a.isoformat()} to {b.isoformat()} ({days} days apart)" for a, b, days in gaps[:3])
        more = f" and {len(gaps) - 3} more" if len(gaps) > 3 else ""
        health.warnings.append(f"{plural(len(gaps), 'gap')} in the history: {shown}{more}.")
    moves = find_extreme_moves(frame, cfg.extreme_move_pct)
    if moves:
        shown = "; ".join(f"{d.isoformat()} {'rose' if v > 0 else 'fell'} {abs(v):.1f} percent" for d, v in moves[:3])
        more = f" and {len(moves) - 3} more" if len(moves) > 3 else ""
        health.warnings.append(f"{plural(len(moves), 'one day move')} bigger than {cfg.extreme_move_pct:g} percent: "
                               f"{shown}{more}. Real or a data error? Check before trusting it.")
    zero = int((frame["volume"] == 0).sum())
    if zero:
        health.warnings.append(f"{plural(zero, 'bar')} with zero volume.")
    return health


def prepare(raw: pd.DataFrame, asset: Asset, cfg: Config, now: datetime,
            source: str) -> Tuple[pd.DataFrame, AssetHealth]:
    """The whole cleaning line: normalize, drop broken rows, drop unfinished bars, then judge."""
    frame = normalize_frame(raw)
    frame, removed = clean_bars(frame, cfg.data.ohlc_tolerance_pct)
    frame, unfinished = drop_unfinished(frame, asset.market, now, cfg.data.confirm_delay_minutes)
    return frame, evaluate(asset, frame, now, cfg.data, source, removed, unfinished)


# ---------------------------------------------------------------- saved files

def cache_paths(folder: Path, symbol: str) -> Tuple[Path, Path]:
    return folder / f"{symbol}_1d.csv", folder / f"{symbol}_1d.json"


def _write_atomic(path: Path, text: str) -> None:
    """Write to a temporary file first, so a crash never leaves half a file behind."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def save_cache(folder: Path, asset: Asset, frame: pd.DataFrame, source: str, adjusted: bool,
               now: datetime) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    csv_path, meta_path = cache_paths(folder, asset.symbol)
    meta = {
        "symbol": asset.symbol, "yahoo": asset.yahoo, "source": source, "interval": "1d", "adjusted": adjusted,
        "downloaded_at_utc": utc_now(now).replace(microsecond=0).isoformat(),
        "rows": len(frame), "first_bar": frame.index[0].date().isoformat(),
        "last_bar": frame.index[-1].date().isoformat(),
    }
    _write_atomic(csv_path, frame.to_csv(date_format="%Y-%m-%d"))
    _write_atomic(meta_path, json.dumps(meta, indent=2))


def load_asset(cfg: Config, asset: Asset, now: Optional[datetime] = None,
               demo: bool = False) -> Tuple[pd.DataFrame, AssetHealth]:
    """Read saved bars and judge them again, because saved data goes stale. Real and made up data never mix."""
    folder = cfg.data.demo_folder if demo else cfg.data.folder
    csv_path, meta_path = cache_paths(folder, asset.symbol)
    if not csv_path.exists() or not meta_path.exists():
        kind, command = ("made up ", "demo") if demo else ("", "fetch")
        raise DataError(f"No saved {kind}data for {asset.symbol}. Run: python -m algo_lab {command}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        frame = pd.read_csv(csv_path, index_col="date", parse_dates=["date"])
        made_at = datetime.fromisoformat(meta["downloaded_at_utc"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DataError(f"The saved file for {asset.symbol} could not be read ({_short(error)}). "
                        "Fetch it again.") from error
    if (meta.get("source") == SYNTHETIC) != demo:
        what = "real" if demo else "made up"
        raise DataError(f"The saved file for {asset.symbol} holds {what} data in the wrong folder, so it is not used.")
    frame = normalize_frame(frame)
    if meta.get("rows") != len(frame):
        raise DataError(f"The saved file for {asset.symbol} does not match its label. Fetch it again.")
    # Made up data is judged as of the moment it was made, so a demo never looks stale.
    reference = made_at if demo else utc_now(now)
    return frame, evaluate(asset, frame, reference, cfg.data, str(meta.get("source", "saved file")))


def write_summary(folder: Path, text: str) -> Path:
    """A plain text copy of the report. It holds no secrets, so it is safe to paste into a chat."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "summary.txt"
    _write_atomic(path, text + "\n")
    return path


# ---------------------------------------------------------------- fetching

def pick_assets(cfg: Config, symbols: Optional[Sequence[str]] = None) -> List[Asset]:
    return [cfg.asset(s) for s in symbols] if symbols else list(cfg.assets)


def fetch_one(cfg: Config, asset: Asset, now: datetime, downloader: Downloader) -> AssetHealth:
    start = (now - timedelta(days=int(cfg.data.history_years * 365.25))).date()
    try:
        raw = downloader(asset.yahoo, start, cfg.data.adjusted)
    except DataError:
        raise
    except Exception as error:  # the outside world failed in a way the downloader did not expect
        raise DataError(f"Could not download {asset.symbol}: {_short(error)}") from error
    frame, health = prepare(raw, asset, cfg, now, YAHOO)
    if health.status != STOP:  # bad data is reported and never saved over good data
        try:
            save_cache(cfg.data.folder, asset, frame, YAHOO, cfg.data.adjusted, now)
        except OSError as error:
            raise DataError(f"Could not save {asset.symbol}: {_short(error)}") from error
    return health


def fetch_all(cfg: Config, symbols: Optional[Sequence[str]] = None, now: Optional[datetime] = None,
              downloader: Optional[Downloader] = None, pause: float = 1.0,
              progress: Optional[Callable[[AssetHealth], None]] = None) -> List[AssetHealth]:
    """Download, clean and judge every asset. A failure becomes a STOP for that asset, never fake data."""
    now = utc_now(now)
    downloader = downloader or download_yahoo
    results: List[AssetHealth] = []
    for number, asset in enumerate(pick_assets(cfg, symbols)):
        if number and pause:
            clock.sleep(pause)  # be polite to a free service
        try:
            health = fetch_one(cfg, asset, now, downloader)
        except SetupError:
            raise
        except DataError as error:
            health = AssetHealth(symbol=asset.symbol, source=YAHOO, problems=[str(error)])
        results.append(health)
        if progress:
            progress(health)
    return results


# ---------------------------------------------------------------- the report

def lag_text(cfg: DataConfig) -> str:
    return (f"A daily bar is used only after its session is over plus {cfg.confirm_delay_minutes} minutes "
            "(US stocks and ETFs close at 16:00 New York time, crypto days end at midnight UTC). "
            "Yahoo can publish late and sometimes fixes old bars, so the newest bar is always the last "
            "finished session and never a live price.")


def render_report(results: Sequence[AssetHealth], cfg: DataConfig, now: datetime, synthetic: bool = False) -> str:
    now = utc_now(now)
    lines: List[str] = []
    if synthetic:
        lines += ["*** MADE UP DATA. For tests and demos only. Never use it to decide anything. ***", ""]
    sources = ", ".join(sorted({r.source for r in results})) or "none"
    lines += [
        "DATA BOT REPORT",
        f"Report time: {now:%Y-%m-%d %H:%M} UTC",
        f"Source: {sources}",
        f"Interval: daily bars. Prices adjusted for splits and dividends: {'yes' if cfg.adjusted else 'no'}.",
        "Data lag: " + ("none, this data is made up." if synthetic else lag_text(cfg)),
        "",
        f"{'Symbol':<8}{'Bars':>6}  {'First':<12}{'Last':<12}{'Age':>4}  Status",
    ]
    for r in results:
        first = r.first.isoformat() if r.first else "none"
        last = r.last.isoformat() if r.last else "none"
        age = str(r.age_days) if r.age_days is not None else "n/a"
        lines.append(f"{r.symbol:<8}{r.bars:>6}  {first:<12}{last:<12}{age:>4}  {r.status}")
    lines.append("Age is the number of days since the newest finished bar.")
    for r in results:
        detail = ([f"  STOP: {t}" for t in r.problems] + [f"  WARN: {t}" for t in r.warnings]
                  + [f"  note: {t}" for t in r.notes])
        if detail:
            lines += ["", r.symbol] + detail
    overall = overall_status(results)
    lines.append("")
    if overall == STOP:
        lines.append("OVERALL: STOP. The Data Bot stops everything until this is fixed. "
                     "Nothing was guessed or filled in.")
    else:
        lines.append(f"OVERALL: {overall}")
    return "\n".join(lines)
