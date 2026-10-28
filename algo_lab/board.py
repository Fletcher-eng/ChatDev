"""The Trade Board: practice trades drawn on real price charts, built from practice/calls.json.

The page shows each practice call with its entry, stop and target on the price chart, the risk limits, and the
watch only tickers. A call is a record that does not change when prices move: the shares, the ATR and the stop gap
are fixed on the day the call is written. Only the charts are refreshed.
"""

from __future__ import annotations

import json
import re
import time as clock
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .config import Config
from .data import DataError, Downloader, download_yahoo, utc_now
from .look import load_bars, look_at

CALLS_PATH = Path("practice") / "calls.json"
OUT_PATH = Path("WareHouse") / "algo_lab" / "board.html"
TEMPLATE_PATH = Path(__file__).with_name("board_template.html")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,10}$")


def _positive(obj: dict, key: str, where: str, whole: bool = False) -> float:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise DataError(f"{where}: {key} must be a number above zero, got {value!r}.")
    if whole and int(value) != value:
        raise DataError(f"{where}: {key} must be a whole number, got {value!r}.")
    return value


def _text(obj: dict, key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{where}: {key} must be text, got {value!r}.")
    return value.strip()


def _day(obj: dict, key: str, where: str) -> str:
    value = _text(obj, key, where)
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise DataError(f"{where}: {key} must be a date like 2026-10-28, got {value!r}.") from error
    return value


def _symbol(obj: dict, where: str, seen: set) -> str:
    symbol = _text(obj, "symbol", where).upper()
    if not SYMBOL_RE.match(symbol):
        raise DataError(f"{where}: symbol {symbol!r} must be 1 to 10 letters or digits.")
    if symbol in seen:
        raise DataError(f"{where}: {symbol} is listed twice.")
    seen.add(symbol)
    return symbol


def load_calls(path: Path = CALLS_PATH) -> dict:
    """Read and check the practice file. A wrong number here would draw a wrong trade, so it stops loudly."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise DataError(f"Could not read the practice file {path}: {error}") from error
    except ValueError as error:
        raise DataError(f"The practice file {path} is not valid JSON: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("calls"), list) or not raw["calls"]:
        raise DataError(f"The practice file {path} needs a list of calls.")
    out = {
        "account": _positive(raw, "account", "practice"),
        "risk_pct": _positive(raw, "risk_pct", "practice"),
        "position_cap_pct": _positive(raw, "position_cap_pct", "practice"),
        "invested_cap_pct": _positive(raw, "invested_cap_pct", "practice"),
        "max_positions": int(_positive(raw, "max_positions", "practice", whole=True)),
        "chart_bars": int(_positive(raw, "chart_bars", "practice", whole=True)),
        "watch_bars": int(_positive(raw, "watch_bars", "practice", whole=True)),
        "written": _day(raw, "written", "practice"),
        "from_close": _day(raw, "from_close", "practice"),
        "calls": [], "watch": [],
    }
    seen: set = set()
    for number, call in enumerate(raw["calls"], start=1):
        where = f"call {number}"
        if not isinstance(call, dict):
            raise DataError(f"{where}: each call needs its fields.")
        if not isinstance(call.get("optional"), bool):
            raise DataError(f"{where}: optional must be true or false.")
        out["calls"].append({
            "symbol": _symbol(call, where, seen), "name": _text(call, "name", where),
            "action": _text(call, "action", where), "odds": _text(call, "odds", where),
            "reason": _text(call, "reason", where), "optional": call["optional"],
            "shares": int(_positive(call, "shares", where, whole=True)),
            "ref_close": float(_positive(call, "ref_close", where)),
            "atr14": float(_positive(call, "atr14", where)),
            "stop_gap": float(_positive(call, "stop_gap", where)),
        })
    for number, item in enumerate(raw.get("watch", []), start=1):
        where = f"watch entry {number}"
        if not isinstance(item, dict):
            raise DataError(f"{where}: each entry needs its fields.")
        out["watch"].append({"symbol": _symbol(item, where, seen), "name": _text(item, "name", where),
                             "why": _text(item, "why", where)})
    return out


def _series(frame: pd.DataFrame, average_bars: int, show: int) -> Dict[str, list]:
    """The last `show` bars as plain lists, with the simple average computed on the full history."""
    close = frame["close"]
    average = close.rolling(average_bars).mean()
    tail = frame.tail(show)
    digits = 2 if float(close.iloc[-1]) >= 1 else 4
    return {
        "d": [stamp.date().isoformat() for stamp in tail.index],
        "c": [round(float(value), digits) for value in tail["close"]],
        "a": [None if pd.isna(value) else round(float(value), digits) for value in average.loc[tail.index]],
    }


def build_data(cfg: Config, calls: dict, now: Optional[datetime] = None, downloader: Optional[Downloader] = None,
               pause: float = 1.0) -> dict:
    """Download real bars for every ticker in the practice file and shape them for the page."""
    now = utc_now(now)
    downloader = downloader or download_yahoo
    symbols = [c["symbol"] for c in calls["calls"]] + [w["symbol"] for w in calls["watch"]]
    frames = {}
    for number, symbol in enumerate(symbols):
        if number and pause:
            clock.sleep(pause)  # be polite to a free service
        frame, _, _ = load_bars(cfg, symbol, now, downloader)
        if len(frame) == 0:
            raise DataError(f"No finished daily bars came back for {symbol}, so the board cannot be drawn.")
        frames[symbol] = frame

    average_bars = cfg.look.fast_bars
    reference_day = pd.Timestamp(date.fromisoformat(calls["from_close"]))
    trades: List[dict] = []
    warnings: List[str] = []
    for call in calls["calls"]:
        frame = frames[call["symbol"]]
        if reference_day in frame.index:
            seen_close = float(frame.loc[reference_day, "close"])
            if abs(seen_close / call["ref_close"] - 1.0) > 0.005:
                warnings.append(f"Yahoo now shows {call['symbol']} closing at ${seen_close:.2f} on "
                                f"{reference_day:%d %b %Y}, not ${call['ref_close']:.2f}. The call was written with "
                                "the second number, and Yahoo may have adjusted its history since.")
        trades.append({
            "symbol": call["symbol"], "name": call["name"], "action": call["action"], "shares": call["shares"],
            "refClose": call["ref_close"], "atr14": call["atr14"], "stopGap": call["stop_gap"],
            "optional": call["optional"], "odds": call["odds"], "reason": call["reason"],
            "series": _series(frame, average_bars, calls["chart_bars"]),
        })
    watch: List[dict] = []
    for item in calls["watch"]:
        frame = frames[item["symbol"]]
        look = look_at(item["symbol"], frame, now, cfg.look)
        watch.append({
            "symbol": item["symbol"], "name": item["name"], "why": item["why"],
            "stats": {"last": look.last_close, "change5": look.change_5, "change20": look.change_20, "bars": look.bars},
            "flags": [{"name": name, "text": text[:1].upper() + text[1:]} for name, text in look.flags],
            "series": _series(frame, average_bars, calls["watch_bars"]),
        })
    as_of = max(frames[c["symbol"]].index[-1] for c in calls["calls"]).date().isoformat()
    return {
        "asOf": as_of, "builtAt": now.replace(microsecond=0).isoformat(), "written": calls["written"],
        "account": calls["account"], "riskPct": calls["risk_pct"], "positionCapPct": calls["position_cap_pct"],
        "investedCapPct": calls["invested_cap_pct"], "maxPositions": calls["max_positions"],
        "averageBars": average_bars, "trades": trades, "watch": watch, "warnings": warnings,
    }


def render_page(data: dict, standalone: bool = True) -> str:
    """Put the data into the page. `standalone` wraps it as a full document that opens in any browser."""
    # Every "<" in the data is escaped, so text from the outside can never close the script tag early.
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")
    body = TEMPLATE_PATH.read_text(encoding="utf-8").replace("__DATA__", blob)
    if not standalone:
        return body
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "</head>\n<body>\n" + body + "\n</body>\n</html>\n")


def write_board(cfg: Config, calls_path: Path = CALLS_PATH, out_path: Path = OUT_PATH,
                now: Optional[datetime] = None, downloader: Optional[Downloader] = None,
                pause: float = 1.0, standalone: bool = True) -> Path:
    data = build_data(cfg, load_calls(calls_path), now, downloader, pause)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_page(data, standalone), encoding="utf-8")
    return out
