"""Settlement: replay the hidden future candle by candle and decide what happened."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .data import Candle
from .scenario import Setup

WIN = "WIN"
LOSS = "LOSS"
TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class Outcome:
    result: str       # WIN, LOSS, or TIMEOUT
    k: int            # index of the future candle where it resolved
    entry: float
    exit: float
    r_gross: float    # result in units of planned risk, before fees
    r_net: float      # after fees (slippage is already inside the prices)

    @property
    def bars(self) -> int:
        return self.k + 1


def settle(setup: Setup, future: List[Candle]) -> Outcome:
    """Enter at the next open, then walk forward. A candle that touches both levels counts as a stop."""
    if not future:
        raise ValueError("No future candles to settle")
    entry = future[0].o * (1 + setup.slip)
    risk = setup.risk
    last = min(len(future), setup.horizon)
    result, exit_price, k = TIMEOUT, future[last - 1].c * (1 - setup.slip), last - 1
    for i in range(last):
        candle = future[i]
        stop_hit = candle.l <= setup.stop or (i == 0 and entry <= setup.stop)
        target_hit = candle.h >= setup.target or (i == 0 and entry >= setup.target)
        if stop_hit:
            fill = min(setup.stop, candle.o) if candle.o < setup.stop else setup.stop
            result, exit_price, k = LOSS, fill * (1 - setup.slip), i
            break
        if target_hit:
            fill = max(setup.target, candle.o) if candle.o >= setup.target else setup.target
            result, exit_price, k = WIN, fill, i
            break
    r_gross = (exit_price - entry) / risk
    r_net = r_gross - setup.fee * (entry + exit_price) / risk
    return Outcome(result, k, entry, exit_price, r_gross, r_net)


def bet_payoff(side: str, stake: float, outcome: Outcome, rr: float) -> float:
    """Play money payoff. Bulls bet the target comes first, bears bet it does not. Zero sum."""
    if outcome.result == WIN:
        base = rr
    elif outcome.result == LOSS:
        base = -1.0
    else:
        base = max(-1.0, min(rr, outcome.r_gross))
    return stake * base if side == "bull" else -stake * base
