"""The Arena runner: place bets blind, reveal the future, settle, and keep the receipts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .agents import AgentSpec, Bet, UsageMeter, ask_for_bet, build_user_prompt, format_table, reference_bets
from .scenario import Scenario, snapshot_text
from .settle import Outcome, bet_payoff, settle

NO_BET_PENALTY = -1.0  # an analyst that fails to place a bet loses a point


@dataclass
class ArenaConfig:
    rounds: int = 1                  # 1 = independent bets, 2 = a debate round after seeing the table
    workers: int = 7
    temperature: float = 0.7
    max_tokens: int = 400
    lessons: Optional[str] = None


@dataclass
class ScenarioResult:
    scenario: Scenario
    outcome: Outcome
    first_bets: List[Bet]
    bets: List[Bet]                   # the final bets that are scored
    refs: List[Bet]
    payoffs: Dict[str, float] = field(default_factory=dict)
    ref_payoffs: Dict[str, float] = field(default_factory=dict)


def planned_calls(n_scenarios: int, n_agents: int, rounds: int) -> int:
    return n_scenarios * n_agents * rounds


def _failed(spec: AgentSpec, round_no: int, error: Exception) -> Bet:
    return Bet(spec.id, spec.name, spec.side, spec.lens_key, 0.0, 0.0, kind="llm", valid=False,
               round=round_no, note=f"model call failed: {type(error).__name__}")


def _ask_all(pool, client, roster: List[AgentSpec], prompts: List[str], meter: UsageMeter,
             cfg: ArenaConfig, round_no: int) -> List[Bet]:
    futures = [pool.submit(ask_for_bet, client, spec, prompt, meter, cfg.temperature, cfg.max_tokens, round_no)
               for spec, prompt in zip(roster, prompts)]
    bets = []
    for spec, future in zip(roster, futures):
        try:
            bets.append(future.result())
        except Exception as error:  # one failed call must not stop the whole run
            bets.append(_failed(spec, round_no, error))
    return bets


def score_bets(bets: List[Bet], outcome: Outcome, rr: float) -> Dict[str, float]:
    return {
        b.agent: (bet_payoff(b.side, b.stake, outcome, rr) if b.valid else NO_BET_PENALTY)
        for b in bets
    }


def run_scenarios(
    scenarios: List[Scenario],
    roster: List[AgentSpec],
    client,
    cfg: ArenaConfig,
    meter: UsageMeter,
    progress: Optional[Callable[[int, int, ScenarioResult], None]] = None,
) -> List[ScenarioResult]:
    results: List[ScenarioResult] = []
    with ThreadPoolExecutor(max_workers=max(1, cfg.workers)) as pool:
        for n, sc in enumerate(scenarios, start=1):
            snapshot = snapshot_text(sc)  # the only thing the analysts ever see
            first = _ask_all(pool, client, roster,
                             [build_user_prompt(snapshot, s, cfg.lessons) for s in roster], meter, cfg, 1)
            if n == 1 and getattr(client, "kind", "llm") == "llm" and not any(b.valid for b in first):
                raise RuntimeError("Every model call failed. Check API_KEY, BASE_URL, and the model name.")
            final = first
            if cfg.rounds >= 2:
                table = format_table(first)
                final = _ask_all(pool, client, roster,
                                 [build_user_prompt(snapshot, s, cfg.lessons, table) for s in roster],
                                 meter, cfg, 2)
                # an analyst whose round two failed keeps the round one bet
                final = [f if f.valid else o for o, f in zip(first, final)]
            outcome = settle(sc.setup, sc.reveal())  # the future is revealed only now
            refs = reference_bets(sc)
            result = ScenarioResult(sc, outcome, first, final, refs,
                                    score_bets(final, outcome, sc.setup.rr),
                                    score_bets(refs, outcome, sc.setup.rr))
            results.append(result)
            if progress:
                progress(n, len(scenarios), result)
    return results
