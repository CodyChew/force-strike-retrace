# Force Strike Lab

Fresh MT5-direct research lab for the Force Strike Bar Formation strategy.

The lab is intentionally separate from the older `xauusd_m1_research` and
`mt5_strategy_lab` projects. It supports `M30`, `H4`, and `D1` research through
config only.

## Current Baseline

The current working strategy is:

- Config: `configs/d1_current_legacy_filtered.json`
- Mode: legacy D1
- Candidate: `fs_atr_tp1p5_sma0p0_risk1p25`
- Fixed 14-symbol filtered basket

Run it from the repository parent:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json
```

## First Run / Data Refresh

Pull MT5 data:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\pull_mt5_data.py --config force_strike_lab\configs\d1_current_legacy_filtered.json
```

Run research from already-pulled data:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json
```

Pull and run in one command:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\run_research.py --config force_strike_lab\configs\d1_current_legacy_filtered.json --pull
```

Run tests:

```powershell
.\venv\Scripts\python -m unittest discover force_strike_lab\tests
```

Export visual trade review charts from the latest report:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\export_trade_review.py --report-dir force_strike_lab\reports\force_strike\M30\latest
```

Review a specific candidate:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\export_trade_review.py --report-dir force_strike_lab\reports\force_strike\M30\latest --candidate-id fs_atr_tp2p5_sma0p25_risk1p25
```

Export raw Force Strike scenarios for manual labeling:

```powershell
.\venv\Scripts\python force_strike_lab\scripts\export_pattern_labeling.py --config force_strike_lab\configs\m30_forex_basket.json --max-per-symbol 12
```

## Current Context Gate

The current legacy config requires trend-following 50 SMA context. A bullish setup must
be on the bullish side of the 50 SMA, begin from a lower 50-SMA transition area,
make a meaningful impulse, and avoid stale sideways drift before the Force
Strike. Bearish setups use the mirrored rule. The gate is calibrated from the
manual labeling workflow, not from the old strict "first pullback only" rule.

Swing/retrace configs remain in the repo as archived experiments and should be
compared against the current legacy baseline before being promoted.
