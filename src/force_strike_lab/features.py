"""Feature engineering for Force Strike pattern research."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyGridConfig


def infer_point_size(frame: pd.DataFrame) -> float:
    """Infer a practical point size from displayed OHLC decimals."""

    values = frame[["open", "high", "low", "close"]].stack().dropna()
    if values.empty:
        return 0.00001
    max_decimals = 0
    for value in values.head(500).astype(float):
        text = f"{value:.10f}".rstrip("0").rstrip(".")
        if "." in text:
            max_decimals = max(max_decimals, len(text.split(".", maxsplit=1)[1]))
    return float(10 ** (-max_decimals)) if max_decimals > 0 else 1.0


def true_range(frame: pd.DataFrame) -> pd.Series:
    """Compute true range from OHLC data."""

    prev_close = frame["close"].shift(1)
    return pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def build_features(
    frame: pd.DataFrame,
    strategy: StrategyGridConfig,
    *,
    point_size: float | None = None,
    fallback_spread_points: float = 0.0,
) -> pd.DataFrame:
    """Return OHLC features used by the Force Strike detector and backtester."""

    data = frame.copy()
    data["time_utc"] = pd.to_datetime(data["time_utc"], utc=True)
    data = data.sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)
    data["point"] = infer_point_size(data) if point_size is None or point_size <= 0 else float(point_size)
    spread = pd.to_numeric(data.get("spread_points"), errors="coerce")
    data["spread_points_effective"] = spread.where(spread > 0, float(fallback_spread_points)).fillna(float(fallback_spread_points))
    data["spread_price"] = data["spread_points_effective"] * data["point"]
    data["range"] = data["high"] - data["low"]
    data["close_location"] = np.where(data["range"] > 0, (data["close"] - data["low"]) / data["range"], 0.5)
    data["is_bullish_bar"] = (data["range"] > 0) & (data["close_location"] >= (2.0 / 3.0))
    data["is_bearish_bar"] = (data["range"] > 0) & (data["close_location"] <= (1.0 / 3.0))
    data["body"] = (data["close"] - data["open"]).abs()
    data["upper_wick"] = data["high"] - data[["open", "close"]].max(axis=1)
    data["lower_wick"] = data[["open", "close"]].min(axis=1) - data["low"]
    tr = true_range(data)
    data["atr"] = tr.rolling(int(strategy.atr_window)).mean()
    data["sma_fast"] = data["close"].rolling(int(strategy.sma_fast)).mean()
    data["sma_slow"] = data["close"].rolling(int(strategy.sma_slow)).mean()
    data["year_utc"] = data["time_utc"].dt.year.astype(int)
    return data


def context_ok(row: pd.Series, *, side: int, structure_low: float, structure_high: float, buffer_atr: float) -> bool:
    """Return whether the 20/50 SMA trend-retracement context is satisfied."""

    atr = float(row.get("atr", np.nan))
    sma_fast = float(row.get("sma_fast", np.nan))
    sma_slow = float(row.get("sma_slow", np.nan))
    close = float(row.get("close", np.nan))
    if not np.isfinite(atr) or atr <= 0 or not np.isfinite(sma_fast) or not np.isfinite(sma_slow):
        return False
    buffer = float(buffer_atr) * atr
    zone_low = min(sma_fast, sma_slow)
    zone_high = max(sma_fast, sma_slow)
    overlaps_zone = (float(structure_low) <= zone_high + buffer) and (float(structure_high) >= zone_low - buffer)
    if side > 0:
        return bool(sma_fast > sma_slow and close >= zone_low - buffer and overlaps_zone)
    return bool(sma_fast < sma_slow and close <= zone_high + buffer and overlaps_zone)


def trend_context_ok(
    frame: pd.DataFrame,
    *,
    side: int,
    mother_index: int,
    signal_index: int,
    structure_low: float,
    structure_high: float,
    buffer_atr: float,
    lookback_bars: int,
    min_impulse_atr: float,
    prior_pullback_atr: float,
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
) -> bool:
    """Return whether the setup has clear trend-following 50 SMA context."""

    if mother_index <= 0 or signal_index >= len(frame):
        return False
    signal = frame.iloc[signal_index]
    zone_buffer_atr = max(float(buffer_atr), float(min_context_zone_buffer_atr))
    if not context_ok(
        signal,
        side=side,
        structure_low=structure_low,
        structure_high=structure_high,
        buffer_atr=zone_buffer_atr,
    ):
        return False

    atr = float(signal.get("atr", np.nan))
    if not np.isfinite(atr) or atr <= 0:
        return False
    anchor_index = _find_current_sma50_anchor(
        frame,
        side=side,
        mother_index=mother_index,
        lookback_bars=lookback_bars,
    )
    if anchor_index is None or anchor_index >= mother_index:
        return False

    anchor = frame.iloc[anchor_index]
    anchor_close = float(anchor.get("close", np.nan))
    anchor_sma = float(anchor.get("sma_slow", np.nan))
    signal_sma = float(signal.get("sma_slow", np.nan))
    if not np.isfinite(anchor_close) or not np.isfinite(anchor_sma) or not np.isfinite(signal_sma):
        return False

    impulse = frame.iloc[anchor_index : mother_index + 1]
    min_impulse = float(min_impulse_atr) * atr
    if side > 0:
        peak = float(impulse["high"].max())
        if anchor_close >= float(structure_low):
            return False
        if peak - anchor_close < min_impulse:
            return False
        sma_slope_atr = (signal_sma - anchor_sma) / atr
        if not _sma_slope_passes(sma_slope_atr, min_sma_slope_atr):
            return False
    else:
        trough = float(impulse["low"].min())
        if anchor_close <= float(structure_high):
            return False
        if anchor_close - trough < min_impulse:
            return False
        sma_slope_atr = (anchor_sma - signal_sma) / atr
        if not _sma_slope_passes(sma_slope_atr, min_sma_slope_atr):
            return False

    del prior_pullback_atr
    if not _trend_has_enough_directional_quality(
        frame,
        side=side,
        anchor_index=anchor_index,
        mother_index=mother_index,
        atr=atr,
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
        recent_progress_lookback_bars=recent_progress_lookback_bars,
        max_anchor_bars_without_recent_progress=max_anchor_bars_without_recent_progress,
        min_recent_progress_atr=min_recent_progress_atr,
    ):
        return False
    return True


def _find_current_sma50_anchor(
    frame: pd.DataFrame,
    *,
    side: int,
    mother_index: int,
    lookback_bars: int,
) -> int | None:
    start_index = max(0, mother_index - int(lookback_bars))
    last_opposite_index: int | None = None
    for index in range(start_index, mother_index):
        row = frame.iloc[index]
        close = float(row.get("close", np.nan))
        sma_slow = float(row.get("sma_slow", np.nan))
        if not np.isfinite(close) or not np.isfinite(sma_slow):
            continue
        if side > 0 and close <= sma_slow:
            last_opposite_index = index
        elif side < 0 and close >= sma_slow:
            last_opposite_index = index

    if last_opposite_index is None:
        return None
    for index in range(last_opposite_index + 1, mother_index + 1):
        row = frame.iloc[index]
        close = float(row.get("close", np.nan))
        sma_slow = float(row.get("sma_slow", np.nan))
        if not np.isfinite(close) or not np.isfinite(sma_slow):
            continue
        if side > 0 and close > sma_slow:
            return index
        if side < 0 and close < sma_slow:
            return index
    return None


def _sma_slope_passes(sma_slope_atr: float, min_sma_slope_atr: float) -> bool:
    if not np.isfinite(sma_slope_atr):
        return False
    threshold = float(min_sma_slope_atr)
    if threshold <= 0:
        return bool(sma_slope_atr > 0)
    return bool(sma_slope_atr >= threshold)


def _has_prior_completed_retracement(
    frame: pd.DataFrame,
    *,
    side: int,
    anchor_index: int,
    mother_index: int,
    threshold: float,
) -> bool:
    if mother_index - anchor_index <= 2:
        return False
    threshold = max(float(threshold), 0.0)
    if side > 0:
        running_high = float(frame.iloc[anchor_index]["high"])
        pullback_peak: float | None = None
        for index in range(anchor_index + 1, mother_index + 1):
            row = frame.iloc[index]
            high = float(row["high"])
            low = float(row["low"])
            if pullback_peak is None:
                running_high = max(running_high, high)
                if running_high - low >= threshold:
                    pullback_peak = running_high
            elif high > pullback_peak:
                return True
        return False

    running_low = float(frame.iloc[anchor_index]["low"])
    pullback_trough: float | None = None
    for index in range(anchor_index + 1, mother_index + 1):
        row = frame.iloc[index]
        high = float(row["high"])
        low = float(row["low"])
        if pullback_trough is None:
            running_low = min(running_low, low)
            if high - running_low >= threshold:
                pullback_trough = running_low
        elif low < pullback_trough:
            return True
    return False


def _trend_has_enough_directional_quality(
    frame: pd.DataFrame,
    *,
    side: int,
    anchor_index: int,
    mother_index: int,
    atr: float,
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
    recent_progress_lookback_bars: int,
    max_anchor_bars_without_recent_progress: int,
    min_recent_progress_atr: float,
) -> bool:
    impulse = frame.iloc[anchor_index : mother_index + 1]
    if impulse.empty:
        return False
    anchor_close = float(impulse.iloc[0]["close"])
    mother_close = float(impulse.iloc[-1]["close"])
    impulse_range = float(impulse["high"].max() - impulse["low"].min())
    if impulse_range <= 0:
        return False
    anchor_efficiency = abs(mother_close - anchor_close) / impulse_range
    if anchor_efficiency < float(min_anchor_efficiency):
        return False

    lookback_start = max(0, mother_index - int(trend_side_lookback_bars))
    trend_window = frame.iloc[lookback_start : mother_index + 1]
    if trend_window.empty:
        return False
    if side > 0:
        trend_side_count = int((trend_window["close"] > trend_window["sma_slow"]).sum())
    else:
        trend_side_count = int((trend_window["close"] < trend_window["sma_slow"]).sum())
    if trend_side_count / len(trend_window) < float(min_trend_side_ratio):
        return False

    retrace_atr, retrace_bars = _pre_mother_retracement_leg(
        frame,
        side=side,
        anchor_index=anchor_index,
        mother_index=mother_index,
        atr=atr,
    )
    if retrace_atr < float(min_pre_mother_retrace_atr):
        return False
    if retrace_bars < int(min_pre_mother_retrace_bars):
        return False

    if str(prior_price_action_mode).lower() == "swing_retrace_v1" and not _prior_swing_retrace_ok(
        frame,
        side=side,
        anchor_index=anchor_index,
        mother_index=mother_index,
        atr=atr,
        min_impulse_bars=min_prior_impulse_bars,
        min_swing_progress_atr=min_prior_swing_progress_atr,
        min_close_progress_atr=min_prior_close_progress_atr,
        min_retrace_close_atr=min_prior_retrace_close_atr,
        min_directional_close_ratio=min_prior_directional_close_ratio,
        min_retrace_atr=min_pre_mother_retrace_atr,
        min_retrace_bars=min_pre_mother_retrace_bars,
        max_retrace_fraction=max_prior_retrace_fraction,
    ):
        return False

    if mother_index - anchor_index > int(max_anchor_bars_without_recent_progress):
        recent_start = max(0, mother_index - int(recent_progress_lookback_bars))
        recent = frame.iloc[recent_start : mother_index + 1]
        if recent.empty:
            return False
        recent_net_atr = (float(recent.iloc[-1]["close"]) - float(recent.iloc[0]["close"])) * int(side) / float(atr)
        if recent_net_atr < float(min_recent_progress_atr):
            return False
    return True


def _prior_swing_retrace_ok(
    frame: pd.DataFrame,
    *,
    side: int,
    anchor_index: int,
    mother_index: int,
    atr: float,
    min_impulse_bars: int,
    min_swing_progress_atr: float,
    min_close_progress_atr: float,
    min_retrace_close_atr: float,
    min_directional_close_ratio: float,
    min_retrace_atr: float,
    min_retrace_bars: int,
    max_retrace_fraction: float,
) -> bool:
    """Return whether prior price action has a clean impulse then pullback.

    Bullish means a prior upside swing from the 50-SMA anchor into a pre-mother
    high, followed by downside retracement before the mother bar. Bearish uses
    the mirrored downside swing and upside retracement.
    """

    if atr <= 0 or mother_index - anchor_index <= 1:
        return False
    pre_mother = frame.iloc[anchor_index:mother_index]
    if len(pre_mother) < 2:
        return False

    anchor_close = float(frame.iloc[anchor_index]["close"])
    if side > 0:
        extreme_index = int(pre_mother["high"].idxmax())
        extreme_price = float(pre_mother.loc[extreme_index, "high"])
        extreme_close = float(pre_mother.loc[extreme_index, "close"])
    else:
        extreme_index = int(pre_mother["low"].idxmin())
        extreme_price = float(pre_mother.loc[extreme_index, "low"])
        extreme_close = float(pre_mother.loc[extreme_index, "close"])

    impulse_bars = int(extreme_index - anchor_index)
    retrace_bars = int(mother_index - extreme_index - 1)
    if impulse_bars < int(min_impulse_bars):
        return False
    if retrace_bars < int(min_retrace_bars):
        return False

    swing_progress_atr = (extreme_price - anchor_close) * int(side) / float(atr)
    close_progress_atr = (extreme_close - anchor_close) * int(side) / float(atr)
    if swing_progress_atr < float(min_swing_progress_atr):
        return False
    if close_progress_atr < float(min_close_progress_atr):
        return False

    impulse_leg = frame.iloc[anchor_index : extreme_index + 1]["close"].astype(float)
    directional_moves = (impulse_leg.diff() * int(side)).dropna()
    if directional_moves.empty:
        return False
    directional_ratio = float((directional_moves > 0).sum() / len(directional_moves))
    if directional_ratio < float(min_directional_close_ratio):
        return False

    retrace_atr, _ = _pre_mother_retracement_leg(
        frame,
        side=side,
        anchor_index=anchor_index,
        mother_index=mother_index,
        atr=atr,
    )
    if retrace_atr < float(min_retrace_atr):
        return False
    after_extreme = frame.iloc[extreme_index + 1 : mother_index]
    if min_retrace_close_atr > 0:
        if after_extreme.empty:
            return False
        if side > 0:
            retrace_close_atr = (extreme_close - float(after_extreme["close"].min())) / float(atr)
        else:
            retrace_close_atr = (float(after_extreme["close"].max()) - extreme_close) / float(atr)
        if retrace_close_atr < float(min_retrace_close_atr):
            return False
    if max_retrace_fraction > 0 and swing_progress_atr > 0:
        if retrace_atr / swing_progress_atr > float(max_retrace_fraction):
            return False
    return True


def _pre_mother_retracement_leg(
    frame: pd.DataFrame,
    *,
    side: int,
    anchor_index: int,
    mother_index: int,
    atr: float,
) -> tuple[float, int]:
    if atr <= 0 or mother_index - anchor_index <= 1:
        return 0.0, 0
    pre_mother = frame.iloc[anchor_index:mother_index]
    if len(pre_mother) < 2:
        return 0.0, 0
    if side > 0:
        extreme_index = int(pre_mother["high"].idxmax())
        after_extreme = frame.iloc[extreme_index + 1 : mother_index]
        if after_extreme.empty:
            return 0.0, 0
        retrace_atr = (float(pre_mother["high"].max()) - float(after_extreme["low"].min())) / float(atr)
    else:
        extreme_index = int(pre_mother["low"].idxmin())
        after_extreme = frame.iloc[extreme_index + 1 : mother_index]
        if after_extreme.empty:
            return 0.0, 0
        retrace_atr = (float(after_extreme["high"].max()) - float(pre_mother["low"].min())) / float(atr)
    return float(max(retrace_atr, 0.0)), int(mother_index - extreme_index - 1)
