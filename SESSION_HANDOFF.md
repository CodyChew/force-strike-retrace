# Force Strike Lab Session Handoff

Last updated: 2026-04-28 Australia/Perth.

## How To Switch Context Modes

The switch is in the config under `strategy.prior_price_action_mode`.

Legacy mode:

```json
"prior_price_action_mode": "legacy"
```

Swing/retrace mode:

```json
"prior_price_action_mode": "swing_retrace_v1"
```

Existing comparison configs:

- Legacy D1 G8: `configs/d1_forex_g8_legacy_context.json`
- Swing/retrace D1 G8: `configs/d1_forex_g8_swing_retrace_v1.json`
- Swing/retrace D1 4-pair: `configs/d1_forex_basket_swing_retrace_v1.json`
- Swing/retrace H4 4-pair: `configs/h4_forex_basket_swing_retrace_v1.json`

Run examples:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_g8_swing_retrace_v1.json --pull
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_forex_g8_legacy_context.json
```

Use `--pull` once when refreshing data. Then rerun comparison configs without `--pull` so both use the same local data files.

## Current Research Read

The broad D1 G8 comparison shows `swing_retrace_v1` is better than legacy when both are tested on all 28 G8 pairs:

- Legacy G8: -17.85R, PF 0.94, max DD 37.59R, 482 trades.
- Swing/retrace G8: +11.27R, PF 1.07, max DD 16.16R, 289 trades.

However, the broad G8 basket is weaker than the original focused D1 basket.

Conservative first candidate:

- Mode: `swing_retrace_v1`
- Candidate: `fs_atr_tp2p0_sma0p0_risk1p25`
- Tickers: `GBPAUD`, `GBPJPY`, `GBPCHF`, `CHFJPY`
- Result: +33.31R, PF 2.64, max DD 3.07R, 47 trades, positive years 9/10.

Aggressive historical-profit candidate:

- Mode: `legacy`
- Candidate: `fs_atr_tp1p25_sma0p0_risk1p25`
- Tickers: all full-sample positive legacy symbols:
  `GBPAUD`, `GBPCHF`, `AUDCHF`, `AUDUSD`, `GBPJPY`, `USDJPY`, `AUDCAD`, `AUDNZD`, `EURJPY`, `EURUSD`, `USDCHF`, `CHFJPY`, `NZDJPY`, `GBPNZD`
- Result: +62.67R, PF 1.61, max DD 7.86R, 235 trades.
- Caveat: selected with full-history hindsight, so more curve-fit risk.

Avoid for now:

- `USDCAD`
- `GBPUSD`
- `EURCHF`
- `NZDCHF`
- `GBPCAD`
- `CADJPY`
- `AUDCAD`
- `EURNZD`

## Dashboard And Notes

- Dashboard: `reports/findings_dashboard/index.html`
- Recommendation note: `reports/findings_dashboard/ticker_strategy_recommendation.md`
- Main project state: `PROJECT_STATE.md`

## Adding More Heuristics

Preferred workflow:

1. Add a new named mode in config, for example:

```json
"prior_price_action_mode": "swing_retrace_v2"
```

2. Update validation in `src/force_strike_lab/config.py`.
3. Add the new filter branch in `src/force_strike_lab/features.py`, near `_prior_swing_retrace_ok`.
4. Add focused tests in `tests/test_force_strike_lab.py`.
5. Create a new config with a unique `report_dir`, for example:

```json
"report_dir": "reports/force_strike_experiments/swing_retrace_v2_g8"
```

6. Compare against legacy and `swing_retrace_v1` on the same pulled data.

Keep each heuristic isolated by config and report directory. Do not overwrite existing modes until a new heuristic clearly beats them.

## Repo Bulk Control

This framework can become bulky because it creates:

- raw MT5 data under `data/raw`
- timestamped report folders
- large CSVs such as `trades.csv`, `yearly_summary.csv`, and `rolling_summary.csv`

Treat report output as disposable research artifacts. Keep:

- source code
- tests
- configs
- `PROJECT_STATE.md`
- dashboard summary files
- only the most important final reports

Archive or delete old timestamp folders when they are no longer useful. If this becomes a Git repo, do not commit:

- `venv/`
- `venv.zip`
- `data/raw/`
- timestamped `reports/**/20*/`
- large generated CSVs unless needed for a specific checkpoint

The efficient long-term shape is: configs define experiments, source/tests define behavior, reports are regenerated when needed.
