# Ticker And Strategy Recommendation

Generated from the fresh D1 G8 `swing_retrace_v1` rerun ending 2026-04-27.

## Recommendation

Use the D1 `swing_retrace_v1` context logic with:

- Candidate: `fs_atr_tp2p0_sma0p0_risk1p25`
- Tickers: `GBPAUD`, `GBPJPY`, `GBPCHF`, `CHFJPY`

Candidate meaning:

- ATR stop model.
- Target: 2.0R.
- SMA touch buffer: 0.0 ATR.
- Maximum entry risk: 1.25 ATR.

## Why This Set

This is not the highest possible historical net R after filtering symbols. It is the best balance I found between profitability and robustness:

- 47 trades.
- Full net R: +33.31R.
- Profit factor: 2.64.
- Max drawdown: 3.07R.
- Discovery net R: +13.58R.
- Selection net R: +4.93R.
- Holdout net R: +14.80R.
- Positive years: 9 of 10.
- Worst year: -0.02R.

Per symbol:

| Symbol | Trades | Net R | PF | Max DD | Discovery | Selection | Holdout |
|---|---:|---:|---:|---:|---:|---:|---:|
| GBPAUD | 12 | +11.87R | 3.93 | 1.02R | +4.94R | +1.99R | +4.94R |
| GBPCHF | 11 | +9.80R | 3.39 | 2.06R | +4.84R | +1.99R | +2.96R |
| GBPJPY | 15 | +8.76R | 2.24 | 3.03R | +2.84R | +0.00R | +5.92R |
| CHFJPY | 9 | +2.88R | 1.57 | 2.02R | -2.04R | +2.97R | +1.95R |

Leave-one-symbol-out remained positive:

| Excluded | Trades | Net R | PF | Max DD | Holdout |
|---|---:|---:|---:|---:|---:|
| CHFJPY | 38 | +30.43R | 3.00 | 3.07R | +12.85R |
| GBPJPY | 32 | +24.55R | 2.86 | 3.11R | +8.87R |
| GBPCHF | 36 | +23.51R | 2.45 | 3.06R | +12.81R |
| GBPAUD | 35 | +21.44R | 2.32 | 4.04R | +9.86R |

## Higher-R But Less Conservative Alternative

A mechanically filtered 10-symbol basket with `fs_atr_tp2p5_sma0p0_risk1p25` produced +55.83R:

- Tickers: `AUDJPY`, `AUDNZD`, `AUDUSD`, `CADCHF`, `CHFJPY`, `EURUSD`, `GBPAUD`, `GBPCHF`, `GBPJPY`, `NZDCAD`
- Trades: 117.
- PF: 1.82.
- Max drawdown: 9.47R.
- Holdout: +14.53R.
- Worst year: -4.87R.

I do not recommend this as the first live candidate because the ticker list is selected using full-history knowledge and has materially higher drawdown and weaker year stability.

## Avoid For Now

Do not include these in the core basket:

- `USDCAD`
- `GBPUSD`
- `EURCHF`
- `NZDCHF`
- `GBPCAD`
- `CADJPY`
- `AUDCAD`
- `EURNZD`

They either lost materially in the latest G8 run or showed weak split/holdout behavior.

## Operating Constraint

This remains historical backtest evidence, not proof of future edge. Before live use, visually validate the accepted D1 setups for the recommended tickers and run a forward/paper period with fixed risk.
