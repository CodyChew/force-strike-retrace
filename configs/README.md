# Force Strike Configs

## Current Baseline

- `d1_current_legacy_filtered.json`
  - Current working strategy.
  - D1 legacy context.
  - Filtered positive-symbol basket from the latest G8 research.
  - Single candidate: `fs_atr_tp1p5_sma0p0_risk1p25`.

Run it from the repository parent:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json
```

## Comparison Configs

- `d1_forex_g8_legacy_context.json` tests legacy on all 28 G8 pairs.
- `d1_forex_g8_swing_retrace_v1.json` tests the stricter swing/retrace experiment on all 28 G8 pairs.
- `d1_forex_basket.json`, `h4_forex_basket.json`, and `m30_forex_basket.json` are original 4-pair timeframe baselines.
- `*_swing_retrace_v1.json` files are archived experiments, not the current working strategy.

Generated report folders are disposable and ignored by Git except the curated dashboard under `reports/findings_dashboard`.
