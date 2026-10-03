"""Reports built from one run record: report.md, bets.csv, scenarios.csv, run.json, and replay.html."""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .arena import ScenarioResult
from .scoring import brier, crowd_p

TEMPLATE = Path(__file__).with_name("replay_template.html")


# ---------------------------------------------------------------- formatting helpers (no dashes in prose)

def _missing(x: Optional[float]) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _plain(x: float, nd: int) -> str:
    """A number as words: a negative one starts with the word minus, never with a dash."""
    text = f"{abs(x):.{nd}f}"
    return f"minus {text}" if x < 0 and float(text) != 0 else text


def sg(x: Optional[float], nd: int = 2) -> str:
    if _missing(x):
        return "n/a"
    text = _plain(x, nd)
    return text if text.startswith("minus") else f"plus {text}"


def pc(x: Optional[float], nd: int = 0) -> str:
    return "n/a" if _missing(x) else f"{_plain(x * 100, nd)} percent"


def num(x: Optional[float], nd: int = 3) -> str:
    return "n/a" if _missing(x) else _plain(x, nd)


def when(t: int, intraday: bool) -> str:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    text = f"{dt:%b} {dt.day}, {dt.year}"
    return text + f" {dt:%H:%M} UTC" if intraday else text


def px(x: float) -> str:
    return f"{x:.0f}" if x >= 1000 else f"{x:.2f}" if x >= 10 else f"{x:.4f}"


def tidy(text: str) -> str:
    """Prose in the report never carries hyphens or dashes."""
    return re.sub(r"\s*[\-‐-―−]+\s*", " ", text or "").strip()


def n_of(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------- the run record

def _row(c) -> list:
    return [c.t, c.o, c.h, c.l, c.c, c.v]


def _bet(b, payoff: float, first_p: Optional[float]) -> dict:
    return {"agent": b.agent, "name": b.name, "side": b.side, "lens": b.lens, "p": b.p_win, "stake": b.stake,
            "case": tidy(b.case), "risk": tidy(b.risk), "valid": b.valid, "payoff": payoff, "p1": first_p,
            "note": b.note, "round": b.round}


def sanitize(obj):
    """Replace NaN and infinity with None so the saved JSON is valid everywhere, including browsers."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


def build_record(results: List[ScenarioResult], roster, summary: dict, meta: dict, usage: dict,
                 learning: Optional[dict] = None) -> dict:
    scenarios = []
    for r in results:
        sc, s, o = r.scenario, r.scenario.setup, r.outcome
        first = {b.agent: (b.p_win if b.valid else None) for b in r.first_bets}
        scenarios.append({
            "id": sc.id, "index": sc.index, "decision_t": sc.decision_time,
            "setup": {"ref": s.ref_price, "stop": s.stop, "target": s.target, "atr": s.atr, "rr": s.rr,
                      "horizon": s.horizon, "cost_r": s.cost_r, "base_rate": s.base_rate,
                      "breakeven_p": s.breakeven_p},
            "window": [_row(c) for c in sc.window[-sc.shown:]],
            "future": [_row(c) for c in sc.reveal()],
            "outcome": {"result": o.result, "k": o.k, "entry": o.entry, "exit": o.exit,
                        "r_gross": o.r_gross, "r_net": o.r_net},
            "crowd_p": crowd_p(r),
            "bets": [_bet(b, r.payoffs[b.agent], first.get(b.agent)) for b in r.bets],
            "refs": [_bet(b, r.ref_payoffs[b.agent], None) for b in r.refs],
        })
    return sanitize({"meta": meta, "usage": usage, "summary": summary, "scenarios": scenarios,
                     "learning": learning})


# ---------------------------------------------------------------- markdown

def render_markdown(rec: dict) -> str:
    m, s, sc = rec["meta"], rec["summary"], rec["scenarios"]
    intraday = bool(m.get("intraday"))
    p = m["params"]
    out: List[str] = []
    add = out.append
    add("# Trading Arena report")
    add("")
    add(f"Data: {tidy(m['label'])}, {m['interval']} candles. Scenarios: {s['n_scenarios']}. "
        f"Model: {tidy(m['model'])}{' (offline demo with no skill)' if m.get('offline') else ''}. "
        f"Rounds: {m['rounds']} ({'debate' if m['rounds'] >= 2 else 'independent bets'}).")
    add(f"Setup: long only, stop at {p['k_atr']} ATR, reward to risk {p['rr']} to 1, {p['horizon']} candles to resolve, "
        f"round trip costs {(2 * p['fee'] + 2 * p['slip']) * 100:.2f} percent.")
    if sc:
        made_up = " (made up prices, so made up dates)" if m.get("synthetic") else ""
        add(f"Decision dates{made_up}: from {when(sc[0]['decision_t'], intraday)} to {when(sc[-1]['decision_t'], intraday)}. "
            "Dates, coin, and real prices were hidden from the analysts.")
    add("")
    add("## The short answer")
    add("")
    add(tidy(s["verdict"]))
    add("")
    add(f"The setup hit its target in {pc(s['observed_win_rate'])} of scenarios "
        f"({n_of(s['outcomes']['WIN'], 'win')}, {n_of(s['outcomes']['LOSS'], 'stop')}, "
        f"{n_of(s['outcomes']['TIMEOUT'], 'time out')}). "
        f"Fair odds say {pc(s['fair_odds_win_rate'])}, and the break even after costs is "
        f"{pc(s['breakeven_after_costs'], 1)}. Anyone who is only as good as the base rate loses a little to costs.")
    d = s["crowd_minus_base_brier"]
    add("")
    add(f"Crowd Brier score: {num(s['brier_crowd'])}. Base rate bot: {num(s['brier_base_rate_bot'])}. "
        f"Trend rule bot: {num(s['brier_trend_rule_bot'])}. Lower is better. "
        f"Crowd minus base rate bot: {sg(d['mean'], 4)} (95 percent range {sg(d['ci_low'], 4)} to {sg(d['ci_high'], 4)}). "
        "If that range includes zero, luck can explain the difference.")
    add("")
    add("## Bulls versus bears")
    add("")
    t = s["teams"]
    add(f"Bulls ended {sg(t['bull']['pnl'], 1)} points. Average probability {num(t['bull']['avg_p'], 2)}. "
        f"They picked the right side {pc(t['bull']['right_side_rate'])} of the time.")
    add(f"Bears ended {sg(t['bear']['pnl'], 1)} points. Average probability {num(t['bear']['avg_p'], 2)}. "
        f"They picked the right side {pc(t['bear']['right_side_rate'])} of the time.")
    add("A bear is right more often because the target is the harder outcome, but a bear only wins 1 point where a "
        "bull wins 2. Compare points, not hit rates.")
    add("")
    add("## Leaderboard")
    add("")
    add("Analysts, ranked by points. Skill is the Brier improvement over a bot that always answers with the base "
        "rate, so zero means no better than that bot.")
    n = 0
    for row in s["leaderboard"]:
        if not row["reference"]:
            n += 1
            add(f"{n}. {row['name']}: {sg(row['pnl'], 1)} points, {row['bets']} bets"
                f"{', ' + str(row['no_bets']) + ' missed' if row['no_bets'] else ''}, average probability "
                f"{num(row['avg_p'], 2)}, Brier {num(row['brier'])}, skill {sg(row['skill'], 3)}.")
    add("")
    add("Reference bots, for comparison:")
    n = 0
    for row in s["leaderboard"]:
        if row["reference"]:
            n += 1
            add(f"{n}. {row['name']}: {sg(row['pnl'], 1)} points, Brier {num(row['brier'])}, skill {sg(row['skill'], 3)}.")
    add("")
    add("## Which lens has skill?")
    add("")
    add("Each lens is a debate between its bull and its bear. This scores the pair's average probability.")
    for row in s["lens_pairs"]:
        add(f"1. {row['lens']}: Brier {num(row['brier'])} over {n_of(row['n'], 'scenario')}, "
            f"average probability {num(row['avg_p'], 2)}.")
    add("")
    add("## Calibration")
    add("")
    add("When the crowd said a probability in a range, how often did the target really come first?")
    for row in s["calibration_crowd"]:
        if row["n"]:
            add(f"1. Said {row['range']}: {n_of(row['n'], 'scenario')}, average said {num(row['avg_p'], 2)}, "
                f"actual hit rate {pc(row['hit_rate'])}.")
    add("")
    add("## Are fourteen analysts really fourteen opinions?")
    add("")
    o = s["opinions"]
    if o["avg_correlation"] is None:
        add("Not enough scenarios to measure.")
    else:
        add(f"Average correlation between analysts: {num(o['avg_correlation'], 2)}. That is like having about "
            f"{o['effective']:.1f} independent opinions instead of {o['n_agents']}. Copies of one model tend to agree, "
            "so more analysts help less than they look.")
    add("")
    add("## Would following the crowd have made money?")
    add("")
    f = s["follow_the_crowd"]
    add(f"The rule: take the trade only when the crowd's probability beats the cost adjusted break even. "
        f"It took {f['taken']} of {f['of']} setups.")
    if f["taken"]:
        add(f"Average result per trade taken: {sg(f['mean_r_net'], 2)} R after costs, total {sg(f['total_r_net'], 1)} R"
            + (f" (95 percent range {sg(f['ci_low'], 2)} to {sg(f['ci_high'], 2)})." if f["ci_low"] is not None else "."))
    add(f"For comparison, taking every setup averaged {sg(f['take_everything_mean_r_net'], 2)} R after costs.")
    if "debate_effect" in s:
        de = s["debate_effect"]
        add("")
        add("## Did the debate round help?")
        add("")
        add(f"Crowd Brier before the debate: {num(de['brier_round_one'])}. After: {num(de['brier_final'])}. "
            f"Change {sg(de['mean'], 4)} (95 percent range {sg(de['ci_low'], 4)} to {sg(de['ci_high'], 4)}). "
            "Negative means the debate helped. Analysts often just drift toward the crowd.")
    lr = rec.get("learning")
    if lr:
        add("")
        add("## Learning experiment")
        add("")
        add(f"The first {lr['train_n']} scenarios were training. A coach wrote lessons from them. "
            f"The last {lr['test_n']} were the test, run once without lessons and once with.")
        add("Every other number in this report scores the runs without lessons. The with lessons run is only "
            "compared here, and its probabilities are saved in run.json.")
        add("Lessons:")
        for line in (lr["lessons"] or "").splitlines():
            add(f"   {tidy(line)}" if not line[:1].isdigit() else f"   {line}")
        e = lr.get("effect")
        if e:
            add(f"Crowd Brier without lessons: {num(e['brier_plain'])}. With lessons: {num(e['brier_learned'])}. "
                f"Difference {sg(e['mean'], 4)} (95 percent range {sg(e['ci_low'], 4)} to {sg(e['ci_high'], 4)}).")
            add(tidy(e["verdict"]))
        else:
            add("The coach found no reliable lesson, so there was nothing to test.")
    add("")
    add("## Check it yourself on TradingView")
    add("")
    if m.get("synthetic"):
        add("These prices are made up, so there is nothing to check on TradingView. Run with real candles to use it.")
    else:
        sym = m.get("tv_symbol") or "the same coin and exchange as your data"
        add(f"Open {sym} on the {m['interval']} timeframe, click Replay in the top toolbar, choose Select bar, and "
            "click the candle with the date below. Then play. TradingView reportedly allows Replay on the free plan "
            "only for daily and longer candles. Use it by eye only, because its terms do not allow copying its data "
            "into tools.")
        for r in sc[:10]:
            st, o2 = r["setup"], r["outcome"]
            add(f"{r['id']}. Candle dated {when(r['decision_t'], intraday)}. Entry at the next open, stop "
                f"{px(st['stop'])}, target {px(st['target'])}. Our result: {o2['result']} after "
                f"{n_of(o2['k'] + 1, 'candle')}.")
    add("")
    add("## Cost of this run")
    add("")
    u = rec["usage"]
    add(f"Model calls: {u['calls']}. Input tokens: {u['prompt_tokens']:,}. Output tokens: {u['completion_tokens']:,}.")
    if s["no_bets"] or s["clamped_bets"]:
        add(f"Problems: {s['no_bets']} missed bets (each costs 1 point) and {s['clamped_bets']} bets that were clamped "
            "into the allowed range.")
    add("")
    add("## Honest limits")
    add("")
    for line in (
        "Under 100 scenarios, treat every ranking as luck. Even with many, a good result can still be a fluke.",
        "The analysts never see dates, the coin, or the future. A language model may still half remember real "
        "history, so run on data from after its training period when you can.",
        "Prices come from a public exchange feed or your own file. They are not TradingView data.",
        "Costs are an assumption. A real account may pay more or less.",
        "If the crowd looks too good, look for a bug or a leak before you celebrate.",
        "Play money only. Nothing here is advice, and most traders lose money.",
    ):
        add(f"1. {line}")
    add("")
    return "\n".join(out)


# ---------------------------------------------------------------- csv and json

def write_csvs(out_dir: Path, rec: dict) -> None:
    with (out_dir / "bets.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "outcome", "agent", "side", "lens", "p_win", "stake", "valid", "payoff", "brier",
                    "round1_p", "case", "main_risk"])
        for sc in rec["scenarios"]:
            y = 1.0 if sc["outcome"]["result"] == "WIN" else 0.0
            for b in sc["bets"] + sc["refs"]:
                w.writerow([sc["id"], sc["outcome"]["result"], b["name"], b["side"], b["lens"],
                            round(b["p"], 4), round(b["stake"], 2), int(b["valid"]), round(b["payoff"], 4),
                            round(brier(b["p"], y), 4) if b["valid"] else "", b["p1"] if b["p1"] is not None else "",
                            b["case"], b["risk"]])
    with (out_dir / "scenarios.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "decision_time_utc", "entry_reference", "stop", "target", "outcome",
                    "candles_to_result", "r_gross", "r_net", "crowd_p"])
        for sc in rec["scenarios"]:
            st, o = sc["setup"], sc["outcome"]
            w.writerow([sc["id"], datetime.fromtimestamp(sc["decision_t"], tz=timezone.utc).isoformat(),
                        round(st["ref"], 6), round(st["stop"], 6), round(st["target"], 6), o["result"], o["k"] + 1,
                        round(o["r_gross"], 4), round(o["r_net"], 4),
                        round(sc["crowd_p"], 4) if sc["crowd_p"] is not None else ""])


# ---------------------------------------------------------------- replay page

def render_replay(rec: dict) -> str:
    s, m = rec["summary"], rec["meta"]
    data = {
        "meta": {"label": tidy(m["label"]), "interval": m["interval"], "intraday": bool(m.get("intraday")),
                 "tv_symbol": m.get("tv_symbol"), "model": tidy(m["model"]), "offline": bool(m.get("offline")),
                 "synthetic": bool(m.get("synthetic"))},
        "summary": {"verdict": tidy(s["verdict"]), "bull_pnl": s["teams"]["bull"]["pnl"],
                    "bear_pnl": s["teams"]["bear"]["pnl"], "observed_win_rate": s["observed_win_rate"],
                    "fair_odds_win_rate": s["fair_odds_win_rate"],
                    "breakeven_after_costs": s["breakeven_after_costs"]},
        "scenarios": rec["scenarios"],
    }
    # model text is untrusted: with no raw "<" in the blob it cannot close the script block or open a comment in it
    blob = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    return TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", blob)


def write_all(out_dir: str | Path, rec: dict) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "run": out / "run.json", "report": out / "report.md", "replay": out / "replay.html",
        "bets": out / "bets.csv", "scenarios": out / "scenarios.csv",
    }
    paths["run"].write_text(json.dumps(rec, indent=1), encoding="utf-8")
    paths["report"].write_text(render_markdown(rec), encoding="utf-8")
    paths["replay"].write_text(render_replay(rec), encoding="utf-8")
    write_csvs(out, rec)
    return paths
