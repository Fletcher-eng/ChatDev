"""Command line for the Trading Arena.

    python -m trading_arena demo                      a free offline tour with mock analysts
    python -m trading_arena fetch --pair btcusd       download daily candles from a public exchange feed
    python -m trading_arena run --csv FILE            run the 7 vs 7 arena with a real model
    python -m trading_arena report --run FOLDER       rebuild the reports from a saved run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import data as D
from .agents import MockClient, OpenAIClient, UsageMeter, make_roster
from .arena import ArenaConfig, planned_calls, run_scenarios
from .learn import lesson_pairs, run_learning
from .report import build_record, sg, tidy, when, write_all
from .scenario import Params, build_scenarios
from .scoring import summarize

DEFAULT_ROOT = Path("WareHouse") / "arena"


def load_env() -> None:
    """Use the same .env file as ChatDev. The key is only ever read, never printed."""
    try:
        from utils.env_loader import load_dotenv_file

        load_dotenv_file()
        return
    except Exception:  # fall back to a tiny parser when run outside the repo
        pass
    path = Path(".env")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def die(message: str) -> int:
    print(f"\nProblem: {message}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------- fetch

def cmd_fetch(args) -> int:
    try:
        interval_s = D.parse_interval(args.interval)
    except ValueError as error:
        return die(str(error))
    end = int(time.time()) // interval_s * interval_s
    start = int(end - args.years * 365.25 * 86400)
    print(f"Downloading {args.pair.upper()} {args.interval} candles from {args.source} for {args.years} years...")
    try:
        candles = D.fetch_candles(args.source, args.pair, interval_s, start, end,
                                  progress=lambda n: print(f"  {n} candles so far", end="\r"))
    except (RuntimeError, ValueError) as error:
        return die(str(error))
    if len(candles) < 300:
        return die(f"Only {len(candles)} candles came back. Try a longer --years, another --source, or --csv.")
    out = Path(args.out) if args.out else DEFAULT_ROOT / "data" / f"{args.pair.lower()}_{args.interval}.csv"
    sidecar = {"label": f"{args.pair.upper()} {D.interval_label(interval_s)}", "source": args.source,
               "tv_symbol": D.tv_symbol_hint(args.source, args.pair)}
    try:
        D.save_csv(out, candles)
        out.with_suffix(".json").write_text(json.dumps(sidecar), encoding="utf-8")
    except OSError as error:
        return die(f"Could not save {out}: {error}")
    print(f"\nSaved {len(candles)} candles to {out}")
    print(f"From {D.fmt_time(candles[0].t, interval_s)} to {D.fmt_time(candles[-1].t, interval_s)}.")
    print(f"Next: python -m trading_arena run --csv {out} --agents mock   (free), then with a real model.")
    return 0


# ---------------------------------------------------------------- run

def load_dataset(args) -> D.Dataset:
    interval_s = D.parse_interval(args.interval) if args.interval else None
    if args.csv:
        ds = D.load_csv(args.csv, label=args.label, interval_s=interval_s)
        sidecar = Path(args.csv).with_suffix(".json")
        if sidecar.exists():
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            ds.label = args.label or meta.get("label", ds.label)
            ds.source = meta.get("source", ds.source)
            ds.tv_symbol = meta.get("tv_symbol")
        if args.tv_symbol:
            ds.tv_symbol = args.tv_symbol
        return ds
    if args.synthetic:
        return D.synthetic(args.synthetic, seed=args.seed, interval_s=interval_s or 86400)
    raise ValueError("Give --csv FILE (real prices) or --synthetic N (made up prices for a demo).")


def make_client(args):
    if args.agents == "mock":
        return MockClient(args.seed), "mock", True
    key = os.environ.get("API_KEY")
    if not key:
        raise ValueError("API_KEY is not set. Put it in your .env file (never in a chat), or use --agents mock.")
    model = args.model or os.environ.get("MODEL_NAME") or "gpt-4o"
    return OpenAIClient(model, key, os.environ.get("BASE_URL")), model, False


def estimate(args, n: int, n_agents: int) -> int:
    if args.learn:
        train = max(1, min(n - 1, int(n * args.train_fraction)))
        test = n - train
        return planned_calls(train, n_agents, args.rounds) + 1 + 2 * planned_calls(test, n_agents, args.rounds)
    return planned_calls(n, n_agents, args.rounds)


def cmd_run(args) -> int:
    load_env()
    try:
        ds = load_dataset(args)
        if args.rr < 2.0:
            raise ValueError("Reward to risk must be at least 2, the program rule of 1 to 2.")
        params = Params.for_interval(ds.interval_s, horizon=args.horizon, k_atr=args.k, rr=args.rr,
                                     fee=args.fee / 100.0, slip=args.slip / 100.0)
        scenarios = build_scenarios(ds, args.scenarios, params, seed=args.seed)
        if len(scenarios) < 2:
            raise ValueError("Not enough candles for that many scenarios. Use more data or fewer scenarios.")
        client, model, offline = make_client(args)
    except (ValueError, OSError) as error:
        return die(str(error))

    roster = make_roster()
    calls = estimate(args, len(scenarios), len(roster))
    intraday = ds.interval_s < 86400
    print(f"\nData: {tidy(ds.label)}, {D.interval_label(ds.interval_s)} candles, {len(ds.candles)} in total.")
    print(f"Scenarios: {len(scenarios)} (from {when(scenarios[0].decision_time, intraday)} to "
          f"{when(scenarios[-1].decision_time, intraday)}), each with {params.horizon} candles to resolve.")
    s0 = scenarios[0].setup
    print(f"Setup: stop {params.k_atr} ATR, reward to risk {params.rr} to 1, round trip costs "
          f"{(2 * params.fee + 2 * params.slip) * 100:.2f} percent, break even win rate about {s0.breakeven_p * 100:.0f} percent.")
    if len(scenarios) < args.scenarios:
        print(f"Note: only {len(scenarios)} non overlapping scenarios fit in this data.")
    print(f"Analysts: 7 bulls and 7 bears, {args.rounds} round{'s' if args.rounds > 1 else ''}. Model: {model}.")
    print(f"About {calls:,} model calls, roughly {calls * (1700 if args.rounds == 1 else 2100) / 1e6:.1f} million input "
          f"tokens and {calls * 130 / 1e6:.2f} million output tokens.")
    if args.price_in is not None and args.price_out is not None:
        cost = calls * (1700 if args.rounds == 1 else 2100) / 1e6 * args.price_in + calls * 130 / 1e6 * args.price_out
        print(f"At your prices that is about {cost:.2f} dollars.")
    elif not offline:
        print("I do not know your model's price. Check your provider, or pass --price-in and --price-out "
              "(dollars per million tokens) to see an estimate.")
    if not offline:
        if calls > args.max_calls:
            return die(f"That is {calls:,} calls, over the --max-calls limit of {args.max_calls:,}. "
                       "Lower --scenarios or raise the limit on purpose.")
        if not args.yes and input("Type YES to start (this uses your API credits): ").strip() != "YES":
            print("Cancelled.")
            return 1

    meter = UsageMeter()
    cfg = ArenaConfig(rounds=args.rounds, workers=args.workers, temperature=args.temperature)

    def progress(*parts) -> None:
        phase = parts[0] if len(parts) == 4 else ""
        i, n, r = parts[-3:]
        o = r.outcome
        bull = sum(v for k, v in r.payoffs.items() if k.startswith("bull_"))
        bear = sum(v for k, v in r.payoffs.items() if k.startswith("bear_"))
        print(f"{phase + ' ' if phase else ''}{i}/{n} decided {when(r.scenario.decision_time, intraday)}: {o.result} "
              f"after {o.bars} candles. Bulls {sg(bull, 1)}, bears {sg(bear, 1)}.")

    learning = None
    try:
        print("\nPlacing blind bets, then revealing the future...\n")
        if args.learn:
            lr = run_learning(scenarios, roster, client, cfg, meter, train_fraction=args.train_fraction,
                              progress=progress)
            results = lr["train"] + lr["test_plain"]  # the headline never mixes in runs that had lessons
            learning = {"lessons": lr["lessons"], "train_n": lr["train_n"], "test_n": lr["test_n"],
                        "effect": lr["effect"], "pairs": lesson_pairs(lr)}
        else:
            results = run_scenarios(scenarios, roster, client, cfg, meter, progress)
    except RuntimeError as error:
        return die(str(error))
    except KeyboardInterrupt:
        print("\nStopped. Nothing was saved for this run.")
        return 130

    summary = summarize(results, roster)
    meta = {
        "created": datetime.now(timezone.utc).isoformat(), "label": ds.label, "source": ds.source,
        "interval": D.interval_label(ds.interval_s), "interval_s": ds.interval_s, "intraday": intraday,
        "tv_symbol": ds.tv_symbol, "model": model, "offline": offline, "rounds": args.rounds, "seed": args.seed,
        "synthetic": ds.source == "synthetic",
        "params": {"k_atr": params.k_atr, "rr": params.rr, "horizon": params.horizon, "fee": params.fee,
                   "slip": params.slip},
    }
    usage = {"calls": meter.total.calls, "prompt_tokens": meter.total.prompt_tokens,
             "completion_tokens": meter.total.completion_tokens}
    record = build_record(results, roster, summary, meta, usage, learning)
    out_dir = Path(args.out) if args.out else DEFAULT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = write_all(out_dir, record)

    print(f"\n{tidy(summary['verdict'])}")
    t = summary["teams"]
    print(f"Bulls {sg(t['bull']['pnl'], 1)} points, bears {sg(t['bear']['pnl'], 1)} points.")
    print(f"\nSaved to {out_dir}")
    print(f"  Watch it play: {paths['replay'].resolve().as_uri()}")
    print(f"  Read the numbers: {paths['report']}")
    return 0


def cmd_report(args) -> int:
    run_dir = Path(args.run)
    try:
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return die(f"Could not read {run_dir / 'run.json'}: {error}")
    paths = write_all(run_dir, record)
    print(f"Rebuilt the reports in {run_dir}")
    print(f"  Watch it play: {paths['replay'].resolve().as_uri()}")
    return 0


def cmd_demo(args) -> int:
    args.csv, args.label, args.tv_symbol, args.synthetic, args.agents = None, None, None, 3000, "mock"
    args.interval = "1d"
    return cmd_run(args)


# ---------------------------------------------------------------- argument parsing

def add_run_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scenarios", type=int, default=30, help="how many scenarios (use 100 or more for any conclusion)")
    p.add_argument("--rounds", type=int, choices=(1, 2), default=1, help="1 = independent bets, 2 = add a debate round")
    p.add_argument("--workers", type=int, default=7, help="parallel model calls")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--horizon", type=int, default=None, help="candles to resolve (default depends on the interval)")
    p.add_argument("--k", type=float, default=1.5, help="stop distance in ATRs")
    p.add_argument("--rr", type=float, default=2.0, help="reward to risk, at least 2")
    p.add_argument("--fee", type=float, default=0.10, help="exchange fee per side, in percent")
    p.add_argument("--slip", type=float, default=0.05, help="slippage per side, in percent")
    p.add_argument("--learn", action="store_true", help="coach lessons from the first half, tested on the second half")
    p.add_argument("--train-fraction", dest="train_fraction", type=float, default=0.5)
    p.add_argument("--model", default=None, help="model name (default MODEL_NAME from .env, else gpt-4o)")
    p.add_argument("--price-in", dest="price_in", type=float, default=None, help="dollars per million input tokens")
    p.add_argument("--price-out", dest="price_out", type=float, default=None, help="dollars per million output tokens")
    p.add_argument("--max-calls", dest="max_calls", type=int, default=3000, help="refuse to run above this many calls")
    p.add_argument("--yes", action="store_true", help="skip the confirmation question")
    p.add_argument("--out", default=None, help="output folder (default WareHouse/arena/<time>)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading_arena", description="7 bulls vs 7 bears, play money bets, hidden future.")
    sub = parser.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="download candles from a public exchange feed (no key needed)")
    f.add_argument("--source", choices=("bitstamp", "coinbase", "binance"), default="bitstamp")
    f.add_argument("--pair", default="btcusd")
    f.add_argument("--interval", default="1d")
    f.add_argument("--years", type=float, default=8.0)
    f.add_argument("--out", default=None)
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("run", help="run the arena")
    src = r.add_argument_group("data")
    src.add_argument("--csv", default=None, help="a candle file with time, open, high, low, close, volume")
    src.add_argument("--synthetic", type=int, default=None, help="use N made up candles for a demo")
    src.add_argument("--interval", default=None, help="candle size, such as 1d (guessed from the file if omitted)")
    src.add_argument("--label", default=None)
    src.add_argument("--tv-symbol", dest="tv_symbol", default=None, help="TradingView symbol hint, such as BITSTAMP:BTCUSD")
    r.add_argument("--agents", choices=("llm", "mock"), default="llm", help="llm uses your API key, mock is free and has no skill")
    add_run_options(r)
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("demo", help="a free offline tour with made up prices and mock analysts")
    add_run_options(d)
    d.set_defaults(func=cmd_demo, scenarios=24, rounds=2)

    p = sub.add_parser("report", help="rebuild the reports from a saved run folder")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
