"""Made up prices for tests and the demo. Always labelled SYNTHETIC, kept in their own folder, never a fallback.

The generator switches between three hidden regimes (bear, neutral, bull), each with its own average daily
return and its own daily swing. Because the hidden path is known, later steps can check whether the regime
model finds it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .config import Config
from .data import SYNTHETIC, AssetHealth, prepare, save_cache

# regime: (average daily log return, daily standard deviation)
REGIMES = {
    "bear": (-0.0020, 0.025),
    "neutral": (0.0003, 0.010),
    "bull": (0.0012, 0.008),
}


def make_series(n_bars: int, market: str, end: date, seed: int, start_price: float = 100.0,
                stay: float = 0.97, vol_scale: float = 1.0) -> Tuple[pd.DataFrame, pd.Series]:
    """Made up daily bars ending on or before `end`, plus the hidden regime of every bar."""
    rng = np.random.default_rng(seed)
    if market == "crypto":
        dates = pd.date_range(end=pd.Timestamp(end), periods=n_bars, freq="D")
    else:
        dates = pd.bdate_range(end=pd.Timestamp(end), periods=n_bars)
    names = list(REGIMES)
    state = int(rng.integers(len(names)))
    path: List[str] = []
    for _ in range(n_bars):
        path.append(names[state])
        if rng.random() > stay:  # a regime usually lasts a while, then jumps to one of the other two
            state = int(rng.choice([i for i in range(len(names)) if i != state]))
    mean = np.array([REGIMES[name][0] for name in path])
    vol = np.array([REGIMES[name][1] for name in path]) * vol_scale
    close = start_price * np.exp(np.cumsum(rng.normal(mean, vol)))
    previous = np.concatenate([[start_price], close[:-1]])
    open_ = previous * np.exp(rng.normal(0.0, vol * 0.3))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0.0, vol * 0.5)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0.0, vol * 0.5)))
    volume = np.round(1_000_000 * np.exp(rng.normal(0.0, 0.35, n_bars)) * (vol / 0.01))
    index = pd.DatetimeIndex(dates, name="date")
    frame = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index)
    return frame, pd.Series(path, index=index, name="regime")


def make_universe(cfg: Config, end: date, bars: int = 1500, seed: int = 7) -> Dict[str, pd.DataFrame]:
    """One made up series per asset in the config. Crypto swings more than stocks."""
    frames = {}
    for number, asset in enumerate(cfg.assets):
        scale = 2.0 if asset.market == "crypto" else 1.0
        frames[asset.symbol] = make_series(bars, asset.market, end, seed + number, vol_scale=scale)[0]
    return frames


def write_demo(cfg: Config, now: datetime) -> List[AssetHealth]:
    """Save made up bars for every asset in the demo folder, through the same cleaning line as real data."""
    end = (now - timedelta(days=1)).date()
    frames = make_universe(cfg, end)
    results = []
    for asset in cfg.assets:
        frame, health = prepare(frames[asset.symbol], asset, cfg, now, SYNTHETIC)
        save_cache(cfg.data.demo_folder, asset, frame, SYNTHETIC, cfg.data.adjusted, now)
        results.append(health)
    return results
