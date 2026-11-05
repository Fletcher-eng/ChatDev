# Investopedia handoff (read this first in a new chat)

Use this page to start a fresh chat that only covers the Investopedia contest. It holds what a new chat needs, so the long history is not required.

## Who and what

* The user is a 15 year old aspiring entrepreneur and engineer. Claude is their mentor, analyst and coach in a supervised, paper trading only academy.
* Style: short answers, plain words, one topic at a time. Never use dashes or hyphens that look machine written. Write "minus 40", "1 to 2" and so on.
* Rules that always apply: be honest, never promise profits, define new terms, say "I don't know". The student decides (Human Gate). No leverage, no margin, no shorting. Never ask for passwords, PINs, seed phrases or API keys. Never suggest hiding anything from a parent or guardian. XP is for process, never profit.

## The contest

* Game: Nexus Stock Exchange 4 on Investopedia, 209 players, 2026-10-26 to 2027-01-31, $100,000 start, no margin, no options, 20 minute price delay, Quick Sell 15 minutes, resets allowed. The ranking rule is unknown.
* The user reset to $100,000 on 2026-11-03. A reset counts as a failure on our own scoreboard.
* The user clicks. Claude cannot see their screen and cannot message their PC. Details are in `docs/investopedia_contest.md`.

## The plan (as of 2026-11-03, before the open)

* Rules: risk 1 percent per trade (half size, 0.5 percent, while the market falls), stop at 2 ATR(14) below the fill, target 2 to 1, at most 6 positions of 10 percent or less, 60 percent invested at most, plain Stop orders that are Good till cancelled, set right after each fill.
* Placeholder stock rule (not a tested edge): above the 200 day average, within 5 percent of the 50 day average, at least 3 percent under the 1 year high, very liquid.
* Bought or to buy now: JPM 36 shares (stop fill minus 12.54), OXY 151 shares (stop fill minus 3.29).
* Spread list: JNJ 37, MSFT 19, plus a tech sleeve of 25 percent at most, bought in 3 steps once SPY closes up 2 days in a row (NVDA 39 shares, GOOGL 24 shares, MSFT 19 shares in total).
* Swing exit: sell half at fill plus 1 gap, move the stop to the fill, sell the rest at fill plus 2 gaps.
* Lottery tickets: $1,000 at most, one at a time, written plan first, stop 25 percent below. None today.
* Never buy: penny stocks, recent reverse splits (NUWE, NEXR, NCPL, CHSN, FTFT), takeover stocks (ULBI), or a stock that already rose 50 percent in a week.

## Lessons so far

* QQQ fell through its stop because no stop order was placed. Always place the stop after the fill.
* AIOK (a spin off with about 4.3 million shares) fell 61 percent in 4 days after a 6 times spike.
* Yahoo can return a blank close for the current day after 8 pm New York. The Data Bot drops that row.
* A reverse split can look like a 1000 percent jump in data and possibly in the game.

## Daily routine

1. After the US close (4 pm New York), the user says "evening check". Claude checks stops and targets and writes the next calls.
2. About 3:45 pm New York, the user says "check". Claude pulls live prices and says whether a trigger has fired.
3. Buy about 10:00 am New York, not at the open.

## Tools in this repository

* Install: `python3 -m venv .venv`, then `.venv/bin/pip install -r algo_lab/requirements.txt`.
* Commands: `python -m algo_lab look TICKER`, `python -m algo_lab board`, `python -m algo_lab fetch`, `python -m algo_lab health`.
* The Trade Board artifact keeps fills in its own database. The practice record is `practice/calls.json`.
* Sizing used in chat: ATR(14) with Wilder smoothing, stop gap = 2 ATR, shares = smaller of the 1 percent risk size and the position cap.

## The bigger build (paused)

The Algo Trading Lab is paper only. Step 1, the Data Bot, and Step 2, the regime model (`python -m algo_lab regime SPY`), are built. Step 2 waits for the user's approval. Next: 8 against 8 voting teams, backtest with costs, regime terminal, then Filing Bot (SEC EDGAR), Risk Bot, Skeptic and Coach. See `docs/algo_lab.md`.
