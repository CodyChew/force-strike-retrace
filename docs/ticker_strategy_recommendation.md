# Ticker And Strategy Recommendation

Generated from the fresh D1 G8 reruns ending 2026-04-27.

## Current Working Baseline

Use the D1 legacy context logic with:

- Config: `configs/d1_current_legacy_filtered.json`
- Candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Tickers: `GBPAUD`, `AUDUSD`, `GBPCHF`, `GBPJPY`, `AUDCHF`, `AUDNZD`, `EURUSD`, `USDCHF`, `USDJPY`, `AUDCAD`, `GBPNZD`, `NZDJPY`, `CHFJPY`, `EURJPY`

Candidate meaning:

- Legacy prior price-action mode.
- ATR stop model.
- Target: 1.5R.
- SMA touch buffer: 0.0 ATR.
- Maximum entry risk: 1.25 ATR.

## Baseline Result

This is the current baseline because it gives materially more trades than the conservative swing/retrace basket while keeping the historical result positive:

- 231 trades.
- Full net R: +67.76R.
- Profit factor: 1.61.
- Max drawdown: 6.75R using the repo report metric.
- Discovery net R: +26.30R.
- Selection net R: +19.87R.
- Holdout net R: +21.59R.
- Approximate frequency: 23 to 24 trades per year across the basket.

Per symbol:

| Symbol | Trades | Net R | PF |
|---|---:|---:|---:|
| GBPAUD | 15 | +12.31R | 4.04 |
| AUDUSD | 17 | +10.26R | 2.69 |
| GBPCHF | 17 | +10.21R | 2.66 |
| GBPJPY | 23 | +6.66R | 1.60 |
| AUDCHF | 23 | +6.56R | 1.58 |
| AUDNZD | 14 | +5.61R | 1.92 |
| EURUSD | 18 | +4.29R | 1.47 |
| USDCHF | 16 | +3.87R | 1.48 |
| USDJPY | 11 | +3.84R | 1.76 |
| AUDCAD | 18 | +1.60R | 1.16 |
| GBPNZD | 11 | +1.39R | 1.23 |
| NZDJPY | 14 | +0.68R | 1.08 |
| CHFJPY | 12 | +0.31R | 1.04 |
| EURJPY | 22 | +0.18R | 1.01 |

## Nearby Alternative

Legacy `fs_atr_tp1p25_sma0p0_risk1p25` on its positive-symbol basket is also valid:

- 235 trades.
- Full net R: +62.67R.
- Profit factor: 1.61.
- Max drawdown: 5.08R using the repo report metric.

Use this if the priority is slightly more trades and a lower target. Use TP 1.5R if the priority is the strongest historical net R in the saved legacy tests.

## Archived Challenger

The swing/retrace experiment remains useful, but it is no longer the working baseline:

- Expanded swing `fs_atr_tp2p0_sma0p0_risk1p25`, 12 symbols: 143 trades, +55.42R, PF 1.72, max DD 7.19R.
- Conservative swing core, 4 symbols: 47 trades, +33.31R, PF 2.64, max DD 3.05R.

Swing/retrace is cleaner and stricter, but it produces fewer trades. It should only replace legacy if a future controlled test beats this legacy baseline after accounting for trade count.

## Operating Constraint

This remains historical backtest evidence, not proof of future edge. The legacy filtered basket was chosen using historical symbol performance, so the next validation step should be fixed-list paper/forward testing without reselecting symbols.
