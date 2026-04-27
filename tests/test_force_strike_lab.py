from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from force_strike_lab.backtest import run_backtest
from force_strike_lab.config import CostConfig, StrategyGridConfig, load_config
from force_strike_lab.strategy import StrategyCandidate, detect_force_strikes, is_bearish_bar, is_bullish_bar
from force_strike_lab.timeframes import get_timeframe_spec


def _frame(rows: list[dict]) -> pd.DataFrame:
    base = []
    times = pd.date_range("2026-01-01 00:00:00+00:00", periods=len(rows), freq="30min", tz="UTC")
    for index, row in enumerate(rows):
        item = {
            "time_utc": times[index],
            "symbol": "EURUSD",
            "timeframe": "M30",
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "atr": row.get("atr", 8.0),
            "sma_fast": row.get("sma_fast", 96.0),
            "sma_slow": row.get("sma_slow", 94.0),
            "spread_price": row.get("spread_price", 0.0),
            "point": row.get("point", 0.00001),
        }
        item["range"] = item["high"] - item["low"]
        item["close_location"] = 0.5 if item["range"] <= 0 else (item["close"] - item["low"]) / item["range"]
        item["is_bullish_bar"] = item["range"] > 0 and item["close_location"] >= (2.0 / 3.0)
        item["is_bearish_bar"] = item["range"] > 0 and item["close_location"] <= (1.0 / 3.0)
        base.append(item)
    return pd.DataFrame(base)


def _candidate(stop_model: str = "structure", target_r: float = 1.0) -> StrategyCandidate:
    return StrategyCandidate(
        candidate_id=f"test_{stop_model}_{target_r}",
        stop_model=stop_model,
        target_r=target_r,
        sma_touch_buffer_atr=0.0,
        max_risk_atr=1.25,
        structure_stop_buffer_atr=0.0,
    )


def _strategy_without_first_retracement() -> StrategyGridConfig:
    return StrategyGridConfig(require_first_retracement_context=False)


def _swing_retrace_context_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "require_context": True,
        "require_first_retracement_context": True,
        "context_lookback_bars": 20,
        "min_impulse_atr": 1.0,
        "prior_pullback_atr": 1.0,
        "trend_side_lookback_bars": 6,
        "min_trend_side_ratio": 0.45,
        "min_anchor_efficiency": 0.20,
        "min_pre_mother_retrace_atr": 0.75,
        "min_pre_mother_retrace_bars": 1,
        "prior_price_action_mode": "swing_retrace_v1",
        "min_prior_impulse_bars": 2,
        "min_prior_swing_progress_atr": 1.5,
        "min_prior_close_progress_atr": 0.5,
        "min_prior_retrace_close_atr": 0.5,
        "min_prior_directional_close_ratio": 0.45,
        "max_prior_retrace_fraction": 1.0,
        "min_sma_slope_atr": 0.10,
    }
    kwargs.update(overrides)
    return kwargs


def _bullish_swing_retrace_rows(*, retrace_close: float = 105.0, signal_sma_slow: float = 101.0) -> list[dict]:
    return [
        {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "atr": 4.0, "sma_fast": 99.0, "sma_slow": 100.0},
        {"open": 100.0, "high": 102.0, "low": 100.0, "close": 101.0, "atr": 4.0, "sma_fast": 100.5, "sma_slow": 100.0},
        {"open": 101.0, "high": 105.0, "low": 101.0, "close": 104.0, "atr": 4.0, "sma_fast": 102.0, "sma_slow": 100.2},
        {"open": 104.0, "high": 109.0, "low": 104.0, "close": 108.0, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.4},
        {"open": 108.0, "high": 108.0, "low": 104.0, "close": retrace_close, "atr": 4.0, "sma_fast": 105.5, "sma_slow": 100.6},
        {"open": 105.0, "high": 107.0, "low": 103.0, "close": 105.0, "atr": 4.0, "sma_fast": 105.0, "sma_slow": 100.8},
        {"open": 105.0, "high": 106.5, "low": 103.5, "close": 105.0, "atr": 4.0, "sma_fast": 105.1, "sma_slow": 100.9},
        {"open": 104.0, "high": 106.8, "low": 102.5, "close": 106.0, "atr": 4.0, "sma_fast": 105.2, "sma_slow": signal_sma_slow},
    ]


class ForceStrikeLabTests(unittest.TestCase):
    def test_bullish_and_bearish_bar_boundaries_are_inclusive(self) -> None:
        self.assertTrue(is_bullish_bar(0.0, 3.0, 0.0, 2.0))
        self.assertTrue(is_bearish_bar(0.0, 3.0, 0.0, 1.0))
        self.assertFalse(is_bullish_bar(1.0, 1.0, 1.0, 1.0))
        self.assertFalse(is_bearish_bar(1.0, 1.0, 1.0, 1.0))

    def test_same_candle_bullish_force_strike_detects(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95},
                {"open": 94, "high": 99, "low": 91, "close": 95},
                {"open": 90, "high": 97, "low": 88, "close": 96},
            ]
        )
        signals = detect_force_strikes(data, require_context=False)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].side, 1)
        self.assertEqual(signals[0].total_bars, 3)

    def test_separate_breakout_then_bearish_close_back_inside_detects(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95, "sma_fast": 94, "sma_slow": 96},
                {"open": 94, "high": 99, "low": 91, "close": 95, "sma_fast": 94, "sma_slow": 96},
                {"open": 99, "high": 103, "low": 98, "close": 101, "sma_fast": 94, "sma_slow": 96},
                {"open": 100, "high": 101, "low": 91, "close": 92, "sma_fast": 94, "sma_slow": 96},
            ]
        )
        signals = detect_force_strikes(data, require_context=True, require_first_retracement_context=False)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].side, -1)
        self.assertEqual(signals[0].total_bars, 4)

    def test_max_six_bar_expiry(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95},
                {"open": 94, "high": 99, "low": 91, "close": 95},
                {"open": 95, "high": 98, "low": 89, "close": 89},
                {"open": 90, "high": 98, "low": 89, "close": 89},
                {"open": 90, "high": 98, "low": 89, "close": 89},
                {"open": 90, "high": 98, "low": 89, "close": 89},
                {"open": 90, "high": 97, "low": 88, "close": 96},
            ]
        )
        signals = detect_force_strikes(data, require_context=False)
        self.assertFalse([signal for signal in signals if signal.mother_index == 0])

    def test_two_sided_breakout_discards_formation(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95},
                {"open": 94, "high": 99, "low": 91, "close": 95},
                {"open": 95, "high": 101, "low": 89, "close": 96},
            ]
        )
        signals = detect_force_strikes(data, require_context=False)
        self.assertEqual(signals, [])

    def test_sma_context_gate_blocks_wrong_trend(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95, "sma_fast": 94, "sma_slow": 96},
                {"open": 94, "high": 99, "low": 91, "close": 95, "sma_fast": 94, "sma_slow": 96},
                {"open": 90, "high": 97, "low": 88, "close": 96, "sma_fast": 94, "sma_slow": 96},
            ]
        )
        signals = detect_force_strikes(data, require_context=True, require_first_retracement_context=False)
        self.assertEqual(signals, [])

    def test_trend_context_allows_clear_bullish_setup(self) -> None:
        data = _frame(
            [
                {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "atr": 4.0, "sma_fast": 99.0, "sma_slow": 100.0},
                {"open": 100.0, "high": 102.0, "low": 100.0, "close": 101.0, "atr": 4.0, "sma_fast": 100.5, "sma_slow": 100.0},
                {"open": 101.0, "high": 108.0, "low": 103.0, "close": 107.0, "atr": 4.0, "sma_fast": 102.0, "sma_slow": 100.1},
                {"open": 107.0, "high": 107.0, "low": 104.0, "close": 106.0, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.2},
                {"open": 106.0, "high": 106.5, "low": 105.0, "close": 106.0, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.3},
                {"open": 104.0, "high": 106.8, "low": 103.5, "close": 106.5, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.4},
            ]
        )
        signals = detect_force_strikes(
            data,
            require_context=True,
            require_first_retracement_context=True,
            context_lookback_bars=10,
            min_impulse_atr=1.0,
            prior_pullback_atr=1.0,
            min_pre_mother_retrace_atr=0.0,
            min_pre_mother_retrace_bars=0,
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].side, 1)
        self.assertEqual(signals[0].mother_index, 3)

    def test_trend_context_blocks_sideways_bullish_setup(self) -> None:
        data = _frame(
            [
                {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "atr": 4.0, "sma_fast": 99.0, "sma_slow": 100.0},
                {"open": 100.0, "high": 102.0, "low": 100.0, "close": 101.0, "atr": 4.0, "sma_fast": 100.5, "sma_slow": 100.0},
                {"open": 101.0, "high": 108.0, "low": 105.0, "close": 107.0, "atr": 4.0, "sma_fast": 102.0, "sma_slow": 100.1},
                {"open": 107.0, "high": 107.0, "low": 103.0, "close": 102.0, "atr": 4.0, "sma_fast": 103.0, "sma_slow": 100.2},
                {"open": 102.0, "high": 108.0, "low": 101.0, "close": 106.0, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.3},
                {"open": 106.0, "high": 108.0, "low": 104.0, "close": 101.0, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.4},
                {"open": 105.0, "high": 107.0, "low": 105.0, "close": 106.0, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.5},
                {"open": 104.0, "high": 107.0, "low": 103.5, "close": 106.5, "atr": 4.0, "sma_fast": 104.0, "sma_slow": 100.6},
            ]
        )
        signals = detect_force_strikes(
            data,
            require_context=True,
            require_first_retracement_context=True,
            context_lookback_bars=10,
            min_impulse_atr=1.0,
            prior_pullback_atr=1.0,
        )
        self.assertEqual(signals, [])

    def test_swing_retrace_context_allows_prior_upside_then_downside_bullish_setup(self) -> None:
        data = _frame(_bullish_swing_retrace_rows())
        signals = detect_force_strikes(data, **_swing_retrace_context_kwargs())
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].side, 1)
        self.assertEqual(signals[0].mother_index, 5)

    def test_swing_retrace_context_blocks_bullish_setup_without_close_retracement(self) -> None:
        data = _frame(_bullish_swing_retrace_rows(retrace_close=107.8))
        signals = detect_force_strikes(data, **_swing_retrace_context_kwargs())
        self.assertEqual(signals, [])

    def test_swing_retrace_context_blocks_weak_sma50_slope(self) -> None:
        data = _frame(_bullish_swing_retrace_rows(signal_sma_slow=100.2))
        signals = detect_force_strikes(data, **_swing_retrace_context_kwargs())
        self.assertEqual(signals, [])

    def test_next_open_risk_rejection_uses_pullback_entry_and_hits_target(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95},
                {"open": 94, "high": 99, "low": 91, "close": 95},
                {"open": 90, "high": 97, "low": 88, "close": 96},
                {"open": 100, "high": 104, "low": 98, "close": 101},
                {"open": 101, "high": 108, "low": 100, "close": 107},
            ]
        )
        result = run_backtest(
            data,
            candidate=_candidate("structure", 1.0),
            strategy_config=_strategy_without_first_retracement(),
            costs=CostConfig(fallback_spread_points=0.0),
        )
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].entry_mode, "pullback_limit")
        self.assertEqual(result.trades[0].exit_reason, "target")

    def test_retrace_entry_cancels_when_one_r_is_reached_before_fill(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95},
                {"open": 94, "high": 99, "low": 91, "close": 95},
                {"open": 90, "high": 97, "low": 88, "close": 96},
                {"open": 100, "high": 108, "low": 99, "close": 107},
            ]
        )
        result = run_backtest(
            data,
            candidate=_candidate("structure", 1.0),
            strategy_config=_strategy_without_first_retracement(),
            costs=CostConfig(fallback_spread_points=0.0),
        )
        self.assertEqual(len(result.trades), 0)
        self.assertEqual(result.pending_cancelled, 1)

    def test_tp_sl_only_end_of_data_close_flag(self) -> None:
        data = _frame(
            [
                {"open": 95, "high": 100, "low": 90, "close": 95, "atr": 10},
                {"open": 94, "high": 99, "low": 91, "close": 95, "atr": 10},
                {"open": 90, "high": 97, "low": 88, "close": 96, "atr": 10},
                {"open": 98, "high": 99, "low": 95, "close": 97, "atr": 10},
                {"open": 97, "high": 99, "low": 95, "close": 97, "atr": 10},
            ]
        )
        result = run_backtest(
            data,
            candidate=_candidate("structure", 2.5),
            strategy_config=_strategy_without_first_retracement(),
            costs=CostConfig(fallback_spread_points=0.0),
        )
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].exit_reason, "end_of_data")

    def test_timeframe_registry_supports_only_v1_set(self) -> None:
        self.assertEqual(get_timeframe_spec("M30").expected_delta, pd.Timedelta(minutes=30))
        self.assertEqual(get_timeframe_spec("H4").expected_delta, pd.Timedelta(hours=4))
        self.assertEqual(get_timeframe_spec("D1").expected_delta, pd.Timedelta(days=1))
        with self.assertRaises(ValueError):
            get_timeframe_spec("M15")

    def test_config_loads_supported_timeframe(self) -> None:
        payload = {
            "symbols": ["EURUSD"],
            "timeframe": "H4",
            "history_years": 5,
            "costs": {},
            "strategy": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = load_config(path)
        self.assertEqual(config.timeframe, "H4")
        self.assertEqual(config.symbols, ["EURUSD"])


if __name__ == "__main__":
    unittest.main()
