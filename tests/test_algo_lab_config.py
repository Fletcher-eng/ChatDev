"""Tests for the Algo Trading Lab settings file."""

from pathlib import Path

import pytest
import yaml

from algo_lab.config import DEFAULT_CONFIG_PATH, ConfigError, load_config


def raw_config() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def write(tmp_path: Path, raw) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def test_default_config_has_the_agreed_assets():
    cfg = load_config()
    assert [a.symbol for a in cfg.assets] == ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "JPM", "QNT"]
    qnt = cfg.asset("qnt")
    assert (qnt.kind, qnt.market, qnt.yahoo) == ("crypto", "crypto", "QNT-USD")
    aapl = cfg.asset("AAPL")
    assert (aapl.kind, aapl.market, aapl.yahoo) == ("stock", "us", "AAPL")
    assert cfg.asset("SPY").market == "us"


def test_default_numbers_come_from_the_file():
    data = load_config().data
    assert data.interval == "1d"
    assert data.min_bars == 400
    assert data.confirm_delay_minutes == 30
    assert data.stale_after_days == {"us": 4, "crypto": 2}
    assert data.max_gap_days == {"us": 5, "crypto": 1}
    assert data.adjusted is True
    assert data.folder != data.demo_folder


def test_symbols_are_upper_cased(tmp_path):
    raw = raw_config()
    raw["assets"][0]["symbol"] = "spy"
    assert load_config(write(tmp_path, raw)).assets[0].symbol == "SPY"


@pytest.mark.parametrize("edit, expected", [
    (lambda r: r["assets"].append({"symbol": "SPY", "kind": "etf", "sector": "x"}), "listed twice"),
    (lambda r: r["assets"][0].update(kind="coin"), "kind for SPY must be one of"),
    (lambda r: r.update(assets=[]), "at least one asset"),
    (lambda r: r["assets"][0].update(symbol=True), "must be text"),
    (lambda r: r["assets"][0].update(symbol="BAD SYMBOL"), "1 to 10 letters"),
    (lambda r: r["assets"][0].pop("sector"), "sector must be text"),
    (lambda r: r["data"].update(interval="1h"), "interval must be 1d"),
    (lambda r: r["data"].update(adjusted="yes"), "adjusted must be true or false"),
    (lambda r: r["data"].update(min_bars=True), "min_bars must be a number"),
    (lambda r: r["data"].update(min_bars=10), "min_bars must be between"),
    (lambda r: r["data"].update(min_bars=400.5), "whole number"),
    (lambda r: r["data"]["stale_after_days"].pop("crypto"), "exactly two entries"),
    (lambda r: r["data"].update(demo_folder=r["data"]["folder"]), "must differ"),
])
def test_bad_settings_are_explained(tmp_path, edit, expected):
    raw = raw_config()
    edit(raw)
    with pytest.raises(ConfigError, match=expected):
        load_config(write(tmp_path, raw))


def test_missing_file_and_bad_yaml_are_explained(tmp_path):
    with pytest.raises(ConfigError, match="Could not read"):
        load_config(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("assets: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(bad)
    plain = tmp_path / "list.yaml"
    plain.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="sections assets and data"):
        load_config(plain)


def test_unknown_symbol_names_the_known_ones():
    with pytest.raises(ConfigError, match="Unknown symbol XYZ. Your config has: SPY"):
        load_config().asset("XYZ")
