# Force Strike Lab Project State

Last updated: 2026-04-27 local time after fresh MT5 reruns.

## Goal

Build and research a generic Force Strike strategy that can be tested on multiple symbols and timeframes. The user wants automation, but the rule definition is still being calibrated visually before treating backtest results as reliable.

Supported v1 timeframes:
- M30
- H4
- D1

Current basket:
- EURUSD
- EURGBP
- GBPAUD
- GBPJPY

## Current Strategy Rules

Pattern:
- Bullish bar: close is in or equal to the upper third of its bar range.
- Bearish bar: close is in or equal to the lower third of its bar range.
- Formation length is 3 to 6 total bars, from mother bar through signal bar.
- Bar 2 must be inside or equal to the mother bar range.
- Bullish Force Strike: one-sided break below mother low, then bullish candle closes back inside mother range.
- Bearish Force Strike: one-sided break above mother high, then bearish candle closes back inside mother range.
- If both mother high and mother low break before a valid signal, discard.

Trend/context:
- Bullish setups should be in an uptrend and around the 20/50 SMA retracement zone.
- Bearish setups should be in a downtrend and around the 20/50 SMA retracement zone.
- Current code looks for a 50 SMA trend anchor before the mother bar.
- Bullish anchor must start below the Force Strike structure; bearish anchor must start above it.
- Anchor impulse must be at least 1.5 ATR.
- 50 SMA slope must agree with trade side.
- Recent closes should mostly be on the correct trend side of the 50 SMA.
- Current code also requires some opposite retracement before the mother bar, but this heuristic is still imperfect and needs more visual review.
- Experimental `swing_retrace_v1` context adds a stricter definition:
  - Bullish: prior upside swing above the 50 SMA, then downside close retracement before the mother bar.
  - Bearish: prior downside swing below the 50 SMA, then upside close retracement before the mother bar.
  - It also requires a minimum ATR-normalized 50 SMA slope to block flat-trend examples.

Entry/exit:
- Primary entry is next bar open after the signal if risk is <= 1.25 ATR and next open remains inside mother range.
- If next-open risk is too wide, code calculates a risk-capped retracement entry and waits for fill.
- Setup is cancelled if price reaches +1R from ideal entry before filling.
- Stops tested: structure, ATR, and wider-of-structure-or-ATR.
- Targets tested: 1.0R, 1.25R, 1.5R, 2.0R, 2.5R.
- Exit is TP or SL only. End-of-data closes are flagged.
- Conservative same-bar handling: if TP and SL both touch, SL wins.

## Latest Research Results

M30 latest:
- Report: `reports/force_strike/M30/latest/report.md`
- Timestamp folder: `reports/force_strike/M30/20260427_142301`
- Best listed candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Full net R: -241.89
- Holdout net R: -27.48
- Full PF: about 0.66
- Trades: 964
- Takeaway: not profitable; too many weak/noisy signals.

H4 latest:
- Report: `reports/force_strike/H4/latest/report.md`
- Timestamp folder: `reports/force_strike/H4/20260427_143108`
- Best holdout-ranked candidate: `fs_structure_tp2p0_sma0p0_risk1p25`
- Full net R: -12.25
- Holdout net R: +2.38
- Full PF: about 0.90
- Holdout PF: about 1.13
- Trades: 173
- Max drawdown: 16.17R
- Best full-sample candidate: `fs_atr_tp2p5_sma0p0_risk1p25`
- Best full-sample full net R: +2.01
- Best full-sample holdout net R: +0.53
- Best full-sample PF: about 1.01
- Best full-sample trades: 196
- Takeaway: H4 now has enough signals after the fresh rerun, but not a robust standalone edge. Simple SMA context and raw no-context tests were negative, and relaxed/tightened strict-gate tests did not produce stable full plus holdout strength. H4 should be treated as a visual validation candidate or execution/confirmation layer, not a live standalone strategy.

D1 latest:
- Report: `reports/force_strike/D1/latest/report.md`
- Timestamp folder: `reports/force_strike/D1/20260427_143147`
- Best listed candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Full net R: +20.14
- Holdout net R: +8.31
- Full PF: about 1.66
- Holdout PF: about 2.64
- Trades: 64
- Max drawdown: 5.61R
- Frequency: about 0.02 trades/day, roughly 6 trades/year across the 4-pair basket.
- Per-symbol for top D1 candidate:
  - EURUSD: +4.29R, 18 trades
  - EURGBP: -3.12R, 8 trades
  - GBPAUD: +12.31R, 15 trades
  - GBPJPY: +6.66R, 23 trades
- Takeaway: first timeframe with positive result, but low frequency and must be visually validated.

Swing retrace v1 experiment:
- Configs:
  - `configs/d1_forex_basket_swing_retrace_v1.json`
  - `configs/h4_forex_basket_swing_retrace_v1.json`
- Reports:
  - D1: `reports/force_strike_experiments/swing_retrace_v1/D1/20260427_143147/report.md`
  - H4: `reports/force_strike_experiments/swing_retrace_v1/H4/20260427_143241/report.md`
- D1 top candidate remained `fs_atr_tp1p5_sma0p0_risk1p25`.
  - Full net R: +19.90 vs baseline +20.14.
  - Holdout net R: +7.83 vs baseline +8.31.
  - Trades: 47 vs baseline 64.
  - Max drawdown: 3.03R vs baseline 5.61R.
  - Takeaway: quality filter is plausible but not a clear upgrade; it cuts trades and drawdown while slightly reducing net R.
- H4 top candidate remained `fs_structure_tp2p0_sma0p0_risk1p25`.
  - Full net R: -4.89 vs baseline -12.25.
  - Holdout net R: +6.74 vs baseline +2.38.
  - Trades: 126 vs baseline 173.
  - Max drawdown: 11.03R vs baseline 16.17R.
  - Takeaway: improved filter quality, but full sample is still negative and symbol concentration is too high. H4 is still not standalone-live quality.

D1 G8 majors plus crosses swing retrace v1 expansion:
- Config: `configs/d1_forex_g8_swing_retrace_v1.json`
- Report: `reports/force_strike_experiments/swing_retrace_v1_g8/D1/latest/report.md`
- Generated breakdown: `reports/force_strike_experiments/swing_retrace_v1_g8/D1/latest/breakdown.md`
- Latest timestamp folder: `reports/force_strike_experiments/swing_retrace_v1_g8/D1/20260427_142612`
- Universe: 28 D1 pairs from EUR, GBP, AUD, NZD, USD, CAD, CHF, and JPY.
- Top holdout/full candidate: `fs_wider_tp1p5_sma0p0_risk1p25`.
  - Full net R: +11.27, PF 1.07, 289 trades, max drawdown 16.16R.
  - Discovery net R: +8.59.
  - Selection net R: -3.70.
  - Holdout net R: +6.38, holdout PF 1.17, holdout max drawdown 12.70R.
  - Non-USD crosses: +17.25R, 209 trades, PF 1.14.
  - USD majors: -5.98R, 80 trades, PF 0.88.
- Takeaway: broad expansion weakens the D1 result. Positive contribution is concentrated in crosses, especially GBP crosses; USD majors should not be included blindly.

D1 G8 majors plus crosses legacy-context check:
- Purpose: test the pre-`swing_retrace_v1` context behavior on the same 28-pair D1 G8 universe.
- Config: `configs/d1_forex_g8_legacy_context.json`
- Report: `reports/force_strike_experiments/legacy_context_g8/D1/latest/report.md`
- Latest timestamp folder: `reports/force_strike_experiments/legacy_context_g8/D1/20260427_142900`
- Top holdout candidate: `fs_atr_tp1p25_sma0p0_risk1p25` and equivalent SMA-buffer variants.
  - Full net R: -17.85, PF 0.94, 482 trades, max drawdown 37.59R.
  - Discovery net R: -17.91.
  - Selection net R: -2.93.
  - Holdout net R: +2.99, holdout PF 1.05, holdout max drawdown 16.75R.
  - Non-USD crosses: -5.40R, 352 trades.
  - USD majors: -12.45R, 130 trades.
  - Takeaway: the old legacy context does not hold up on the broad G8 D1 universe. The stricter `swing_retrace_v1` filter materially improves full-sample result, drawdown, and trade count, though the edge is still weak and uneven.

Fresh rerun data coverage notes:
- Unit tests: 23 passed.
- M30 baseline data ends `2026-04-27 14:00:00+00:00` across the 4-pair basket.
- H4 baseline data ends `2026-04-27 12:00:00+00:00` across the 4-pair basket.
- D1 G8 data ends `2026-04-27 00:00:00+00:00` across all 28 symbols.

## Visual Review Pages

M30 labeling:
- `reports/force_strike/M30/labeling/latest/index.html`

D1 labeling:
- `reports/force_strike/D1/labeling/latest/index.html`

H4 labeling:
- `reports/force_strike/H4/labeling/latest/index.html`

D1 top candidate trade review:
- `reports/force_strike/D1/latest/review/fs_atr_tp1p5_sma0p0_risk1p25/index.html`

H4 trade reviews:
- Holdout-ranked candidate: `reports/force_strike/H4/latest/review/fs_structure_tp2p0_sma0p0_risk1p25/index.html`
- Best full-sample candidate: `reports/force_strike/H4/latest/review/fs_atr_tp2p5_sma0p0_risk1p25/index.html`

## TradingView Indicator

- Pine script: `tradingview/force_strike_signal.pine`
- Usage note: `tradingview/README.md`
- Purpose: clean client-facing chart signal and optional diagnostics.
- Boundary: TradingView evaluates the rule family on TradingView chart candles. Python/MT5 evaluates the rule family on MT5 candles loaded into the lab. Both can be correct for their own chart stream, so exact bar-by-bar parity is only expected when candle data is identical.

## Current Configs

- `configs/m30_forex_basket.json`
- `configs/h4_forex_basket.json`
- `configs/d1_forex_basket.json`
- `configs/h4_forex_basket_swing_retrace_v1.json`
- `configs/d1_forex_basket_swing_retrace_v1.json`
- `configs/d1_forex_majors_swing_retrace_v1.json`
- `configs/d1_forex_g8_swing_retrace_v1.json`
- `configs/d1_forex_g8_legacy_context.json`

The original M30/H4/D1 configs remain the legacy fallback. The `swing_retrace_v1` configs are isolated experiments and write to `reports/force_strike_experiments/swing_retrace_v1`.

## Useful Commands

Run tests:

```powershell
.\venv\Scripts\python -m unittest discover force_strike_lab\tests
```

Run M30 research and pull MT5 data:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\m30_forex_basket.json --pull
```

Run H4 research and pull MT5 data:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\h4_forex_basket.json --pull
```

Run D1 research and pull MT5 data:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_basket.json --pull
```

Run swing retrace v1 experiments without touching baseline reports:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_basket_swing_retrace_v1.json
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\h4_forex_basket_swing_retrace_v1.json
```

Run D1 G8 majors plus crosses experiment:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_g8_swing_retrace_v1.json --pull
```

Export D1 labeling page:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\export_pattern_labeling.py --config force_strike_lab\configs\d1_forex_basket.json --max-per-symbol 20 --current-per-symbol 6 --bars-before 120 --bars-after 40 --seed 11
```

Export D1 top-candidate trade review:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\export_trade_review.py --report-dir force_strike_lab\reports\force_strike\D1\latest --candidate-id fs_atr_tp1p5_sma0p0_risk1p25 --bars-before 120 --bars-after 40 --limit 80 --sort time
```

## Next Best Work

1. Visually review the D1 labeling page and label valid/invalid examples.
2. Focus on whether D1 accepted setups really match the intended Force Strike concept.
3. Review the H4 labeling and trade-review pages only to learn whether H4 has a useful execution/confirmation role; current H4 numbers do not justify standalone use.
4. If D1 labels mostly match, inspect the D1 trade review page to see whether winners/losers differ by entry structure, stop model, width, or trend maturity.
5. Use the `swing_retrace_v1` Pine/MT5 behavior to review examples where prior impulse exists but close retracement is missing.
6. After D1 is validated, test broader baskets and possibly add M30/H4 only as lower-timeframe execution layers rather than standalone signal timeframes.

## Known Open Issue

The hardest rule to encode is the discretionary visual idea:

"There must be a clear prior trend impulse, then an opposite retracement into the 20/50 SMA area, then the Force Strike forms."

The current code approximates this, but examples like sideways price action or tiny local retracements may still slip through. User labels are the most useful way to sharpen this rule.
