"""Research orchestration for Force Strike candidates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .analytics import candidate_summary, render_markdown_report, rolling_summary, trades_to_frame, yearly_summary
from .backtest import run_backtest
from .config import ResearchConfig
from .data import load_rates_csv, manifest_path
from .features import build_features
from .mt5_data import pull_mt5_data
from .strategy import detect_force_strikes, generate_candidates


def _load_manifest(root: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    path = manifest_path(root, symbol, timeframe)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _point_from_manifest(manifest: dict[str, Any]) -> float | None:
    capabilities = dict(manifest.get("capabilities", {}))
    point = capabilities.get("point")
    if point is None:
        return None
    try:
        return float(point)
    except (TypeError, ValueError):
        return None


def _commission_from_manifest(manifest: dict[str, Any], fallback: float) -> float:
    estimate = dict(manifest.get("commission_estimate", {}))
    value = estimate.get("round_turn_commission_points")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return parsed if parsed > 0 else float(fallback)


def _report_root(project_root: Path, config: ResearchConfig) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return project_root / config.report_dir / config.timeframe / stamp


def run_research(
    config: ResearchConfig,
    *,
    project_root: str | Path,
    pull_first: bool = False,
) -> dict[str, Any]:
    """Run the full Force Strike candidate grid."""

    root = Path(project_root)
    if pull_first:
        pull_mt5_data(config, project_root=root)

    candidates = generate_candidates(config.strategy)
    all_trades = []
    signal_counts: dict[str, int] = {candidate.candidate_id: 0 for candidate in candidates}
    pending_counts: dict[str, int] = {candidate.candidate_id: 0 for candidate in candidates}
    skipped_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for symbol in config.symbols:
        data_root = root / config.data_dir
        manifest = _load_manifest(data_root, symbol, config.timeframe)
        frame = load_rates_csv(data_root, symbol=symbol, timeframe=config.timeframe)
        point = _point_from_manifest(manifest)
        featured = build_features(
            frame,
            config.strategy,
            point_size=point,
            fallback_spread_points=config.costs.fallback_spread_points,
        )
        symbol_costs = config.costs.__class__(
            fallback_spread_points=config.costs.fallback_spread_points,
            fallback_commission_points=_commission_from_manifest(manifest, config.costs.fallback_commission_points),
            entry_slippage_points=config.costs.entry_slippage_points,
            exit_slippage_points=config.costs.exit_slippage_points,
        )
        coverage_rows.append(
            {
                "symbol": symbol,
                "timeframe": config.timeframe,
                "rows": int(len(featured)),
                "coverage_start_utc": str(featured["time_utc"].iloc[0]) if not featured.empty else None,
                "coverage_end_utc": str(featured["time_utc"].iloc[-1]) if not featured.empty else None,
                "point": float(featured["point"].iloc[0]) if not featured.empty else None,
                "commission_points": symbol_costs.fallback_commission_points,
            }
        )
        signal_cache = {
            float(buffer): detect_force_strikes(
                featured,
                min_total_bars=config.strategy.min_total_bars,
                max_total_bars=config.strategy.max_total_bars,
                require_context=True,
                require_first_retracement_context=config.strategy.require_first_retracement_context,
                sma_touch_buffer_atr=float(buffer),
                context_lookback_bars=config.strategy.context_lookback_bars,
                min_impulse_atr=config.strategy.min_impulse_atr,
                prior_pullback_atr=config.strategy.prior_pullback_atr,
                min_context_zone_buffer_atr=config.strategy.min_context_zone_buffer_atr,
                trend_side_lookback_bars=config.strategy.trend_side_lookback_bars,
                min_trend_side_ratio=config.strategy.min_trend_side_ratio,
                min_anchor_efficiency=config.strategy.min_anchor_efficiency,
                min_pre_mother_retrace_atr=config.strategy.min_pre_mother_retrace_atr,
                min_pre_mother_retrace_bars=config.strategy.min_pre_mother_retrace_bars,
                prior_price_action_mode=config.strategy.prior_price_action_mode,
                min_prior_impulse_bars=config.strategy.min_prior_impulse_bars,
                min_prior_swing_progress_atr=config.strategy.min_prior_swing_progress_atr,
                min_prior_close_progress_atr=config.strategy.min_prior_close_progress_atr,
                min_prior_retrace_close_atr=config.strategy.min_prior_retrace_close_atr,
                min_prior_directional_close_ratio=config.strategy.min_prior_directional_close_ratio,
                max_prior_retrace_fraction=config.strategy.max_prior_retrace_fraction,
                min_sma_slope_atr=config.strategy.min_sma_slope_atr,
                recent_progress_lookback_bars=config.strategy.recent_progress_lookback_bars,
                max_anchor_bars_without_recent_progress=config.strategy.max_anchor_bars_without_recent_progress,
                min_recent_progress_atr=config.strategy.min_recent_progress_atr,
            )
            for buffer in sorted({candidate.sma_touch_buffer_atr for candidate in candidates})
        }
        for candidate in candidates:
            result = run_backtest(
                featured,
                candidate=candidate,
                strategy_config=config.strategy,
                costs=symbol_costs,
                precomputed_signals=signal_cache[float(candidate.sma_touch_buffer_atr)],
            )
            signal_counts[candidate.candidate_id] += len(result.signals)
            pending_counts[candidate.candidate_id] += result.pending_cancelled
            skipped_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "symbol": symbol,
                    "signals": len(result.signals),
                    "trades": len(result.trades),
                    "pending_cancelled": result.pending_cancelled,
                    "skipped_risk": result.skipped_risk,
                    "skipped_next_open_outside": result.skipped_next_open_outside,
                }
            )
            all_trades.extend(result.trades)

    trades_frame = trades_to_frame(all_trades)
    summary = candidate_summary(trades_frame, signal_counts=signal_counts, pending_counts=pending_counts)
    yearly = yearly_summary(trades_frame)
    rolling = rolling_summary(trades_frame)
    skipped = pd.DataFrame(skipped_rows)
    coverage = pd.DataFrame(coverage_rows)

    output_root = _report_root(root, config)
    output_root.mkdir(parents=True, exist_ok=True)
    trades_path = output_root / "trades.csv"
    summary_path = output_root / "candidate_summary.csv"
    yearly_path = output_root / "yearly_summary.csv"
    rolling_path = output_root / "rolling_summary.csv"
    skipped_path = output_root / "signal_funnel.csv"
    coverage_path = output_root / "coverage.csv"
    config_path = output_root / "config_used.json"
    report_path = output_root / "report.md"

    trades_frame.to_csv(trades_path, index=False)
    summary.to_csv(summary_path, index=False)
    yearly.to_csv(yearly_path, index=False)
    rolling.to_csv(rolling_path, index=False)
    skipped.to_csv(skipped_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    config_path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    report = render_markdown_report(
        title=f"Force Strike {config.timeframe} Research",
        summary=summary,
        output_files={
            "trades": str(trades_path),
            "candidate_summary": str(summary_path),
            "yearly_summary": str(yearly_path),
            "rolling_summary": str(rolling_path),
            "signal_funnel": str(skipped_path),
            "coverage": str(coverage_path),
        },
    )
    report_path.write_text(report, encoding="utf-8")

    latest_root = root / config.report_dir / config.timeframe / "latest"
    latest_root.mkdir(parents=True, exist_ok=True)
    for source in (trades_path, summary_path, yearly_path, rolling_path, skipped_path, coverage_path, config_path, report_path):
        target = latest_root / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "output_root": str(output_root),
        "latest_root": str(latest_root),
        "report_path": str(report_path),
        "candidate_count": len(candidates),
        "trade_count": int(len(trades_frame)),
        "top_candidate": None if summary.empty else str(summary.iloc[0]["candidate_id"]),
    }
