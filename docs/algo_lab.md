# Algo Trading Lab (paper trading only)

A lab that detects the market regime with a Hidden Markov Model (HMM), applies a strategy that matches the regime, and shows everything on a regime terminal. It runs on **paper portfolios only**. Nothing in it places a real order, and it needs no exchange key, no wallet and no paid service.

Run every command from the repository folder, for example `python -m algo_lab check`. Add `uv run` in front if you use uv.

## Where the build stands

| Step | What | Status |
| --- | --- | --- |
| 1 | Data loader (the Data Bot) | Built, tested, waiting for your approval |
| 2 | Regime model (HMM) with a forward only filter | Next |
| 3 | The 8 against 8 voting teams | Not started |
| 4 | Backtest with costs, exits and cooldowns | Not started |
| 5 | Regime terminal (Streamlit and Plotly) | Not started |
| Later | Filing Bot on free SEC EDGAR data, Risk Bot, Skeptic and Coach reports | Not started |

Each step stops and waits for a yes before the next one starts.

## The hard rules

1. Paper only. No real orders, no wallet connections, no exchange keys, no seed phrases. Real trading needs the graduation test and a parent or guardian who owns the account.
2. No leverage and no perpetual futures. QNT is looked at as a plain spot price.
3. Risk per trade is 1 to 2 percent of the paper account, with daily and weekly loss limits.
4. Every recommendation passes the Risk Bot veto and your approval before it is logged.
5. Never invent data. If a source fails, say so and stop.
6. The Ledger is for long term storage only.

## Free only

* Prices come from Yahoo Finance through the free `yfinance` library. It is unofficial, so it can break or slow down, and the lab says so plainly when it does.
* Later, investor filings (Form 4 and 13F) come from the SEC's free EDGAR site. Quiver is not used, because it is paid.
* The lab makes no AI calls, so it needs no model API key. Your chat with your mentor is the only place a model is involved.

## The asset list

| Symbol | What it is | Kind |
| --- | --- | --- |
| SPY | A fund that tracks the 500 biggest US companies | ETF |
| QQQ | A fund that tracks the biggest Nasdaq companies | ETF |
| AAPL, MSFT, NVDA | Big technology companies | Stock |
| JPM | A big bank | Stock |
| QNT | Quant, a crypto coin (Yahoo calls it `QNT-USD`) | Crypto |

The list lives in `algo_lab/config.yaml`, so you can add or remove assets without touching code.

About QNT:

* Crypto trades every day, with no market close, so its bars and its clock rules differ from stocks. The config already knows this.
* A coin has no Form 4 or 13F filings, so the filing tools can say nothing about it. For QNT the lab will use price and volume only.
* It is thinner and wilder than the big names, so paper trades on it should assume higher costs and bigger gaps. The default numbers in the briefing were written with stocks in mind and will need their own values for QNT in Step 3.
* I believe Yahoo lists it as `QNT-USD`, but the build environment could not reach Yahoo to check. Your first real fetch will tell us. If the name is wrong, the report says so and nothing is invented.

## Quick start

1. Install the free libraries:
   ```
   pip install -r algo_lab/requirements.txt
   ```
2. Check that the computer is ready. It prints only "ok", "MISSING" or "later" next to each library, never a secret:
   ```
   python -m algo_lab check
   ```
3. Download and check the bars (about a minute):
   ```
   python -m algo_lab fetch
   ```
   Add symbols to fetch only some, for example `python -m algo_lab fetch SPY QNT`.
4. Check the saved bars again at any time, because saved data goes stale:
   ```
   python -m algo_lab health
   ```
5. Practice offline with made up bars:
   ```
   python -m algo_lab demo
   ```

Real bars are saved in `WareHouse/algo_lab/data/`. Made up bars go to `WareHouse/algo_lab/demo/`, are labelled SYNTHETIC, and the real loader refuses to read them. `fetch` also saves `summary.txt`, a copy of the report with no secrets in it, safe to paste into a chat.

## What the Data Bot does

1. Downloads daily bars and sorts them by date.
2. Removes broken rows and says why: duplicate dates, missing prices or volume, prices at or below zero, negative volume, a high below the low, or an open or close outside the day's range. It never repairs a price and never fills a hole.
3. Uses **confirmed bar closes only**. A bar counts 30 minutes after its session ends (16:00 New York time for US stocks and ETFs, midnight UTC for crypto). Today's unfinished bar is ignored.
4. Stops on **stale** data: if the newest finished bar is older than 4 days for US assets (a weekend plus a holiday) or 2 days for crypto.
5. Stops if fewer than 400 bars are left, because the 200 bar average and the regime model need history.
6. Stops if more than 5 percent of the rows had to be removed, because a source that broken is not trusted.
7. Warns about gaps in the history, one day moves bigger than 40 percent (a real crash or a data error), and bars with zero volume.
8. Stops everything if any one asset is in STOP, as the briefing says.
9. Never saves bad data over good data, and checks saved data again every time it is loaded.
10. States the interval and the data lag in every report.

Every number above is in `algo_lab/config.yaml`.

## Words explained

* **Bar:** one candle. Here one bar is one day: open, high, low, close and volume.
* **Adjusted prices:** old prices rewritten after stock splits and dividends, so a 2 for 1 split does not look like a 50 percent crash.
* **Confirmed bar:** a bar whose session is finished. Using an unfinished bar means acting on a price that has not happened yet.
* **Stale:** too old to trust. Trading on last week's prices as if they were today's is how silent mistakes happen.
* **Gap:** missing days in the history.

## Reading the report

The table shows each asset's number of bars, the first and last bar dates, the age (days since the newest finished bar) and the status.

* **OK:** usable.
* **WARN:** usable with care, and the lines under the table say why.
* **STOP:** do not use it. The whole lab stops until it is fixed.

## What was tested, and what was not

* 95 automated tests (`python -m pytest tests/test_algo_lab_config.py tests/test_algo_lab_data.py tests/test_algo_lab_cli.py`), run on both pandas 2.3 and pandas 3.0. They cover the settings file, every cleaning rule, summer and winter close times, unfinished bars, stale and gap rules, saved files, failures, the report, and the commands. They use made up bars and a stand in for Yahoo, so they need no network.
* 13 deliberate breakages were tried, such as ignoring stale data, saving bad data, mixing made up and real data, and keeping unfinished bars. Every one made a test fail.
* A real `fetch` was run where Yahoo is blocked. It stopped cleanly, said why, saved no data and invented none.
* **Not tested:** a successful download from the real Yahoo Finance, because the build environment cannot reach it. The call was checked against the installed yfinance library's parameter names, but the first real run on your computer is the real test. Paste the report if anything looks odd.
* The made up bars come from a generator with three hidden regimes (bear, neutral, bull), so Step 2 can check whether the regime model finds them.

## Files

* `algo_lab/config.yaml`: every number and the asset list.
* `algo_lab/config.py`: reads and checks the settings, with plain error messages.
* `algo_lab/data.py`: download, cleaning, confirmed bars, health checks, saved files, report.
* `algo_lab/synthetic.py`: made up bars for tests and the demo.
* `algo_lab/cli.py`: the commands `check`, `fetch`, `health` and `demo`.
* `algo_lab/requirements.txt`: the free libraries.
