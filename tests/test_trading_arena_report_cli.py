"""Arena tests for the reports, the replay page data, and the command line. No network and no API key."""

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from trading_arena import cli
from trading_arena import data as D
from trading_arena import report as R
from trading_arena.agents import MockClient, Usage, UsageMeter, make_roster
from trading_arena.arena import ArenaConfig, run_scenarios
from trading_arena.learn import COACH_SYSTEM
from trading_arena.scenario import Params, build_scenarios
from trading_arena.scoring import summarize

REPO = Path(__file__).resolve().parent.parent
DASH = re.compile(r"[\-‐-―−]")
ROSTER = make_roster()
SECRET = "sk-test-secret-1234"


def make_record(rounds=2, n=10, synthetic=False, learning=None, client=None, interval_s=86400):
    ds = D.synthetic(3000 if interval_s >= 86400 else 6000, seed=6, interval_s=interval_s)
    params = Params.for_interval(interval_s)
    scs = build_scenarios(ds, n, params, seed=2)
    meter = UsageMeter()
    results = run_scenarios(scs, ROSTER, client or MockClient(2), ArenaConfig(rounds=rounds), meter)
    meta = {
        "label": "BTCUSD 1D", "source": "bitstamp", "interval": D.interval_label(interval_s), "interval_s": interval_s,
        "intraday": interval_s < 86400, "tv_symbol": "BITSTAMP:BTCUSD", "model": "mock", "offline": True,
        "rounds": rounds, "seed": 7, "synthetic": synthetic,
        "params": {"k_atr": params.k_atr, "rr": params.rr, "horizon": params.horizon, "fee": params.fee,
                   "slip": params.slip},
    }
    usage = {"calls": meter.total.calls, "prompt_tokens": meter.total.prompt_tokens,
             "completion_tokens": meter.total.completion_tokens}
    return R.build_record(results, ROSTER, summarize(results, ROSTER), meta, usage, learning), results


@pytest.fixture(scope="module")
def record():
    return make_record()[0]


# ------------------------------------------------------------------ formatting helpers

def test_number_words_never_use_a_minus_sign():
    assert R.sg(2.5) == "plus 2.50" and R.sg(-0.04, 3) == "minus 0.040" and R.sg(0.0) == "plus 0.00"
    assert R.sg(None) == R.sg(float("nan")) == R.pc(None) == R.num(float("nan")) == "n/a"
    assert R.pc(0.333) == "33 percent" and R.pc(0.3456, 1) == "34.6 percent"
    assert R.num(0.123456) == "0.123" and R.num(-0.0123, 2) == "minus 0.01" and R.pc(-0.05) == "minus 5 percent"
    assert R.sg(-0.001) == "plus 0.00" and R.num(-0.0001, 2) == "0.00"  # a rounded zero has no sign


def test_text_helpers():
    assert R.tidy("a - b — c–d −e") == "a b c d e" and R.tidy(None) == "" and R.tidy("  plain  ") == "plain"
    assert R.n_of(1, "win") == "1 win" and R.n_of(2, "stop") == "2 stops" and R.n_of(0, "win") == "0 wins"
    assert R.px(67123.4) == "67123" and R.px(61.274) == "61.27" and R.px(0.5) == "0.5000"
    assert R.when(1441324800, False) == "Sep 4, 2015"
    assert R.when(1441324800 + 5 * 3600, True) == "Sep 4, 2015 05:00 UTC"


def test_sanitize_replaces_nan_and_infinity_everywhere():
    nasty = {"a": float("nan"), "b": [1.0, float("inf"), (float("-inf"), 2)], "c": {"d": float("nan"), "e": "text"}}
    clean = R.sanitize(nasty)
    assert clean == {"a": None, "b": [1.0, None, [None, 2]], "c": {"d": None, "e": "text"}}
    json.dumps(clean, allow_nan=False)


# ------------------------------------------------------------------ the run record

def test_record_is_strict_json_with_the_expected_shape(record):
    text = json.dumps(record, allow_nan=False)
    assert json.loads(text) == record
    assert len(record["scenarios"]) == 10 and record["meta"]["rounds"] == 2
    for sc in record["scenarios"]:
        assert len(sc["window"]) == 60 and len(sc["future"]) == sc["setup"]["horizon"]
        assert all(len(row) == 6 for row in sc["window"] + sc["future"])
        assert sc["window"][-1][0] == sc["decision_t"] < sc["future"][0][0]
        assert len(sc["bets"]) == 14 and len(sc["refs"]) == 6
        assert sc["crowd_p"] == pytest.approx(sum(b["p"] for b in sc["bets"]) / 14)
        assert sc["setup"]["stop"] < sc["setup"]["ref"] < sc["setup"]["target"]
        assert sc["outcome"]["result"] in ("WIN", "LOSS", "TIMEOUT")
        assert all(b["round"] == 2 and b["p1"] is not None for b in sc["bets"])


def test_record_keeps_round_one_probabilities_as_receipts(record):
    changed = sum(1 for sc in record["scenarios"] for b in sc["bets"] if b["p"] != b["p1"])
    assert changed > 0  # the debate round moved some minds, and the first answer is still on file


# ------------------------------------------------------------------ markdown

def test_markdown_has_every_section_and_no_dashes(record):
    text = R.render_markdown(record)
    for heading in ("# Trading Arena report", "## The short answer", "## Bulls versus bears", "## Leaderboard",
                    "## Which lens has skill?", "## Calibration", "## Are fourteen analysts really fourteen opinions?",
                    "## Would following the crowd have made money?", "## Did the debate round help?",
                    "## Check it yourself on TradingView", "## Cost of this run", "## Honest limits"):
        assert heading in text, heading
    assert not DASH.search(text), [ln for ln in text.splitlines() if DASH.search(ln)][:3]
    assert "BITSTAMP:BTCUSD" in text and "Select bar" in text and "terms do not allow" in text
    assert "offline demo with no skill" in text and "debate" in text
    assert "Play money only" in text and "most traders lose money" in text


def test_markdown_for_made_up_prices_says_there_is_nothing_to_check():
    rec, _ = make_record(synthetic=True, rounds=1, n=6)
    text = R.render_markdown(rec)
    assert "made up prices, so made up dates" in text
    assert "nothing to check on TradingView" in text and "Select bar" not in text
    assert "Did the debate round help?" not in text  # one round means no debate section


def test_markdown_for_intraday_candles_shows_times():
    rec, _ = make_record(rounds=1, n=6, interval_s=3600)
    text = R.render_markdown(rec)
    assert re.search(r"Decision dates.*\d\d:\d\d UTC", text) and "1h candles" in text
    assert re.search(r"Candle dated [A-Z][a-z]{2} \d{1,2}, \d{4} \d\d:\d\d UTC", text)


def test_markdown_reports_missed_bets():
    class OneBroken(MockClient):
        kind = "llm"

        def chat(self, system, user, temperature, max_tokens):
            if "You are the BULL" in user and "YOUR LENS: Candle behavior" in user:
                raise RuntimeError("boom")
            return super().chat(system, user, temperature, max_tokens)

    rec, _ = make_record(rounds=1, n=6, client=OneBroken(1))
    text = R.render_markdown(rec)
    assert "6 missed bets (each costs 1 point)" in text and ", 6 missed," in text


def test_markdown_learning_section_names_the_control():
    learning = {"lessons": "1. Prefer quiet charts.\n2. Be careful after big drops.", "train_n": 5, "test_n": 5,
                "effect": {"n": 5, "mean": -0.01, "ci_low": -0.05, "ci_high": 0.03, "brier_plain": 0.25,
                           "brier_learned": 0.24, "verdict": "Only 5 test scenarios. Too few."}, "pairs": []}
    text = R.render_markdown(make_record(rounds=1, n=10, learning=learning)[0])
    assert "## Learning experiment" in text and "Every other number in this report scores the runs without lessons" in text
    assert "1. Prefer quiet charts." in text and "Crowd Brier without lessons: 0.250. With lessons: 0.240" in text
    nothing = dict(learning, lessons="NO RELIABLE LESSON", effect=None)
    assert "no reliable lesson, so there was nothing to test" in R.render_markdown(make_record(rounds=1, n=10, learning=nothing)[0])
    assert not DASH.search(text)


def test_markdown_survives_a_record_with_missing_numbers(record):
    """Reports are rebuilt from saved JSON, where NaN has become null."""
    damaged = json.loads(json.dumps(record))
    damaged["summary"]["crowd_minus_base_brier"] = {"mean": None, "ci_low": None, "ci_high": None}
    damaged["summary"]["opinions"] = {"avg_correlation": None, "effective": None, "n_agents": 14}
    damaged["summary"]["follow_the_crowd"].update({"mean_r_net": None, "ci_low": None, "ci_high": None, "win_rate": None})
    damaged["summary"]["leaderboard"][0]["brier"] = None
    text = R.render_markdown(damaged)
    assert "n/a" in text and "Not enough scenarios to measure" in text


# ------------------------------------------------------------------ csv files

def test_csv_files_match_the_record(tmp_path, record):
    R.write_csvs(tmp_path, record)
    with (tmp_path / "bets.csv").open(newline="", encoding="utf-8") as fh:
        bets = list(csv.DictReader(fh))
    with (tmp_path / "scenarios.csv").open(newline="", encoding="utf-8") as fh:
        scs = list(csv.DictReader(fh))
    assert len(scs) == 10 and len(bets) == 10 * 20
    assert list(bets[0]) == ["scenario", "outcome", "agent", "side", "lens", "p_win", "stake", "valid", "payoff",
                             "brier", "round1_p", "case", "main_risk"]
    first = record["scenarios"][0]
    rows = [r for r in bets if r["scenario"] == str(first["id"])]
    assert sum(float(r["payoff"]) for r in rows[:14]) == pytest.approx(sum(b["payoff"] for b in first["bets"]), abs=0.01)
    y = 1.0 if first["outcome"]["result"] == "WIN" else 0.0
    assert float(rows[0]["brier"]) == pytest.approx((first["bets"][0]["p"] - y) ** 2, abs=1e-3)
    assert all(r["round1_p"] == "" for r in rows[14:])  # reference bots have no first round
    assert scs[0]["outcome"] == first["outcome"]["result"] and "+00:00" in scs[0]["decision_time_utc"]


def test_csv_leaves_the_brier_blank_for_missed_bets(tmp_path, record):
    broken = json.loads(json.dumps(record))
    broken["scenarios"][0]["bets"][0].update({"valid": False, "p": 0.0, "stake": 0.0, "payoff": -1.0})
    R.write_csvs(tmp_path, broken)
    with (tmp_path / "bets.csv").open(newline="", encoding="utf-8") as fh:
        first = next(csv.DictReader(fh))
    assert first["valid"] == "0" and first["brier"] == "" and first["payoff"] == "-1.0"


# ------------------------------------------------------------------ replay page

def blob_of(html):
    match = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    assert match, "data block not found"
    return match.group(1)


def test_replay_page_embeds_the_run_as_json(record):
    html = R.render_replay(record)
    assert "__DATA__" not in html
    data = json.loads(blob_of(html))
    assert data["scenarios"] == record["scenarios"] and data["meta"]["tv_symbol"] == "BITSTAMP:BTCUSD"
    assert data["summary"]["bull_pnl"] == record["summary"]["teams"]["bull"]["pnl"]
    assert html.count("</script>") == 2  # the data block and the page script, nothing else


def test_replay_page_survives_hostile_model_text(record):
    hostile = json.loads(json.dumps(record))
    nasty = '</script><img src=x onerror=alert(1)> <!-- <script> & "quotes" \u2028'
    hostile["scenarios"][0]["bets"][0]["case"] = nasty
    hostile["scenarios"][0]["bets"][0]["risk"] = nasty
    hostile["meta"]["label"] = nasty
    html = R.render_replay(hostile)
    blob = blob_of(html)
    assert "<" not in blob  # no raw angle bracket can end the block or open a comment inside it
    assert html.count("</script>") == 2 and html.count("<script") == 2
    parsed = json.loads(blob)
    assert parsed["scenarios"][0]["bets"][0]["case"] == nasty and parsed["scenarios"][0]["bets"][0]["risk"] == nasty
    assert "onerror" in parsed["meta"]["label"]  # kept as text, to be escaped by the page when it shows it


def test_write_all_creates_every_file(tmp_path, record):
    paths = R.write_all(tmp_path / "nested" / "run", record)
    assert set(paths) == {"run", "report", "replay", "bets", "scenarios"}
    for path in paths.values():
        assert path.exists() and path.stat().st_size > 100
    assert json.loads(paths["run"].read_text(encoding="utf-8"), parse_constant=lambda c: pytest.fail(f"bad constant {c}"))


# ------------------------------------------------------------------ command line


class FakeLLM(MockClient):
    """Stands in for the real model client, so the llm paths run with no network."""

    kind = "llm"
    created = []
    asked = []
    dead = False

    def __init__(self, model, api_key, base_url=None):
        super().__init__(3)
        self.model = model
        FakeLLM.created.append((model, api_key, base_url))

    def chat(self, system, user, temperature, max_tokens):
        FakeLLM.asked.append(user)
        if FakeLLM.dead:
            raise RuntimeError("401 unauthorized")
        if system == COACH_SYSTEM:
            return "1. Be careful after strong rallies.\n2. Quiet charts break out less often.", Usage(1, 400, 40)
        return super().chat(system, user, temperature, max_tokens)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A sealed lab: no real .env, no real key, no model, and every file lands under tmp_path."""
    env = {k: v for k, v in os.environ.items() if k not in ("API_KEY", "MODEL_NAME", "BASE_URL")}
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "OpenAIClient", FakeLLM)
    monkeypatch.chdir(tmp_path)
    FakeLLM.created, FakeLLM.asked, FakeLLM.dead = [], [], False
    return tmp_path


def read_run(folder):
    return json.loads((Path(folder) / "run.json").read_text(encoding="utf-8"))


def test_parser_defaults_and_choices():
    parser = cli.build_parser()
    demo = parser.parse_args(["demo"])
    assert demo.scenarios == 24 and demo.rounds == 2 and demo.func is cli.cmd_demo
    run = parser.parse_args(["run", "--csv", "x.csv"])
    assert run.scenarios == 30 and run.rounds == 1 and run.agents == "llm" and run.max_calls == 3000 and run.rr == 2.0
    for bad in (["run", "--rounds", "3"], ["fetch", "--source", "kraken"], ["run", "--agents", "gpt"], []):
        with pytest.raises(SystemExit):
            parser.parse_args(bad)


def test_demo_runs_offline_with_no_key(lab, capsys):
    out = lab / "demo"
    assert cli.main(["demo", "--out", str(out), "--scenarios", "8"]) == 0
    printed = capsys.readouterr().out
    assert "Watch it play: file://" in printed and "Bulls" in printed and "Type YES" not in printed
    run = read_run(out)
    assert run["meta"]["offline"] and run["meta"]["synthetic"] and run["meta"]["rounds"] == 2
    assert len(run["scenarios"]) == 8 and run["usage"]["calls"] == 8 * 14 * 2
    assert "made up" in (out / "report.md").read_text(encoding="utf-8")
    assert not FakeLLM.created  # the demo never builds a model client


def test_default_output_folder_is_under_warehouse_arena(lab, capsys):
    assert cli.main(["demo", "--scenarios", "6", "--rounds", "1"]) == 0
    folders = list((lab / "WareHouse" / "arena").iterdir())
    assert len(folders) == 1 and (folders[0] / "report.md").exists()


def test_run_from_a_csv_file_uses_the_sidecar_and_the_symbol_override(lab, capsys):
    csv_path = lab / "btc_1d.csv"
    D.save_csv(csv_path, D.synthetic(1500, seed=5).candles)
    csv_path.with_suffix(".json").write_text(json.dumps(
        {"label": "BTCUSD 1D", "source": "bitstamp", "tv_symbol": "BITSTAMP:BTCUSD"}), encoding="utf-8")
    out = lab / "out"
    assert cli.main(["run", "--csv", str(csv_path), "--agents", "mock", "--scenarios", "6", "--rounds", "1",
                     "--out", str(out)]) == 0
    run = read_run(out)
    assert run["meta"]["tv_symbol"] == "BITSTAMP:BTCUSD" and run["meta"]["source"] == "bitstamp"
    assert run["meta"]["synthetic"] is False and run["meta"]["label"] == "BTCUSD 1D"
    text = (out / "report.md").read_text(encoding="utf-8")
    assert "BITSTAMP:BTCUSD" in text and "nothing to check on TradingView" not in text
    assert len(list(csv.reader((out / "scenarios.csv").open()))) == 7
    assert len(list(csv.reader((out / "bets.csv").open()))) == 1 + 6 * 20
    out2 = lab / "out2"
    assert cli.main(["run", "--csv", str(csv_path), "--tv-symbol", "COINBASE:BTCUSD", "--agents", "mock",
                     "--scenarios", "4", "--rounds", "1", "--out", str(out2)]) == 0
    assert read_run(out2)["meta"]["tv_symbol"] == "COINBASE:BTCUSD"


def test_run_on_hourly_candles_shows_times(lab):
    out = lab / "hourly"
    assert cli.main(["run", "--synthetic", "6000", "--interval", "1h", "--agents", "mock", "--scenarios", "5",
                     "--rounds", "1", "--out", str(out)]) == 0
    run = read_run(out)
    assert run["meta"]["intraday"] is True and run["meta"]["interval"] == "1h"
    assert run["meta"]["params"]["horizon"] == 48 and " UTC" in (out / "report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("argv, message", [
    (["run", "--agents", "mock"], "Give --csv FILE"),
    (["run", "--csv", "missing.csv", "--agents", "mock"], "missing.csv"),
    (["run", "--synthetic", "1500", "--rr", "1.5", "--agents", "mock"], "at least 2"),
    (["run", "--synthetic", "100", "--agents", "mock"], "Not enough candles"),
    (["run", "--synthetic", "1500", "--interval", "7x", "--agents", "mock"], "Unknown interval"),
    (["run", "--synthetic", "1500"], "API_KEY is not set"),
    (["fetch", "--interval", "7x"], "Unknown interval"),
])
def test_problems_are_explained_not_dumped_as_tracebacks(lab, capsys, argv, message):
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert err.startswith("\nProblem:") and message in err and "Traceback" not in err


def test_a_bad_csv_is_explained(lab, capsys):
    bad = lab / "bad.csv"
    bad.write_text("when,price\n1,2\n", encoding="utf-8")
    assert cli.main(["run", "--csv", str(bad), "--agents", "mock"]) == 2
    assert "needs a time column" in capsys.readouterr().err


def test_llm_run_asks_first_and_cancels_without_spending(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    assert cli.main(["run", "--synthetic", "1500", "--scenarios", "4", "--out", str(lab / "o")]) == 1
    out = capsys.readouterr().out
    assert "Cancelled." in out and "About 56 model calls" in out and not FakeLLM.asked and not (lab / "o").exists()


def test_llm_run_with_a_price_gives_a_cost_estimate_and_runs_on_yes(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    monkeypatch.setenv("MODEL_NAME", "model-from-env")
    monkeypatch.setattr("builtins.input", lambda prompt="": "YES")
    out_dir = lab / "o"
    assert cli.main(["run", "--synthetic", "1500", "--scenarios", "4", "--price-in", "2", "--price-out", "8",
                     "--out", str(out_dir)]) == 0
    printed = capsys.readouterr().out
    assert "At your prices that is about" in printed and "I do not know your model's price" not in printed
    assert FakeLLM.created[0][0] == "model-from-env"
    run = read_run(out_dir)
    assert run["meta"]["model"] == "model-from-env" and run["meta"]["offline"] is False and run["usage"]["calls"] == 56
    assert "offline demo" not in (out_dir / "report.md").read_text(encoding="utf-8")


def test_llm_run_without_a_price_says_it_does_not_know(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    assert cli.main(["run", "--synthetic", "1500", "--scenarios", "3", "--yes", "--model", "my-model",
                     "--out", str(lab / "o")]) == 0
    printed = capsys.readouterr().out
    assert "I do not know your model's price" in printed and FakeLLM.created[0][0] == "my-model"


def test_the_call_limit_stops_an_expensive_run_before_any_call(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    assert cli.main(["run", "--synthetic", "3000", "--scenarios", "20", "--max-calls", "100", "--yes"]) == 2
    assert "over the --max-calls limit of 100" in capsys.readouterr().err and not FakeLLM.asked


def test_a_dead_model_ends_the_run_cleanly_and_saves_nothing(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    FakeLLM.dead = True
    assert cli.main(["run", "--synthetic", "1500", "--scenarios", "3", "--yes", "--out", str(lab / "o")]) == 2
    assert "Every model call failed" in capsys.readouterr().err and not (lab / "o").exists()


def test_the_api_key_is_never_printed_or_saved(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    out_dir = lab / "o"
    assert cli.main(["run", "--synthetic", "1500", "--scenarios", "3", "--yes", "--out", str(out_dir)]) == 0
    seen = capsys.readouterr()
    assert SECRET not in seen.out and SECRET not in seen.err
    for path in out_dir.iterdir():
        assert SECRET not in path.read_text(encoding="utf-8"), path.name
    assert FakeLLM.created[0][1] == SECRET  # it was used for the connection, and only there


def test_learning_run_scores_the_control_and_matches_the_cost_estimate(lab, monkeypatch, capsys):
    monkeypatch.setenv("API_KEY", SECRET)
    out_dir = lab / "o"
    assert cli.main(["run", "--synthetic", "3000", "--scenarios", "10", "--learn", "--yes", "--out", str(out_dir)]) == 0
    printed = capsys.readouterr().out
    planned = int(re.search(r"About ([\d,]+) model calls", printed).group(1).replace(",", ""))
    run = read_run(out_dir)
    assert planned == run["usage"]["calls"] == 5 * 14 + 1 + 2 * 5 * 14  # train, coach, then the test twice
    assert run["summary"]["n_scenarios"] == 10  # train plus the control, never the with lessons run
    learning = run["learning"]
    assert learning["train_n"] == 5 and learning["test_n"] == 5 and learning["lessons"].startswith("1. Be careful")
    assert [p["id"] for p in learning["pairs"]] == [6, 7, 8, 9, 10]
    assert all(p["crowd_p_plain"] is not None and p["crowd_p_learned"] is not None for p in learning["pairs"])
    lessons_prompts = [p for p in FakeLLM.asked if "LESSONS FROM EARLIER SCENARIOS" in p]
    assert len(lessons_prompts) == 5 * 14
    assert "## Learning experiment" in (out_dir / "report.md").read_text(encoding="utf-8")


def test_learning_run_with_mock_analysts_works_offline(lab):
    out_dir = lab / "o"
    assert cli.main(["run", "--synthetic", "3000", "--agents", "mock", "--scenarios", "8", "--learn",
                     "--out", str(out_dir)]) == 0
    assert read_run(out_dir)["learning"]["lessons"].startswith("1. Mock coach")


def test_report_rebuilds_every_file_from_the_saved_run(lab, capsys):
    out = lab / "demo"
    assert cli.main(["demo", "--out", str(out), "--scenarios", "6", "--rounds", "1"]) == 0
    before = (out / "report.md").read_text(encoding="utf-8")
    for name in ("report.md", "replay.html", "bets.csv", "scenarios.csv"):
        (out / name).unlink()
    assert cli.main(["report", "--run", str(out)]) == 0
    assert (out / "report.md").read_text(encoding="utf-8") == before
    assert all((out / name).exists() for name in ("replay.html", "bets.csv", "scenarios.csv"))
    assert cli.main(["report", "--run", str(lab / "nowhere")]) == 2
    assert "Could not read" in capsys.readouterr().err


def test_fetch_saves_the_candles_and_a_tradingview_hint(lab, monkeypatch, capsys):
    candles = D.synthetic(800, seed=2).candles
    seen = {}

    def fake_fetch(source, pair, interval_s, start, end, progress=None):
        seen.update(source=source, pair=pair, interval_s=interval_s, span=end - start)
        return candles

    monkeypatch.setattr(D, "fetch_candles", fake_fetch)
    out = lab / "data" / "btc.csv"
    assert cli.main(["fetch", "--source", "bitstamp", "--pair", "btcusd", "--years", "2", "--out", str(out)]) == 0
    assert seen["source"] == "bitstamp" and seen["interval_s"] == 86400 and abs(seen["span"] - 2 * 365.25 * 86400) < 86400
    side = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert side == {"label": "BTCUSD 1D", "source": "bitstamp", "tv_symbol": "BITSTAMP:BTCUSD"}
    assert len(D.load_csv(out).candles) == 800
    assert "Next: python -m trading_arena run --csv" in capsys.readouterr().out
    # and the saved file plugs straight into a run, picking up the hint
    run_out = lab / "run"
    assert cli.main(["run", "--csv", str(out), "--agents", "mock", "--scenarios", "4", "--rounds", "1",
                     "--out", str(run_out)]) == 0
    assert read_run(run_out)["meta"]["tv_symbol"] == "BITSTAMP:BTCUSD"


def test_fetch_failures_are_explained(lab, monkeypatch, capsys):
    def blocked(*args, **kwargs):
        raise RuntimeError("Could not download from the exchange: 403")

    monkeypatch.setattr(D, "fetch_candles", blocked)
    assert cli.main(["fetch", "--out", str(lab / "x.csv")]) == 2
    assert "Could not download" in capsys.readouterr().err
    monkeypatch.setattr(D, "fetch_candles", lambda *a, **k: D.synthetic(100).candles)
    assert cli.main(["fetch", "--out", str(lab / "x.csv")]) == 2
    assert "Only 100 candles came back" in capsys.readouterr().err and not (lab / "x.csv").exists()


def test_env_file_fallback_reads_simple_lines(tmp_path, monkeypatch):
    env = {}
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.setitem(sys.modules, "utils.env_loader", None)  # force the small built in parser
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text('# a comment\nAPI_KEY="sk-from-file"\nMODEL_NAME=\'m1\'\nBASE_URL=https://x.test/v1\nEMPTY\n',
                                   encoding="utf-8")
    cli.load_env()
    assert env == {"API_KEY": "sk-from-file", "MODEL_NAME": "m1", "BASE_URL": "https://x.test/v1"}
    env["API_KEY"] = "already set"
    cli.load_env()
    assert env["API_KEY"] == "already set"  # the real environment wins over the file


def test_module_entry_point_runs_the_demo(tmp_path):
    out = tmp_path / "demo"
    env = {k: v for k, v in os.environ.items() if k != "API_KEY"}
    env["PYTHONPATH"] = str(REPO)
    done = subprocess.run([sys.executable, "-m", "trading_arena", "demo", "--scenarios", "6", "--rounds", "1",
                           "--out", str(out)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert (out / "replay.html").exists() and "Watch it play" in done.stdout
    helped = subprocess.run([sys.executable, "-m", "trading_arena", "--help"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=60)
    assert helped.returncode == 0 and "7 bulls vs 7 bears" in helped.stdout
