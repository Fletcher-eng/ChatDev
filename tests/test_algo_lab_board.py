"""Tests for the Trade Board builder and the practice file behind it."""

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from algo_lab import board as B
from algo_lab import cli
from algo_lab import data as D
from algo_lab.config import load_config
from algo_lab.synthetic import make_series

REPO = Path(__file__).resolve().parent.parent
CALLS_FILE = REPO / "practice" / "calls.json"
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)  # the morning of the first practice day


@pytest.fixture()
def cfg():
    return load_config()


@pytest.fixture()
def calls():
    return B.load_calls(CALLS_FILE)


def fake_downloader(calls, mismatch=None):
    """Made up bars shaped like Yahoo's. The last close on 2026-10-27 equals the call's reference close."""
    refs = {c["symbol"]: c["ref_close"] for c in calls["calls"]}

    def download(symbol, start, adjusted):
        n = 13 if symbol == "AIOK" else 500
        base = make_series(n, "us", date(2026, 10, 27), seed=len(symbol) + n)[0]
        target = refs.get(symbol, 0.55 if symbol == "NEXR" else 13.42)
        if symbol == mismatch:
            target *= 1.05  # Yahoo disagrees with the number the call was written with
        base[D.PRICES] *= target / base["close"].iloc[-1]
        base["volume"] *= 100
        raw = base.rename(columns=str.capitalize).copy()
        raw.index = raw.index.tz_localize("America/New_York")
        raw.index.name = "Date"
        return raw

    return download


# ---------------------------------------------------------------- the practice file

def test_the_practice_file_obeys_its_own_rules(calls):
    account = calls["account"]
    assert [c["symbol"] for c in calls["calls"]] == ["JPM", "QQQ", "MSFT"]
    assert [c["optional"] for c in calls["calls"]] == [False, False, True]
    for call in calls["calls"]:
        assert call["shares"] * call["ref_close"] <= account * calls["position_cap_pct"] / 100, call["symbol"]
        assert call["shares"] * call["stop_gap"] <= account * 0.02, call["symbol"]
        assert abs(call["stop_gap"] - 2 * call["atr14"]) <= 0.02, call["symbol"]
    invested = sum(c["shares"] * c["ref_close"] for c in calls["calls"])
    assert invested <= account * calls["invested_cap_pct"] / 100
    assert len(calls["calls"]) <= calls["max_positions"]


def test_the_numbers_told_to_the_user_are_the_numbers_in_the_file(calls):
    by = {c["symbol"]: c for c in calls["calls"]}
    assert (by["JPM"]["shares"], by["JPM"]["stop_gap"]) == (74, 12.07)
    assert (by["QQQ"]["shares"], by["QQQ"]["stop_gap"]) == (34, 22.86)
    assert (by["MSFT"]["shares"], by["MSFT"]["stop_gap"]) == (19, 21.89)


def write(tmp_path, raw):
    path = tmp_path / "calls.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def raw_file():
    return json.loads(CALLS_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("edit, expected", [
    (lambda r: r.pop("account"), "account must be a number above zero"),
    (lambda r: r["calls"][0].update(shares=0), "shares must be a number above zero"),
    (lambda r: r["calls"][0].update(shares=7.5), "shares must be a whole number"),
    (lambda r: r["calls"][1].update(symbol="JPM"), "JPM is listed twice"),
    (lambda r: r["calls"][0].update(optional="no"), "optional must be true or false"),
    (lambda r: r.update(written="28 Oct"), "written must be a date"),
    (lambda r: r["watch"][0].update(symbol="QQQ"), "QQQ is listed twice"),
    (lambda r: r.update(calls=[]), "needs a list of calls"),
])
def test_bad_practice_files_are_explained(tmp_path, edit, expected):
    raw = raw_file()
    edit(raw)
    with pytest.raises(D.DataError, match=expected):
        B.load_calls(write(tmp_path, raw))


def test_missing_and_broken_files_are_explained(tmp_path):
    with pytest.raises(D.DataError, match="Could not read"):
        B.load_calls(tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(D.DataError, match="not valid JSON"):
        B.load_calls(broken)


# ---------------------------------------------------------------- the data behind the page

def test_build_data_shapes_everything_for_the_page(cfg, calls):
    data = B.build_data(cfg, calls, NOW, fake_downloader(calls), pause=0)
    assert data["asOf"] == "2026-10-27" and data["warnings"] == [] and data["averageBars"] == 50
    assert [t["symbol"] for t in data["trades"]] == ["JPM", "QQQ", "MSFT"]
    for trade in data["trades"]:
        s = trade["series"]
        assert len(s["d"]) == len(s["c"]) == len(s["a"]) == 110
        assert s["a"][0] is not None  # the average comes from the full history, not just the bars drawn
        assert trade["series"]["c"][-1] == trade["refClose"]
    jpm = data["trades"][0]
    assert (jpm["shares"], jpm["stopGap"], jpm["optional"]) == (74, 12.07, False)
    nexr, aiok = data["watch"]
    assert [f["name"] for f in nexr["flags"]] == ["PENNY"] and len(nexr["series"]["c"]) == 60
    assert [f["name"] for f in aiok["flags"]] == ["NEW"] and len(aiok["series"]["c"]) == 13
    assert all(v is None for v in aiok["series"]["a"])  # 13 bars cannot make a 50 bar average
    assert nexr["flags"][0]["text"][0].isupper() and nexr["stats"]["last"] == pytest.approx(0.55)


def test_a_disagreement_with_yahoo_is_written_on_the_page(cfg, calls):
    data = B.build_data(cfg, calls, NOW, fake_downloader(calls, mismatch="JPM"), pause=0)
    assert len(data["warnings"]) == 1
    assert "JPM" in data["warnings"][0] and "not $335.79" in data["warnings"][0]


def test_a_failed_download_stops_the_board(cfg, calls):
    def down(symbol, start, adjusted):
        raise ConnectionError("no internet")

    with pytest.raises(D.DataError, match="Could not download JPM"):
        B.build_data(cfg, calls, NOW, down, pause=0)


# ---------------------------------------------------------------- the page

def test_render_page_embeds_the_data_safely(cfg, calls):
    data = B.build_data(cfg, calls, NOW, fake_downloader(calls), pause=0)
    data["warnings"] = ["</script><script>alert(1)</script>"]
    page = B.render_page(data, standalone=False)
    assert "__DATA__" not in page and "</script><script>alert(1)" not in page
    blob = re.search(r'<script type="application/json" id="board-data">(.*?)</script>', page, re.S).group(1)
    assert json.loads(blob) == data
    assert page.lstrip().startswith("<title>Trade Board</title>") and "<html" not in page
    full = B.render_page(data, standalone=True)
    assert full.startswith("<!doctype html>") and "</body>" in full


def test_the_page_loads_nothing_from_unexpected_places_and_has_no_dashes():
    template = B.TEMPLATE_PATH.read_text(encoding="utf-8")
    hosts = {re.match(r"https?://([^/\"'<>) ]+)", u).group(1) for u in re.findall(r"https?://[^\s\"'<>)]+", template)}
    assert hosts <= {"fonts.googleapis.com"}
    assert "—" not in template and "–" not in template
    assert 'name="claude:viewport-fit-sides"' in template and "env(safe-area-inset-left" in template
    assert 'id="board-data"' in template and template.count("__DATA__") == 1


def test_write_board_and_the_board_command(tmp_path, capsys, monkeypatch, cfg, calls):
    out = B.write_board(cfg, CALLS_FILE, tmp_path / "deep" / "board.html", NOW, fake_downloader(calls), pause=0)
    assert out.exists() and "Trade Board" in out.read_text(encoding="utf-8")
    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", fake_downloader(calls))
    target = tmp_path / "cli.html"
    code = cli.main(["board", "--calls", str(CALLS_FILE), "--out", str(target)])
    assert code == 0 and target.exists() and "Open that file in a browser" in capsys.readouterr().out


def test_the_board_command_stops_when_yahoo_is_down(tmp_path, capsys, monkeypatch):
    def down(symbol, start, adjusted):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", down)
    target = tmp_path / "never.html"
    code = cli.main(["board", "--calls", str(CALLS_FILE), "--out", str(target)])
    assert code == 2 and not target.exists() and "Could not download" in capsys.readouterr().err
