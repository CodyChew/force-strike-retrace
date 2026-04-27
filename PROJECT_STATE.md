# Force Strike Lab Project State

Last updated: 2026-04-28 local time after resetting the working baseline to legacy D1.

## Goal

Build and research a generic Force Strike strategy that can be tested on multiple symbols and timeframes. The current priority is clarity and enough trade frequency, so the working strategy is reset to the simpler legacy logic before adding more heuristics.

## Current Baseline

- Config: `configs/d1_current_legacy_filtered.json`
- Mode: `legacy`
- Timeframe: D1
- Candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Stop model: ATR
- Target: 1.5R
- SMA touch buffer: 0.0 ATR
- Max entry risk: 1.25 ATR
- Symbols: `GBPAUD`, `AUDUSD`, `GBPCHF`, `GBPJPY`, `AUDCHF`, `AUDNZD`, `EURUSD`, `USDCHF`, `USDJPY`, `AUDCAD`, `GBPNZD`, `NZDJPY`, `CHFJPY`, `EURJPY`

Latest saved result for this fixed basket:

- 231 trades.
- Full net R: +67.76R.
- Profit factor: 1.61.
- Max drawdown: 6.75R using the repo report metric.
- Discovery net R: +26.30R.
- Selection net R: +19.87R.
- Holdout net R: +21.59R.
- Approximate frequency: 23 to 24 trades per year across the basket.

Selection risk: the ticker list comes from historical positive contributors in the D1 G8 legacy rerun. This is suitable for fixed-list paper testing, not proof of future edge.

## Current Strategy Rules

Pattern:

- Formation length is 3 to 6 total bars, from mother bar through signal bar.
- Bar 2 must be inside or equal to the mother bar range.
- Bullish Force Strike: one-sided break below mother low, then a bullish signal candle closes back inside the mother range.
- Bearish Force Strike: one-sided break above mother high, then a bearish signal candle closes back inside the mother range.
- If both mother high and mother low break before a valid signal, discard.

Legacy trend/context:

- Setup must form around the 20/50 SMA retracement zone.
- Code finds a 50 SMA trend anchor before the mother bar.
- Bullish anchor must start below the Force Strike structure; bearish anchor must start above it.
- Anchor impulse must be at least 1.5 ATR.
- 50 SMA slope must agree with the trade side.
- Recent closes should mostly be on the correct trend side of the 50 SMA.
- Anchor efficiency, pre-mother retracement size, and recent progress checks must pass.

Entry/exit:

- Primary entry is next bar open after the signal if risk is <= 1.25 ATR and next open remains inside the mother range.
- If next-open risk is too wide, code calculates a risk-capped retracement entry and waits for fill.
- Setup is cancelled if price reaches +1R from ideal entry before filling.
- Current baseline uses ATR stop only.
- Current baseline target is 1.5R.
- Exit is TP or SL only. End-of-data closes are flagged.
- Conservative same-bar handling: if TP and SL both touch, SL wins.

## Research Archive

M30 latest:

- Report: `reports/force_strike/M30/latest/report.md`
- Best listed candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Full net R: -241.89
- Trades: 964
- Takeaway: rejected for now. Too noisy.

H4 latest:

- Report: `reports/force_strike/H4/latest/report.md`
- Best holdout-ranked candidate: `fs_structure_tp2p0_sma0p0_risk1p25`
- Full net R: -12.25
- Trades: 173
- Takeaway: not standalone-live quality.

D1 original 4-pair baseline:

- Report: `reports/force_strike/D1/latest/report.md`
- Best listed candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Full net R: +20.14
- Trades: 64
- Max drawdown: 5.61R
- Takeaway: first timeframe with positive result, but too low-frequency for the current goal.

D1 G8 legacy all-pair check:

- Config: `configs/d1_forex_g8_legacy_context.json`
- Top holdout candidate in the broad report: `fs_atr_tp1p25_sma0p0_risk1p25`
- Full net R: -17.85
- Trades: 482
- Max drawdown: 37.59R
- Takeaway: do not trade broad G8 raw. Symbol filtering is doing important work.

D1 G8 swing/retrace experiment:

- Config: `configs/d1_forex_g8_swing_retrace_v1.json`
- Top broad candidate: `fs_wider_tp1p5_sma0p0_risk1p25`
- Full net R: +11.27
- Trades: 289
- Max drawdown: 16.16R
- Takeaway: better broad filter than raw legacy, but not the current baseline because it reduces trade count and does not beat the filtered legacy result.

Useful saved challenger baskets:

- Legacy TP 1.25R filtered basket: +62.67R, PF 1.61, 235 trades, max DD 5.08R.
- Expanded swing/retrace TP 2.0R basket: +55.42R, PF 1.72, 143 trades, max DD 7.19R.
- Conservative swing/retrace TP 2.0R core: +33.31R, PF 2.64, 47 trades, max DD 3.05R.

## Visual Review Pages

- Dashboard: `docs/index.html`
- Strategy guide: `docs/strategy.html`
- Recommendation note: `docs/ticker_strategy_recommendation.md`
- Local dashboard mirror: `reports/findings_dashboard/index.html`
- D1 labeling page: `reports/force_strike/D1/labeling/latest/index.html`
- D1 top-candidate trade review: `reports/force_strike/D1/latest/review/fs_atr_tp1p5_sma0p0_risk1p25/index.html`

## TradingView Indicator

- Pine script: `tradingview/force_strike_signal.pine`
- Usage note: `tradingview/README.md`
- Default behavior now matches legacy-style context.
- `useSwingRetraceQuality` defaults to false.
- Python/MT5 remains the source of truth for basket backtests, fills, costs, and candidate ranking.
- TradingView evaluates TradingView chart candles, so exact bar-by-bar parity is only expected when candle data is identical.

## Current Configs

- `configs/d1_current_legacy_filtered.json` is the current working baseline.
- `configs/d1_forex_g8_legacy_context.json` is the broad legacy comparison.
- `configs/d1_forex_g8_swing_retrace_v1.json` is the broad swing/retrace experiment.
- `configs/d1_forex_basket.json`, `configs/h4_forex_basket.json`, and `configs/m30_forex_basket.json` are original 4-pair baselines.
- `configs/*_swing_retrace_v1.json` files are archived experiments.

## Useful Commands

Run tests from repo root:

```powershell
.\..\venv\Scripts\python -m unittest discover tests
```

Run the current baseline from the repository parent:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json
```

Run and refresh MT5 data intentionally:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json --pull
```

Run broad comparison configs:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_g8_legacy_context.json
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_g8_swing_retrace_v1.json
```

## Next Best Work

1. Paper-test the fixed legacy D1 basket without changing symbols.
2. Visually review accepted D1 setups against `docs/strategy.html`.
3. If adding heuristics, create a separate config and compare against `d1_current_legacy_filtered.json`.
4. Keep a heuristic only if it improves the legacy baseline without destroying trade count.
