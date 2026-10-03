"""Scoring: did the analysts beat luck? Every number here is paired with how much luck could explain it."""

from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence, Tuple

from .agents import AgentSpec
from .arena import ScenarioResult
from .settle import WIN


def brier(p: float, y: float) -> float:
    return (p - y) ** 2


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def pearson(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 3:
        return float("nan")
    ma, mb = mean(a), mean(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def bootstrap_mean_ci(values: Sequence[float], reps: int = 2000, seed: int = 1) -> Tuple[float, float, float]:
    """Mean with a 95 percent bootstrap interval. With few values the interval is wide, as it should be."""
    if not values:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return mean(values), means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def outcome_y(r: ScenarioResult) -> float:
    return 1.0 if r.outcome.result == WIN else 0.0


def valid_ps(r: ScenarioResult, use_first: bool = False) -> List[float]:
    bets = r.first_bets if use_first else r.bets
    return [b.p_win for b in bets if b.valid]


def crowd_p(r: ScenarioResult, use_first: bool = False) -> Optional[float]:
    ps = valid_ps(r, use_first)
    return mean(ps) if ps else None


def calibration(pairs: Sequence[Tuple[float, float]],
                edges: Sequence[float] = (0.0, 0.2, 0.3, 0.4, 0.5, 1.01)) -> List[dict]:
    rows = []
    for lo, hi in zip(edges, edges[1:]):
        chunk = [(p, y) for p, y in pairs if lo <= p < hi]
        rows.append({
            "range": f"{lo:.1f} to {min(hi, 1.0):.1f}", "n": len(chunk),
            "avg_p": mean([p for p, _ in chunk]) if chunk else None,
            "hit_rate": mean([y for _, y in chunk]) if chunk else None,
        })
    return rows


def leaderboard(results: List[ScenarioResult], roster: List[AgentSpec]) -> List[dict]:
    rows = []
    q0 = 1.0 / (1.0 + results[0].scenario.setup.rr) if results else 1.0 / 3.0
    ids = [(s.id, s.name, s.side, s.lens_title) for s in roster]
    ref_ids = []
    if results:
        ref_ids = [(b.agent, b.name, b.side, "reference") for b in results[0].refs]
    for agent_id, name, _, lens in ids + ref_ids:
        is_ref = agent_id.startswith("ref_")
        pnl, stakes, correct, briers, ps, no_bets, n_bets = 0.0, [], [], [], [], 0, 0
        ref_briers = []
        for r in results:
            pool = r.refs if is_ref else r.bets
            payoffs = r.ref_payoffs if is_ref else r.payoffs
            bet = next((b for b in pool if b.agent == agent_id), None)
            if bet is None:
                continue
            pnl += payoffs[agent_id]
            if not bet.valid:
                no_bets += 1
                continue
            n_bets += 1
            y = outcome_y(r)
            stakes.append(bet.stake)
            ps.append(bet.p_win)
            correct.append(1.0 if (bet.side == "bull") == (y == 1.0) else 0.0)
            briers.append(brier(bet.p_win, y))
            ref_briers.append(brier(q0, y))
        b_mean = mean(briers) if briers else None
        skill = (1.0 - b_mean / mean(ref_briers)) if briers and mean(ref_briers) > 0 else None
        rows.append({
            "id": agent_id, "name": name, "side": rows_side(agent_id, is_ref), "lens": lens,
            "reference": is_ref, "bets": n_bets, "no_bets": no_bets, "pnl": pnl,
            "avg_stake": mean(stakes) if stakes else None, "avg_p": mean(ps) if ps else None,
            "right_side_rate": mean(correct) if correct else None, "brier": b_mean, "skill": skill,
        })
    return sorted(rows, key=lambda row: row["pnl"], reverse=True)


def rows_side(agent_id: str, is_ref: bool) -> str:
    if is_ref:
        return "mixed"
    return "bull" if agent_id.startswith("bull_") else "bear"


def team_table(results: List[ScenarioResult]) -> dict:
    out = {}
    for side in ("bull", "bear"):
        pnl, ps, correct = 0.0, [], []
        for r in results:
            y = outcome_y(r)
            for b in r.bets:
                if b.side != side:
                    continue
                pnl += r.payoffs[b.agent]
                if b.valid:
                    ps.append(b.p_win)
                    correct.append(1.0 if (side == "bull") == (y == 1.0) else 0.0)
        out[side] = {"pnl": pnl, "avg_p": mean(ps) if ps else None,
                     "right_side_rate": mean(correct) if correct else None}
    return out


def lens_pairs(results: List[ScenarioResult], roster: List[AgentSpec]) -> List[dict]:
    """Each lens is a debate between its bull and its bear. Score the pair's average probability."""
    rows = []
    for key, title in dict.fromkeys((s.lens_key, s.lens_title) for s in roster):
        pair_p, ys, pnl = [], [], 0.0
        for r in results:
            bets = [b for b in r.bets if b.lens == key and b.valid]
            pnl += sum(r.payoffs.get(f"{side}_{key}", 0.0) for side in ("bull", "bear"))
            if len(bets) == 2:
                pair_p.append(mean([b.p_win for b in bets]))
                ys.append(outcome_y(r))
        rows.append({"lens": title, "n": len(ys), "avg_p": mean(pair_p) if pair_p else None,
                     "brier": mean([brier(p, y) for p, y in zip(pair_p, ys)]) if pair_p else None})
    return rows


def effective_opinions(results: List[ScenarioResult], roster: List[AgentSpec]) -> dict:
    series = {s.id: [] for s in roster}
    for r in results:
        if all(any(b.agent == s.id and b.valid for b in r.bets) for s in roster):
            for b in r.bets:
                series[b.agent].append(b.p_win)
    ids = list(series)
    cors = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            c = pearson(series[ids[i]], series[ids[j]])
            if not math.isnan(c):
                cors.append(c)
    n = len(ids)
    if not cors:
        return {"avg_correlation": None, "effective": None, "n_agents": n}
    rho = mean(cors)
    effective = n / (1 + (n - 1) * max(rho, 0.0))
    return {"avg_correlation": rho, "effective": effective, "n_agents": n}


def follow_the_crowd(results: List[ScenarioResult]) -> dict:
    """If we had taken the trade whenever the crowd's probability beat the cost adjusted break even."""
    taken, all_net = [], []
    for r in results:
        p = crowd_p(r)
        all_net.append(r.outcome.r_net)
        if p is not None and p > r.scenario.setup.breakeven_p:
            taken.append(r.outcome)
    nets = [o.r_net for o in taken]
    m, lo, hi = bootstrap_mean_ci(nets) if len(nets) >= 5 else (mean(nets) if nets else float("nan"),
                                                                   float("nan"), float("nan"))
    return {
        "taken": len(taken), "of": len(results), "mean_r_net": m if nets else None,
        "ci_low": None if math.isnan(lo) else lo, "ci_high": None if math.isnan(hi) else hi,
        "total_r_net": sum(nets), "win_rate": mean([1.0 if o.result == WIN else 0.0 for o in taken]) if taken else None,
        "take_everything_mean_r_net": mean(all_net) if all_net else None,
    }


def summarize(results: List[ScenarioResult], roster: List[AgentSpec]) -> dict:
    if not results:
        raise ValueError("There are no scenarios to summarize.")
    n = len(results)
    ys = [outcome_y(r) for r in results]
    setup0 = results[0].scenario.setup
    q0 = 1.0 / (1.0 + setup0.rr)
    base_briers = [brier(q0, y) for y in ys]

    crowd_pairs = [(crowd_p(r), y) for r, y in zip(results, ys) if crowd_p(r) is not None]
    crowd_b = [brier(p, y) for p, y in crowd_pairs]
    paired = [(brier(crowd_p(r), y) - brier(q0, y)) for r, y in zip(results, ys) if crowd_p(r) is not None]
    d_mean, d_lo, d_hi = bootstrap_mean_ci(paired) if paired else (float("nan"),) * 3

    trend_ref = []
    for r, y in zip(results, ys):
        ref = next(b for b in r.refs if b.agent == "ref_trend")
        trend_ref.append(brier(ref.p_win, y))

    summary = {
        "n_scenarios": n,
        "outcomes": {k: sum(1 for r in results if r.outcome.result == k) for k in ("WIN", "LOSS", "TIMEOUT")},
        "observed_win_rate": mean(ys),
        "fair_odds_win_rate": q0,
        "breakeven_after_costs": mean([r.scenario.setup.breakeven_p for r in results]),
        "brier_crowd": mean(crowd_b) if crowd_b else None,
        "brier_base_rate_bot": mean(base_briers),
        "brier_trend_rule_bot": mean(trend_ref),
        "crowd_minus_base_brier": {"mean": d_mean, "ci_low": d_lo, "ci_high": d_hi},
        "teams": team_table(results),
        "leaderboard": leaderboard(results, roster),
        "lens_pairs": lens_pairs(results, roster),
        "calibration_crowd": calibration([(p, y) for p, y in crowd_pairs]),
        "calibration_all_bets": calibration([(b.p_win, outcome_y(r)) for r in results for b in r.bets if b.valid]),
        "opinions": effective_opinions(results, roster),
        "follow_the_crowd": follow_the_crowd(results),
        "no_bets": sum(1 for r in results for b in r.bets if not b.valid),
        "clamped_bets": sum(1 for r in results for b in r.bets if b.valid and b.note),
    }
    if any(r.first_bets is not r.bets for r in results):
        deb = [(brier(crowd_p(r), y) - brier(crowd_p(r, True), y))
               for r, y in zip(results, ys) if crowd_p(r) is not None and crowd_p(r, True) is not None]
        m, lo, hi = bootstrap_mean_ci(deb) if deb else (float("nan"),) * 3
        summary["debate_effect"] = {"mean": m, "ci_low": lo, "ci_high": hi,
                                    "brier_round_one": mean([brier(crowd_p(r, True), y) for r, y in zip(results, ys)
                                                             if crowd_p(r, True) is not None]),
                                    "brier_final": mean(crowd_b) if crowd_b else None}
    summary["verdict"] = verdict(summary)
    return summary


def verdict(s: dict) -> str:
    """A plain language answer to: did the analysts beat luck?"""
    n = s["n_scenarios"]
    d = s["crowd_minus_base_brier"]
    if s["brier_crowd"] is None:
        return "No valid bets were placed, so there is nothing to score."
    if n < 30:
        return (f"Only {n} scenarios. That is far too few to tell skill from luck. "
                "Run 100 or more before drawing any conclusion.")
    if d["ci_high"] < 0:
        text = ("In this sample the crowd beat the base rate bot, and the gap is larger than luck alone usually "
                "explains. That is a clue, not proof. Check for leaks, then confirm on data it has never seen.")
    elif d["ci_low"] > 0:
        text = "In this sample the crowd was clearly worse than a bot that always answers with the base rate."
    else:
        text = ("The crowd cannot be told apart from the base rate bot. Any difference you see could easily be luck.")
    f = s["follow_the_crowd"]
    if f["taken"] >= 10 and f["mean_r_net"] is not None and f["ci_low"] is not None:
        if f["ci_high"] < 0:
            text += " Following the crowd would have lost money after costs."
        elif f["ci_low"] > 0:
            text += " Following the crowd would have made money after costs in this sample, so test it hard."
        else:
            text += " Following the crowd could not be told apart from zero after costs."
    return text
