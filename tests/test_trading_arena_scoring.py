"""Arena tests for bet parsing, the runner, scoring, and the learning loop. No network and no API key."""

import math
import random
import re
from dataclasses import replace

import pytest

from trading_arena import data as D
from trading_arena import scoring as S
from trading_arena.agents import (
    RETRY_NOTE,
    SYSTEM_PROMPT,
    Bet,
    MockClient,
    Usage,
    UsageMeter,
    ask_for_bet,
    build_user_prompt,
    extract_json,
    format_table,
    make_roster,
    parse_bet,
    reference_bets,
)
from trading_arena.arena import NO_BET_PENALTY, ArenaConfig, ScenarioResult, run_scenarios, score_bets
from trading_arena.learn import (
    COACH_SYSTEM,
    NO_LESSON,
    clean_lessons,
    coach_prompt,
    learning_effect,
    lesson_pairs,
    make_lessons,
    run_learning,
)
from trading_arena.scenario import Params, build_scenarios, snapshot_text
from trading_arena.settle import LOSS, TIMEOUT, WIN, Outcome, settle

DASH = re.compile(r"[\-‐-―−]")
ROSTER = make_roster()


def scenarios(n=12, seed=3, candles=3000):
    ds = D.synthetic(candles, seed=seed)
    params = Params.for_interval(ds.interval_s)
    return build_scenarios(ds, n, params, seed=2), params


def outcome(result, r_gross=None):
    r = {WIN: 2.0, LOSS: -1.0, TIMEOUT: 0.3}[result] if r_gross is None else r_gross
    return Outcome(result, 3, 100.0, 100.0 + 5 * r, r, r - 0.07)


def bets_for(p=1 / 3, stake=1.0, **override):
    """One bet per analyst. override maps an agent id to a probability, or to None for a missed bet."""
    out = []
    for spec in ROSTER:
        value = override.get(spec.id, p)
        if value is None:
            out.append(Bet(spec.id, spec.name, spec.side, spec.lens_key, 0.0, 0.0, valid=False, note="missed"))
        else:
            out.append(Bet(spec.id, spec.name, spec.side, spec.lens_key, value, stake))
    return out


def result_for(sc, out, bets):
    refs = reference_bets(sc)
    rr = sc.setup.rr
    return ScenarioResult(sc, out, bets, bets, refs, score_bets(bets, out, rr), score_bets(refs, out, rr))


# ------------------------------------------------------------------ bet parsing

def test_extract_json_handles_noise_fences_and_braces_in_strings():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure! Here you go:\n```json\n{"a": 1, "b": "x"}\n```\nGood luck.') == {"a": 1, "b": "x"}
    assert extract_json('{"case": "uses {braces} and a \\" quote", "p": 2}') == {"case": 'uses {braces} and a " quote', "p": 2}
    assert extract_json('{broken json} then {"ok": true}') == {"ok": True}
    assert extract_json('{"first": 1} {"second": 2}') == {"first": 1}


def test_extract_json_returns_none_when_there_is_no_object():
    assert extract_json("no json here") is None
    assert extract_json("[1, 2, 3]") is None
    assert extract_json('{"unclosed": 1') is None
    assert extract_json("") is None


def test_parse_bet_accepts_a_normal_reply():
    bet = parse_bet('{"p_win": 0.34, "stake": 1.2, "case": "Trend is up.", "main_risk": "A gap down."}')
    assert bet == {"p_win": 0.34, "stake": 1.2, "case": "Trend is up.", "risk": "A gap down.", "note": ""}


def test_parse_bet_accepts_strings_and_percent_answers():
    assert parse_bet('{"p_win": "0.4", "stake": "1"}')["p_win"] == pytest.approx(0.4)
    assert parse_bet('{"p_win": 35, "stake": 1}')["p_win"] == pytest.approx(0.35)
    assert parse_bet('{"p_win": 100, "stake": 1}')["p_win"] == pytest.approx(0.98)  # certainty is clamped, not refused
    assert parse_bet('{"p_win": 1, "stake": 1}')["p_win"] == pytest.approx(0.98)
    assert parse_bet('{"p_win": 0, "stake": 1}')["p_win"] == pytest.approx(0.02)


def test_parse_bet_clamps_and_says_so():
    low = parse_bet('{"p_win": 0.001, "stake": 0.1}')
    assert low["p_win"] == pytest.approx(0.02) and low["stake"] == pytest.approx(0.5)
    assert "probability clamped" in low["note"] and "stake clamped" in low["note"]
    high = parse_bet('{"p_win": 0.999, "stake": 50}')
    assert high["p_win"] == pytest.approx(0.98) and high["stake"] == pytest.approx(2.0)


def test_parse_bet_falls_back_to_plain_text_fields():
    bet = parse_bet("I think p_win: 0.42 and stake = 1.5 because of volume")
    assert bet["p_win"] == pytest.approx(0.42) and bet["stake"] == pytest.approx(1.5)


@pytest.mark.parametrize("text", [
    "", "I refuse to bet", '{"p_win": 0.4}', '{"stake": 1}', '{"p_win": -0.2, "stake": 1}', '{"p_win": 0.4, "stake": 0}', '{"p_win": 0.4, "stake": -1}',
    '{"p_win": "nan", "stake": 1}', '{"p_win": "inf", "stake": 1}', '{"p_win": null, "stake": 1}',
    '{"p_win": true, "stake": 1}', '{"p_win": [0.4], "stake": 1}', '{"p_win": 250, "stake": 1}',
])
def test_parse_bet_rejects_unusable_replies(text):
    assert parse_bet(text) is None


def test_parse_bet_truncates_long_text():
    bet = parse_bet('{"p_win": 0.3, "stake": 1, "case": "' + "x" * 900 + '", "main_risk": "' + "y" * 900 + '"}')
    assert len(bet["case"]) == 400 and len(bet["risk"]) == 200


# ------------------------------------------------------------------ asking for a bet


class Scripted:
    """A model that returns prepared replies and remembers what it was asked."""

    kind = "llm"

    def __init__(self, replies):
        self.replies = list(replies)
        self.asked = []

    def chat(self, system, user, temperature, max_tokens):
        self.asked.append((system, user, temperature))
        return self.replies.pop(0), Usage(1, 100, 20)


def test_ask_for_bet_first_reply_is_enough():
    client, meter = Scripted(['{"p_win": 0.31, "stake": 1.4, "case": "ok", "main_risk": "gap"}']), UsageMeter()
    bet = ask_for_bet(client, ROSTER[0], "PROMPT", meter, 0.7, 400, 1)
    assert bet.valid and bet.p_win == pytest.approx(0.31) and bet.stake == pytest.approx(1.4)
    assert (bet.agent, bet.side, bet.lens, bet.round) == (ROSTER[0].id, "bull", ROSTER[0].lens_key, 1)
    assert len(client.asked) == 1 and client.asked[0][0] == SYSTEM_PROMPT and meter.total.calls == 1


def test_ask_for_bet_retries_once_with_a_note_and_zero_temperature():
    client, meter = Scripted(["Hmm, hard to say.", '{"p_win": 0.3, "stake": 1}']), UsageMeter()
    bet = ask_for_bet(client, ROSTER[8], "PROMPT", meter, 0.7, 400, 2)
    assert bet.valid and bet.side == "bear" and bet.round == 2
    assert len(client.asked) == 2 and meter.total.calls == 2
    assert client.asked[1][1].endswith(RETRY_NOTE) and client.asked[1][2] == 0.0


def test_ask_for_bet_gives_up_after_one_retry():
    client = Scripted(["no", "still no"])
    bet = ask_for_bet(client, ROSTER[0], "PROMPT", UsageMeter(), 0.7, 400)
    assert not bet.valid and bet.p_win == 0.0 and bet.stake == 0.0 and "after a retry" in bet.note


def test_missed_bets_cost_a_point_and_valid_bets_pay_by_the_rules():
    win = outcome(WIN)
    bets = [Bet("bull_a", "Bull A", "bull", "a", 0.5, 1.5), Bet("bear_a", "Bear A", "bear", "a", 0.2, 1.0),
            Bet("bull_b", "Bull B", "bull", "b", 0.0, 0.0, valid=False)]
    pay = score_bets(bets, win, 2.0)
    assert pay == {"bull_a": pytest.approx(3.0), "bear_a": pytest.approx(-2.0), "bull_b": NO_BET_PENALTY}


def test_roster_is_seven_bulls_and_seven_bears_with_one_lens_each():
    assert len(ROSTER) == 14 and len({s.id for s in ROSTER}) == 14
    assert [s.side for s in ROSTER].count("bull") == 7 and [s.side for s in ROSTER].count("bear") == 7
    for key in {s.lens_key for s in ROSTER}:
        assert sorted(s.side for s in ROSTER if s.lens_key == key) == ["bear", "bull"]


def test_prompts_add_lessons_and_the_table_only_when_asked():
    sc = scenarios(2)[0][0]
    snap = snapshot_text(sc)
    plain = build_user_prompt(snap, ROSTER[0])
    assert "LESSONS" not in plain and "ROUND TWO" not in plain and snap in plain
    both = build_user_prompt(snap, ROSTER[0], "1. A lesson.", "Bull 1, Trend and structure: p_win=0.30")
    assert "LESSONS FROM EARLIER SCENARIOS" in both and "1. A lesson." in both and "ROUND TWO" in both
    assert not DASH.search(SYSTEM_PROMPT.split("Rules:")[1].replace("hyphens or dashes", ""))


def test_format_table_skips_missed_bets():
    text = format_table(bets_for(p=0.3, **{"bear_momentum": None}))
    assert len(text.splitlines()) == 13 and "Bear 4, Momentum" not in text


def test_mock_client_is_deterministic_and_never_skilled():
    mock = MockClient(3)
    a = mock.chat("s", "same prompt", 0.7, 400)[0]
    assert a == mock.chat("s", "same prompt", 0.7, 400)[0] != mock.chat("s", "other prompt", 0.7, 400)[0]
    assert a == MockClient(3).chat("s", "same prompt", 0.7, 400)[0] != MockClient(4).chat("s", "same prompt", 0.7, 400)[0]
    assert parse_bet(a) is not None


def test_reference_bots_are_valid_and_use_the_visible_chart_only():
    sc = scenarios(3)[0][0]
    before = [(b.agent, b.p_win, b.side) for b in reference_bets(sc)]
    sc._future = [D.Candle(c.t, 5.0, 5.0, 5.0, 5.0, 1.0) for c in sc._future]
    assert [(b.agent, b.p_win, b.side) for b in reference_bets(sc)] == before
    assert {b.agent for b in reference_bets(sc)} == {"ref_base", "ref_bull", "ref_bear", "ref_trend", "ref_rsi", "ref_coin"}
    base = next(b for b in reference_bets(sc) if b.agent == "ref_base")
    assert base.p_win == pytest.approx(1 / 3)


# ------------------------------------------------------------------ the runner


def test_run_one_round_with_mock_analysts():
    scs, _ = scenarios(6)
    meter, seen = UsageMeter(), []
    results = run_scenarios(scs, ROSTER, MockClient(1), ArenaConfig(rounds=1), meter,
                            lambda i, n, r: seen.append((i, n)))
    assert seen == [(i, 6) for i in range(1, 7)]
    assert meter.total.calls == 6 * 14
    for r, sc in zip(results, scs):
        assert r.first_bets is r.bets and len(r.bets) == 14 and len(r.refs) == 6
        assert {b.agent for b in r.bets} == {s.id for s in ROSTER}
        assert set(r.payoffs) == {s.id for s in ROSTER} and len(r.ref_payoffs) == 6
        assert r.outcome == settle(sc.setup, sc.reveal())
        assert all(b.valid and 0.02 <= b.p_win <= 0.98 and 0.5 <= b.stake <= 2.0 for b in r.bets)


def test_run_two_rounds_lets_analysts_change_their_minds():
    scs, _ = scenarios(4)
    meter = UsageMeter()
    results = run_scenarios(scs, ROSTER, MockClient(1), ArenaConfig(rounds=2), meter)
    assert meter.total.calls == 4 * 14 * 2
    for r in results:
        assert r.first_bets is not r.bets
        assert all(b.round == 1 for b in r.first_bets) and all(b.round == 2 for b in r.bets)
        assert any(a.p_win != b.p_win for a, b in zip(r.first_bets, r.bets))


def test_round_two_prompt_shows_all_fourteen_round_one_bets():
    class Recorder(MockClient):
        def __init__(self):
            super().__init__(1)
            self.prompts = []

        def chat(self, system, user, temperature, max_tokens):
            self.prompts.append(user)
            return super().chat(system, user, temperature, max_tokens)

    rec = Recorder()
    run_scenarios(scenarios(1)[0], ROSTER, rec, ArenaConfig(rounds=2, workers=1), UsageMeter())
    second = [p for p in rec.prompts if "ROUND TWO" in p]
    assert len(second) == 14 and len(rec.prompts) == 28
    assert all(len(re.findall(r"p_win=", p)) == 14 for p in second)


def test_a_failed_round_two_keeps_the_round_one_bet():
    class FailsInRoundTwo(MockClient):
        def chat(self, system, user, temperature, max_tokens):
            if "ROUND TWO" in user:
                raise RuntimeError("provider down")
            return super().chat(system, user, temperature, max_tokens)

    results = run_scenarios(scenarios(3)[0], ROSTER, FailsInRoundTwo(1), ArenaConfig(rounds=2), UsageMeter())
    for r in results:
        assert all(b.valid and b.round == 1 for b in r.bets)


def test_one_failing_analyst_loses_a_point_and_the_run_goes_on():
    class OneBroken(MockClient):
        kind = "llm"

        def chat(self, system, user, temperature, max_tokens):
            if "YOUR LENS: Momentum" in user and "You are the BEAR" in user:
                raise RuntimeError("boom")
            return super().chat(system, user, temperature, max_tokens)

    results = run_scenarios(scenarios(4)[0], ROSTER, OneBroken(1), ArenaConfig(rounds=1), UsageMeter())
    assert len(results) == 4
    for r in results:
        broken = next(b for b in r.bets if b.agent == "bear_momentum")
        assert not broken.valid and "model call failed" in broken.note
        assert r.payoffs["bear_momentum"] == NO_BET_PENALTY
        assert sum(1 for b in r.bets if b.valid) == 13
    assert S.summarize(results, ROSTER)["no_bets"] == 4


def test_a_dead_model_stops_the_run_with_a_clear_message():
    class Dead:
        kind = "llm"

        def chat(self, *args):
            raise RuntimeError("401 unauthorized")

    with pytest.raises(RuntimeError, match="Every model call failed"):
        run_scenarios(scenarios(3)[0], ROSTER, Dead(), ArenaConfig(), UsageMeter())


def test_analysts_never_see_the_future_and_bets_do_not_depend_on_it():
    scs, _ = scenarios(5)
    flipped = [replace(sc, _future=[D.Candle(c.t, 987654.0, 987655.0, 987653.0, 987654.5, 555555.0) for c in sc._future])
               for sc in scs]

    class Recorder(MockClient):
        def __init__(self):
            super().__init__(9)
            self.prompts = []

        def chat(self, system, user, temperature, max_tokens):
            self.prompts.append(user)
            return super().chat(system, user, temperature, max_tokens)

    honest, poisoned = Recorder(), Recorder()
    cfg = ArenaConfig(rounds=2, workers=1)
    a = run_scenarios(scs, ROSTER, honest, cfg, UsageMeter())
    b = run_scenarios(flipped, ROSTER, poisoned, cfg, UsageMeter())
    assert all("987654" not in p and "987655" not in p and "555555" not in p for p in poisoned.prompts)
    assert honest.prompts == poisoned.prompts  # the future cannot change a single word the analysts read
    for x, y in zip(a, b):
        assert [(i.p_win, i.stake) for i in x.bets] == [(i.p_win, i.stake) for i in y.bets]
        assert y.outcome.result == WIN  # while the settlement does see the poisoned future


# ------------------------------------------------------------------ scoring


def test_brier_mean_and_pearson():
    assert S.brier(0.3, 1.0) == pytest.approx(0.49) and S.brier(0.3, 0.0) == pytest.approx(0.09)
    assert S.mean([1, 2, 3]) == 2 and math.isnan(S.mean([]))
    assert S.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert S.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert math.isnan(S.pearson([1, 1, 1, 1], [1, 2, 3, 4])) and math.isnan(S.pearson([1, 2], [1, 2]))


def test_bootstrap_interval_behaviour():
    m, lo, hi = S.bootstrap_mean_ci([0.5] * 20)
    assert m == pytest.approx(0.5) and lo == pytest.approx(0.5) and hi == pytest.approx(0.5)
    few = S.bootstrap_mean_ci([0.0, 1.0, 0.0, 1.0, 1.0])
    many = S.bootstrap_mean_ci([0.0, 1.0, 0.0, 1.0, 1.0] * 40)
    assert few[1] <= few[0] <= few[2]
    assert (few[2] - few[1]) > (many[2] - many[1]) > 0  # more data, narrower range
    assert S.bootstrap_mean_ci([0.1, 0.9, 0.4], seed=5) == S.bootstrap_mean_ci([0.1, 0.9, 0.4], seed=5)
    assert all(math.isnan(x) for x in S.bootstrap_mean_ci([]))


def test_calibration_bins():
    rows = S.calibration([(0.10, 0.0), (0.15, 1.0), (0.25, 0.0), (0.45, 1.0), (0.50, 1.0), (0.90, 1.0)])
    assert [r["n"] for r in rows] == [2, 1, 0, 1, 2]
    assert rows[0]["avg_p"] == pytest.approx(0.125) and rows[0]["hit_rate"] == pytest.approx(0.5)
    assert rows[2]["avg_p"] is None and rows[2]["hit_rate"] is None
    assert rows[0]["range"] == "0.0 to 0.2" and rows[-1]["range"] == "0.5 to 1.0"


def test_leaderboard_numbers_are_exact():
    scs, _ = scenarios(3)
    outs = [outcome(WIN), outcome(WIN), outcome(LOSS)]  # y is 1, 1, 0
    results = [result_for(sc, o, bets_for(**{"bull_trend": 0.9})) for sc, o in zip(scs, outs)]
    rows = {r["id"]: r for r in S.leaderboard(results, ROSTER)}
    assert len(rows) == 14 + 6
    flat = rows["bull_volume"]  # always says one third, the fair odds probability
    assert flat["bets"] == 3 and flat["no_bets"] == 0 and flat["side"] == "bull"
    assert flat["pnl"] == pytest.approx(3.0)  # plus 2, plus 2, minus 1 at stake 1
    assert flat["brier"] == pytest.approx(1 / 3) and flat["skill"] == pytest.approx(0.0, abs=1e-9)
    assert flat["right_side_rate"] == pytest.approx(2 / 3) and flat["avg_stake"] == pytest.approx(1.0)
    sharp = rows["bull_trend"]
    assert sharp["brier"] == pytest.approx((0.01 + 0.01 + 0.81) / 3) and sharp["skill"] == pytest.approx(0.17)
    assert rows["bear_volume"]["pnl"] == pytest.approx(-3.0) and rows["bear_volume"]["right_side_rate"] == pytest.approx(1 / 3)
    assert rows["ref_base"]["reference"] and rows["ref_base"]["skill"] == pytest.approx(0.0, abs=1e-9)
    ordered = [r["pnl"] for r in S.leaderboard(results, ROSTER)]
    assert ordered == sorted(ordered, reverse=True)


def test_leaderboard_counts_missed_bets():
    scs, _ = scenarios(3)
    outs = [outcome(WIN), outcome(LOSS), outcome(LOSS)]
    bets = [bets_for(), bets_for(**{"bull_volume": None}), bets_for()]
    results = [result_for(sc, o, b) for sc, o, b in zip(scs, outs, bets)]
    row = next(r for r in S.leaderboard(results, ROSTER) if r["id"] == "bull_volume")
    assert row["bets"] == 2 and row["no_bets"] == 1
    assert row["pnl"] == pytest.approx(2.0 + NO_BET_PENALTY - 1.0)
    assert row["brier"] == pytest.approx((4 / 9 + 1 / 9) / 2)


def test_team_table_is_zero_sum_when_stakes_match():
    scs, _ = scenarios(5)
    outs = [outcome(WIN), outcome(LOSS), outcome(LOSS), outcome(TIMEOUT), outcome(WIN)]
    results = [result_for(sc, o, bets_for(0.4)) for sc, o in zip(scs, outs)]
    teams = S.team_table(results)
    assert teams["bull"]["pnl"] == pytest.approx(-teams["bear"]["pnl"])
    assert teams["bull"]["avg_p"] == pytest.approx(0.4) and teams["bear"]["avg_p"] == pytest.approx(0.4)
    assert teams["bull"]["right_side_rate"] == pytest.approx(2 / 5)
    assert teams["bear"]["right_side_rate"] == pytest.approx(3 / 5)


def test_lens_pairs_score_the_bull_and_bear_together():
    scs, _ = scenarios(2)
    results = [result_for(scs[0], outcome(WIN), bets_for(**{"bull_momentum": 0.6, "bear_momentum": 0.2})),
               result_for(scs[1], outcome(LOSS), bets_for(**{"bull_momentum": 0.6, "bear_momentum": 0.2}))]
    row = next(r for r in S.lens_pairs(results, ROSTER) if r["lens"] == "Momentum")
    assert row["n"] == 2 and row["avg_p"] == pytest.approx(0.4)
    assert row["brier"] == pytest.approx(((0.4 - 1) ** 2 + 0.4 ** 2) / 2)
    assert len(S.lens_pairs(results, ROSTER)) == 7


def test_effective_opinions_copies_count_as_one_and_independent_analysts_count_as_many():
    sc = scenarios(2)[0][0]
    rng = random.Random(5)
    copies, independent = [], []
    for _ in range(60):
        p = rng.uniform(0.2, 0.5)
        copies.append(result_for(sc, outcome(LOSS), bets_for(p)))
        independent.append(result_for(sc, outcome(LOSS), [replace(b, p_win=rng.uniform(0.2, 0.5)) for b in bets_for()]))
    same = S.effective_opinions(copies, ROSTER)
    assert same["avg_correlation"] == pytest.approx(1.0) and same["effective"] == pytest.approx(1.0)
    many = S.effective_opinions(independent, ROSTER)
    assert abs(many["avg_correlation"]) < 0.1 and many["effective"] > 8 and many["n_agents"] == 14
    assert S.effective_opinions(copies[:2], ROSTER)["effective"] is None


def test_follow_the_crowd_takes_only_trades_above_the_cost_adjusted_break_even():
    scs, _ = scenarios(8)
    plan = [(0.6, WIN), (0.6, LOSS), (0.2, WIN), (0.6, LOSS), (0.2, LOSS), (0.6, WIN), (0.6, LOSS), (0.6, LOSS)]
    results = [result_for(sc, outcome(res), bets_for(p)) for sc, (p, res) in zip(scs, plan)]
    out = S.follow_the_crowd(results)
    taken = [r.outcome for r, (p, _) in zip(results, plan) if p == 0.6]
    assert out["taken"] == 6 and out["of"] == 8
    assert out["total_r_net"] == pytest.approx(sum(o.r_net for o in taken))
    assert out["mean_r_net"] == pytest.approx(sum(o.r_net for o in taken) / 6)
    assert out["win_rate"] == pytest.approx(2 / 6) and out["ci_low"] is not None
    assert out["take_everything_mean_r_net"] == pytest.approx(sum(r.outcome.r_net for r in results) / 8)


def test_follow_the_crowd_gives_no_interval_for_a_handful_of_trades():
    scs, _ = scenarios(3)
    results = [result_for(sc, outcome(WIN), bets_for(0.6)) for sc in scs]
    out = S.follow_the_crowd(results)
    assert out["taken"] == 3 and out["ci_low"] is None and out["ci_high"] is None
    nothing = S.follow_the_crowd([result_for(sc, outcome(WIN), bets_for(0.1)) for sc in scs])
    assert nothing["taken"] == 0 and nothing["mean_r_net"] is None and nothing["win_rate"] is None


def stub(n=100, lo=-0.02, hi=0.01, crowd=0.2, taken=0, mean_r=None, ci=(None, None)):
    return {"n_scenarios": n, "brier_crowd": crowd,
            "crowd_minus_base_brier": {"mean": (lo + hi) / 2, "ci_low": lo, "ci_high": hi},
            "follow_the_crowd": {"taken": taken, "mean_r_net": mean_r, "ci_low": ci[0], "ci_high": ci[1]}}


def test_verdict_is_honest_in_every_branch():
    assert "far too few" in S.verdict(stub(n=12)) and "100 or more" in S.verdict(stub(n=12))
    assert "No valid bets" in S.verdict(stub(crowd=None))
    assert "beat the base rate bot" in S.verdict(stub(lo=-0.05, hi=-0.01)) and "clue, not proof" in S.verdict(stub(lo=-0.05, hi=-0.01))
    assert "clearly worse" in S.verdict(stub(lo=0.01, hi=0.05))
    assert "cannot be told apart" in S.verdict(stub(lo=-0.01, hi=0.02))
    assert "lost money after costs" in S.verdict(stub(taken=12, mean_r=-0.2, ci=(-0.4, -0.05)))
    assert "made money after costs" in S.verdict(stub(taken=12, mean_r=0.2, ci=(0.05, 0.4)))
    assert "zero after costs" in S.verdict(stub(taken=12, mean_r=0.0, ci=(-0.2, 0.2)))
    assert "after costs" not in S.verdict(stub(taken=3, mean_r=0.2, ci=(0.05, 0.4)))  # too few trades to say anything
    for text in (S.verdict(stub(n=5)), S.verdict(stub(lo=-0.05, hi=-0.01)), S.verdict(stub(taken=12, mean_r=0.2, ci=(0.1, 0.4)))):
        assert not DASH.search(text)


def test_summarize_a_mock_run():
    scs, _ = scenarios(24)
    results = run_scenarios(scs, ROSTER, MockClient(2), ArenaConfig(rounds=2), UsageMeter())
    s = S.summarize(results, ROSTER)
    assert s["n_scenarios"] == 24 and sum(s["outcomes"].values()) == 24
    assert s["observed_win_rate"] == pytest.approx(s["outcomes"]["WIN"] / 24)
    assert s["fair_odds_win_rate"] == pytest.approx(1 / 3) and s["breakeven_after_costs"] > 1 / 3
    assert len(s["leaderboard"]) == 20 and len(s["lens_pairs"]) == 7 and s["no_bets"] == 0
    bulls = sum(r["pnl"] for r in s["leaderboard"] if r["side"] == "bull")
    assert bulls == pytest.approx(s["teams"]["bull"]["pnl"])
    assert sum(r["n"] for r in s["calibration_crowd"]) == 24
    assert sum(r["n"] for r in s["calibration_all_bets"]) == 24 * 14
    assert "debate_effect" in s and s["debate_effect"]["ci_low"] <= s["debate_effect"]["mean"] <= s["debate_effect"]["ci_high"]
    assert s["verdict"] == S.verdict(s) and "far too few" in s["verdict"]  # 24 is under 30, so it must say so
    one_round = S.summarize(run_scenarios(scs, ROSTER, MockClient(2), ArenaConfig(rounds=1), UsageMeter()), ROSTER)
    assert "debate_effect" not in one_round


def test_summarize_refuses_an_empty_run():
    with pytest.raises(ValueError, match="no scenarios"):
        S.summarize([], ROSTER)


def test_mock_analysts_show_no_skill_over_many_scenarios():
    """A guard against a scoring bug that would flatter noise: random analysts must not look skilled."""
    scs, _ = scenarios(60, seed=21, candles=6000)
    results = run_scenarios(scs, ROSTER, MockClient(4), ArenaConfig(rounds=1), UsageMeter())
    d = S.summarize(results, ROSTER)["crowd_minus_base_brier"]
    assert not d["ci_high"] < 0, "mock analysts have no skill, so they must not beat the base rate bot beyond luck"


# ------------------------------------------------------------------ learning


def test_clean_lessons_strips_bullets_and_dashes_and_caps_the_list():
    raw = "- First lesson - with a dash\n* Second lesson\n3) Third lesson\n\n4. Fourth\n5. Fifth\n6. Sixth\n7. Seventh\n"
    lines = clean_lessons(raw).splitlines()
    assert lines[0] == "1. First lesson with a dash" and lines[1] == "2. Second lesson"
    assert len(lines) == 6 and not DASH.search(" ".join(lines).replace(". ", " "))


@pytest.mark.parametrize("text", ["", "   \n  ", "NO RELIABLE LESSON", "no reliable lesson.", "1. No reliable lesson"])
def test_clean_lessons_recognises_no_lesson(text):
    assert clean_lessons(text) == NO_LESSON


def test_coach_prompt_lists_only_the_training_rows_without_dates():
    scs, _ = scenarios(6)
    results = run_scenarios(scs, ROSTER, MockClient(1), ArenaConfig(), UsageMeter())
    text = coach_prompt(results, ROSTER)
    rows = [ln for ln in text.splitlines() if re.match(r"^\d+: ", ln)]
    assert len(rows) == 6 and "6 training scenarios" in text
    assert not re.search(r"\b(19|20)\d{2}\b", text) and not DASH.search(text)
    assert "BY LENS" in text and "always says the base rate" in text


def test_make_lessons_with_a_model_cleans_and_counts_the_call():
    scs, _ = scenarios(6)
    results = run_scenarios(scs, ROSTER, MockClient(1), ArenaConfig(), UsageMeter())
    coach, meter = Scripted(["1. Lesson A, minus 2 percent - careful.\n- Lesson B."]), UsageMeter()
    lessons = make_lessons(coach, results, ROSTER, meter)
    assert lessons == "1. Lesson A, minus 2 percent careful.\n2. Lesson B." and meter.total.calls == 1
    assert coach.asked[0][0] == COACH_SYSTEM
    assert make_lessons(MockClient(1), results, ROSTER, UsageMeter()).startswith("1. Mock coach")


def paired(n, plain_p, learned_p, wins):
    sc = scenarios(2)[0][0]
    plain, learned = [], []
    for i in range(n):
        out = outcome(WIN if i < wins else LOSS)
        plain.append(result_for(sc, out, bets_for(plain_p(i))))
        learned.append(result_for(sc, out, bets_for(learned_p(i))))
    return plain, learned


def test_learning_effect_verdicts():
    right = lambda i: 0.8 if i < 10 else 0.1  # the first ten are wins  # noqa: E731
    wrong = lambda i: 0.1 if i < 10 else 0.8  # noqa: E731
    flat = lambda i: 1 / 3  # noqa: E731
    better = learning_effect(*paired(40, flat, right, 10))
    assert better["n"] == 40 and better["mean"] < 0 and better["ci_high"] < 0
    assert better["brier_learned"] < better["brier_plain"] and "scored better" in better["verdict"]
    worse = learning_effect(*paired(40, flat, wrong, 10))
    assert worse["mean"] > 0 and "clearly worse" in worse["verdict"]
    same = learning_effect(*paired(40, flat, flat, 10))
    assert same["mean"] == pytest.approx(0.0) and "did not help" in same["verdict"]
    small = learning_effect(*paired(12, flat, right, 4))
    assert "Only 12 test scenarios" in small["verdict"] and "noise" in small["verdict"]
    assert all(not DASH.search(x["verdict"]) for x in (better, worse, same, small))


def test_learning_effect_with_no_valid_bets():
    sc = scenarios(2)[0][0]
    dead = [result_for(sc, outcome(WIN), bets_for(**{s.id: None for s in ROSTER})) for _ in range(3)]
    assert learning_effect(dead, dead)["verdict"] == "No valid bets to compare."


class RecordingMock(MockClient):
    kind = "llm"  # behaves like a model, so the coach is really called

    def __init__(self, coach_reply="1. Prefer quiet charts.\n2. Be careful after big drops."):
        super().__init__(5)
        self.coach_reply = coach_reply
        self.prompts, self.coach_prompts = [], []

    def chat(self, system, user, temperature, max_tokens):
        if system == COACH_SYSTEM:
            self.coach_prompts.append(user)
            return self.coach_reply, Usage(1, 500, 60)
        self.prompts.append(user)
        return super().chat(system, user, temperature, max_tokens)


def test_learning_loop_has_a_purged_split_and_routes_lessons_correctly():
    scs, params = scenarios(12)
    client, meter = RecordingMock(), UsageMeter()
    out = run_learning(scs, ROSTER, client, ArenaConfig(rounds=1, workers=1), meter)
    assert out["train_n"] == 6 and out["test_n"] == 6
    assert [r.scenario.id for r in out["train"]] == [1, 2, 3, 4, 5, 6]
    assert [r.scenario.id for r in out["test_plain"]] == [r.scenario.id for r in out["test_learned"]] == [7, 8, 9, 10, 11, 12]
    # every training outcome is settled before the first test decision
    assert out["train"][-1].scenario.index + params.horizon < out["test_plain"][0].scenario.index
    # the coach sees training rows only
    rows = [ln for ln in client.coach_prompts[0].splitlines() if re.match(r"^\d+: ", ln)]
    assert [int(r.split(":")[0]) for r in rows] == [1, 2, 3, 4, 5, 6]
    # lessons reach exactly the analysts of the with lessons run
    with_lessons = [p for p in client.prompts if "LESSONS FROM EARLIER SCENARIOS" in p]
    assert len(client.prompts) == 3 * 6 * 14 and len(with_lessons) == 6 * 14
    assert client.prompts[: 2 * 6 * 14] == [p for p in client.prompts[: 2 * 6 * 14] if "LESSONS" not in p]
    assert all("Prefer quiet charts" in p for p in with_lessons)
    assert meter.total.calls == 3 * 6 * 14 + 1
    assert out["effect"]["n"] == 6
    pairs = lesson_pairs(out)
    assert [p["id"] for p in pairs] == [7, 8, 9, 10, 11, 12]
    assert all(set(p) == {"id", "result", "crowd_p_plain", "crowd_p_learned"} for p in pairs)


def test_learning_loop_skips_the_lessons_test_when_the_coach_finds_nothing():
    scs, _ = scenarios(10)
    client, meter = RecordingMock("NO RELIABLE LESSON"), UsageMeter()
    out = run_learning(scs, ROSTER, client, ArenaConfig(rounds=1), meter)
    assert out["lessons"] == NO_LESSON and out["test_learned"] is None and out["effect"] is None
    assert meter.total.calls == (5 + 5) * 14 + 1 and lesson_pairs(out) == []
    assert not any("LESSONS FROM EARLIER SCENARIOS" in p for p in client.prompts)


def test_learning_split_always_leaves_something_to_test():
    for n in (2, 3, 9):
        scs, _ = scenarios(n)
        out = run_learning(scs, ROSTER, MockClient(1), ArenaConfig(), UsageMeter())
        assert out["train_n"] >= 1 and out["test_n"] >= 1 and out["train_n"] + out["test_n"] == len(scs)
