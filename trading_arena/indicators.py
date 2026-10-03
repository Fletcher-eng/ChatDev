"""Small, dependency free indicators. Every function only looks at the candles it is given."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .data import Candle


def sma(values: Sequence[float], n: int) -> float:
    window = values[-n:]
    return sum(window) / len(window)


def true_ranges(candles: Sequence[Candle]) -> List[float]:
    out = []
    for i, c in enumerate(candles):
        if i == 0:
            out.append(c.h - c.l)
        else:
            prev = candles[i - 1].c
            out.append(max(c.h - c.l, abs(c.h - prev), abs(c.l - prev)))
    return out


def atr(candles: Sequence[Candle], n: int = 14) -> float:
    """Average true range with Wilder smoothing, using only the given candles."""
    trs = true_ranges(candles)
    first = trs[:n]
    value = sum(first) / len(first)
    for tr in trs[n:]:
        value = (value * (n - 1) + tr) / n
    return value


def rsi(closes: Sequence[float], n: int = 14) -> float:
    if len(closes) < 2:
        return 50.0
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain = sum(gains[:n]) / len(gains[:n])
    avg_loss = sum(losses[:n]) / len(losses[:n])
    for g, loss in zip(gains[n:], losses[n:]):
        avg_gain = (avg_gain * (n - 1) + g) / n
        avg_loss = (avg_loss * (n - 1) + loss) / n
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def roc(closes: Sequence[float], k: int) -> float:
    """Percent change over the last k candles."""
    if len(closes) <= k:
        k = len(closes) - 1
    if k <= 0:
        return 0.0
    return (closes[-1] / closes[-1 - k] - 1.0) * 100.0


def swing(candles: Sequence[Candle], lookback: int = 40) -> Tuple[float, float, int, int]:
    """Highest high, lowest low, and how many candles ago each happened."""
    view = candles[-lookback:]
    hh = max(c.h for c in view)
    ll = min(c.l for c in view)
    since_hh = next(i for i, c in enumerate(reversed(view)) if c.h == hh)
    since_ll = next(i for i, c in enumerate(reversed(view)) if c.l == ll)
    return hh, ll, since_hh, since_ll
