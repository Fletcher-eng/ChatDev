"""Tests for the regime model (Step 2). They use made up bars whose hidden regimes are known."""

import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

pytest.importorskip("hmmlearn")

from algo_lab import cli
from algo_lab import regime as R
from algo_lab.data import DataError, SetupError
from algo_lab.synthetic import make_series

END = date(2026, 10, 1)


@pytest.fixture(scope="module")
def series():
    return make_series(2000, "us", END, seed=3)


@pytest.fixture(scope="module")
def walked(series):
    frame, truth = series
    return R.walk_forward(frame, "SYN", min_train=500, refit_every=126, restarts=3), truth


def no_dashes(text):
    assert "—" not in text and "–" not in text and " - " not in text and " -- " not in text


def test_features_use_only_that_day_and_earlier_days(series):
    frame, _ = series
    whole = R.features(frame)
    part = R.features(frame.iloc[:900])
    assert np.allclose(whole.loc[part.index].to_numpy(), part.to_numpy())


def test_the_filter_never_looks_ahead(series):
    frame, _ = series
    x = R.features(frame).to_numpy()
    model = R.fit(x[:800], restarts=2)
    assert np.allclose(R.forward_filter(model, x[:1200])[:900], R.forward_filter(model, x[:900]))


def test_probabilities_are_real_probabilities(walked):
    result, _ = walked
    probs = result.probabilities.dropna()
    assert len(probs) > 0
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert probs.to_numpy().min() >= 0.0 and probs.to_numpy().max() <= 1.0


def test_nothing_is_said_before_the_first_fit(walked):
    result, _ = walked
    assert result.regime.iloc[: result.min_train].isna().all()
    assert result.regime.iloc[result.min_train:].notna().all()
    assert result.refits[0] == result.probabilities.index[result.min_train]


def test_names_always_mean_the_same_thing(walked):
    result, _ = walked
    typical = result.model.typical()
    scores = [typical[name][0] / typical[name][1] for name in ("bear", "neutral", "bull")]  # return per unit of wildness
    assert scores == sorted(scores)
    assert typical["bear"][1] > typical["bull"][1]  # the bear regime is the stormy one


def test_it_finds_the_hidden_regimes_better_than_chance(walked):
    result, truth = walked
    truth = truth.reindex(result.regime.index)
    known = result.regime.notna()
    accuracy = float((result.regime[known] == truth[known]).mean())
    bear_recall = float((result.regime[known][truth[known] == "bear"] == "bear").mean())
    assert accuracy > 0.5  # guessing would give about 0.33
    assert bear_recall > 0.7  # the stormy regime is the one it must not miss


def test_cutting_off_the_future_changes_nothing_in_the_past(series, walked):
    frame, _ = series
    result, _ = walked
    cut = R.walk_forward(frame.iloc[:1300], "SYN", min_train=500, refit_every=126, restarts=3)
    shared = cut.probabilities.index
    assert np.allclose(result.probabilities.loc[shared].dropna().to_numpy(), cut.probabilities.dropna().to_numpy())


def test_the_label_does_not_flicker_every_day(walked):
    result, _ = walked
    info = R.describe(result)
    assert info["flips"] / info["years"] < 40


@pytest.fixture(scope="module")
def crashed(series):
    """The same made up bars, but the last 20 days swing six times harder than anything before."""
    frame, _ = series
    frame = frame.copy()
    daily = np.log(frame["close"] / frame["close"].shift(1)).fillna(0.0)
    daily.iloc[-20:] *= 6.0
    frame["close"] = frame["close"].iloc[0] * np.exp(daily.cumsum())
    return R.walk_forward(frame, "CRASH", min_train=500, refit_every=126, restarts=3)


def test_a_crash_worse_than_anything_it_learned_from_is_called_unseen(crashed):
    labelled = crashed.regime.dropna()
    assert (labelled[crashed.unseen[labelled.index]] == "unseen").all()
    assert crashed.unseen.iloc[-15:].mean() > 0.6
    assert crashed.unseen.iloc[:-30].mean() < 0.05  # ordinary days are almost never called unseen


def test_the_report_says_unseen_plainly(crashed):
    text = R.render_regime(crashed)
    assert text.startswith("CRASH: UNSEEN") and "no new trades" in text and "not trusted" in text
    no_dashes(text)


def test_ordinary_data_is_rarely_unseen(walked):
    result, _ = walked
    assert R.describe(result)["unseen_share"] < 0.05


def test_too_little_history_is_explained(series):
    frame, _ = series
    with pytest.raises(DataError, match="needs at least 501"):
        R.walk_forward(frame.iloc[:400], "NEW")
    with pytest.raises(DataError, match="too few for 3 regimes"):
        R.fit(np.zeros((100, 2)))
    with pytest.raises(DataError, match="supports 2 or 3 regimes"):
        R.fit(np.zeros((400, 2)), n_states=4)


def test_a_missing_library_gives_a_plain_message(monkeypatch, series):
    frame, _ = series
    monkeypatch.setitem(sys.modules, "hmmlearn.hmm", None)
    with pytest.raises(SetupError, match="pip install -r algo_lab/requirements_later.txt"):
        R.fit(R.features(frame).to_numpy())


def test_a_two_regime_model_works_too(series):
    frame, _ = series
    model = R.fit(R.features(frame).to_numpy(), n_states=2, restarts=2)
    assert model.names == ("bear", "bull")
    assert model.typical()["bear"][0] < model.typical()["bull"][0]


def test_the_report_is_plain_and_has_no_dashes(walked):
    result, _ = walked
    text = R.render_regime(result)
    assert text.startswith("SYN: ") and " percent sure" in text and "What each regime looks like" in text
    no_dashes(text)
    no_dashes(R.FOOTER)


def live_downloader(bars):
    def download(symbol, start, adjusted):
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        frame = make_series(bars, "us", end, seed=2)[0]
        raw = frame.rename(columns=str.capitalize).copy()
        raw.index = raw.index.tz_localize("America/New_York")
        raw.index.name = "Date"
        return raw

    return download


def test_the_command_prints_a_mood_for_each_ticker(monkeypatch, capsys):
    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", live_downloader(800))
    code = cli.main(["regime", "SPY", "QQQ"])
    out = capsys.readouterr().out
    assert code == 0 and "SPY: " in out and "QQQ: " in out and "not tested for profit yet" in out
    no_dashes(out)


def test_the_command_says_so_when_there_is_not_enough_history(monkeypatch, capsys):
    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cli, "download_yahoo", live_downloader(300))
    code = cli.main(["regime", "NEWCO"])
    out = capsys.readouterr().out
    assert code == 2 and "NEWCO: no answer." in out and "needs at least 501" in out
