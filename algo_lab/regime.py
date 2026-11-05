"""Step 2: the regime model. A Hidden Markov Model (HMM) that says whether a market is in a bear, neutral or bull mood.

A regime here is a label for how the market has been behaving: its typical daily move and its typical daily swing.
It is not a prediction, and nothing in this file is tested for profit. That test is Step 4.

Two rules keep it honest:
* Forward only. The probability for a day uses that day and earlier days, never later ones. The usual "best path"
  answer (Viterbi) and the smoothed answer both peek at the future, so they are not used for decisions.
* Walk forward. The model is refit every few weeks on the days before that point only, then used on the days after.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .data import DataError, SetupError, plural

NAMES_BY_COUNT = {2: ("bear", "bull"), 3: ("bear", "neutral", "bull")}
UNSEEN_PERCENTILE = 0.5  # the least ordinary half percent of the training days sets the line for "unseen"
MIN_COVAR = 1e-3  # a floor on the spread of each regime (in standardized units), so a regime cannot collapse to one point


@dataclass(frozen=True)
class RegimeModel:
    names: Tuple[str, ...]  # ordered from the lowest average daily return to the highest
    start: np.ndarray  # chance of each regime on the first day
    trans: np.ndarray  # trans[i][j] is the chance of moving from regime i to regime j tomorrow
    means: np.ndarray  # per regime, per feature, in standardized units
    variances: np.ndarray
    center: np.ndarray  # the training averages used to standardize, from the training days only
    scale: np.ndarray
    weights: np.ndarray  # how much of the time the model spends in each regime in the long run
    floor: float  # a day that is less likely than this under the whole model counts as "unseen"

    def typical(self) -> Dict[str, Tuple[float, float]]:
        """Per regime: the average daily return and the usual size of a daily move, both in percent."""
        raw = self.means * self.scale + self.center
        return {name: (float(np.expm1(raw[i, 0]) * 100.0), float(raw[i, 1] * 100.0))
                for i, name in enumerate(self.names)}


@dataclass
class RegimeResult:
    symbol: str
    probabilities: pd.DataFrame  # one column per regime, NaN before the first fit
    regime: pd.Series  # the most likely regime each day, or "unseen" for a day unlike any the model learned from
    unseen: pd.Series  # True for those days
    model: RegimeModel  # the newest fit
    refits: List[pd.Timestamp]
    min_train: int
    refit_every: int


def features(frame: pd.DataFrame) -> pd.DataFrame:
    """Two numbers per day, both from that day and earlier days only: the average daily log return of the last 5
    days, and how big the daily moves of the last 10 days were (their standard deviation). Single day numbers made
    the label flip about 90 times a year on made up data. These make it flip about 14 times a year."""
    daily = np.log(frame["close"] / frame["close"].shift(1))
    out = pd.DataFrame({"ret5": daily.rolling(5).mean(), "vol10": daily.rolling(10).std()}, index=frame.index)
    return out.dropna()


def _require_hmmlearn():
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError as error:
        raise SetupError("The hmmlearn library is not installed. Run: pip install -r algo_lab/requirements_later.txt") \
            from error
    return GaussianHMM


def fit(x: np.ndarray, n_states: int = 3, restarts: int = 5, seed: int = 0) -> RegimeModel:
    """Fit the HMM on past days only. Several random starts are tried and the best one is kept."""
    if n_states not in NAMES_BY_COUNT:
        raise DataError(f"The regime model supports 2 or 3 regimes, not {n_states}.")
    if len(x) < 50 * n_states:
        raise DataError(f"Only {plural(len(x), 'day')} to learn from, which is too few for {n_states} regimes.")
    GaussianHMM = _require_hmmlearn()
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 0, scale, 1.0)
    z = (x - center) / scale
    best, best_score = None, -np.inf
    logging.getLogger("hmmlearn").setLevel(logging.CRITICAL)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for attempt in range(restarts):
            model = GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=200, tol=1e-4,
                                min_covar=MIN_COVAR, random_state=seed + attempt)
            try:
                model.fit(z)
                score = model.score(z)
            except (ValueError, FloatingPointError):
                continue
            if np.isfinite(score) and score > best_score:
                best, best_score = model, score
    if best is None:
        raise DataError("The regime model could not be fit on these days.")
    raw = best.means_ * scale + center  # per regime, in plain units: average 5 day return and usual daily move
    order = np.argsort(raw[:, 0] / raw[:, 1])  # return per unit of wildness, lowest first, so the names keep their meaning
    trans = best.transmat_[np.ix_(order, order)]
    means = best.means_[order]
    variances = np.array([np.diag(c) for c in best.covars_])[order]
    values, vectors = np.linalg.eig(trans.T)  # the long run share of time in each regime
    weights = np.abs(np.real(vectors[:, np.argmax(np.real(values))]))
    weights = weights / weights.sum()
    floor = float(np.percentile(_day_logp(z, means, variances, weights), UNSEEN_PERCENTILE))
    return RegimeModel(names=NAMES_BY_COUNT[n_states], start=best.startprob_[order], trans=trans, means=means,
                       variances=variances, center=center, scale=scale, weights=weights, floor=floor)


def _log_emission(z: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    """For every day, the log chance of that day's numbers under each regime. Shape: days by regimes."""
    diff = z[:, None, :] - means[None, :, :]
    return -0.5 * (np.log(2 * np.pi * variances)[None, :, :] + diff ** 2 / variances[None, :, :]).sum(axis=2)


def _day_logp(z: np.ndarray, means: np.ndarray, variances: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """How likely each day is under the whole model (the regimes mixed by how often each one occurs)."""
    log_e = _log_emission(z, means, variances) + np.log(weights)[None, :]
    top = log_e.max(axis=1)
    return top + np.log(np.exp(log_e - top[:, None]).sum(axis=1))


def unseen_days(model: RegimeModel, x: np.ndarray) -> np.ndarray:
    """True for days that look like nothing the model learned from, for example a crash far worse than any it saw."""
    z = (x - model.center) / model.scale
    return _day_logp(z, model.means, model.variances, model.weights) < model.floor


def forward_filter(model: RegimeModel, x: np.ndarray) -> np.ndarray:
    """Probability of each regime on each day, using that day and earlier days only (the HMM forward algorithm)."""
    z = (x - model.center) / model.scale
    k = len(model.names)
    out = np.empty((len(z), k))
    previous = model.start
    log_emissions = _log_emission(z, model.means, model.variances)
    for t in range(len(z)):
        prior = previous if t == 0 else previous @ model.trans
        log_emission = log_emissions[t]
        weight = prior * np.exp(log_emission - log_emission.max())
        total = weight.sum()
        previous = weight / total if total > 0 else np.full(k, 1.0 / k)
        out[t] = previous
    return out


def walk_forward(frame: pd.DataFrame, symbol: str = "", n_states: int = 3, min_train: int = 500,
                 refit_every: int = 63, restarts: int = 5, seed: int = 0) -> RegimeResult:
    """Refit every `refit_every` days on the days before, and filter forward from there."""
    feats = features(frame)
    x = feats.to_numpy()
    if len(x) < min_train + 1:
        raise DataError(f"{symbol or 'This asset'} has {plural(len(x), 'usable day')}, and the regime model needs "
                        f"at least {min_train + 1} (it learns from {min_train} before it says anything).")
    names = NAMES_BY_COUNT[n_states]
    probs = np.full((len(x), n_states), np.nan)
    unseen = np.zeros(len(x), dtype=bool)
    refits: List[pd.Timestamp] = []
    model = None
    for k in range(min_train, len(x), refit_every):
        model = fit(x[:k], n_states, restarts, seed)
        refits.append(feats.index[k])
        end = min(k + refit_every, len(x))
        probs[k:end] = forward_filter(model, x[:end])[k:end]
        unseen[k:end] = unseen_days(model, x[k:end])
    table = pd.DataFrame(probs, index=feats.index, columns=[f"p_{n}" for n in names])
    known = ~np.isnan(probs[:, 0])
    picked = np.array(names, dtype=object)[np.argmax(np.nan_to_num(probs, nan=-1.0), axis=1)]
    picked = np.where(unseen, "unseen", picked)
    labels = pd.Series(np.where(known, picked, None), index=feats.index, name="regime", dtype=object)
    return RegimeResult(symbol=symbol, probabilities=table, regime=labels,
                        unseen=pd.Series(unseen & known, index=feats.index, name="unseen"), model=model, refits=refits,
                        min_train=min_train, refit_every=refit_every)


# ---------------------------------------------------------------- plain words

def describe(result: RegimeResult) -> Dict[str, object]:
    """The numbers behind the report: today's regime, how long it has lasted, how often the label flips."""
    labels = result.regime.dropna()
    probs = result.probabilities.dropna()
    today = labels.iloc[-1]
    run = 1
    for value in reversed(labels.iloc[:-1].tolist()):
        if value != today:
            break
        run += 1
    flips = int((labels != labels.shift()).sum() - 1)
    share = labels.value_counts(normalize=True).to_dict()
    guess = probs.iloc[-1].idxmax()[2:]
    return {"date": labels.index[-1].date(), "regime": today, "confidence": float(probs.iloc[-1].max()),
            "days_in_regime": run, "flips": flips, "years": len(labels) / 252.0, "share": share, "guess": guess,
            "unseen_share": float(result.unseen.loc[labels.index].mean()),
            "today": {name[2:]: float(v) for name, v in probs.iloc[-1].items()}}


def render_regime(result: RegimeResult) -> str:
    info = describe(result)
    if info["regime"] == "unseen":
        lines = [(f"{result.symbol}: UNSEEN as of {info['date']}. Today's moves are unlike anything the model learned "
                  f"from, so it will not name a regime. Treat it as a storm: smaller sizes and no new trades. "
                  f"It has read unseen for {plural(info['days_in_regime'], 'day')} in a row. "
                  f"Its best guess would be {info['guess']}, but that guess is not trusted.")]
    else:
        lines = [(f"{result.symbol}: {str(info['regime']).upper()} as of {info['date']} "
                  f"({info['confidence'] * 100:.0f} percent sure). It has read {info['regime']} for "
                  f"{plural(info['days_in_regime'], 'day')} in a row.")]
    lines.append("  Chances today: " + ", ".join(f"{name} {p * 100:.0f} percent" for name, p in info["today"].items()))
    lines.append("  What each regime looks like (from the newest fit):")
    for name, (ret, swing) in result.model.typical().items():
        lines.append(f"    {name:<8} average day {ret:+.2f} percent, usual daily move {swing:.2f} percent, "
                     f"{info['share'].get(name, 0.0) * 100:.0f} percent of the days")
    lines.append(f"  Checked over {info['years']:.1f} years that the model had not seen when it labelled each day. "
                 f"The label flipped {plural(info['flips'], 'time')}"
                 f" ({info['flips'] / max(info['years'], 0.1):.0f} a year). "
                 f"{info['unseen_share'] * 100:.1f} percent of those days were unseen.")
    return "\n".join(lines)


FOOTER = ("A regime is a label for how the market has been behaving, not a prediction. The model refits every "
          "few weeks on past days only and never uses a day's future. It is not tested for profit yet; that is Step 4.")
