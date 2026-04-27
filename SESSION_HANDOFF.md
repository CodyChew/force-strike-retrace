# Force Strike Lab Session Handoff

Last updated: 2026-04-28 Australia/Perth.

## Current Working Strategy

The project baseline is reset to legacy D1.

- Config: `configs/d1_current_legacy_filtered.json`
- Mode: `legacy`
- Candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Timeframe: D1
- Stop: ATR
- Target: 1.5R
- SMA touch buffer: 0.0 ATR
- Max entry risk: 1.25 ATR
- Tickers: `GBPAUD`, `AUDUSD`, `GBPCHF`, `GBPJPY`, `AUDCHF`, `AUDNZD`, `EURUSD`, `USDCHF`, `USDJPY`, `AUDCAD`, `GBPNZD`, `NZDJPY`, `CHFJPY`, `EURJPY`

Backtest read from the latest D1 G8 legacy rerun:

- 231 trades.
- Full net R: +67.76R.
- Profit factor: 1.61.
- Max drawdown: 6.75R using the repo report metric.
- Discovery net R: +26.30R.
- Selection net R: +19.87R.
- Holdout net R: +21.59R.
- Approximate frequency: 23 to 24 trades per year across the basket.

Important caveat: the ticker list was selected from historical winners. Forward/paper validation must keep this list fixed instead of reselecting symbols after every run.

## Current Docs

- Published dashboard source: `docs/index.html`
- Strategy guide: `docs/strategy.html`
- Recommendation note: `docs/ticker_strategy_recommendation.md`
- Local dashboard mirror: `reports/findings_dashboard/`
- Config guide: `configs/README.md`

GitHub Pages serves from `docs/`.

## How To Run The Current Baseline

From the repository parent:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json
```

Use `--pull` only when intentionally refreshing MT5 data:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json --pull
```

## Comparison Configs

- Legacy all-G8 comparison: `configs/d1_forex_g8_legacy_context.json`
- Swing/retrace all-G8 experiment: `configs/d1_forex_g8_swing_retrace_v1.json`
- Original D1 4-pair baseline: `configs/d1_forex_basket.json`
- Original H4 4-pair baseline: `configs/h4_forex_basket.json`
- Original M30 4-pair baseline: `configs/m30_forex_basket.json`
- Archived swing/retrace 4-pair configs:
  - `configs/d1_forex_basket_swing_retrace_v1.json`
  - `configs/h4_forex_basket_swing_retrace_v1.json`

## Current Research Read

Legacy is now the working baseline because it is simpler and gives more trades than the conservative swing/retrace core.

Key comparison:

- Current legacy TP 1.5R filtered basket: +67.76R, PF 1.61, 231 trades, max DD 6.75R.
- Legacy TP 1.25R filtered basket: +62.67R, PF 1.61, 235 trades, max DD 5.08R.
- Expanded swing/retrace TP 2.0R basket: +55.42R, PF 1.72, 143 trades, max DD 7.19R.
- Conservative swing/retrace TP 2.0R core: +33.31R, PF 2.64, 47 trades, max DD 3.05R.

Swing/retrace is not deleted. It is an archived challenger that should only become current if it beats the legacy baseline in a controlled comparison.

## Pine Script State

- Pine script: `tradingview/force_strike_signal.pine`
- Default behavior is now legacy-style context.
- `useSwingRetraceQuality` defaults to `false`.
- Python/MT5 remains the source of truth for backtests, fills, costs, and candidate ranking.
- TradingView remains a chart-side visual validation layer and can differ if TradingView candles differ from MT5 candles.

## Adding More Heuristics

Add only one idea at a time:

1. Create a new config with a unique report directory.
2. Keep the same fixed current ticker list unless the experiment is specifically about symbol selection.
3. Compare against `d1_current_legacy_filtered.json`.
4. Keep the heuristic only if it improves the baseline without destroying trade count.

Minimum comparison metrics:

- Net R
- Profit factor
- Max drawdown
- Discovery/selection/holdout behavior
- Trades per year
- Per-symbol contribution

## Repo Bulk Control

Do not commit generated raw data or timestamped reports:

- `data/raw/`
- `reports/force_strike*/`
- large CSV outputs
- `venv/`
- `*.zip`

Keep committed:

- source code
- tests
- configs
- docs
- `PROJECT_STATE.md`
- `SESSION_HANDOFF.md`
- curated dashboard files under `reports/findings_dashboard/`
