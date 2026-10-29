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

The game is called **Nexus Stock Exchange 4** and had 209 players. Its own Game Rules page, read on 2026-10-28 by Claude in Chrome on the user's PC, shows the dates **2026-10-26 to 2027-01-31**, so it has already started and late entry is on. Every setting in the table matched the page, which also shows a margin interest of 0.08 percent. Quick Sell only says 15 minutes with no explanation, so what it means is still a guess (probably a minimum holding time after buying). **Still unknown:** how the winner is picked (total account value or percent return). The page gives no ranking rule.

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

**You decide and you approve every order.** Nothing in this repository logs into Investopedia, stores a password or places an order. There is no official Investopedia API, and the unofficial tools need your password and might break the contest's rules. The lab prepares the thinking. On Day 0 the clicking was done in your own Chrome, already signed in by you, by Claude in Chrome running in a Claude Code window on your PC. It filled each form, showed the preview, and submitted only after you typed yes (you submitted JPM yourself). You can always click by hand instead. This cloud chat is not allowed to message that window, so you paste what I write into it.

## Daily routine

* **Evening, 5 minutes, after the US close (4 pm New York):** check the finished bars with `python -m algo_lab look SYMBOLS`, decide together, write the order ticket (ticker, shares, stop, target, reason, dollars at risk).
* **Place the orders** that evening if the game holds them for the next open (test with one order), or in the morning. There is no race at the open.
* **Morning, 2 minutes:** check fills, set stops, log the journal row.
* **Weekly:** compare with SPY and review the three best and three worst trades by process.

## Practice calls, played in the contest portfolio

The plan was to practice in the app's practice portfolio first. On 2026-10-28 it turned out the game had started on 2026-10-26, and the user chose to place calls 1 and 2 straight into the contest portfolio. So every call now counts in the contest, and everyone can see the holdings. The process is unchanged:

1. **Day 0 (2026-10-28).** No reset was needed, because the contest portfolio was still at $100,000. The benchmark is SPY at $770.80, its price at 10:25 am New York time when both orders were in.
2. **Claude decides, you click.** Each evening Claude writes 1 to 3 calls: ticker, buy or skip, stop, target, size, reason, and a confidence range. You enter them by hand and log each one in the journal before the click.
3. **After 30 calls**, compare the portfolio with simply holding SPY. If the calls are no better, the answer is no better.
4. A reset after Day 0 counts as a failure on the scoreboard.
5. The contest settings were checked against the game's own rules page on 2026-10-28 (see the table above). Nothing differed.

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

### Day 0 record (2026-10-28)

Both calls went into **Nexus Stock Exchange 4**, the school contest. Each order was previewed and approved by the user before it was submitted.

| | JPM | QQQ |
| --- | --- | --- |
| Order placed (New York time) | 10:21 am | 10:24 am |
| Preview price | $335.66 | $721.67 |
| Fill price | $337.66 | $721.64 |
| Shares | 74 | 34 |
| Cost | $24,986.84 | $24,535.76 |
| Stop (fill minus the gap) | $325.59 | $698.78 |
| Target (fill plus twice the gap) | $361.80 | $767.36 |
| Money at risk at the stop | $893.18 | $777.24 |
| Money gained at the target | $1,786.36 | $1,554.48 |
| Close on 2026-10-28 | $339.30 | $725.61 |
| Gain at that close | $121.36 | $134.98 |

Cash $50,477.40, invested $49,522.60 (49.5 percent), money at risk at both stops $1,670.42 (1.67 percent), account value at the 2026-10-28 close $100,256.34. SPY closed that day at $772.31. SPY stayed between $770.23 and $770.90 from 10:25 to 11:00 am, so the exact fill time (the app shows only the date) moves the benchmark by less than 0.1 percent.

What Day 0 taught:

* A market order cannot be cancelled once it is submitted. The page says so.
* Fills took up to about 30 minutes. Both had filled by 10:53 am.
* JPM filled $2.00 (0.6 percent) above its preview price, because the simulator's quotes run 20 minutes late. Both fills stayed inside the 1.5 percent check.
* The first helper brief said practice only, and the helper stopped because the selected portfolio was the public default game (Investopedia Trading Game, about 3.1 million players). The user then picked the school game from the list. Every brief should name the portfolio.
* Stops are not placed yet. Whether this game offers a Stop order type is not confirmed.

## Tickers considered (real data through 2026-10-27)

* **NEXR** (Nexera Technologies): $0.55. Down 69 percent in 20 trading days and 98 percent below its 200 bar average. Five moves bigger than 20 percent in the last 60 bars. Its one year high shows $569.80, which is reverse splits showing through. Cheap and falling, not a bargain. Watch only.
* **AIOK** (AI OKTO Corp.): $13.42. It started trading on 2026-10-09 and closed that first day at $8.70. It slid to about $4 over the next week, then jumped 183 percent in one day (2026-10-23) and ended at $13.42. It has 13 bars of history and 6 moves bigger than 20 percent. A stop can be jumped over, so a loss could be bigger than planned. Watch only. An earlier version of this page said it started near $3.90. That was its lowest price, not its first.

Both fail the warning sign checks in `python -m algo_lab look`.
