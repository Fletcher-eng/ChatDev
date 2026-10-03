"""The learning experiment.

A coach reads the results of an earlier training period and writes a few lessons. The lessons are then
tested on later scenarios, side by side with a control run that gets no lessons. Scenarios are spaced so
every training outcome is settled before the first test decision, which keeps the split free of leaks.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Callable, List, Optional

from .agents import AgentSpec, UsageMeter
from .arena import ArenaConfig, ScenarioResult, run_scenarios
from .scenario import Scenario, facts_line
from .scoring import bootstrap_mean_ci, brier, crowd_p, lens_pairs, mean, outcome_y

NO_LESSON = "NO RELIABLE LESSON"

COACH_SYSTEM = """You are a research coach for a paper trading game with play money. You only see summary tables from past scenarios. You never see the future of any new scenario.
Write up to 6 short lessons that might help the analysts on NEW scenarios.
Rules:
1. A lesson must be supported by at least 5 scenarios in the rows. If nothing is, reply with exactly: NO RELIABLE LESSON
2. Be honest about luck. With few scenarios most patterns are noise, so prefer fewer lessons.
3. Each lesson is one sentence of at most 25 words, in a numbered list. Use plain sentences. Do not use hyphens or dashes. Write negative amounts as the word minus.
4. Do not mention dates, coin names, or years."""


def coach_prompt(results: List[ScenarioResult], roster: List[AgentSpec]) -> str:
    setup = results[0].scenario.setup
    n = len(results)
    wins = sum(1 for r in results if r.outcome.result == "WIN")
    base = mean([brier(1.0 / (1.0 + setup.rr), outcome_y(r)) for r in results])
    lines = [
        f"{n} training scenarios. Reward to risk is {setup.rr:.1f} to 1 with a horizon of {setup.horizon} candles. "
        f"The target came first in {wins} of {n}. Fair odds say {100 / (1 + setup.rr):.0f} percent.",
        "BY LENS (average probability of the bull and bear pair, and Brier score where lower is better):",
    ]
    for row in lens_pairs(results, roster):
        if row["n"]:
            lines.append(f"{row['lens']}: average p {row['avg_p']:.2f}, Brier {row['brier']:.3f}")
    lines.append(f"A bot that always says the base rate scores a Brier of {base:.3f}.")
    lines.append("ROWS (crowd probability, what happened, and facts about the chart at decision time):")
    for r in results:
        p = crowd_p(r)
        lines.append(f"{r.scenario.id}: crowd p {p:.2f}, {r.outcome.result}. {facts_line(r.scenario)}"
                     if p is not None else f"{r.scenario.id}: no valid bets, {r.outcome.result}.")
    return "\n".join(lines)


def clean_lessons(text: str) -> str:
    out = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*([\-\*•]|\d+[.)])\s*", "", raw).strip()
        line = re.sub(r"\s*[\-‐-―−]+\s*", " ", line)
        if line:
            out.append(line)
    if not out or NO_LESSON in out[0].upper():
        return NO_LESSON
    return "\n".join(f"{i}. {line}" for i, line in enumerate(out[:6], start=1))


def make_lessons(client, results: List[ScenarioResult], roster: List[AgentSpec], meter: UsageMeter) -> str:
    if getattr(client, "kind", "llm") == "mock":
        return "1. Mock coach: with this few scenarios there is no reliable pattern, so treat every lesson as luck."
    text, usage = client.chat(COACH_SYSTEM, coach_prompt(results, roster), 0.2, 600)
    meter.add(usage)
    return clean_lessons(text)


def learning_effect(plain: List[ScenarioResult], learned: List[ScenarioResult]) -> dict:
    """Paired by scenario: negative means the lessons made the crowd's Brier score better."""
    diffs = []
    for a, b in zip(plain, learned):
        pa, pb = crowd_p(a), crowd_p(b)
        if pa is not None and pb is not None:
            y = outcome_y(a)
            diffs.append(brier(pb, y) - brier(pa, y))
    m, lo, hi = bootstrap_mean_ci(diffs) if diffs else (float("nan"),) * 3
    brier_plain = mean([brier(crowd_p(r), outcome_y(r)) for r in plain if crowd_p(r) is not None])
    brier_learned = mean([brier(crowd_p(r), outcome_y(r)) for r in learned if crowd_p(r) is not None])
    if not diffs:
        verdict = "No valid bets to compare."
    elif len(diffs) < 30:
        verdict = (f"Only {len(diffs)} test scenarios. That is too few to tell whether the lessons helped. "
                   "Models also give different answers each time they run, so a small gap is mostly noise.")
    elif hi < 0:
        verdict = ("The crowd scored better with the lessons and the gap is larger than luck usually explains. "
                   "Repeat on fresh scenarios before trusting it.")
    elif lo > 0:
        verdict = "The lessons made the crowd clearly worse."
    else:
        verdict = "The lessons did not help beyond what luck could explain."
    return {"n": len(diffs), "mean": m, "ci_low": lo, "ci_high": hi, "brier_plain": brier_plain,
            "brier_learned": brier_learned, "verdict": verdict}


def lesson_pairs(run: dict) -> List[dict]:
    """Receipts for the lessons test: the crowd probability on each test scenario without and with lessons."""
    learned = run.get("test_learned") or []
    return [{"id": a.scenario.id, "result": a.outcome.result, "crowd_p_plain": crowd_p(a), "crowd_p_learned": crowd_p(b)}
            for a, b in zip(run["test_plain"], learned)]


def run_learning(
    scenarios: List[Scenario],
    roster: List[AgentSpec],
    client,
    cfg: ArenaConfig,
    meter: UsageMeter,
    coach_client=None,
    train_fraction: float = 0.5,
    progress: Optional[Callable[[str, int, int, ScenarioResult], None]] = None,
) -> dict:
    split = max(1, min(len(scenarios) - 1, int(len(scenarios) * train_fraction)))
    train, test = scenarios[:split], scenarios[split:]
    plain_cfg = replace(cfg, lessons=None)

    def tag(name):
        return (lambda i, n, r: progress(name, i, n, r)) if progress else None

    train_results = run_scenarios(train, roster, client, plain_cfg, meter, tag("train"))
    lessons = make_lessons(coach_client or client, train_results, roster, meter)
    test_plain = run_scenarios(test, roster, client, plain_cfg, meter, tag("test without lessons"))
    out = {"train_n": len(train), "test_n": len(test), "lessons": lessons, "train": train_results,
           "test_plain": test_plain, "test_learned": None, "effect": None}
    if lessons != NO_LESSON:
        test_learned = run_scenarios(test, roster, client, replace(cfg, lessons=lessons), meter, tag("test with lessons"))
        out["test_learned"] = test_learned
        out["effect"] = learning_effect(test_plain, test_learned)
    return out
