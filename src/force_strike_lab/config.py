"""Config loading for Force Strike research runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .timeframes import get_timeframe_spec, normalize_timeframe


@dataclass(frozen=True)
class CostConfig:
    fallback_spread_points: float = 10.0
    fallback_commission_points: float = 0.0
    entry_slippage_points: float = 0.0
    exit_slippage_points: float = 0.0


@dataclass(frozen=True)
class StrategyGridConfig:
    min_total_bars: int = 3
    max_total_bars: int = 6
    atr_window: int = 14
    sma_fast: int = 20
    sma_slow: int = 50
    require_first_retracement_context: bool = True
    context_lookback_bars: int = 120
    min_impulse_atr: float = 1.5
    prior_pullback_atr: float = 1.0
    min_context_zone_buffer_atr: float = 0.5
    trend_side_lookback_bars: int = 24
    min_trend_side_ratio: float = 0.45
    min_anchor_efficiency: float = 0.22
    min_pre_mother_retrace_atr: float = 0.75
    min_pre_mother_retrace_bars: int = 1
    prior_price_action_mode: str = "legacy"
    min_prior_impulse_bars: int = 2
    min_prior_swing_progress_atr: float = 1.0
    min_prior_close_progress_atr: float = 0.5
    min_prior_retrace_close_atr: float = 0.25
    min_prior_directional_close_ratio: float = 0.45
    max_prior_retrace_fraction: float = 1.0
    min_sma_slope_atr: float = 0.0
    recent_progress_lookback_bars: int = 12
    max_anchor_bars_without_recent_progress: int = 12
    min_recent_progress_atr: float = -0.25
    max_risk_atr: float = 1.25
    stop_models: list[str] = field(default_factory=lambda: ["structure", "atr", "wider"])
    target_rs: list[float] = field(default_factory=lambda: [1.0, 1.25, 1.5, 2.0, 2.5])
    sma_touch_buffer_atrs: list[float] = field(default_factory=lambda: [0.0, 0.25, 0.5])
    structure_stop_buffer_atr: float = 0.0


@dataclass(frozen=True)
class ResearchConfig:
    project_name: str
    symbols: list[str]
    timeframe: str
    history_years: int | None
    date_start_utc: str | None
    date_end_utc: str | None
    data_dir: str
    report_dir: str
    costs: CostConfig
    strategy: StrategyGridConfig

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_float_list(values: list[Any]) -> list[float]:
    return [float(value) for value in values]


def load_config(path: str | Path) -> ResearchConfig:
    """Load and validate a Force Strike research config."""

    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    timeframe = normalize_timeframe(str(payload.get("timeframe", "M30")))
    spec = get_timeframe_spec(timeframe)
    symbols = [str(symbol).upper() for symbol in payload.get("symbols", [])]
    if not symbols:
        raise ValueError("Config must contain at least one symbol.")

    costs_payload = dict(payload.get("costs", {}))
    strategy_payload = dict(payload.get("strategy", {}))
    strategy = StrategyGridConfig(
        min_total_bars=int(strategy_payload.get("min_total_bars", 3)),
        max_total_bars=int(strategy_payload.get("max_total_bars", 6)),
        atr_window=int(strategy_payload.get("atr_window", 14)),
        sma_fast=int(strategy_payload.get("sma_fast", 20)),
        sma_slow=int(strategy_payload.get("sma_slow", 50)),
        require_first_retracement_context=bool(strategy_payload.get("require_first_retracement_context", True)),
        context_lookback_bars=int(strategy_payload.get("context_lookback_bars", 120)),
        min_impulse_atr=float(strategy_payload.get("min_impulse_atr", 1.5)),
        prior_pullback_atr=float(strategy_payload.get("prior_pullback_atr", 1.0)),
        min_context_zone_buffer_atr=float(strategy_payload.get("min_context_zone_buffer_atr", 0.5)),
        trend_side_lookback_bars=int(strategy_payload.get("trend_side_lookback_bars", 24)),
        min_trend_side_ratio=float(strategy_payload.get("min_trend_side_ratio", 0.45)),
        min_anchor_efficiency=float(strategy_payload.get("min_anchor_efficiency", 0.22)),
        min_pre_mother_retrace_atr=float(strategy_payload.get("min_pre_mother_retrace_atr", 0.75)),
        min_pre_mother_retrace_bars=int(strategy_payload.get("min_pre_mother_retrace_bars", 1)),
        prior_price_action_mode=str(strategy_payload.get("prior_price_action_mode", "legacy")).lower(),
        min_prior_impulse_bars=int(strategy_payload.get("min_prior_impulse_bars", 2)),
        min_prior_swing_progress_atr=float(strategy_payload.get("min_prior_swing_progress_atr", 1.0)),
        min_prior_close_progress_atr=float(strategy_payload.get("min_prior_close_progress_atr", 0.5)),
        min_prior_retrace_close_atr=float(strategy_payload.get("min_prior_retrace_close_atr", 0.25)),
        min_prior_directional_close_ratio=float(strategy_payload.get("min_prior_directional_close_ratio", 0.45)),
        max_prior_retrace_fraction=float(strategy_payload.get("max_prior_retrace_fraction", 1.0)),
        min_sma_slope_atr=float(strategy_payload.get("min_sma_slope_atr", 0.0)),
        recent_progress_lookback_bars=int(strategy_payload.get("recent_progress_lookback_bars", 12)),
        max_anchor_bars_without_recent_progress=int(strategy_payload.get("max_anchor_bars_without_recent_progress", 12)),
        min_recent_progress_atr=float(strategy_payload.get("min_recent_progress_atr", -0.25)),
        max_risk_atr=float(strategy_payload.get("max_risk_atr", 1.25)),
        stop_models=[str(value).lower() for value in strategy_payload.get("stop_models", ["structure", "atr", "wider"])],
        target_rs=_as_float_list(strategy_payload.get("target_rs", [1.0, 1.25, 1.5, 2.0, 2.5])),
        sma_touch_buffer_atrs=_as_float_list(strategy_payload.get("sma_touch_buffer_atrs", [0.0, 0.25, 0.5])),
        structure_stop_buffer_atr=float(strategy_payload.get("structure_stop_buffer_atr", 0.0)),
    )
    if strategy.min_total_bars < 3:
        raise ValueError("min_total_bars must be at least 3.")
    if strategy.max_total_bars < strategy.min_total_bars:
        raise ValueError("max_total_bars must be >= min_total_bars.")
    if strategy.max_total_bars > 6:
        raise ValueError("V1 supports max_total_bars up to 6.")
    if strategy.context_lookback_bars < strategy.max_total_bars:
        raise ValueError("context_lookback_bars must be at least max_total_bars.")
    if strategy.min_impulse_atr < 0:
        raise ValueError("min_impulse_atr must be non-negative.")
    if strategy.prior_pullback_atr < 0:
        raise ValueError("prior_pullback_atr must be non-negative.")
    if strategy.min_context_zone_buffer_atr < 0:
        raise ValueError("min_context_zone_buffer_atr must be non-negative.")
    if strategy.trend_side_lookback_bars < 1:
        raise ValueError("trend_side_lookback_bars must be positive.")
    if not 0 <= strategy.min_trend_side_ratio <= 1:
        raise ValueError("min_trend_side_ratio must be between 0 and 1.")
    if strategy.min_anchor_efficiency < 0:
        raise ValueError("min_anchor_efficiency must be non-negative.")
    if strategy.min_pre_mother_retrace_atr < 0:
        raise ValueError("min_pre_mother_retrace_atr must be non-negative.")
    if strategy.min_pre_mother_retrace_bars < 0:
        raise ValueError("min_pre_mother_retrace_bars must be non-negative.")
    if strategy.prior_price_action_mode not in {"legacy", "swing_retrace_v1"}:
        raise ValueError("prior_price_action_mode must be 'legacy' or 'swing_retrace_v1'.")
    if strategy.min_prior_impulse_bars < 0:
        raise ValueError("min_prior_impulse_bars must be non-negative.")
    if strategy.min_prior_swing_progress_atr < 0:
        raise ValueError("min_prior_swing_progress_atr must be non-negative.")
    if strategy.min_prior_close_progress_atr < 0:
        raise ValueError("min_prior_close_progress_atr must be non-negative.")
    if strategy.min_prior_retrace_close_atr < 0:
        raise ValueError("min_prior_retrace_close_atr must be non-negative.")
    if not 0 <= strategy.min_prior_directional_close_ratio <= 1:
        raise ValueError("min_prior_directional_close_ratio must be between 0 and 1.")
    if strategy.max_prior_retrace_fraction < 0:
        raise ValueError("max_prior_retrace_fraction must be non-negative.")
    if strategy.min_sma_slope_atr < 0:
        raise ValueError("min_sma_slope_atr must be non-negative.")
    if strategy.recent_progress_lookback_bars < 1:
        raise ValueError("recent_progress_lookback_bars must be positive.")
    if strategy.max_anchor_bars_without_recent_progress < 0:
        raise ValueError("max_anchor_bars_without_recent_progress must be non-negative.")
    unsupported_stops = set(strategy.stop_models) - {"structure", "atr", "wider"}
    if unsupported_stops:
        raise ValueError(f"Unsupported stop model(s): {sorted(unsupported_stops)}")

    history_years = payload.get("history_years", spec.default_history_years)
    return ResearchConfig(
        project_name=str(payload.get("project_name", "force_strike_lab")),
        symbols=symbols,
        timeframe=timeframe,
        history_years=None if history_years in (None, "") else int(history_years),
        date_start_utc=None if payload.get("date_start_utc") in (None, "") else str(payload["date_start_utc"]),
        date_end_utc=None if payload.get("date_end_utc") in (None, "") else str(payload["date_end_utc"]),
        data_dir=str(payload.get("data_dir", "data/raw")),
        report_dir=str(payload.get("report_dir", "reports/force_strike")),
        costs=CostConfig(
            fallback_spread_points=float(costs_payload.get("fallback_spread_points", 10.0)),
            fallback_commission_points=float(costs_payload.get("fallback_commission_points", 0.0)),
            entry_slippage_points=float(costs_payload.get("entry_slippage_points", 0.0)),
            exit_slippage_points=float(costs_payload.get("exit_slippage_points", 0.0)),
        ),
        strategy=strategy,
    )
