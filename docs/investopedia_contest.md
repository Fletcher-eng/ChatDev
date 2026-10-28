# Investopedia contest plan (paper money, school and friends)

A school trading competition on Investopedia's stock simulator, played against friends. It is play money, so it fits the academy's paper trading rules. This page keeps the contest rules, the draft plan and the open questions in one place.

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

**Still unknown:** the end date, and whether the winner is picked by total account value or percent return.

## What the rules mean

* **Trades are free and unlimited.** The game never punishes overtrading, one giant position, or penny stocks. Real life does. Results here will flatter risky habits.
* **Short selling is on.** A short means borrowing shares to bet on a fall, and it can lose more than you put in. The academy rule is no shorting, so we skip it.
* **Resets are allowed.** A player can gamble, blow up, reset and try again. The leaderboard therefore rewards luck as much as skill. A reset counts as a failure on our own scoreboard.
* **Prices run 20 minutes late for everyone**, and Quick Sell is believed to be a minimum holding time after buying. Fast trading has no edge here. One decision a day, after the close, on finished bars, suits it.
* **No options, no margin.** QNT is a crypto coin, so it is probably not tradable in this game.

## Draft rules for us (not approved yet)

1. Long only. No shorting, and no stocks under 5 dollars unless you decide otherwise, in writing, before the contest.
2. Risk 1 percent of the account per trade (about $1,000), never more than 2 percent. Shares equal the risk dollars divided by the gap between entry and stop. Example: buy at 50 with a stop at 46. The gap is 4, so 1,000 divided by 4 is 250 shares, which costs $12,500.
3. At most 3 open positions, 25 percent of the account in one stock, 60 percent invested.
4. Entry, stop, target and reason go in the journal before the click.
5. Down 5 percent from the peak: half size. Down 10 percent: no new trades. Down 15 percent: stop and review.
6. Benchmark: SPY bought and held from the start date.

XP follows the academy table: for process, never for rank.

## Who clicks

**You, by hand.** Nothing in this repository logs into Investopedia, stores a password or places an order. There is no official Investopedia API, and the unofficial tools need your password and might break the contest's rules. The lab prepares the thinking. You decide and click.

## Daily routine

* **Evening, 5 minutes, after the US close (4 pm New York):** check the finished bars with `python -m algo_lab look SYMBOLS`, decide together, write the order ticket (ticker, shares, stop, target, reason, dollars at risk).
* **Place the orders** that evening if the game holds them for the next open (test with one order), or in the morning. There is no race at the open.
* **Morning, 2 minutes:** check fills, set stops, log the journal row.
* **Weekly:** compare with SPY and review the three best and three worst trades by process.

## Practice first

Before anything is trusted, the calls are practiced in shadow mode:

1. Each evening, Claude writes 1 to 3 calls in the chat before the open: ticker, buy or skip, stop, target, size, reason, and a confidence range.
2. They are not traded automatically. Anyone who wants to follow one does it by hand, under the rules above.
3. After 30 calls they are scored against simply holding SPY. If they are no better, the answer is no better.

Claude cannot see live prices from its cloud session, so the numbers come from `python -m algo_lab look` on your computer, pasted into the chat.

## Tickers under consideration

* **NEXR** (Nexera Technologies): a Nasdaq penny stock with a very large fall and a history that looks like reverse splits. Under the 5 dollar rule.
* **AIOK** (AI OKTO Corp.): a shipping company that started trading on Nasdaq on 2026-10-09, so it has only a few weeks of history. Nothing can be measured yet.

Both are watch only until `look` shows what they really do.
