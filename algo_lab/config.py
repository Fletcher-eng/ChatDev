"""Settings for the lab, read from config.yaml. Every number that can change lives there, never in the code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")
KINDS = ("stock", "etf", "crypto")
MARKETS = ("us", "crypto")
SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{1,10}$")


class ConfigError(ValueError):
    """The config file has a problem. The message says what to fix."""


@dataclass(frozen=True)
class Asset:
    symbol: str  # short name used in reports and file names
    kind: str  # stock, etf or crypto
    sector: str
    yahoo: str  # the name Yahoo Finance uses

    @property
    def market(self) -> str:
        """Which clock the asset follows: crypto trades every day, everything else follows US market days."""
        return "crypto" if self.kind == "crypto" else "us"


@dataclass(frozen=True)
class DataConfig:
    interval: str
    history_years: float
    adjusted: bool
    min_bars: int
    confirm_delay_minutes: int
    stale_after_days: Dict[str, int]
    max_gap_days: Dict[str, int]
    extreme_move_pct: float
    ohlc_tolerance_pct: float
    bad_rows_stop_pct: float
    folder: Path
    demo_folder: Path


@dataclass(frozen=True)
class Config:
    assets: Tuple[Asset, ...]
    data: DataConfig

    def asset(self, symbol: str) -> Asset:
        wanted = symbol.strip().upper()
        for asset in self.assets:
            if asset.symbol == wanted:
                return asset
        known = ", ".join(a.symbol for a in self.assets)
        raise ConfigError(f"Unknown symbol {symbol}. Your config has: {known}.")


def _number(section: dict, key: str, where: str, lo: float, hi: float, integer: bool = False) -> float:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}: {key} must be a number, got {value!r}.")
    if integer and int(value) != value:
        raise ConfigError(f"{where}: {key} must be a whole number, got {value!r}.")
    if not lo <= value <= hi:
        raise ConfigError(f"{where}: {key} must be between {lo:g} and {hi:g}, got {value!r}.")
    return int(value) if integer else float(value)


def _text(section: dict, key: str, where: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {key} must be text, got {value!r}.")
    return value.strip()


def _by_market(section: dict, key: str, lo: int, hi: int) -> Dict[str, int]:
    value = section.get(key)
    if not isinstance(value, dict) or set(value) != set(MARKETS):
        raise ConfigError(f"data: {key} needs exactly two entries, us and crypto.")
    return {m: int(_number(value, m, f"data, {key}", lo, hi, integer=True)) for m in MARKETS}


def _assets(entries: Any) -> Tuple[Asset, ...]:
    if not isinstance(entries, list) or not entries:
        raise ConfigError("assets: give at least one asset.")
    out, seen = [], set()
    for number, entry in enumerate(entries, start=1):
        where = f"assets, entry {number}"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: each asset needs a symbol, a kind and a sector.")
        symbol = entry.get("symbol")
        if not isinstance(symbol, str):
            raise ConfigError(f"{where}: symbol must be text. Put quotes around it, like \"ON\".")
        symbol = symbol.strip().upper()
        if not SYMBOL_RE.match(symbol):
            raise ConfigError(f"{where}: symbol {symbol!r} must be 1 to 10 letters or digits. "
                              "Use the yahoo line for names like QNT-USD.")
        if symbol in seen:
            raise ConfigError(f"{where}: {symbol} is listed twice.")
        seen.add(symbol)
        kind = entry.get("kind")
        if kind not in KINDS:
            raise ConfigError(f"{where}: kind for {symbol} must be one of {', '.join(KINDS)}, got {kind!r}.")
        sector = _text(entry, "sector", f"{where} ({symbol})")
        yahoo = _text(entry, "yahoo", f"{where} ({symbol})") if "yahoo" in entry else symbol
        out.append(Asset(symbol=symbol, kind=kind, sector=sector, yahoo=yahoo))
    return tuple(out)


def _data(section: Any) -> DataConfig:
    if not isinstance(section, dict):
        raise ConfigError("data: this section is missing.")
    interval = section.get("interval")
    if interval != "1d":
        raise ConfigError(f"data: interval must be 1d (daily bars). Other intervals are not built yet, got {interval!r}.")
    adjusted = section.get("adjusted")
    if not isinstance(adjusted, bool):
        raise ConfigError("data: adjusted must be true or false.")
    folder = _text(section, "folder", "data")
    demo_folder = _text(section, "demo_folder", "data")
    if Path(folder) == Path(demo_folder):
        raise ConfigError("data: folder and demo_folder must differ, so made up data never mixes with real data.")
    return DataConfig(
        interval=interval,
        history_years=_number(section, "history_years", "data", 1, 30),
        adjusted=adjusted,
        min_bars=int(_number(section, "min_bars", "data", 250, 100000, integer=True)),
        confirm_delay_minutes=int(_number(section, "confirm_delay_minutes", "data", 0, 1440, integer=True)),
        stale_after_days=_by_market(section, "stale_after_days", 1, 30),
        max_gap_days=_by_market(section, "max_gap_days", 1, 30),
        extreme_move_pct=_number(section, "extreme_move_pct", "data", 1, 500),
        ohlc_tolerance_pct=_number(section, "ohlc_tolerance_pct", "data", 0, 5),
        bad_rows_stop_pct=_number(section, "bad_rows_stop_pct", "data", 0, 100),
        folder=Path(folder),
        demo_folder=Path(demo_folder),
    )


def load_config(path: Optional[Path] = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"Could not read the config file {path}: {error}") from error
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"The config file {path} is not valid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError(f"The config file {path} must have the sections assets and data.")
    return Config(assets=_assets(raw.get("assets")), data=_data(raw.get("data")))
