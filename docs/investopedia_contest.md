# Investopedia contest plan (paper money, school and friends)

A school trading competition on Investopedia's stock simulator, played against friends. It is play money, so it fits the academy's paper trading rules. This page keeps the contest rules, the draft plan, the practice record and the open questions in one place.

## The game's rules (pasted on 2026-10-28)

| Setting | Value |
| --- | --- |
| Starting cash | $100,000 |
| Margin trading | No |
| Short selling | Yes |
| Option trading | No |
| Late entry | Yes |
| Portfolio viewing | Yes (everyone can see everyone's holdings) |
| Portfolio resetting | Yes |
| Market delay | 20 minutes |
| Quick Sell | 15 minutes |
| Commission, daily volume cap, minimum price, diversification, cash interest | All disabled |
| Margin interest | 0.08 percent (does not matter, margin is off) |

The game has not started yet. **Still unknown:** the start and end dates, and whether the winner is picked by total account value or percent return.

## What the rules mean

* **Trades are free and unlimited.** The game never punishes overtrading, one giant position, or penny stocks. Real life does. Results here will flatter risky habits.
* **Short selling is on.** A short means borrowing shares to bet on a fall, and it can lose more than you put in. The academy rule is no shorting, so we skip it.
* **Resets are allowed.** A player can gamble, blow up, reset and try again. The leaderboard therefore rewards luck as much as skill. A reset counts as a failure on our own scoreboard.
* **Prices run 20 minutes late for everyone**, and Quick Sell is believed to be a minimum holding time after buying. Fast trading has no edge here. One decision a day, after the close, on finished bars, suits it.
* **No options, no margin.** QNT is a crypto coin, so it is probably not tradable in this game.

## Draft rules for us (not approved yet)

1. Long only. No shorting, and no stocks under 5 dollars unless you decide otherwise, in writing, before the contest.
2. Risk 1 percent of the account per trade (about $1,000), never more than 2 percent. Shares equal the risk dollars divided by the gap between entry and stop.
3. The stop sits 2 ATR below the entry. ATR(14) is the typical daily swing of the stock over the last 14 days. The target is twice the stop distance (a 2 to 1 reward to risk).
4. At most 3 open positions, 25 percent of the account in one stock, 60 percent invested.
5. Entry, stop, target and reason go in the journal before the click.
6. Down 5 percent from the peak: half size. Down 10 percent: no new trades. Down 15 percent: stop and review.
7. Benchmark: SPY bought and held from the start date.

XP follows the academy table: for process, never for rank.

## Who clicks

**You, by hand.** Nothing in this repository logs into Investopedia, stores a password or places an order. There is no official Investopedia API, and the unofficial tools need your password and might break the contest's rules. The lab prepares the thinking. You decide and click.

## Daily routine

* **Evening, 5 minutes, after the US close (4 pm New York):** check the finished bars with `python -m algo_lab look SYMBOLS`, decide together, write the order ticket (ticker, shares, stop, target, reason, dollars at risk).
* **Place the orders** that evening if the game holds them for the next open (test with one order), or in the morning. There is no race at the open.
* **Morning, 2 minutes:** check fills, set stops, log the journal row.
* **Weekly:** compare with SPY and review the three best and three worst trades by process.

## Practice first (the app's practice portfolio)

The game has not started, and the app has a practice mode. Before anything is trusted, the calls are practiced there:

1. **Day 0.** Reset the practice portfolio to $100,000 once, and write down SPY's price when the first order fills. That is the benchmark.
2. **Claude decides, you click.** Each evening Claude writes 1 to 3 calls: ticker, buy or skip, stop, target, size, reason, and a confidence range. You enter them by hand and log each one in the journal before the click.
3. **After 30 calls**, or when the game starts, compare the practice portfolio with simply holding SPY. If the calls are no better, the answer is no better.
4. A reset after Day 0 counts as a failure on the scoreboard.
5. Check that the practice portfolio has the same settings as the contest (no margin, no options, the same delay). Note any difference.

Claude's cloud session could reach Yahoo on 2026-10-28, so it can run `python -m algo_lab look` itself. That can change, so the same command also works on your own computer.

### Practice calls 1 and 2 (written 2026-10-28 before the open, from the close of 2026-10-27)

Buy at market at the open. The rule used was a placeholder to practice the process, not a tested edge: above the 200 bar average, within 5 percent of the 50 bar average, at least 3 percent under the one year high, very liquid. Four names passed (QQQ, MSFT, NVDA, JPM). JPM and QQQ were picked so the two are different bets.

| | JPM | QQQ |
| --- | --- | --- |
| Close on 2026-10-27 | $335.79 | $721.25 |
| ATR(14), the typical daily swing | $6.04 | $11.43 |
| Shares (the smaller of the 1 percent risk size and the 25 percent cap) | 74 | 34 |
| Stop | fill price minus $12.07 | fill price minus $22.86 |
| Target (2 to 1) | fill price plus $24.14 | fill price plus $45.72 |
| Money at risk | about $890 | about $780 |
| Position | about $24,800 | about $24,500 |

Together: 49 percent invested, two of the three position slots, about 1.7 percent of the account at risk. The honest odds that a target is hit before its stop are about 30 to 40 percent each, and break even is 33 percent, so one or both losing is normal. If a fill lands far from the close above, the numbers are redone.

### Optional call 3 (MSFT), only if a third position is wanted

Buy about 19 shares at market at the open (about $10,100). Stop at the fill price minus $21.89, target at the fill price plus $43.78, about $416 at risk. It is smaller than the other two so the account stays under the 60 percent invested cap: 59 percent invested and about 2.1 percent of the account at risk across all three.

## Tickers considered (real data through 2026-10-27)

* **NEXR** (Nexera Technologies): $0.55. Down 69 percent in 20 trading days and 98 percent below its 200 bar average. Five moves bigger than 20 percent in the last 60 bars. Its one year high shows $569.80, which is reverse splits showing through. Cheap and falling, not a bargain. Watch only.
* **AIOK** (AI OKTO Corp.): $13.42. It started trading on 2026-10-09 and closed that first day at $8.70. It slid to about $4 over the next week, then jumped 183 percent in one day (2026-10-23) and ended at $13.42. It has 13 bars of history and 6 moves bigger than 20 percent. A stop can be jumped over, so a loss could be bigger than planned. Watch only. An earlier version of this page said it started near $3.90. That was its lowest price, not its first.

Both fail the warning sign checks in `python -m algo_lab look`.
