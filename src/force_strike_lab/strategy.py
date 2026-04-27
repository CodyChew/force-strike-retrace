"""Force Strike formation detection and candidate definitions.

The detector evaluates the OHLC frame passed into it. MT5 research and the
TradingView indicator can both be correct for their own candle streams even
when feed/session differences make individual signal bars differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pandas as pd

from .config import StrategyGridConfig
from .features import context_ok, trend_context_ok


@dataclass(frozen=True)
class ForceStrikeSignal:
    symbol: str
    timeframe: str
    side: int
    mother_index: int
    signal_index: int
    mother_time_utc: str
    signal_time_utc: str
    mother_high: float
    mother_low: float
    structure_high: float
    structure_low: float
    total_bars: int
    breakout_side: str


@dataclass(frozen=True)
class StrategyCandidate:
    candidate_id: str
    stop_model: str
    target_r: float
    sma_touch_buffer_atr: float
    max_risk_atr: float
    structure_stop_buffer_atr: float

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "stop_model": self.stop_model,
            "target_r": self.target_r,
            "sma_touch_buffer_atr": self.sma_touch_buffer_atr,
            "max_risk_atr": self.max_risk_atr,
            "structure_stop_buffer_atr": self.structure_stop_buffer_atr,
        }


def close_location(open_: float, high: float, low: float, close: float) -> float:
    """Return close location in bar range, with zero-range bars neutral."""

    del open_
    bar_range = float(high) - float(low)
    if bar_range <= 0:
        return 0.5
    return (float(close) - float(low)) / bar_range


def is_bullish_bar(open_: float, high: float, low: float, close: float) -> bool:
    """A bullish bar closes in or equal to the upper third of its range."""

    return close_location(open_, high, low, close) >= (2.0 / 3.0) and float(high) > float(low)


def is_bearish_bar(open_: float, high: float, low: float, close: float) -> bool:
    """A bearish bar closes in or equal to the lower third of its range."""

    return close_location(open_, high, low, close) <= (1.0 / 3.0) and float(high) > float(low)


def generate_candidates(strategy: StrategyGridConfig) -> list[StrategyCandidate]:
    """Generate the constrained v1 strategy grid."""

    candidates: list[StrategyCandidate] = []
    for stop_model, target_r, sma_buffer in product(
        strategy.stop_models,
        strategy.target_rs,
        strategy.sma_touch_buffer_atrs,
    ):
        candidate_id = (
            f"fs_{stop_model}_tp{str(target_r).replace('.', 'p')}_"
            f"sma{str(sma_buffer).replace('.', 'p')}_risk{str(strategy.max_risk_atr).replace('.', 'p')}"
        )
        candidates.append(
            StrategyCandidate(
                candidate_id=candidate_id,
                stop_model=str(stop_model).lower(),
                target_r=float(target_r),
                sma_touch_buffer_atr=float(sma_buffer),
                max_risk_atr=float(strategy.max_risk_atr),
                structure_stop_buffer_atr=float(strategy.structure_stop_buffer_atr),
            )
        )
    return candidates


def _inside_mother(row: pd.Series, mother_high: float, mother_low: float) -> bool:
    return float(row["high"]) <= mother_high and float(row["low"]) >= mother_low


def _close_inside_mother(row: pd.Series, mother_high: float, mother_low: float) -> bool:
    return mother_low <= float(row["close"]) <= mother_high


def _signal_from_window(
    frame: pd.DataFrame,
    *,
    mother_index: int,
    signal_index: int,
    require_context: bool,
    require_first_retracement_context: bool,
    sma_touch_buffer_atr: float,
    context_lookback_bars: int,
    min_impulse_atr: float,
    prior_pullback_atr: float,
    min_context_zone_buffer_atr: float,
    trend_side_lookback_bars: int,
    min_trend_side_ratio: float,
    min_anchor_efficiency: float,
    min_pre_mother_retrace_atr: float,
    min_pre_mother_retrace_bars: int,
    prior_price_action_mode: str,
    min_prior_impulse_bars: int,
    min_prior_swing_progress_atr: float,
    min_prior_close_progress_atr: float,
    min_prior_retrace_close_atr: float,
    min_prior_directional_close_ratio: float,
    max_prior_retrace_fraction: float,
    min_sma_slope_atr: float,
    recent_progress_lookback_bars: int,
    max_anchor_bars_without_recent_progress: int,
    min_recent_progress_atr: float,
) -> ForceStrikeSignal | None:
    mother = frame.iloc[mother_index]
    signal = frame.iloc[signal_index]
    mother_high = float(mother["high"])
    mother_low = float(mother["low"])
    between = frame.iloc[mother_index + 1 : signal_index + 1]
    structure_high = float(frame.iloc[mother_index : signal_index + 1]["high"].max())
    structure_low = float(frame.iloc[mother_index : signal_index + 1]["low"].min())
    broke_low = bool((between["low"] < mother_low).any())
    broke_high = bool((between["high"] > mother_high).any())
    if broke_low and broke_high:
        return None
    close_inside = _close_inside_mother(signal, mother_high, mother_low)
    if not close_inside:
        return None

    side = 0
    breakout_side = ""
    if broke_low and bool(signal["is_bullish_bar"]):
        side = 1
        breakout_side = "below_mother_low"
    elif broke_high and bool(signal["is_bearish_bar"]):
        side = -1
        breakout_side = "above_mother_high"
    if side == 0:
        return None
    if require_context:
        if require_first_retracement_context:
            if not trend_context_ok(
                frame,
                side=side,
                mother_index=mother_index,
                signal_index=signal_index,
                structure_low=structure_low,
                structure_high=structure_high,
                buffer_atr=sma_touch_buffer_atr,
                lookback_bars=context_lookback_bars,
                min_impulse_atr=min_impulse_atr,
                prior_pullback_atr=prior_pullback_atr,
                min_context_zone_buffer_atr=min_context_zone_buffer_atr,
                trend_side_lookback_bars=trend_side_lookback_bars,
                min_trend_side_ratio=min_trend_side_ratio,
                min_anchor_efficiency=min_anchor_efficiency,
                min_pre_mother_retrace_atr=min_pre_mother_retrace_atr,
                min_pre_mother_retrace_bars=min_pre_mother_retrace_bars,
                prior_price_action_mode=prior_price_action_mode,
                min_prior_impulse_bars=min_prior_impulse_bars,
                min_prior_swing_progress_atr=min_prior_swing_progress_atr,
                min_prior_close_progress_atr=min_prior_close_progress_atr,
                min_prior_retrace_close_atr=min_prior_retrace_close_atr,
                min_prior_directional_close_ratio=min_prior_directional_close_ratio,
                max_prior_retrace_fraction=max_prior_retrace_fraction,
                min_sma_slope_atr=min_sma_slope_atr,
                recent_progress_lookback_bars=recent_progress_lookback_bars,
                max_anchor_bars_without_recent_progress=max_anchor_bars_without_recent_progress,
                min_recent_progress_atr=min_recent_progress_atr,
            ):
                return None
        elif not context_ok(
            signal,
            side=side,
            structure_low=structure_low,
            structure_high=structure_high,
            buffer_atr=sma_touch_buffer_atr,
        ):
            return None
    return ForceStrikeSignal(
        symbol=str(signal["symbol"]),
        timeframe=str(signal["timeframe"]),
        side=side,
        mother_index=mother_index,
        signal_index=signal_index,
        mother_time_utc=str(mother["time_utc"]),
        signal_time_utc=str(signal["time_utc"]),
        mother_high=mother_high,
        mother_low=mother_low,
        structure_high=structure_high,
        structure_low=structure_low,
        total_bars=int(signal_index - mother_index + 1),
        breakout_side=breakout_side,
    )


def detect_force_strikes(
    frame: pd.DataFrame,
    *,
    min_total_bars: int = 3,
    max_total_bars: int = 6,
    require_context: bool = True,
    require_first_retracement_context: bool = True,
    sma_touch_buffer_atr: float = 0.0,
    context_lookback_bars: int = 120,
    min_impulse_atr: float = 1.5,
    prior_pullback_atr: float = 1.0,
    min_context_zone_buffer_atr: float = 0.5,
    trend_side_lookback_bars: int = 24,
    min_trend_side_ratio: float = 0.45,
    min_anchor_efficiency: float = 0.22,
    min_pre_mother_retrace_atr: float = 0.75,
    min_pre_mother_retrace_bars: int = 1,
    prior_price_action_mode: str = "legacy",
    min_prior_impulse_bars: int = 2,
    min_prior_swing_progress_atr: float = 1.0,
    min_prior_close_progress_atr: float = 0.5,
    min_prior_retrace_close_atr: float = 0.25,
    min_prior_directional_close_ratio: float = 0.45,
    max_prior_retrace_fraction: float = 1.0,
    min_sma_slope_atr: float = 0.0,
    recent_progress_lookback_bars: int = 12,
    max_anchor_bars_without_recent_progress: int = 12,
    min_recent_progress_atr: float = -0.25,
) -> list[ForceStrikeSignal]:
    """Detect Force Strike signals with no lookahead beyond each signal bar."""

    if max_total_bars < min_total_bars:
        raise ValueError("max_total_bars must be >= min_total_bars.")
    signals: list[ForceStrikeSignal] = []
    data = frame.sort_values("time_utc").reset_index(drop=True)
    last_mother = len(data) - min_total_bars
    for mother_index in range(max(last_mother + 1, 0)):
        mother = data.iloc[mother_index]
        mother_high = float(mother["high"])
        mother_low = float(mother["low"])
        first_baby_index = mother_index + 1
        if first_baby_index >= len(data):
            continue
        if not _inside_mother(data.iloc[first_baby_index], mother_high, mother_low):
            continue
        max_signal_index = min(mother_index + max_total_bars - 1, len(data) - 1)
        for signal_index in range(mother_index + min_total_bars - 1, max_signal_index + 1):
            signal = _signal_from_window(
                data,
                mother_index=mother_index,
                signal_index=signal_index,
                require_context=require_context,
                require_first_retracement_context=require_first_retracement_context,
                sma_touch_buffer_atr=sma_touch_buffer_atr,
                context_lookback_bars=context_lookback_bars,
                min_impulse_atr=min_impulse_atr,
                prior_pullback_atr=prior_pullback_atr,
                min_context_zone_buffer_atr=min_context_zone_buffer_atr,
                trend_side_lookback_bars=trend_side_lookback_bars,
                min_trend_side_ratio=min_trend_side_ratio,
                min_anchor_efficiency=min_anchor_efficiency,
                min_pre_mother_retrace_atr=min_pre_mother_retrace_atr,
                min_pre_mother_retrace_bars=min_pre_mother_retrace_bars,
                prior_price_action_mode=prior_price_action_mode,
                min_prior_impulse_bars=min_prior_impulse_bars,
                min_prior_swing_progress_atr=min_prior_swing_progress_atr,
                min_prior_close_progress_atr=min_prior_close_progress_atr,
                min_prior_retrace_close_atr=min_prior_retrace_close_atr,
                min_prior_directional_close_ratio=min_prior_directional_close_ratio,
                max_prior_retrace_fraction=max_prior_retrace_fraction,
                min_sma_slope_atr=min_sma_slope_atr,
                recent_progress_lookback_bars=recent_progress_lookback_bars,
                max_anchor_bars_without_recent_progress=max_anchor_bars_without_recent_progress,
                min_recent_progress_atr=min_recent_progress_atr,
            )
            if signal is not None:
                signals.append(signal)
                break
    return signals
