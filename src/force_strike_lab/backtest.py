"""Sequential TP/SL-only Force Strike backtester."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import CostConfig, StrategyGridConfig
from .strategy import ForceStrikeSignal, StrategyCandidate, detect_force_strikes


@dataclass(frozen=True)
class TradeRecord:
    candidate_id: str
    symbol: str
    timeframe: str
    side: int
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_mode: str
    entry_price: float
    entry_reference_price: float
    stop_price: float
    target_price: float
    exit_price: float
    risk_distance: float
    gross_r: float
    cost_r: float
    net_r: float
    bars_held: int
    exit_reason: str
    mother_high: float
    mother_low: float
    total_bars: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    candidate: StrategyCandidate
    symbol: str
    timeframe: str
    signals: list[ForceStrikeSignal]
    trades: list[TradeRecord]
    pending_cancelled: int
    skipped_risk: int
    skipped_next_open_outside: int


def _half_spread(row: pd.Series) -> float:
    return float(row.get("spread_price", 0.0) or 0.0) / 2.0


def _entry_fill(side: int, reference_price: float, row: pd.Series, costs: CostConfig) -> float:
    slippage = float(costs.entry_slippage_points) * float(row.get("point", 0.0) or 0.0)
    if side > 0:
        return float(reference_price + _half_spread(row) + slippage)
    return float(reference_price - _half_spread(row) - slippage)


def _exit_fill(side: int, reference_price: float, row: pd.Series, costs: CostConfig) -> float:
    slippage = float(costs.exit_slippage_points) * float(row.get("point", 0.0) or 0.0)
    if side > 0:
        return float(reference_price - _half_spread(row) - slippage)
    return float(reference_price + _half_spread(row) + slippage)


def _commission_price(row: pd.Series, costs: CostConfig) -> float:
    return float(costs.fallback_commission_points) * float(row.get("point", 0.0) or 0.0)


def _structure_stop(signal: ForceStrikeSignal, row: pd.Series, side: int, buffer_atr: float) -> float:
    buffer = float(buffer_atr) * float(row["atr"])
    if side > 0:
        return float(signal.structure_low - buffer)
    return float(signal.structure_high + buffer)


def _stop_for_entry(signal: ForceStrikeSignal, row: pd.Series, candidate: StrategyCandidate, entry_ref: float) -> float:
    side = int(signal.side)
    atr = float(row["atr"])
    structure = _structure_stop(signal, row, side, candidate.structure_stop_buffer_atr)
    atr_stop = float(entry_ref - atr) if side > 0 else float(entry_ref + atr)
    if candidate.stop_model == "structure":
        return structure
    if candidate.stop_model == "atr":
        return atr_stop
    if candidate.stop_model == "wider":
        return min(structure, atr_stop) if side > 0 else max(structure, atr_stop)
    raise ValueError(f"Unsupported stop model {candidate.stop_model!r}.")


def _risk_distance(side: int, entry_ref: float, stop_price: float) -> float:
    return float(entry_ref - stop_price) if side > 0 else float(stop_price - entry_ref)


def _inside_mother_price(signal: ForceStrikeSignal, price: float) -> bool:
    return float(signal.mother_low) <= float(price) <= float(signal.mother_high)


def _target_price(side: int, entry_ref: float, stop_price: float, target_r: float) -> float:
    risk = abs(float(entry_ref) - float(stop_price))
    return float(entry_ref + risk * target_r) if side > 0 else float(entry_ref - risk * target_r)


def _bar_hits_exit(side: int, bar: pd.Series, stop_price: float, target_price: float) -> tuple[bool, bool]:
    high = float(bar["high"])
    low = float(bar["low"])
    if side > 0:
        return low <= stop_price, high >= target_price
    return high >= stop_price, low <= target_price


def _close_trade(
    *,
    candidate: StrategyCandidate,
    signal: ForceStrikeSignal,
    frame: pd.DataFrame,
    entry_index: int,
    exit_index: int,
    entry_mode: str,
    entry_ref: float,
    entry_fill: float,
    stop_price: float,
    target_price: float,
    exit_ref: float,
    exit_reason: str,
    costs: CostConfig,
) -> TradeRecord:
    side = int(signal.side)
    exit_row = frame.iloc[exit_index]
    exit_fill = _exit_fill(side, exit_ref, exit_row, costs)
    risk = abs(float(entry_ref) - float(stop_price))
    gross_r = ((exit_fill - entry_fill) / risk) if side > 0 else ((entry_fill - exit_fill) / risk)
    cost_r = _commission_price(frame.iloc[entry_index], costs) / risk if risk > 0 else 0.0
    return TradeRecord(
        candidate_id=candidate.candidate_id,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        side=side,
        signal_time_utc=signal.signal_time_utc,
        entry_time_utc=str(frame.iloc[entry_index]["time_utc"]),
        exit_time_utc=str(exit_row["time_utc"]),
        entry_mode=entry_mode,
        entry_price=float(entry_fill),
        entry_reference_price=float(entry_ref),
        stop_price=float(stop_price),
        target_price=float(target_price),
        exit_price=float(exit_fill),
        risk_distance=float(risk),
        gross_r=float(gross_r),
        cost_r=float(cost_r),
        net_r=float(gross_r - cost_r),
        bars_held=int(exit_index - entry_index + 1),
        exit_reason=exit_reason,
        mother_high=float(signal.mother_high),
        mother_low=float(signal.mother_low),
        total_bars=int(signal.total_bars),
    )


def _simulate_exit(
    *,
    candidate: StrategyCandidate,
    signal: ForceStrikeSignal,
    frame: pd.DataFrame,
    entry_index: int,
    entry_mode: str,
    entry_ref: float,
    stop_price: float,
    target_price: float,
    costs: CostConfig,
) -> tuple[TradeRecord, int]:
    side = int(signal.side)
    entry_fill = _entry_fill(side, entry_ref, frame.iloc[entry_index], costs)
    for index in range(entry_index, len(frame)):
        bar = frame.iloc[index]
        stop_hit, target_hit = _bar_hits_exit(side, bar, stop_price, target_price)
        if stop_hit:
            return (
                _close_trade(
                    candidate=candidate,
                    signal=signal,
                    frame=frame,
                    entry_index=entry_index,
                    exit_index=index,
                    entry_mode=entry_mode,
                    entry_ref=entry_ref,
                    entry_fill=entry_fill,
                    stop_price=stop_price,
                    target_price=target_price,
                    exit_ref=stop_price,
                    exit_reason="stop" if not target_hit else "same_bar_stop_priority",
                    costs=costs,
                ),
                index + 1,
            )
        if target_hit:
            return (
                _close_trade(
                    candidate=candidate,
                    signal=signal,
                    frame=frame,
                    entry_index=entry_index,
                    exit_index=index,
                    entry_mode=entry_mode,
                    entry_ref=entry_ref,
                    entry_fill=entry_fill,
                    stop_price=stop_price,
                    target_price=target_price,
                    exit_ref=target_price,
                    exit_reason="target",
                    costs=costs,
                ),
                index + 1,
            )

    final_index = len(frame) - 1
    final_close = float(frame.iloc[final_index]["close"])
    return (
        _close_trade(
            candidate=candidate,
            signal=signal,
            frame=frame,
            entry_index=entry_index,
            exit_index=final_index,
            entry_mode=entry_mode,
            entry_ref=entry_ref,
            entry_fill=entry_fill,
            stop_price=stop_price,
            target_price=target_price,
            exit_ref=final_close,
            exit_reason="end_of_data",
            costs=costs,
        ),
        len(frame),
    )


def _resolve_entry(
    *,
    frame: pd.DataFrame,
    signal: ForceStrikeSignal,
    candidate: StrategyCandidate,
) -> tuple[str, int, float, float, float] | str:
    next_index = signal.signal_index + 1
    if next_index >= len(frame):
        return "no_next_bar"
    next_row = frame.iloc[next_index]
    side = int(signal.side)
    atr = float(next_row["atr"])
    if not np.isfinite(atr) or atr <= 0:
        return "bad_atr"
    next_open = float(next_row["open"])
    if not _inside_mother_price(signal, next_open):
        return "next_open_outside"
    stop_price = _stop_for_entry(signal, next_row, candidate, next_open)
    risk = _risk_distance(side, next_open, stop_price)
    max_risk = float(candidate.max_risk_atr) * atr
    if risk <= 0:
        return "bad_risk"
    if risk <= max_risk:
        target = _target_price(side, next_open, stop_price, candidate.target_r)
        return "next_open", next_index, next_open, stop_price, target

    ideal_entry = float(stop_price + max_risk) if side > 0 else float(stop_price - max_risk)
    if not _inside_mother_price(signal, ideal_entry):
        return "risk_too_wide"
    cancel_level = _target_price(side, ideal_entry, stop_price, 1.0)
    for index in range(next_index, len(frame)):
        bar = frame.iloc[index]
        if side > 0:
            cancel_hit = float(bar["high"]) >= cancel_level
            fill_hit = float(bar["low"]) <= ideal_entry
        else:
            cancel_hit = float(bar["low"]) <= cancel_level
            fill_hit = float(bar["high"]) >= ideal_entry
        if cancel_hit:
            return "pending_cancelled"
        if fill_hit:
            stop_at_fill = _stop_for_entry(signal, bar, candidate, ideal_entry)
            risk_at_fill = _risk_distance(side, ideal_entry, stop_at_fill)
            if risk_at_fill <= 0 or risk_at_fill > max_risk:
                return "risk_too_wide"
            target = _target_price(side, ideal_entry, stop_at_fill, candidate.target_r)
            return "pullback_limit", index, ideal_entry, stop_at_fill, target
    return "pending_cancelled"


def run_backtest(
    frame: pd.DataFrame,
    *,
    candidate: StrategyCandidate,
    strategy_config: StrategyGridConfig,
    costs: CostConfig,
    precomputed_signals: list[ForceStrikeSignal] | None = None,
) -> BacktestResult:
    """Run a single candidate on one featured symbol frame."""

    data = frame.sort_values("time_utc").reset_index(drop=True)
    signals = (
        precomputed_signals
        if precomputed_signals is not None
        else detect_force_strikes(
            data,
            min_total_bars=strategy_config.min_total_bars,
            max_total_bars=strategy_config.max_total_bars,
            require_context=True,
            require_first_retracement_context=strategy_config.require_first_retracement_context,
            sma_touch_buffer_atr=candidate.sma_touch_buffer_atr,
            context_lookback_bars=strategy_config.context_lookback_bars,
            min_impulse_atr=strategy_config.min_impulse_atr,
            prior_pullback_atr=strategy_config.prior_pullback_atr,
            min_context_zone_buffer_atr=strategy_config.min_context_zone_buffer_atr,
            trend_side_lookback_bars=strategy_config.trend_side_lookback_bars,
            min_trend_side_ratio=strategy_config.min_trend_side_ratio,
            min_anchor_efficiency=strategy_config.min_anchor_efficiency,
            min_pre_mother_retrace_atr=strategy_config.min_pre_mother_retrace_atr,
            min_pre_mother_retrace_bars=strategy_config.min_pre_mother_retrace_bars,
            prior_price_action_mode=strategy_config.prior_price_action_mode,
            min_prior_impulse_bars=strategy_config.min_prior_impulse_bars,
            min_prior_swing_progress_atr=strategy_config.min_prior_swing_progress_atr,
            min_prior_close_progress_atr=strategy_config.min_prior_close_progress_atr,
            min_prior_retrace_close_atr=strategy_config.min_prior_retrace_close_atr,
            min_prior_directional_close_ratio=strategy_config.min_prior_directional_close_ratio,
            max_prior_retrace_fraction=strategy_config.max_prior_retrace_fraction,
            min_sma_slope_atr=strategy_config.min_sma_slope_atr,
            recent_progress_lookback_bars=strategy_config.recent_progress_lookback_bars,
            max_anchor_bars_without_recent_progress=strategy_config.max_anchor_bars_without_recent_progress,
            min_recent_progress_atr=strategy_config.min_recent_progress_atr,
        )
    )
    trades: list[TradeRecord] = []
    pending_cancelled = 0
    skipped_risk = 0
    skipped_next_open_outside = 0
    blocked_until_index = 0

    for signal in signals:
        if signal.signal_index < blocked_until_index:
            continue
        entry = _resolve_entry(frame=data, signal=signal, candidate=candidate)
        if isinstance(entry, str):
            if entry == "pending_cancelled":
                pending_cancelled += 1
                blocked_until_index = max(blocked_until_index, signal.signal_index + 1)
            elif entry == "next_open_outside":
                skipped_next_open_outside += 1
            elif entry in {"risk_too_wide", "bad_risk", "bad_atr"}:
                skipped_risk += 1
            continue
        entry_mode, entry_index, entry_ref, stop_price, target_price = entry
        trade, next_index = _simulate_exit(
            candidate=candidate,
            signal=signal,
            frame=data,
            entry_index=entry_index,
            entry_mode=entry_mode,
            entry_ref=entry_ref,
            stop_price=stop_price,
            target_price=target_price,
            costs=costs,
        )
        trades.append(trade)
        blocked_until_index = max(blocked_until_index, next_index)

    return BacktestResult(
        candidate=candidate,
        symbol=str(data["symbol"].iloc[0]) if not data.empty else "",
        timeframe=str(data["timeframe"].iloc[0]) if not data.empty else "",
        signals=signals,
        trades=trades,
        pending_cancelled=pending_cancelled,
        skipped_risk=skipped_risk,
        skipped_next_open_outside=skipped_next_open_outside,
    )
