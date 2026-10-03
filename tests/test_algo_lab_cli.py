"""Tests for the Algo Trading Lab command line."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from algo_lab import cli
from algo_lab import data as D
from algo_lab.config import DEFAULT_CONFIG_PATH
from algo_lab.synthetic import make_series

LAB_FOLDER = Path(__file__).resolve().parent.parent / "algo_lab"
DOCS_FILE = Path(__file__).resolve().parent.parent / "docs" / "algo_lab.md"


@pytest.fixture()
def config_file(tmp_path):
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["data"]["folder"] = str(tmp_path / "real")
    raw["data"]["demo_folder"] = str(tmp_path / "demo")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def no_dashes(text):
    assert "—" not in text and "–" not in text and " - " not in text and " -- " not in text


def live_downloader(symbol, start, adjusted):
    """Made up bars that end yesterday, so these tests never go stale as the calendar moves."""
    crypto = symbol.endswith("-USD")
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    frame = make_series(800, "crypto" if crypto else "us", end, seed=2)[0]
    raw = frame.rename(columns=str.capitalize).copy()
    raw.index = raw.index.tz_localize("UTC" if crypto else "America/New_York")
    raw.index.name = "Date"
    return raw


@pytest.fixture()
def offline(monkeypatch):
    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", live_downloader)


ALL_INSTALLED = [(pip, purpose, needed, "1.0") for _, pip, purpose, needed in cli.LIBRARIES]


def test_check_is_ready_when_everything_is_installed(monkeypatch, capsys, config_file):
    monkeypatch.setattr(cli, "library_status", lambda: ALL_INSTALLED)
    code, out, _ = run(capsys, "check", "--config", str(config_file))
    assert code == 0
    assert "Config: ok, 7 assets: SPY, QQQ, AAPL, MSFT, NVDA, JPM, QNT" in out
    assert "no paid service, no API key, no exchange account, no wallet" in out
    assert "Nothing here can place a real order" in out
    no_dashes(out)


def test_check_flags_a_missing_library(monkeypatch, capsys, config_file):
    rows = [(pip, purpose, needed, None if pip == "yfinance" else "1.0") for pip, purpose, needed, _ in ALL_INSTALLED]
    monkeypatch.setattr(cli, "library_status", lambda: rows)
    code, out, _ = run(capsys, "check", "--config", str(config_file))
    assert code == 2 and "MISSING  yfinance (needed for downloading prices)" in out
    assert "pip install -r algo_lab/requirements.txt" in out


def test_a_library_needed_only_later_is_not_a_failure(monkeypatch, capsys, config_file):
    rows = [(pip, purpose, needed, None if pip == "hmmlearn" else "1.0") for pip, purpose, needed, _ in ALL_INSTALLED]
    monkeypatch.setattr(cli, "library_status", lambda: rows)
    code, out, _ = run(capsys, "check", "--config", str(config_file))
    assert code == 0 and "later    hmmlearn (needed for Step 2, the regime model)" in out


def test_check_runs_on_the_real_environment(capsys, config_file):
    code, out, _ = run(capsys, "check", "--config", str(config_file))
    assert code in (0, 2) and "Python 3" in out and "pandas" in out


def test_demo_writes_labelled_made_up_data(capsys, config_file, tmp_path):
    code, out, _ = run(capsys, "demo", "--config", str(config_file))
    assert code == 0 and "MADE UP DATA" in out and "labelled SYNTHETIC" in out
    assert len(list((tmp_path / "demo").glob("*_1d.csv"))) == 7
    assert not (tmp_path / "real").exists()
    no_dashes(out)


def test_health_with_nothing_saved_stops(capsys, config_file):
    code, out, _ = run(capsys, "health", "--config", str(config_file))
    assert code == 2 and "No saved data for SPY. Run: python -m algo_lab fetch" in out
    assert "OVERALL: STOP" in out


def test_fetch_then_health(capsys, config_file, tmp_path, offline):
    code, out, _ = run(capsys, "fetch", "--config", str(config_file))
    assert code == 0 and "OVERALL: OK" in out and "safe to paste into a chat" in out
    assert (tmp_path / "real" / "summary.txt").exists()
    assert len(list((tmp_path / "real").glob("*_1d.csv"))) == 7
    no_dashes(out)
    code, out, _ = run(capsys, "health", "SPY", "QNT", "--config", str(config_file))
    assert code == 0 and "OVERALL: OK" in out and "QQQ" not in out


def test_a_failed_fetch_stops_and_invents_nothing(monkeypatch, capsys, config_file, tmp_path):
    def down(symbol, start, adjusted):
        raise ConnectionError("no internet")

    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", down)
    code, out, _ = run(capsys, "fetch", "--config", str(config_file))
    assert code == 2 and "OVERALL: STOP" in out and "Nothing was guessed" in out
    assert "check your internet" in out
    assert not list((tmp_path / "real").glob("*.csv"))
    no_dashes(out)


def test_a_missing_library_gives_one_clear_message(monkeypatch, capsys, config_file):
    def no_library(symbol, start, adjusted):
        raise D.SetupError("The yfinance library is not installed. Run: pip install yfinance")

    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", no_library)
    code, out, err = run(capsys, "fetch", "--config", str(config_file))
    assert code == 2 and err.count("pip install yfinance") == 1 and "OVERALL" not in out


def test_unknown_symbol_and_bad_config_are_friendly(capsys, config_file, tmp_path, offline):
    code, _, err = run(capsys, "fetch", "XYZ", "--config", str(config_file))
    assert code == 2 and "Unknown symbol XYZ" in err
    bad = tmp_path / "bad.yaml"
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    raw["data"]["interval"] = "1h"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    code, _, err = run(capsys, "check", "--config", str(bad))
    assert code == 2 and "interval must be 1d" in err


def test_no_em_or_en_dashes_anywhere_in_the_lab():
    files = [p for p in LAB_FOLDER.rglob("*") if p.suffix in {".py", ".yaml", ".txt"}]
    if DOCS_FILE.exists():
        files.append(DOCS_FILE)
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "—" not in text and "–" not in text, path.name
