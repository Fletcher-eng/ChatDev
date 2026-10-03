"""Command line for the Algo Trading Lab (paper trading only).

    python -m algo_lab check             are the libraries, the config and the folders ready?
    python -m algo_lab fetch [SYMBOLS]   download daily bars from Yahoo Finance (free) and check them
    python -m algo_lab health [SYMBOLS]  check the saved bars again, because saved data goes stale
    python -m algo_lab moves SYMBOL      list every big one day move in the saved bars and what happened next
    python -m algo_lab demo              write MADE UP bars to a separate folder, to try things offline
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .data import (STOP, AssetHealth, DataError, download_yahoo, fetch_all, load_asset, overall_status, pick_assets,
                   render_moves, render_report, write_summary)
from .synthetic import write_demo

# import name, pip name, what it is for, needed right now
LIBRARIES = (
    ("pandas", "pandas", "the data", True),
    ("numpy", "numpy", "the data", True),
    ("yaml", "pyyaml", "reading config.yaml", True),
    ("yfinance", "yfinance", "downloading prices", True),
    ("hmmlearn", "hmmlearn", "Step 2, the regime model", False),
    ("sklearn", "scikit-learn", "Step 2, the regime model", False),
    ("streamlit", "streamlit", "Step 5, the terminal", False),
    ("plotly", "plotly", "Step 5, the terminal", False),
)


PAUSE_SECONDS = 1.0  # a polite pause between downloads from a free service


def die(message: str) -> int:
    print(f"\nProblem: {message}", file=sys.stderr)
    return 2


def load(args):
    return load_config(Path(args.config) if args.config else None)


def library_status() -> list:
    rows = []
    for module, pip_name, purpose, needed in LIBRARIES:
        version = None
        if importlib.util.find_spec(module) is not None:
            try:
                version = importlib.metadata.version(pip_name)
            except importlib.metadata.PackageNotFoundError:
                version = "installed"
        rows.append((pip_name, purpose, needed, version))
    return rows


# ---------------------------------------------------------------- commands

def cmd_check(args) -> int:
    print("ALGO LAB CHECK (paper trading only)")
    print(f"Python {platform.python_version()}")
    print("Libraries:")
    ready = True
    for pip_name, purpose, needed, version in library_status():
        if version:
            print(f"  ok       {pip_name} {version if version != 'installed' else ''}".rstrip())
        elif needed:
            ready = False
            print(f"  MISSING  {pip_name} (needed for {purpose})")
        else:
            print(f"  later    {pip_name} (needed for {purpose})")
    print("Install everything with: pip install -r algo_lab/requirements.txt")
    cfg = load(args)
    print(f"Config: ok, {len(cfg.assets)} assets: " + ", ".join(a.symbol for a in cfg.assets))
    folder = cfg.data.folder
    print(f"Saved data folder: {folder} ({'exists' if folder.exists() else 'not created yet, fetch makes it'})")
    print("Money and secrets: no paid service, no API key, no exchange account, no wallet. "
          "Nothing here can place a real order.")
    return 0 if ready else 2


def cmd_fetch(args) -> int:
    cfg = load(args)
    now = datetime.now(timezone.utc)
    print("Downloading daily bars from Yahoo Finance (free, no key). This takes a minute or two.")
    results = fetch_all(cfg, args.symbols, now, downloader=download_yahoo, pause=PAUSE_SECONDS,
                        progress=lambda health: print(f"  {health.symbol:<6} {health.status}"))
    report = render_report(results, cfg.data, now)
    print()
    print(report)
    try:
        path = write_summary(cfg.data.folder, report)
        print(f"\nBars are saved in {cfg.data.folder}. This report is also in {path}.")
        print("It holds no secrets, so it is safe to paste into a chat.")
    except OSError as error:
        print(f"\nCould not save the report file: {error}")
    if overall_status(results) == STOP:
        print("\nIf the problem is a connection error, check your internet and try again in a few minutes. "
              "Yahoo sometimes slows down free users.")
        return 2
    return 0


def cmd_health(args) -> int:
    cfg = load(args)
    now = datetime.now(timezone.utc)
    results = []
    for asset in pick_assets(cfg, args.symbols):
        try:
            _, health = load_asset(cfg, asset, now)
        except DataError as error:
            health = AssetHealth(symbol=asset.symbol, source="saved file", problems=[str(error)])
        results.append(health)
    print(render_report(results, cfg.data, now))
    return 2 if overall_status(results) == STOP else 0


def cmd_moves(args) -> int:
    cfg = load(args)
    asset = cfg.asset(args.symbol)
    frame, _ = load_asset(cfg, asset, datetime.now(timezone.utc))
    print(render_moves(asset.symbol, frame, cfg.data.extreme_move_pct))
    return 0


def cmd_demo(args) -> int:
    cfg = load(args)
    now = datetime.now(timezone.utc)
    results = write_demo(cfg, now)
    print(render_report(results, cfg.data, now, synthetic=True))
    print(f"\nMade up bars are saved in {cfg.data.demo_folder}. They are labelled SYNTHETIC, "
          "and the real loader refuses to read them.")
    return 0


# ---------------------------------------------------------------- entry point

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help=f"a settings file (default: {DEFAULT_CONFIG_PATH.as_posix()})")
    parser = argparse.ArgumentParser(prog="python -m algo_lab", description="Algo Trading Lab. Paper trading only.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", parents=[common], help="check libraries, config and folders").set_defaults(func=cmd_check)
    for name, func, text in (("fetch", cmd_fetch, "download and check daily bars"),
                             ("health", cmd_health, "check the saved bars again")):
        p = sub.add_parser(name, parents=[common], help=text)
        p.add_argument("symbols", nargs="*", help="only these symbols (default: all in the config)")
        p.set_defaults(func=func)
    moves = sub.add_parser("moves", parents=[common], help="list every big one day move in the saved bars")
    moves.add_argument("symbol", help="for example QNT")
    moves.set_defaults(func=cmd_moves)
    sub.add_parser("demo", parents=[common], help="write made up bars for offline practice").set_defaults(func=cmd_demo)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, DataError) as error:
        return die(str(error))
