"""The fourteen analysts, the reference bots, the model clients, and the bet format.

Every analyst must place a bet: a probability and a stake. There is no way to pass.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .indicators import roc, rsi, sma
from .scenario import Scenario

P_MIN, P_MAX = 0.02, 0.98
STAKE_MIN, STAKE_MAX = 0.5, 2.0  # 0.5 to 2 points on a 100 point bankroll: the 1 to 2 percent rule

LENSES = [
    ("trend", "Trend and structure",
     "Judge the direction of the swings on both the candle table and the higher timeframe table: higher highs "
     "and higher lows, lower highs and lower lows, or a range. Ask whether a long setup goes with or against the "
     "higher timeframe trend and whether the structure just broke. Trap: trends end without notice."),
    ("levels", "Support and resistance",
     "Find the nearest swing highs and lows and clusters of wicks. Is the TARGET before an obvious resistance "
     "zone, and is the STOP beyond a believable support zone? Trap: drawing perfect lines in noise."),
    ("volume", "Volume and participation",
     "Compare recent volume with the average. Do rises come with more volume and pullbacks with less? Look for "
     "climax spikes and drying up. Trap: volume shows effort, not direction."),
    ("momentum", "Momentum",
     "Use RSI, the distance from the 20 and 50 candle averages, and the rate of change. Is momentum strong, "
     "fading, or stretched? Trap: indicators lag, and RSI can stay extreme in a strong trend."),
    ("volatility", "Volatility and risk",
     "Look at ATR, the size of recent candles, and whether volatility is expanding or compressing. Is the STOP "
     "inside normal noise, so it is likely to be hit by chance? Is the TARGET a realistic distance to travel in "
     "the horizon given recent movement per candle? Trap: quiet markets can explode."),
    ("candles", "Candle behavior",
     "Read the last 5 to 10 candles: bodies, wicks, rejections, gaps, and follow through. Trap: one candle is a "
     "fact about the past, and patterns are weak evidence."),
    ("outside", "Base rates and costs",
     "Start from the base rate: a 2 to 1 target on a random path is hit first about one time in three, and "
     "costs push the break even higher. Move away from that only for a specific, checkable reason in the data. "
     "Your job is to resist stories and overconfidence."),
]

SIDE_TEXT = {
    "bull": "You are the BULL. You bet that the TARGET is touched before the STOP. Build the strongest honest case "
            "for the setup from your lens.",
    "bear": "You are the BEAR. You bet that the TARGET is NOT touched before the STOP, meaning the stop is hit "
            "first or time runs out. Build the strongest honest case against the setup from your lens.",
}

SYSTEM_PROMPT = """You are one analyst in a paper trading research game called the Arena. Fourteen analysts (7 bulls and 7 bears) look at the same anonymized chart data, and each places a play money bet. Nobody trades real money and nothing here is advice.

Rules:
1. You only know the data you are given. The coin, the date, and the future are hidden. Never claim to know what happens next, and do not guess which coin or period it is.
2. You are scored on calibration and on your bet. Argue your side from your lens, but p_win must be your honest estimate of the chance that the TARGET is touched before the STOP within the horizon. Inflated or deflated probabilities lose points.
3. Remember the baseline: with a 2 to 1 reward to risk and a random price path, the target is hit first about one time in three. Move away from that only for reasons you can name in the data.
4. You MUST place a bet: a probability and a stake between 0.5 and 2.0 points. Use a bigger stake only when you are more confident. You cannot pass.
5. Reply with ONLY one JSON object and no other text: {"p_win": <number between 0.02 and 0.98>, "stake": <number between 0.5 and 2.0>, "case": "<your argument in at most 45 words>", "main_risk": "<what could make you wrong, in at most 20 words>"}
6. Writing style: plain sentences. Do not use hyphens or dashes. Write negative amounts as the word minus."""

RETRY_NOTE = ("Your last reply was not a valid bet. Reply again with ONLY the JSON object containing numeric "
              "p_win and stake, a case, and a main_risk.")


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    side: str       # bull or bear
    lens_key: str
    lens_title: str
    lens_text: str


@dataclass
class Bet:
    agent: str       # agent id
    name: str
    side: str
    lens: str
    p_win: float
    stake: float
    case: str = ""
    risk: str = ""
    kind: str = "llm"      # llm, mock, or reference
    valid: bool = True
    round: int = 1
    note: str = ""


def make_roster() -> List[AgentSpec]:
    roster = []
    for side in ("bull", "bear"):
        for n, (key, title, text) in enumerate(LENSES, start=1):
            roster.append(AgentSpec(f"{side}_{key}", f"{side.capitalize()} {n}, {title}", side, key, title, text))
    return roster


# ---------------------------------------------------------------- bet parsing

def extract_json(text: str) -> Optional[dict]:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:i + 1])
                        if isinstance(value, dict):
                            return value
                    except ValueError:
                        pass
                    break
        start = text.find("{", start + 1)
    return None


def parse_bet(text: str) -> Optional[dict]:
    """Return {'p_win', 'stake', 'case', 'risk', 'note'} or None when no usable bet is in the text."""
    obj = extract_json(text)
    if obj is None:
        p = re.search(r"p_win\"?\s*[:=]\s*([0-9.]+)", text)
        s = re.search(r"stake\"?\s*[:=]\s*([0-9.]+)", text)
        if not (p and s):
            return None
        obj = {"p_win": p.group(1), "stake": s.group(1)}
    try:
        if isinstance(obj["p_win"], bool) or isinstance(obj["stake"], bool):
            return None  # true and false are not numbers here
        p = float(obj["p_win"])
        stake = float(obj["stake"])
    except (KeyError, TypeError, ValueError):
        return None
    if math.isnan(p) or math.isnan(stake):
        return None
    if 1.0 < p <= 100.0:
        p /= 100.0  # the model answered in percent
    if not 0.0 <= p <= 1.0 or stake <= 0:
        return None  # a probability outside 0 to 1, or a stake of nothing, is not a bet
    notes = []
    clamped_p = min(max(p, P_MIN), P_MAX)
    clamped_stake = min(max(stake, STAKE_MIN), STAKE_MAX)
    if clamped_p != p:
        notes.append("probability clamped")
    if clamped_stake != stake:
        notes.append("stake clamped")
    return {
        "p_win": clamped_p, "stake": clamped_stake,
        "case": str(obj.get("case", ""))[:400], "risk": str(obj.get("main_risk", obj.get("risk", "")))[:200],
        "note": ", ".join(notes),
    }


# ---------------------------------------------------------------- clients

@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class UsageMeter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = Usage()

    def add(self, u: Usage) -> None:
        with self._lock:
            self.total.calls += u.calls
            self.total.prompt_tokens += u.prompt_tokens
            self.total.completion_tokens += u.completion_tokens


class OpenAIClient:
    """Talks to any OpenAI compatible endpoint. The key is read from the environment and never printed."""

    kind = "llm"

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 timeout: float = 90.0):
        from openai import OpenAI  # imported here so the offline modes need no key or package setup

        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout)
        self._token_param = "max_tokens"
        self._send_temperature = True

    def chat(self, system: str, user: str, temperature: float, max_tokens: int) -> Tuple[str, Usage]:
        last: Optional[Exception] = None
        for attempt in range(5):
            kwargs = {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                self._token_param: max_tokens,
            }
            if self._send_temperature:
                kwargs["temperature"] = temperature
            try:
                response = self._client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content or ""
                usage = getattr(response, "usage", None)
                return text, Usage(1, getattr(usage, "prompt_tokens", 0) or 0,
                                   getattr(usage, "completion_tokens", 0) or 0)
            except Exception as error:  # provider errors vary, so adapt or retry
                message = str(error).lower()
                last = error
                if "max_tokens" in message and self._token_param == "max_tokens":
                    self._token_param = "max_completion_tokens"
                    continue
                if "temperature" in message and self._send_temperature:
                    self._send_temperature = False
                    continue
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"The model call failed after retries: {type(last).__name__}")


class MockClient:
    """A fake model for demos and tests. It has no skill: its answers come from a hash of the prompt."""

    kind = "mock"
    model = "mock"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def chat(self, system: str, user: str, temperature: float, max_tokens: int) -> Tuple[str, Usage]:
        digest = hashlib.sha256((str(self.seed) + user).encode()).digest()
        p = 0.18 + 0.30 * digest[0] / 255
        if "You are the BULL" in user:
            p += 0.04
        elif "You are the BEAR" in user:
            p -= 0.04
        if "ROUND TWO" in user:
            others = [float(x) for x in re.findall(r"p_win=([0-9.]+)", user)]
            if others:
                p = 0.6 * p + 0.4 * (sum(others) / len(others))  # herding, so debate paths are exercised
        stake = 0.5 + 1.5 * digest[1] / 255
        lens = re.search(r"YOUR LENS: ([^.]+)\.", user)
        reply = {
            "p_win": round(min(max(p, P_MIN), P_MAX), 3), "stake": round(stake, 2),
            "case": f"Mock analyst. The {lens.group(1) if lens else 'chart'} view gives no real edge.",
            "main_risk": "This is a mock analyst with no skill.",
        }
        return json.dumps(reply), Usage(1, len(user) // 4, 40)


# ---------------------------------------------------------------- asking for a bet

def build_user_prompt(snapshot: str, spec: AgentSpec, lessons: Optional[str] = None,
                      table: Optional[str] = None) -> str:
    parts = [snapshot, "", f"YOUR ASSIGNMENT. {SIDE_TEXT[spec.side]}",
             f"YOUR LENS: {spec.lens_title}. {spec.lens_text}"]
    if lessons:
        parts += ["", "LESSONS FROM EARLIER SCENARIOS (use them only if they truly fit this chart):", lessons]
    if table:
        parts += ["", "ROUND TWO. Here are the first round bets of all fourteen analysts:", table,
                  "You may change your probability and stake after reading the other side's best points. "
                  "Do not change just to agree with the crowd."]
    parts += ["", "Reply with ONLY the JSON object."]
    return "\n".join(parts)


def ask_for_bet(client, spec: AgentSpec, user_prompt: str, meter: UsageMeter, temperature: float,
                max_tokens: int, round_no: int = 1) -> Bet:
    text, usage = client.chat(SYSTEM_PROMPT, user_prompt, temperature, max_tokens)
    meter.add(usage)
    parsed = parse_bet(text)
    if parsed is None:
        text, usage = client.chat(SYSTEM_PROMPT, user_prompt + "\n\n" + RETRY_NOTE, 0.0, max_tokens)
        meter.add(usage)
        parsed = parse_bet(text)
    kind = getattr(client, "kind", "llm")
    if parsed is None:
        return Bet(spec.id, spec.name, spec.side, spec.lens_key, 0.0, 0.0, kind=kind, valid=False,
                   round=round_no, note="no valid bet after a retry")
    return Bet(spec.id, spec.name, spec.side, spec.lens_key, parsed["p_win"], parsed["stake"], parsed["case"],
               parsed["risk"], kind, True, round_no, parsed["note"])


def format_table(bets: List[Bet]) -> str:
    lines = []
    for b in bets:
        if b.valid:
            lines.append(f"{b.name}: p_win={b.p_win:.2f}, stake={b.stake:.1f}. Case: {b.case}")
    return "\n".join(lines)


# ---------------------------------------------------------------- reference bots

def reference_bets(sc: Scenario) -> List[Bet]:
    """Simple rule based forecasters. The analysts must beat these to show any skill."""
    s = sc.setup
    base = s.base_rate
    closes = [c.c for c in sc.window]
    s20, s50, last = sma(closes, 20), sma(closes, 50), closes[-1]
    uptrend = last > s50 and s20 > s50
    rng = random.Random(sc.id * 7919)

    def side_for(p: float) -> str:
        return "bull" if p > base else "bear"

    rows = [
        ("ref_base", "Base rate bot", base),
        ("ref_bull", "Always bull", 0.50),
        ("ref_bear", "Always bear", 0.20),
        ("ref_trend", "Trend rule bot", 0.40 if uptrend else 0.27),
        ("ref_rsi", "Overbought rule bot", 0.25 if rsi(closes) > 70 else 0.36 if roc(closes, 10) > 0 else 0.30),
        ("ref_coin", "Coin flip bot", round(rng.uniform(0.2, 0.5), 3)),
    ]
    return [Bet(i, n, side_for(p), "reference", p, 1.0, kind="reference") for i, n, p in rows]
