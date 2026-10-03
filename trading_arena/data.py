"""Candle data for the Arena: CSV files, public exchange downloads, and a synthetic generator."""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (trading-arena educational paper trading lab)"

INTERVALS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
    "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400, "1w": 604800,
}


@dataclass(frozen=True)
class Candle:
    """One candle. The fields use the usual letters, so l is the low."""

    t: int  # unix seconds, start of the candle (UTC)
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float


@dataclass
class Dataset:
    candles: List[Candle]
    interval_s: int
    label: str = "synthetic"
    source: str = "synthetic"
    tv_symbol: Optional[str] = None  # hint for a manual replay on TradingView, such as BITSTAMP:BTCUSD


def parse_interval(text: str) -> int:
    key = text.strip().lower()
    if key in INTERVALS:
        return INTERVALS[key]
    raise ValueError(f"Unknown interval '{text}'. Use one of: {', '.join(INTERVALS)}")


def interval_label(seconds: int) -> str:
    for name, secs in INTERVALS.items():
        if secs == seconds:
            return name.upper() if name.endswith(("d", "w")) else name
    return f"{seconds}s"


def fmt_time(t: int, interval_s: int) -> str:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    if interval_s >= 86400:
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def clean_candles(candles: Iterable[Candle]) -> List[Candle]:
    """Sort by time, drop duplicates and broken rows, and repair high and low."""
    by_time = {}
    for c in candles:
        values = (c.o, c.h, c.l, c.c, c.v)
        if any(isinstance(x, float) and math.isnan(x) for x in values):
            continue
        if min(c.o, c.h, c.l, c.c) <= 0 or c.v < 0:
            continue
        high = max(c.h, c.o, c.c)
        low = min(c.l, c.o, c.c)
        by_time[c.t] = Candle(c.t, c.o, high, low, c.c, c.v)
    return [by_time[t] for t in sorted(by_time)]


# ---------------------------------------------------------------- CSV

_TIME_KEYS = ("time", "timestamp", "date", "datetime", "open_time", "open time")
_COLUMN_NAMES = {
    "o": ("open", "o"),
    "h": ("high", "h"),
    "l": ("low", "l"),
    "c": ("close", "c"),
    "v": ("volume", "vol", "v"),
}


def parse_time_cell(cell: str) -> int:
    text = cell.strip()
    try:
        number = float(text)
        if number > 1e14:
            number /= 1e6
        elif number > 1e11:
            number /= 1000.0
        return int(number)
    except ValueError:
        pass
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def infer_interval(candles: List[Candle]) -> int:
    if len(candles) < 3:
        return 86400
    diffs = [b.t - a.t for a, b in zip(candles[:300], candles[1:301])]
    median = statistics.median(diffs)
    return int(min(INTERVALS.values(), key=lambda s: abs(s - median)))


def load_csv(path: str | Path, label: Optional[str] = None, interval_s: Optional[int] = None) -> Dataset:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path} has no header row")
        names = {name.strip().lower(): name for name in reader.fieldnames}
        time_col = next((names[k] for k in _TIME_KEYS if k in names), None)
        if time_col is None:
            raise ValueError("The CSV needs a time column named time, timestamp, date, or datetime")
        cols = {}
        for key, options in _COLUMN_NAMES.items():
            found = next((names[o] for o in options if o in names), None)
            if found is None and key != "v":
                raise ValueError(f"The CSV needs a column for {options[0]}")
            cols[key] = found
        rows = []
        for row in reader:
            try:
                volume = float(row[cols["v"]]) if cols["v"] and row[cols["v"]] not in ("", None) else 0.0
                rows.append(Candle(
                    parse_time_cell(row[time_col]), float(row[cols["o"]]), float(row[cols["h"]]),
                    float(row[cols["l"]]), float(row[cols["c"]]), volume,
                ))
            except (ValueError, TypeError, KeyError):
                continue
    candles = clean_candles(rows)
    if len(candles) < 50:
        raise ValueError(f"Only {len(candles)} usable candles found in {path}")
    return Dataset(candles, interval_s or infer_interval(candles), label or path.stem, f"csv:{path.name}")


def save_csv(path: str | Path, candles: List[Candle]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([c.t, c.o, c.h, c.l, c.c, c.v])


# ---------------------------------------------------------------- public exchange downloads

def parse_bitstamp(payload: dict) -> List[Candle]:
    rows = payload["data"]["ohlc"]
    return [Candle(int(r["timestamp"]), float(r["open"]), float(r["high"]), float(r["low"]),
                   float(r["close"]), float(r["volume"])) for r in rows]


def parse_coinbase(payload: list) -> List[Candle]:
    # each row is [time, low, high, open, close, volume]
    return [Candle(int(r[0]), float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])) for r in payload]


def parse_binance(payload: list) -> List[Candle]:
    # each row is [open time in ms, open, high, low, close, volume, ...]
    return [Candle(int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in payload]


def http_get_json(url: str, params: Optional[dict] = None, timeout: int = 30, retries: int = 3):
    full = url + ("?" + urlencode(params) if params else "")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            last_error = error
            if error.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(
                f"HTTP {error.code} from {url}. The source may not serve your country. "
                "Try another --source, or use --csv with a file you downloaded."
            ) from error
        except (URLError, TimeoutError) as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Could not reach {url}: {last_error}. Check your internet, try another --source, or use --csv.")


def split_pair(pair: str) -> Tuple[str, str]:
    cleaned = pair.upper().replace("/", "").replace("-", "").replace("_", "")
    for quote in ("USDT", "USDC", "USD", "EUR", "GBP", "BTC"):
        if cleaned.endswith(quote) and len(cleaned) > len(quote):
            return cleaned[: -len(quote)], quote
    return cleaned[:-3], cleaned[-3:]


def tv_symbol_hint(source: str, pair: str) -> Optional[str]:
    base, quote = split_pair(pair)
    if source == "bitstamp":
        return f"BITSTAMP:{base}{quote}"
    if source == "coinbase":
        return f"COINBASE:{base}{quote}"
    if source == "binance":
        return f"BINANCE:{base}{'USDT' if quote == 'USD' else quote}"
    return None


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_candles(
    source: str,
    pair: str,
    interval_s: int,
    start_ts: int,
    end_ts: int,
    http: Callable = http_get_json,
    progress: Optional[Callable[[int], None]] = None,
    pause: float = 0.2,
) -> List[Candle]:
    """Download candles from a public endpoint. No API key is needed."""
    out: List[Candle] = []
    base, quote = split_pair(pair)
    cursor = start_ts
    if source == "bitstamp":
        if interval_s not in (60, 180, 300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400, 259200):
            raise ValueError("Bitstamp does not offer that interval")
        while cursor < end_ts:
            rows = parse_bitstamp(http(
                f"https://www.bitstamp.net/api/v2/ohlc/{(base + quote).lower()}/",
                {"step": interval_s, "limit": 1000, "start": cursor, "end": end_ts},
            ))
            if not rows:
                break
            out.extend(rows)
            following = rows[-1].t + interval_s
            if following <= cursor:
                break
            cursor = following
            if progress:
                progress(len(out))
            time.sleep(pause)
    elif source == "coinbase":
        if interval_s not in (60, 300, 900, 3600, 21600, 86400):
            raise ValueError("Coinbase does not offer that interval")
        span = 300 * interval_s
        while cursor < end_ts:
            window_end = min(cursor + span, end_ts)
            out.extend(parse_coinbase(http(
                f"https://api.exchange.coinbase.com/products/{base}-{quote}/candles",
                {"granularity": interval_s, "start": _iso(cursor), "end": _iso(window_end)},
            )))
            cursor = window_end
            if progress:
                progress(len(out))
            time.sleep(pause)
    elif source == "binance":
        names = {v: k for k, v in INTERVALS.items()}
        if interval_s not in names:
            raise ValueError("Binance does not offer that interval")
        symbol = base + ("USDT" if quote == "USD" else quote)
        cursor_ms = start_ts * 1000
        while cursor_ms < end_ts * 1000:
            rows = parse_binance(http(
                "https://data-api.binance.vision/api/v3/klines",
                {"symbol": symbol, "interval": names[interval_s], "limit": 1000,
                 "startTime": cursor_ms, "endTime": end_ts * 1000},
            ))
            if not rows:
                break
            out.extend(rows)
            cursor_ms = (rows[-1].t + interval_s) * 1000
            if progress:
                progress(len(out))
            time.sleep(pause)
    else:
        raise ValueError("source must be bitstamp, coinbase, or binance")
    return clean_candles(out)


# ---------------------------------------------------------------- synthetic prices

def synthetic(n: int, seed: int = 7, interval_s: int = 86400, start_price: float = 100.0,
              start_time: int = 1_420_070_400) -> Dataset:
    """A regime switching random walk with volatility clustering. For demos and tests only."""
    rng = random.Random(seed)
    regimes = {0: (0.0, 0.015), 1: (0.0015, 0.02), 2: (-0.0015, 0.02), 3: (-0.003, 0.04)}
    regime = 0
    price = start_price
    candles: List[Candle] = []
    for i in range(n):
        if rng.random() < 0.04:
            regime = rng.choice([0, 1, 2, 3])
        drift, vol = regimes[regime]
        path = [price]
        for _ in range(12):
            path.append(path[-1] * math.exp(rng.gauss(drift / 12, vol / math.sqrt(12))))
        o, c = path[0], path[-1]
        volume = 1000.0 * (1 + 8 * abs(math.log(c / o)) / vol) * math.exp(rng.gauss(0, 0.25))
        candles.append(Candle(start_time + i * interval_s, o, max(path), min(path), c, volume))
        price = c
    return Dataset(candles, interval_s, "synthetic demo prices", "synthetic", None)
