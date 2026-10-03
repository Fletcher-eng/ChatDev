"""Scenarios: a fixed long setup, the visible history, and a hidden future.

The analysts only ever receive text built by snapshot_text(), which reads the visible window
and the setup. The future is kept private and is read only by settle() and the reports.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List

from .data import Candle, Dataset, interval_label
from .indicators import atr, roc, rsi, sma, swing


@dataclass(frozen=True)
class Params:
    horizon: int = 20          # candles allowed after entry
    k_atr: float = 1.5         # stop distance in ATRs
    rr: float = 2.0            # reward to risk, never below the program rule of 1 to 2
    fee: float = 0.001         # exchange fee per side, as a fraction of price
    slip: float = 0.0005       # slippage per side, as a fraction of price
    atr_n: int = 14
    shown: int = 60            # candles shown to the analysts
    htf_factor: int = 7        # candles per higher timeframe candle
    warmup: int = 120          # candles needed before the first decision
    window_size: int = 300     # candles kept for indicators

    @staticmethod
    def for_interval(interval_s: int, **overrides) -> "Params":
        if interval_s >= 86400:
            base = {"horizon": 20, "htf_factor": 7}
        elif interval_s >= 14400:
            base = {"horizon": 30, "htf_factor": 6}
        elif interval_s >= 3600:
            base = {"horizon": 48, "htf_factor": 24}
        else:
            base = {"horizon": 48, "htf_factor": 12}
        base.update({k: v for k, v in overrides.items() if v is not None})
        return Params(**base)


@dataclass(frozen=True)
class Setup:
    ref_price: float
    stop: float
    target: float
    atr: float
    rr: float
    horizon: int
    fee: float
    slip: float

    @property
    def risk(self) -> float:
        return self.ref_price - self.stop

    @property
    def reward(self) -> float:
        return self.target - self.ref_price

    @property
    def cost_r(self) -> float:
        """Round trip costs measured in units of risk."""
        return (2 * self.fee + 2 * self.slip) * self.ref_price / self.risk

    @property
    def base_rate(self) -> float:
        """Chance the target comes first on a driftless random walk with no time limit."""
        return self.risk / (self.risk + self.reward)

    @property
    def breakeven_p(self) -> float:
        """Win chance needed to break even after costs."""
        return (1.0 + self.cost_r) / (self.rr + 1.0)


@dataclass
class Scenario:
    id: int
    index: int
    window: List[Candle]
    setup: Setup
    interval_s: int
    htf_factor: int
    shown: int
    _future: List[Candle]  # hidden from the analysts

    @property
    def decision_time(self) -> int:
        return self.window[-1].t

    def reveal(self) -> List[Candle]:
        """Only settlement and the reports may call this."""
        return self._future


def build_setup(window: List[Candle], params: Params) -> Setup:
    ref = window[-1].c
    a = atr(window, params.atr_n)
    stop = max(ref - params.k_atr * a, ref * 0.01)
    target = ref + params.rr * (ref - stop)
    return Setup(ref, stop, target, a, params.rr, params.horizon, params.fee, params.slip)


def pick_indices(n_candles: int, count: int, params: Params, seed: int) -> List[int]:
    """Decision points spaced so the outcome windows never overlap."""
    step = params.horizon + 1
    candidates = list(range(params.warmup, n_candles - params.horizon, step))
    rng = random.Random(seed)
    return sorted(rng.sample(candidates, min(count, len(candidates))))


def build_scenarios(ds: Dataset, count: int, params: Params, seed: int = 7) -> List[Scenario]:
    out = []
    for n, i in enumerate(pick_indices(len(ds.candles), count, params, seed), start=1):
        window = ds.candles[max(0, i - params.window_size + 1): i + 1]
        future = ds.candles[i + 1: i + 1 + params.horizon]
        out.append(Scenario(n, i, window, build_setup(window, params), ds.interval_s,
                            params.htf_factor, params.shown, future))
    return out


def _signed(x: float, nd: int = 2) -> str:
    return f"+{x:.{nd}f}" if x >= 0 else f"minus {abs(x):.{nd}f}"


def facts(sc: Scenario) -> dict:
    """Numbers about the visible window only. Used in the prompt and by the learning coach."""
    w = sc.window
    closes = [c.c for c in w]
    last = closes[-1]
    s20, s50 = sma(closes, 20), sma(closes, 50)
    hh, ll, since_hh, since_ll = swing(w, 40)
    vol20 = (sum(c.v for c in w[-20:]) / len(w[-20:])) or 1.0
    vol5 = sum(c.v for c in w[-5:]) / len(w[-5:])
    return {
        "atr_pct": sc.setup.atr / last * 100, "d20": (last / s20 - 1) * 100, "d50": (last / s50 - 1) * 100,
        "ma20_above_50": s20 > s50, "rsi": rsi(closes),
        "roc": {k: roc(closes, k) for k in (5, 10, 20, 40)},
        "hh": hh / last * 100, "ll": ll / last * 100, "since_hh": since_hh, "since_ll": since_ll,
        "vol_last": w[-1].v / vol20, "vol_5": vol5 / vol20,
    }


def facts_line(sc: Scenario) -> str:
    """One short line of facts, for the coach's table. Plain words, no dashes."""
    f = facts(sc)
    side = "above" if f["d50"] >= 0 else "below"
    return (f"RSI {f['rsi']:.0f}, price {abs(f['d50']):.1f} percent {side} the 50 candle average, "
            f"20 average {'above' if f['ma20_above_50'] else 'below'} the 50 average, "
            f"ATR {f['atr_pct']:.1f} percent, volume {f['vol_last']:.1f} times average")


def snapshot_text(sc: Scenario) -> str:
    """Everything an analyst is allowed to know. Prices are scaled, and no coin or date is named."""
    w = sc.window
    last = w[-1].c
    scale = 100.0 / last
    view = w[-sc.shown:]
    vmean = (sum(c.v for c in view) / len(view)) or 1.0
    lines = [
        f"CANDLES. Each line is one {interval_label(sc.interval_s)} candle, oldest first. Prices are scaled so the "
        "latest close is 100. Volume is scaled so the average is 1.00. The first column counts candles back from "
        "the latest closed candle.",
        "back open high low close volume",
    ]
    for i, c in enumerate(view):
        back = len(view) - 1 - i
        lines.append(f"{back} {c.o * scale:.2f} {c.h * scale:.2f} {c.l * scale:.2f} {c.c * scale:.2f} {c.v / vmean:.2f}")

    f = sc.htf_factor
    groups = []
    for g in range(12):
        hi = len(w) - g * f
        lo = hi - f
        if lo < 0:
            break
        chunk = w[lo:hi]
        groups.append((chunk[0].o, max(x.h for x in chunk), min(x.l for x in chunk), chunk[-1].c,
                       sum(x.v for x in chunk)))
    groups.reverse()
    if groups:
        gmean = (sum(g[4] for g in groups) / len(groups)) or 1.0
        lines += ["", f"HIGHER TIMEFRAME. Each line groups {f} candles. Same scaling.", "back open high low close volume"]
        for i, g in enumerate(groups):
            back = len(groups) - 1 - i
            lines.append(f"{back} {g[0] * scale:.2f} {g[1] * scale:.2f} {g[2] * scale:.2f} {g[3] * scale:.2f} {g[4] / gmean:.2f}")

    f = facts(sc)
    s = sc.setup
    lines += [
        "",
        "FACTS",
        f"ATR14 is {f['atr_pct']:.2f} percent of price.",
        f"Price is {_signed(f['d20'])} percent from the 20 candle average and "
        f"{_signed(f['d50'])} percent from the 50 candle average. The 20 average is "
        f"{'above' if f['ma20_above_50'] else 'below'} the 50 average.",
        f"RSI14 is {f['rsi']:.1f}.",
        "Change over the last 5, 10, 20 and 40 candles in percent: "
        + ", ".join(_signed(f["roc"][k]) for k in (5, 10, 20, 40)) + ".",
        f"The 40 candle high is {f['hh']:.2f}, set {f['since_hh']} candles ago. The 40 candle low is "
        f"{f['ll']:.2f}, set {f['since_ll']} candles ago.",
        f"The latest volume is {f['vol_last']:.2f} times the 20 candle average. The 5 candle average is "
        f"{f['vol_5']:.2f} times it.",
        "",
        "SETUP (long only, play money). Enter about 100.00 at the open of the next candle. "
        f"STOP at {s.stop * scale:.2f} (minus {(s.ref_price - s.stop) / s.ref_price * 100:.2f} percent, "
        f"{s.risk / s.atr:.1f} ATR). TARGET at {s.target * scale:.2f} (plus "
        f"{(s.target - s.ref_price) / s.ref_price * 100:.2f} percent). Reward to risk is {s.rr:.1f} to 1. "
        f"You have {s.horizon} candles after entry. Round trip costs are about "
        f"{(2 * s.fee + 2 * s.slip) * 100:.2f} percent of price.",
        f"QUESTION: is the TARGET touched before the STOP within {s.horizon} candles? If one candle touches both, "
        "the STOP counts first. If neither is touched in time, the answer is no.",
    ]
    return "\n".join(lines)
