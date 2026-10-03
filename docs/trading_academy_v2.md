# Trading Academy Crew, version 2

A paper trading training crew for ChatDev. The workflow file is `yaml_instance/trading_academy_v2.yaml`. It never executes real trades and never needs exchange keys.

## What is new

1. **Taught agents.** Each agent carries its own playbook inside its prompt: rules, formulas, and worked examples with real numbers.
   * Mentor: a day card for each of the 14 training days, with key ideas, an analogy, and a practice task.
   * Chart Analyst: a six step review order and a strict confidence scale (LOW, MEDIUM, HIGH).
   * Devil's Advocate: failure buckets, example hard questions, and a quiz bank with 3 questions per day.
   * Risk Manager: the position size math, a leverage check, the risk to reward rule, and five worked examples.
   * Journal Coach: a strict before entry check and a journal row template.
   * XP Judge: the full reward rules, an evidence first method, and worked arithmetic.
   * Security Officer: secret patterns, scam patterns, safe steps if a secret leaks, and worked examples.
   * Session Summary: an answer key for every quiz, grading rules, and a weekly review.
2. **Security Gate first.** Every message passes through a gate that replaces seed phrases, keys, PINs, and passwords with [REDACTED] before any other agent sees them.
3. **The crew remembers.** The Session Summary saves a record of each session. The Mentor reads the last 3 records at the start of the next session, so it recalls your last scoreboard and your repeated mistakes. A scoreboard you paste always wins over memory.
4. **One place to change the model.** Change `MODEL_NAME` at the top of the file. Use a cheaper model while you are testing.

## How to use it

1. Get the file without switching branches:
   ```
   git fetch origin claude/stoic-fermat-lk6rzu
   git checkout origin/claude/stoic-fermat-lk6rzu -- yaml_instance/trading_academy_v2.yaml
   ```
2. Keep your `API_KEY` and `BASE_URL` only in your `.env` file. Never paste them into a chat and never put them in a workflow file.
3. Restart with `make dev`, open the Launch tab, and choose `trading_academy_v2.yaml`.
4. In the prompt box, paste your training day, your scoreboard, and a lesson request or a paper trade idea. A trade idea needs the paper account size, the coin, the direction, entry, stop loss, target, risk percent, and your reason.
5. Read each agent as it works. At the Human Gate write your quiz answers, your journal reflection, and one word for how you feel.

## Memory

* The record file is `WareHouse/trading_academy/session_log.json` on your computer. It keeps the last 12 sessions, and the Mentor reads the latest 3.
* To make the crew forget everything, delete that file.
* `WareHouse/` is ignored by git, so your records and logs stay on your computer. Do not force add them.

## Privacy

The workflow contains no personal details. Everything about the student comes from what you paste at run time. Keep it that way, because this repository may be public.

## Test scenarios

Run each one and check the result. If an agent gets one wrong, copy its output to your mentor, say what was wrong, and add the case as a new worked example in that agent's prompt. A failure that becomes a permanent example is how the crew learns.

1. **Lesson only.** Paste: Training day 1 and your scoreboard. Expect: a Day 1 lesson, a Chart Analyst note that there is no trade, RISK VERDICT: NOT APPLICABLE, three quiz questions from the Devil's Advocate, and quiz XP marked PENDING by the XP Judge. After you answer, the Session Summary grades the quiz and awards 20 XP, plus 10 if you score 80 percent or higher.
2. **Clean trade.** Account 1000, Long BTC, entry 60000, stop 58200, target 65400, risk 1 percent, written before entering. Expect: position size about 0.005556 BTC (about 333 in value), risk to reward 1 to 3, RISK VERDICT: APPROVED, and plus 15 XP for the pre trade log.
3. **Risk too high.** The same trade with risk 5 percent. Expect: RISK VERDICT: VETO, and minus 40 XP from the XP Judge.
4. **No stop loss.** Remove the stop. Expect: VETO, minus 40 XP, and no pre trade log XP.
5. **Position bigger than the account.** Account 1000, entry 2400, stop 2376, risk 2 percent. Expect: position value about 2000, VETO because it needs borrowed money.
6. **Weak risk to reward.** Entry 100, stop 98, target 103. Expect: risk to reward 1 to 1.5, VETO.
7. **Three losses today.** Say you lost three trades in a row today and want another. Expect: VETO and a plain "stop for the day".
8. **Leverage.** Ask about a 10 times leveraged short. Expect: VETO from the Risk Manager and WARNING from the Security Officer.
9. **Scam.** Say a stranger on a chat app wants 0.1 coin sent and promises 1 back, and invites you to a paid signal group. Expect: SECURITY STATUS: WARNING.
10. **Secret leak.** Paste the public fake test phrase "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about". Never test with a real phrase. Expect: the Security Gate replaces it with [REDACTED], no later agent repeats it, and SECURITY STATUS: WARNING.

## Honest limits

* These agents do not learn on their own the way a trained model does. They follow their playbooks and their memory, and they get better when you and your mentor improve those texts.
* The file was checked with ChatDev's own loader and run end to end against a fake model server, which confirms the order of agents, that every playbook reaches its agent, and that memory is written and read back. It was not run against a real model, so expect to tune the wording after your first real sessions.
* Each session makes 9 model calls. Later agents repeat earlier text, so output grows. If costs are too high, use a cheaper model or lower `max_tokens`.
* Education only. Most retail traders lose money, and nothing here is financial advice.
