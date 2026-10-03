# Trading Arena: 7 bulls against 7 bears

A research game for AI analysts, built for the paper trading academy. Seven bull analysts and seven bear analysts look at the same hidden history, each one places a play money bet, then the future is revealed one candle at a time and every bet is scored. It never trades real money, never needs an exchange key, and never touches TradingView.

Run it from the repository folder with the same Python environment you use for ChatDev, for example `uv run python -m trading_arena demo`. The commands below are written as `python -m trading_arena`, so add `uv run` in front if you use uv.

## What it is, and what it is not

* It is a way to find out whether an AI analyst has any real skill, or whether it only sounds clever.
* It is **not** a trading bot and it is not advice. Nothing here places an order.
* It does **not** automate TradingView. TradingView's terms do not allow scripts, scraping or bots to copy its data. You check results on TradingView yourself, by eye, using its Replay button (see below).

## How one round works

1. The Arena picks a past moment from the candle data. Everything after that moment is hidden.
2. The same long trade idea is fixed for everybody: the stop sits 1.5 ATR below the last close, the target sits at twice that distance above (a reward to risk of 2 to 1), and the trade has 20 daily candles to finish. The trade enters at the next candle's open, and costs of 0.10 percent fee and 0.05 percent slippage per side are charged.
3. The question is always the same: **does the target get touched before the stop?** If one candle touches both, the stop counts first. If neither is touched in time, the answer is no.
4. Fourteen analysts get the chart. Each one has a side and a lens. The seven lenses are Trend and structure, Support and resistance, Volume and participation, Momentum, Volatility and risk, Candle behavior, and Base rates and costs. Every lens has one bull and one bear, so each lens is a small debate.
5. Every analyst must bet. A bet is a probability from 0.02 to 0.98 that the target comes first, plus a stake from 0.5 to 2.0 points. Passing is not allowed. A missed or unreadable bet costs 1 point.
6. The future is revealed and settled. **Bulls bet the target comes first. Bears bet it does not.** The program rule of no shorting still holds, because both sides only bet on the outcome of the same long setup.

### The points

With a 2 to 1 reward to risk and a stake of 1.0:

* Target first: a bull wins 2.0 points and a bear loses 2.0.
* Stop first: a bull loses 1.0 and a bear wins 1.0.
* Time runs out: the trade is marked at its exit price, limited to between minus 1 and plus 2 per point staked, and the bear gets the opposite.

A bull and a bear with the same stake always have opposite results, so the game itself is zero sum. A bear is right more often because the target is the harder outcome, but a bear only wins 1 point where a bull wins 2, so compare points and not hit rates.

### Why the bets cannot cheat

* The analysts only see scaled numbers (the last close is 100), with no dates, no coin name and no future. Only one function builds that text, and it only reads the visible chart and the setup.
* A test poisons the hidden future with absurd prices and checks that not one word the analysts read changes, and that their bets stay identical.
* The learning test splits time in order. A coach reads the first half and writes lessons, and the lessons are tried on the second half, next to a control run with no lessons. Decision points are spaced so every training result is finished before the first test decision.

## Quick start

1. **Free tour with made up prices.** No key and no cost:
   ```
   python -m trading_arena demo
   ```
   It prints a path to `replay.html`. Open that page in a browser and press Play.
2. **Get real candles.** On your own computer, with internet access:
   ```
   python -m trading_arena fetch --pair btcusd
   ```
   This downloads daily candles from a public exchange feed (no key needed) into `WareHouse/arena/data/`. Other choices are `--source coinbase` or `--source binance`. If your network blocks those sites, use your own file instead: a CSV with a header and the columns time, open, high, low, close, volume. Time can be a unix timestamp or a date.
3. **Run it for free with mock analysts** to see the whole flow on real candles:
   ```
   python -m trading_arena run --csv WareHouse/arena/data/btcusd_1d.csv --agents mock --scenarios 30
   ```
4. **Run it with a real model.** Put `API_KEY` (and if needed `BASE_URL` and `MODEL_NAME`) in your `.env` file, the same one ChatDev uses. Never type them into a chat and never save them in a file that goes on GitHub.
   ```
   python -m trading_arena run --csv WareHouse/arena/data/btcusd_1d.csv --scenarios 30
   ```
   It prints the number of model calls it plans to make and waits for you to type YES.
5. **Optional extras:**
   * `--rounds 2` adds a debate round. Each analyst sees all fourteen first bets and may change their mind.
   * `--learn` makes a coach write lessons from the first half and tests them on the second half.
   * `--price-in 2 --price-out 8` prints a cost estimate (dollars per million tokens, from your provider).
   * `python -m trading_arena report --run WareHouse/arena/<folder>` rebuilds every report from a saved run.

A run folder holds `replay.html` (watch it), `report.md` (read it), `bets.csv`, `scenarios.csv` and `run.json` (every number and every bet, kept as receipts).

## Controlling the cost

* Each scenario costs 14 model calls per round. A run of 30 scenarios with one round is 420 calls. With a debate round it is 840. With `--learn` it is about half as many again, because the second half is run twice, once without lessons and once with.
* The estimate is printed before anything is spent. `--max-calls` (default 3000) refuses a run that is bigger than you meant.
* The model's price is unknown to the program, so it will not guess one. Check your provider, and set a spending limit in its dashboard.
* A model run spends API credits. Ask whoever pays for the key before you start.
* Test with `--agents mock` first. It is free.

## Checking a result on TradingView, by eye

1. Open `replay.html` and pick a scenario. The box called Check it yourself on TradingView names the symbol (for example BITSTAMP:BTCUSD), the timeframe and the date of the decision candle.
2. On TradingView open that symbol on that timeframe. Click Replay in the top toolbar, choose Select bar, and click the candle with that date.
3. Press play and watch the next 20 candles. The candle you clicked is the last one the analysts saw, and the trade enters at the open of the first candle that Replay reveals after it. See whether the stop or the target comes first.
4. Compare with the result in the Arena.

Notes:

* TradingView's Replay on the free plan is reportedly limited to daily and longer candles, so the Arena defaults to daily candles. Check what your plan allows.
* TradingView's candles can differ a little from the exchange feed the Arena used, mostly in volume and sometimes in highs and lows. A tiny mismatch is normal. A big one means something is wrong, so tell your mentor.
* With made up prices (the demo) there is nothing to check.

## Reading the report

* **Brier score.** For every bet, take the probability minus what happened (1 if the target came first, otherwise 0), and square it. Lower is better. A bot that always says the fair odds probability sets the bar.
* **Skill.** One minus your Brier divided by the base rate bot's Brier. Zero means no better than that bot. Anything above zero is only interesting if the 95 percent range excludes zero.
* **Calibration.** When the crowd said 40 percent, did the target really come first about 40 percent of the time?
* **Effective opinions.** Fourteen copies of one model tend to agree. The report estimates how many independent opinions you really have, and it is usually far fewer than fourteen.
* **Follow the crowd.** The report asks what would have happened if you took the trade only when the crowd's probability beat the cost adjusted break even, with a range that shows how much luck could explain.
* **Reference bots.** Six simple rules (base rate, always bull, always bear, a trend rule, an overbought rule, and a coin flip) are scored on the same scenarios. An analyst that cannot beat them shows no skill.
* **The verdict.** Under 30 scenarios it only says the sample is far too small. Past that it says whether the crowd beat the base rate bot beyond what luck usually explains, and it still calls a good result a clue and not proof.

## Honest limits

* Under 100 scenarios, treat every ranking as luck. Even with many, a good result can be a fluke.
* Most real traders lose money, and the costs alone make a coin flip lose a little. Do not expect a language model to beat a base rate bot after costs. Finding out whether it can is the whole point.
* Copies of one model are highly correlated, so fourteen analysts are not fourteen independent opinions.
* The analysts never see dates or the coin, but a language model may still half remember real history. Use data from after the model's training period when you can, and treat a result that looks too good as a possible leak or bug first.
* Costs are an assumption. A real account may pay more or less.
* The prices come from a public exchange feed or your own file. They are not TradingView data.
* A debate round often just pulls everyone toward the crowd. The report measures whether it helped.
* Lessons from a coach, or from a human, can fit past noise. That is why they are tested on later scenarios against a control run.

## What was tested, and what was not

* The code has 139 automated tests (`python -m pytest tests/test_trading_arena_core.py tests/test_trading_arena_scoring.py tests/test_trading_arena_report_cli.py`). They cover the indicators, the settlement rules (gaps, same candle touches, slippage, timeouts), the exchange parsers with fake responses, bet parsing, the runner, every scoring formula, the learning loop, the reports and the command line. The tests use mock analysts, made up prices and stand in model clients, so they need no network and no key.
* The replay page was checked in a real browser at desktop and phone sizes, in light and dark mode, including hostile text in a model's answer.
* **Not tested here:** a download from a real exchange (the build environment blocked those sites) and a run with a real language model. Expect to tune after your first real run, and read the first report with a mentor.
* The mock analysts have no skill on purpose. A test checks that they do not look skilled, which guards the scoring against flattering noise.

## Files

* `trading_arena/data.py`: candle files, exchange downloads, made up prices.
* `trading_arena/scenario.py`: the fixed setup, the hidden future, and the only text the analysts see.
* `trading_arena/settle.py`: replays the future candle by candle and pays the bets.
* `trading_arena/agents.py`: the fourteen analysts, bet parsing, model clients, the six reference bots.
* `trading_arena/arena.py`: runs the scenarios, one or two rounds.
* `trading_arena/scoring.py`: every number in the report, each with its luck range.
* `trading_arena/learn.py`: the coach and the lessons test.
* `trading_arena/report.py` and `replay_template.html`: the report, the CSV files and the replay page.
* `trading_arena/cli.py`: the commands `demo`, `fetch`, `run` and `report`.
