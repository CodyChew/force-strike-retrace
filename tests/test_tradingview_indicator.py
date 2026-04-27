from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from force_strike_lab.config import load_config


PINE_PATH = PROJECT_ROOT / "tradingview" / "force_strike_signal.pine"


def _pine_source() -> str:
    return PINE_PATH.read_text(encoding="utf-8")


def _input_default(source: str, name: str) -> object:
    pattern = re.compile(rf"^{re.escape(name)}\s*=\s*input\.(int|float|bool)\(([^,\n]+)", re.MULTILINE)
    match = pattern.search(source)
    if not match:
        raise AssertionError(f"Could not find Pine input default for {name!r}.")
    kind, raw = match.groups()
    value = raw.strip()
    if kind == "bool":
        return value == "true"
    if kind == "int":
        return int(value)
    return float(value)


class TradingViewIndicatorTests(unittest.TestCase):
    def test_pine_indicator_file_has_expected_top_level_contract(self) -> None:
        source = _pine_source()
        self.assertTrue(PINE_PATH.exists())
        self.assertIn("//@version=6", source)
        self.assertIn("indicator(", source)
        self.assertIn('"Force Strike Signal"', source)
        self.assertIn("overlay = true", source)
        self.assertIn("max_bars_back = 1000", source)
        self.assertEqual(source.count("("), source.count(")"))
        self.assertEqual(source.count("["), source.count("]"))
        self.assertNotIn("by -1", source)

    def test_pine_default_inputs_match_current_strategy_config(self) -> None:
        source = _pine_source()
        strategy = load_config(PROJECT_ROOT / "configs" / "d1_forex_basket.json").strategy
        expected = {
            "minTotalBarsInput": strategy.min_total_bars,
            "maxTotalBarsInput": strategy.max_total_bars,
            "requireFirstRetracementContext": strategy.require_first_retracement_context,
            "atrWindow": strategy.atr_window,
            "smaFastLength": strategy.sma_fast,
            "smaSlowLength": strategy.sma_slow,
            "smaTouchBufferAtr": 0.0,
            "minContextZoneBufferAtr": strategy.min_context_zone_buffer_atr,
            "contextLookbackBars": strategy.context_lookback_bars,
            "minImpulseAtr": strategy.min_impulse_atr,
            "trendSideLookbackBars": strategy.trend_side_lookback_bars,
            "minTrendSideRatio": strategy.min_trend_side_ratio,
            "minAnchorEfficiency": strategy.min_anchor_efficiency,
            "minPreMotherRetraceAtr": strategy.min_pre_mother_retrace_atr,
            "minPreMotherRetraceBars": strategy.min_pre_mother_retrace_bars,
            "recentProgressLookbackBars": strategy.recent_progress_lookback_bars,
            "maxAnchorBarsWithoutRecentProgress": strategy.max_anchor_bars_without_recent_progress,
            "minRecentProgressAtr": strategy.min_recent_progress_atr,
        }
        for name, expected_value in expected.items():
            with self.subTest(name=name):
                self.assertEqual(_input_default(source, name), expected_value)

    def test_pine_defaults_are_clean_for_client_use(self) -> None:
        source = _pine_source()
        self.assertTrue(_input_default(source, "showAccepted"))
        self.assertFalse(_input_default(source, "showRejected"))
        self.assertTrue(_input_default(source, "showMotherRange"))
        self.assertFalse(_input_default(source, "showDiagnostics"))
        self.assertTrue(_input_default(source, "confirmOnClose"))
        self.assertEqual(_input_default(source, "minSmaSlopeAtr"), 0.10)
        self.assertEqual(_input_default(source, "minPriorRetraceCloseAtr"), 0.50)

    def test_pine_keeps_chart_source_boundary_documented(self) -> None:
        source = _pine_source()
        self.assertIn("TradingView signals are evaluated only from the OHLC candles", source)
        self.assertIn("Python/MT5 research evaluates the same rule family", source)
        self.assertIn("Both can be correct for their own chart stream", source)

    def test_pine_prior_signal_logic_separates_raw_from_accepted(self) -> None:
        source = _pine_source()
        self.assertIn("bool priorAccepted = f_has_prior_signal(motherOff, true)", source)
        self.assertIn("bool priorRaw = f_has_prior_signal(motherOff, false)", source)
        self.assertIn("bool acceptedCandidate = ctxOk and not priorAccepted", source)
        self.assertIn("bool rejectedCandidate = not ctxOk and not priorRaw", source)

    def test_pine_exposes_swing_then_retrace_filters(self) -> None:
        source = _pine_source()
        self.assertIn("f_pre_mother_retrace_close", source)
        self.assertIn("bool smaSlopeOk = smaSlopeAtr >= minSmaSlopeAtr", source)
        self.assertIn("bool retraceCloseOk = retraceCloseAtr >= minPriorRetraceCloseAtr", source)
        self.assertIn("Fail: retrace close", source)

    def test_pine_exposes_client_signal_alerts(self) -> None:
        source = _pine_source()
        self.assertIn('alertcondition(showAcceptedSignal and foundSide > 0, "Bullish Force Strike"', source)
        self.assertIn('alertcondition(showAcceptedSignal and foundSide < 0, "Bearish Force Strike"', source)


if __name__ == "__main__":
    unittest.main()
