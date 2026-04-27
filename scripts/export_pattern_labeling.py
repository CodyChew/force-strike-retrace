from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from force_strike_lab.config import load_config
from force_strike_lab.data import load_rates_csv
from force_strike_lab.features import build_features, context_ok, _find_current_sma50_anchor, _pre_mother_retracement_leg
from force_strike_lab.strategy import ForceStrikeSignal, detect_force_strikes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Force Strike pattern labeling charts.")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "m30_forex_basket.json"))
    parser.add_argument("--symbols", default="", help="Comma-separated subset of symbols. Defaults to config symbols.")
    parser.add_argument("--sma-buffer", type=float, default=0.25, help="Current-model SMA buffer used for accepted/rejected tag.")
    parser.add_argument("--max-per-symbol", type=int, default=20, help="Maximum scenarios per symbol.")
    parser.add_argument("--current-per-symbol", type=int, default=4, help="Current-model accepted scenarios to include per symbol when available.")
    parser.add_argument("--bars-before", type=int, default=70)
    parser.add_argument("--bars-after", type=int, default=25)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--chronological", action="store_true", help="Use earliest scenarios instead of random sampling.")
    return parser.parse_args()


def _polyline_path(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{'M' if index == 0 else 'L'}{x_pos:.2f},{y_pos:.2f}" for index, (x_pos, y_pos) in enumerate(points))


def _signal_key(signal: ForceStrikeSignal) -> tuple[int, int, int]:
    return int(signal.mother_index), int(signal.signal_index), int(signal.side)


def _sample_signals(signals: list[ForceStrikeSignal], *, max_count: int, chronological: bool, seed: int) -> list[ForceStrikeSignal]:
    if len(signals) <= max_count:
        return signals
    if chronological:
        return signals[:max_count]
    rng = random.Random(seed)
    indexes = sorted(rng.sample(range(len(signals)), max_count))
    return [signals[index] for index in indexes]


def _format_price(value: object) -> str:
    try:
        return f"{float(value):.5f}"
    except (TypeError, ValueError):
        return str(value)


def _format_metric(value: object, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _rule_summary(config, sma_buffer: float) -> list[str]:
    strategy = config.strategy
    return [
        "Bullish bar: close is in/equal to the upper third of its bar range. Bearish bar: close is in/equal to the lower third.",
        f"Formation length: {strategy.min_total_bars} to {strategy.max_total_bars} bars from mother bar through signal bar.",
        "Bar 2 must be inside/equal to the mother bar range.",
        "Bullish FS: one-sided break below mother low, then bullish close back inside mother range. Bearish FS is mirrored.",
        "If both mother high and mother low break before a valid signal, reject the formation.",
        f"Trend context: 20 SMA must be above 50 SMA for bullish, below 50 SMA for bearish; structure must overlap the 20/50 zone with max({sma_buffer:g}, {strategy.min_context_zone_buffer_atr:g}) ATR tolerance.",
        f"Trend anchor: find the latest cross to the trade side of the 50 SMA within {strategy.context_lookback_bars} bars before the mother bar.",
        "Bullish anchor close must be below the Force Strike structure; bearish anchor close must be above it.",
        f"Impulse from anchor must be at least {strategy.min_impulse_atr:g} ATR and 50 SMA slope must agree with trade direction.",
        f"Directional quality: anchor-to-mother efficiency must be >= {strategy.min_anchor_efficiency:g}; at least {strategy.min_trend_side_ratio:g} of the last {strategy.trend_side_lookback_bars} bars must close on the trend side of the 50 SMA.",
        f"Before the mother bar, price must show an opposite retracement of at least {strategy.min_pre_mother_retrace_atr:g} ATR over at least {strategy.min_pre_mother_retrace_bars} bar after the prior trend extreme.",
        f"If the anchor is older than {strategy.max_anchor_bars_without_recent_progress} bars, the last {strategy.recent_progress_lookback_bars} bars must not move more than {abs(strategy.min_recent_progress_atr):g} ATR against the trade direction.",
    ]


def _pass_item(label: str, passed: bool, value: object = None, threshold: object = None) -> dict[str, object]:
    return {"label": label, "passed": bool(passed), "value": value, "threshold": threshold}


def _compute_diagnostics(frame: pd.DataFrame, signal: ForceStrikeSignal, config, sma_buffer: float) -> dict[str, object]:
    strategy = config.strategy
    side = int(signal.side)
    signal_row = frame.iloc[int(signal.signal_index)]
    mother_index = int(signal.mother_index)
    signal_index = int(signal.signal_index)
    atr = float(signal_row.get("atr", 0.0) or 0.0)
    zone_buffer_atr = max(float(sma_buffer), float(strategy.min_context_zone_buffer_atr))
    context_pass = context_ok(
        signal_row,
        side=side,
        structure_low=float(signal.structure_low),
        structure_high=float(signal.structure_high),
        buffer_atr=zone_buffer_atr,
    )

    anchor_index = _find_current_sma50_anchor(
        frame,
        side=side,
        mother_index=mother_index,
        lookback_bars=int(strategy.context_lookback_bars),
    )
    anchor_found = anchor_index is not None and anchor_index < mother_index
    anchor_time = None
    anchor_bars = None
    anchor_close = None
    impulse_atr = None
    sma_slope_atr = None
    anchor_price_ok = False
    impulse_ok = False
    sma_slope_ok = False
    efficiency = None
    efficiency_ok = False
    trend_side_ratio = None
    trend_side_ratio_ok = False
    recent_progress_atr = None
    recent_progress_required = False
    recent_progress_ok = True
    pre_mother_retrace_atr = None
    pre_mother_retrace_bars = None
    pre_mother_retrace_ok = False

    if anchor_found:
        anchor = frame.iloc[int(anchor_index)]
        anchor_time = str(anchor["time_utc"])
        anchor_bars = mother_index - int(anchor_index)
        anchor_close = float(anchor["close"])
        anchor_sma = float(anchor["sma_slow"])
        signal_sma = float(signal_row["sma_slow"])
        impulse = frame.iloc[int(anchor_index) : mother_index + 1]
        if side > 0:
            anchor_price_ok = anchor_close < float(signal.structure_low)
            impulse_atr = (float(impulse["high"].max()) - anchor_close) / atr if atr > 0 else None
            sma_slope_atr = (signal_sma - anchor_sma) / atr if atr > 0 else None
            trend_side_count = int((frame.iloc[max(0, mother_index - int(strategy.trend_side_lookback_bars)) : mother_index + 1]["close"] > frame.iloc[max(0, mother_index - int(strategy.trend_side_lookback_bars)) : mother_index + 1]["sma_slow"]).sum())
        else:
            anchor_price_ok = anchor_close > float(signal.structure_high)
            impulse_atr = (anchor_close - float(impulse["low"].min())) / atr if atr > 0 else None
            sma_slope_atr = (anchor_sma - signal_sma) / atr if atr > 0 else None
            trend_side_count = int((frame.iloc[max(0, mother_index - int(strategy.trend_side_lookback_bars)) : mother_index + 1]["close"] < frame.iloc[max(0, mother_index - int(strategy.trend_side_lookback_bars)) : mother_index + 1]["sma_slow"]).sum())
        impulse_ok = impulse_atr is not None and impulse_atr >= float(strategy.min_impulse_atr)
        sma_slope_ok = sma_slope_atr is not None and sma_slope_atr > 0
        impulse_range = float(impulse["high"].max() - impulse["low"].min())
        efficiency = abs(float(impulse.iloc[-1]["close"]) - anchor_close) / impulse_range if impulse_range > 0 else None
        efficiency_ok = efficiency is not None and efficiency >= float(strategy.min_anchor_efficiency)
        trend_start = max(0, mother_index - int(strategy.trend_side_lookback_bars))
        trend_len = len(frame.iloc[trend_start : mother_index + 1])
        trend_side_ratio = trend_side_count / trend_len if trend_len else None
        trend_side_ratio_ok = trend_side_ratio is not None and trend_side_ratio >= float(strategy.min_trend_side_ratio)
        pre_mother_retrace_atr, pre_mother_retrace_bars = _pre_mother_retracement_leg(
            frame,
            side=side,
            anchor_index=int(anchor_index),
            mother_index=mother_index,
            atr=atr,
        )
        pre_mother_retrace_ok = (
            pre_mother_retrace_atr >= float(strategy.min_pre_mother_retrace_atr)
            and pre_mother_retrace_bars >= int(strategy.min_pre_mother_retrace_bars)
        )
        recent_progress_required = anchor_bars > int(strategy.max_anchor_bars_without_recent_progress)
        if recent_progress_required:
            recent_start = max(0, mother_index - int(strategy.recent_progress_lookback_bars))
            recent = frame.iloc[recent_start : mother_index + 1]
            recent_progress_atr = (float(recent.iloc[-1]["close"]) - float(recent.iloc[0]["close"])) * side / atr if atr > 0 and not recent.empty else None
            recent_progress_ok = recent_progress_atr is not None and recent_progress_atr >= float(strategy.min_recent_progress_atr)

    pattern_items = [
        _pass_item("formation length is within configured 3-6 bar window", True, signal.total_bars, f"{strategy.min_total_bars}-{strategy.max_total_bars}"),
        _pass_item("one-sided mother-range break", True, signal.breakout_side, "one side only"),
        _pass_item("signal candle closes back inside mother range", True, _format_price(frame.iloc[signal_index]["close"]), f"{_format_price(signal.mother_low)}-{_format_price(signal.mother_high)}"),
        _pass_item("signal candle direction matches setup", True, "bullish" if side > 0 else "bearish", "trade side"),
    ]
    context_items = [
        _pass_item("20/50 SMA trend-zone context", context_pass, "pass" if context_pass else "fail", f"buffer {zone_buffer_atr:g} ATR"),
        _pass_item("50 SMA trend anchor found before mother", anchor_found, anchor_time, f"lookback {strategy.context_lookback_bars} bars"),
        _pass_item("anchor starts beyond structure on correct side", anchor_price_ok, _format_price(anchor_close), "below structure" if side > 0 else "above structure"),
        _pass_item("anchor impulse is large enough", impulse_ok, _format_metric(impulse_atr), f">= {strategy.min_impulse_atr:g} ATR"),
        _pass_item("50 SMA slope agrees with trade side", sma_slope_ok, _format_metric(sma_slope_atr), "> 0 ATR"),
        _pass_item("anchor-to-mother move is efficient enough", efficiency_ok, _format_metric(efficiency), f">= {strategy.min_anchor_efficiency:g}"),
        _pass_item("recent bars mostly close on trend side of 50 SMA", trend_side_ratio_ok, _format_metric(trend_side_ratio), f">= {strategy.min_trend_side_ratio:g}"),
        _pass_item(
            "prior trend extreme has an opposite retracement before mother",
            pre_mother_retrace_ok,
            f"{_format_metric(pre_mother_retrace_atr)} ATR / {pre_mother_retrace_bars if pre_mother_retrace_bars is not None else 'n/a'} bars",
            f">= {strategy.min_pre_mother_retrace_atr:g} ATR / >= {strategy.min_pre_mother_retrace_bars} bars",
        ),
        _pass_item(
            "stale trend avoids recent adverse drift",
            recent_progress_ok,
            _format_metric(recent_progress_atr),
            f">= {strategy.min_recent_progress_atr:g} ATR" if recent_progress_required else "not required",
        ),
    ]
    all_passed = all(bool(item["passed"]) for item in pattern_items + context_items)
    return {
        "accepted_by_diagnostics": all_passed,
        "anchor_time_utc": anchor_time,
        "anchor_bars_before_mother": anchor_bars,
        "pattern_items": pattern_items,
        "context_items": context_items,
    }


def _render_chart(
    frame: pd.DataFrame,
    *,
    signal: ForceStrikeSignal,
    local_mother_index: int,
    local_signal_index: int,
) -> str:
    width = 1160
    height = 410
    margin_left = 68
    margin_right = 18
    margin_top = 20
    margin_bottom = 34
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    levels = [float(frame["low"].min()), float(frame["high"].max()), float(signal.mother_low), float(signal.mother_high)]
    for column in ("sma_fast", "sma_slow"):
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if not values.empty:
            levels.extend([float(values.min()), float(values.max())])
    price_min = min(levels)
    price_max = max(levels)
    pad = max((price_max - price_min) * 0.06, 0.00001)
    price_min -= pad
    price_max += pad

    def x_at(index: int) -> float:
        if len(frame) <= 1:
            return margin_left + plot_width / 2
        return margin_left + (index / (len(frame) - 1)) * plot_width

    def y_at(price: float) -> float:
        return margin_top + ((price_max - price) / (price_max - price_min)) * plot_height

    candle_width = max(3.0, min(9.0, plot_width / max(len(frame), 1) * 0.62))
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Force Strike scenario">',
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fbfbfb" stroke="#ddd"/>',
    ]

    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        price = price_min + (price_max - price_min) * fraction
        y_pos = y_at(price)
        parts.append(f'<line x1="{margin_left}" x2="{width - margin_right}" y1="{y_pos:.2f}" y2="{y_pos:.2f}" stroke="#eee"/>')
        parts.append(f'<text x="8" y="{y_pos + 4:.2f}" font-size="11" fill="#666">{price:.5f}</text>')

    mother_top = y_at(float(signal.mother_high))
    mother_bottom = y_at(float(signal.mother_low))
    x_left = x_at(local_mother_index) - candle_width
    x_right = x_at(local_signal_index) + candle_width
    parts.append(
        f'<rect x="{x_left:.2f}" y="{mother_top:.2f}" width="{x_right - x_left:.2f}" '
        f'height="{mother_bottom - mother_top:.2f}" fill="#2f80ed" opacity="0.08" stroke="#2f80ed" stroke-dasharray="4 3"/>'
    )

    def hline(price: float, color: str, label: str, dash: str = "4 3") -> None:
        y_pos = y_at(price)
        parts.append(
            f'<line x1="{margin_left}" x2="{width - margin_right}" y1="{y_pos:.2f}" y2="{y_pos:.2f}" '
            f'stroke="{color}" stroke-width="1.4" stroke-dasharray="{dash}"/>'
        )
        parts.append(f'<text x="{width - 122}" y="{y_pos - 5:.2f}" font-size="11" fill="{color}">{escape(label)}</text>')

    hline(float(signal.mother_high), "#2f80ed", "mother high")
    hline(float(signal.mother_low), "#2f80ed", "mother low")

    for column, color, label in (("sma_fast", "#f0a202", "20 SMA"), ("sma_slow", "#d33f49", "50 SMA")):
        points: list[tuple[float, float]] = []
        for local_index, (_, row) in enumerate(frame.iterrows()):
            value = row[column]
            if pd.notna(value):
                points.append((x_at(local_index), y_at(float(value))))
        if points:
            parts.append(f'<path d="{_polyline_path(points)}" fill="none" stroke="{color}" stroke-width="1.6"/>')
            label_y = margin_top + (16 if column == "sma_fast" else 32)
            parts.append(f'<text x="{margin_left + 8}" y="{label_y}" font-size="12" fill="{color}">{label}</text>')

    for local_index, (_, row) in enumerate(frame.iterrows()):
        x_pos = x_at(local_index)
        open_price = float(row["open"])
        close_price = float(row["close"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        color = "#168a45" if close_price >= open_price else "#b8332a"
        parts.append(f'<line x1="{x_pos:.2f}" x2="{x_pos:.2f}" y1="{y_at(high_price):.2f}" y2="{y_at(low_price):.2f}" stroke="{color}"/>')
        body_top = y_at(max(open_price, close_price))
        body_bottom = y_at(min(open_price, close_price))
        parts.append(
            f'<rect x="{x_pos - candle_width / 2:.2f}" y="{body_top:.2f}" width="{candle_width:.2f}" '
            f'height="{max(2.0, body_bottom - body_top):.2f}" fill="{color}" opacity="0.84"/>'
        )

    def vline(local_index: int, color: str, label: str) -> None:
        x_pos = x_at(local_index)
        parts.append(
            f'<line x1="{x_pos:.2f}" x2="{x_pos:.2f}" y1="{margin_top}" y2="{height - margin_bottom}" '
            f'stroke="{color}" stroke-width="1.4" stroke-dasharray="3 3"/>'
        )
        parts.append(f'<text x="{x_pos + 4:.2f}" y="{height - 12}" font-size="11" fill="{color}">{escape(label)}</text>')

    vline(local_mother_index, "#2f80ed", "mother")
    vline(local_signal_index, "#6d3fc0", "signal")

    first_time = pd.Timestamp(frame["time_utc"].iloc[0]).strftime("%Y-%m-%d")
    last_time = pd.Timestamp(frame["time_utc"].iloc[-1]).strftime("%Y-%m-%d")
    parts.append(f'<text x="{margin_left}" y="{height - 3}" font-size="11" fill="#666">{first_time}</text>')
    parts.append(f'<text x="{width - 96}" y="{height - 3}" font-size="11" fill="#666">{last_time}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _slice_for_signal(
    frame: pd.DataFrame,
    signal: ForceStrikeSignal,
    *,
    bars_before: int,
    bars_after: int,
) -> tuple[pd.DataFrame, int, int]:
    start = max(0, int(signal.mother_index) - int(bars_before))
    end = min(len(frame) - 1, int(signal.signal_index) + int(bars_after))
    return frame.iloc[start : end + 1].reset_index(drop=True), int(signal.mother_index) - start, int(signal.signal_index) - start


def _scenario_metadata(
    signal: ForceStrikeSignal,
    *,
    accepted_by_current_model: bool,
    sequence: int,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    return {
        "id": f"{signal.symbol}_{signal.timeframe}_{signal.signal_time_utc}_{signal.side}_{signal.mother_index}_{signal.signal_index}".replace(" ", "_").replace(":", ""),
        "sequence": sequence,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "side": "bullish" if signal.side > 0 else "bearish",
        "mother_time_utc": signal.mother_time_utc,
        "signal_time_utc": signal.signal_time_utc,
        "total_bars": signal.total_bars,
        "breakout_side": signal.breakout_side,
        "mother_high": signal.mother_high,
        "mother_low": signal.mother_low,
        "structure_high": signal.structure_high,
        "structure_low": signal.structure_low,
        "accepted_by_current_model": accepted_by_current_model,
        "diagnostics": diagnostics,
    }


def _render_diagnostics(items: list[dict[str, object]]) -> str:
    rows = []
    for item in items:
        passed = bool(item.get("passed"))
        status = "pass" if passed else "fail"
        status_text = "PASS" if passed else "FAIL"
        value = "" if item.get("value") is None else escape(str(item.get("value")))
        threshold = "" if item.get("threshold") is None else escape(str(item.get("threshold")))
        rows.append(
            "<tr>"
            f'<td><span class="status {status}">{status_text}</span></td>'
            f"<td>{escape(str(item.get('label', '')))}</td>"
            f"<td>{value}</td>"
            f"<td>{threshold}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_card(chart: str, metadata: dict[str, object]) -> str:
    scenario_json = escape(json.dumps(metadata, separators=(",", ":")))
    model_badge = "ACCEPTED by current model" if metadata["accepted_by_current_model"] else "REJECTED by current model"
    badge_class = "accepted" if metadata["accepted_by_current_model"] else "rejected"
    side_class = "bullish" if metadata["side"] == "bullish" else "bearish"
    scenario_id = str(metadata["id"])
    diagnostics = dict(metadata.get("diagnostics", {}))
    pattern_rows = _render_diagnostics(list(diagnostics.get("pattern_items", [])))
    context_rows = _render_diagnostics(list(diagnostics.get("context_items", [])))
    fields = [
        ("symbol", metadata["symbol"]),
        ("side", metadata["side"]),
        ("signal", metadata["signal_time_utc"]),
        ("bars", metadata["total_bars"]),
        ("breakout", metadata["breakout_side"]),
        ("mother high", _format_price(metadata["mother_high"])),
        ("mother low", _format_price(metadata["mother_low"])),
    ]
    meta = "".join(f"<span><b>{escape(str(key))}</b>: {escape(str(value))}</span>" for key, value in fields)
    return f"""
<section class="scenario {side_class}" id="{escape(str(metadata['id']))}" data-scenario="{scenario_json}">
  <div class="scenario-header">
    <h2>#{metadata['sequence']} {escape(str(metadata['symbol']))} {escape(str(metadata['side']).title())}</h2>
    <span class="badge {badge_class}">{escape(model_badge)}</span>
  </div>
  <div class="meta">{meta}</div>
  {chart}
  <details class="diagnostics" open>
    <summary>Model diagnostics</summary>
    <div class="diag-grid">
      <div>
        <h3>Pattern</h3>
        <table><thead><tr><th>Status</th><th>Rule</th><th>Value</th><th>Required</th></tr></thead><tbody>{pattern_rows}</tbody></table>
      </div>
      <div>
        <h3>Trend Context</h3>
        <table><thead><tr><th>Status</th><th>Rule</th><th>Value</th><th>Required</th></tr></thead><tbody>{context_rows}</tbody></table>
      </div>
    </div>
  </details>
  <div class="label-row">
    <label class="choice"><input type="radio" name="label-{escape(scenario_id)}" data-label="valid"><span data-label="valid">Valid</span></label>
    <label class="choice"><input type="radio" name="label-{escape(scenario_id)}" data-label="invalid"><span data-label="invalid">Invalid</span></label>
    <label class="choice"><input type="radio" name="label-{escape(scenario_id)}" data-label="unsure"><span data-label="unsure">Unsure</span></label>
    <input type="text" placeholder="Optional note, e.g. second pullback, no clear impulse, too extended">
  </div>
</section>
"""


def _render_page(*, title: str, cards: list[str], scenarios: list[dict[str, object]], config, sma_buffer: float) -> str:
    scenario_blob = json.dumps(scenarios, separators=(",", ":")).replace("</", "<\\/")
    rules = _rule_summary(config, sma_buffer)
    rules_html = "\n".join(f"<li>{escape(rule)}</li>" for rule in rules)
    accepted = sum(1 for scenario in scenarios if bool(scenario.get("accepted_by_current_model")))
    rejected = len(scenarios) - accepted
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; background: #f5f6f8; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    h2 {{ font-size: 17px; margin: 0; }}
    h3 {{ font-size: 14px; margin: 8px 0; }}
    .top, .scenario {{ background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin-bottom: 18px; }}
    .top p {{ margin: 7px 0; color: #444; }}
    .rules {{ margin: 12px 0 0; padding-left: 22px; line-height: 1.45; color: #333; }}
    .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }}
    .scenario-header {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .badge {{ font-size: 12px; background: #f0f1f4; color: #444; padding: 4px 8px; border-radius: 999px; }}
    .badge.accepted {{ background: #e6f4eb; color: #126b37; }}
    .badge.rejected {{ background: #f8eaea; color: #9d2c24; }}
    .scenario.bullish {{ border-left: 5px solid #168a45; }}
    .scenario.bearish {{ border-left: 5px solid #b8332a; }}
    .scenario[data-current-label="valid"] {{ box-shadow: inset 0 0 0 2px #168a45; }}
    .scenario[data-current-label="invalid"] {{ box-shadow: inset 0 0 0 2px #b8332a; }}
    .scenario[data-current-label="unsure"] {{ box-shadow: inset 0 0 0 2px #8a6d1d; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px 18px; font-size: 13px; color: #444; margin-top: 8px; }}
    .meta span {{ white-space: nowrap; }}
    svg {{ width: 100%; height: auto; display: block; margin-top: 10px; }}
    button, .choice span {{ border: 1px solid #bbb; background: #fff; border-radius: 5px; padding: 7px 12px; cursor: pointer; font-size: 13px; }}
    button:hover, .choice span:hover {{ background: #f3f5f8; }}
    .choice input {{ position: absolute; opacity: 0; pointer-events: none; }}
    .choice input:checked + span[data-label="valid"] {{ background: #168a45; border-color: #168a45; color: #fff; }}
    .choice input:checked + span[data-label="invalid"] {{ background: #b8332a; border-color: #b8332a; color: #fff; }}
    .choice input:checked + span[data-label="unsure"] {{ background: #8a6d1d; border-color: #8a6d1d; color: #fff; }}
    .label-row {{ display: flex; align-items: center; gap: 8px; margin-top: 10px; }}
    .label-row input {{ flex: 1; min-width: 260px; border: 1px solid #bbb; border-radius: 5px; padding: 8px; }}
    .diagnostics {{ margin-top: 10px; border-top: 1px solid #eee; padding-top: 8px; }}
    .diagnostics summary {{ cursor: pointer; font-weight: 600; color: #333; }}
    .diag-grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 5px 6px; text-align: left; vertical-align: top; }}
    th {{ background: #fafafa; color: #444; }}
    .status {{ display: inline-block; min-width: 38px; border-radius: 4px; padding: 2px 5px; font-weight: 700; font-size: 11px; }}
    .status.pass {{ background: #e6f4eb; color: #126b37; }}
    .status.fail {{ background: #f8eaea; color: #9d2c24; }}
    textarea {{ width: 100%; min-height: 130px; margin-top: 10px; font-family: Consolas, monospace; font-size: 12px; }}
    .progress {{ font-weight: 600; }}
    @media (max-width: 900px) {{ .diag-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <section class="top">
    <h1>{escape(title)}</h1>
    <p>This page is the current strategy verification view. The badges show the current model decision; the diagnostics show exactly which rules pass or fail.</p>
    <p><b>Current sample:</b> {len(scenarios)} scenarios, {accepted} accepted by current model, {rejected} rejected.</p>
    <h3>Current Rules</h3>
    <ol class="rules">{rules_html}</ol>
    <p class="progress" id="progress">0 labeled</p>
    <div class="toolbar">
      <button type="button" id="export-json">Export labels JSON</button>
      <button type="button" id="copy-json">Copy labels JSON</button>
      <button type="button" id="clear-labels">Clear labels on this page</button>
    </div>
    <textarea id="label-output" readonly placeholder="Exported labels appear here too."></textarea>
  </section>
  {''.join(cards)}
  <script>
    const scenarios = {scenario_blob};
    const storageKey = 'force_strike_labels:' + document.title;

    function readLabels() {{
      try {{ return JSON.parse(localStorage.getItem(storageKey) || '{{}}'); }}
      catch {{ return {{}}; }}
    }}

    function writeLabels(labels) {{
      localStorage.setItem(storageKey, JSON.stringify(labels));
      renderLabels();
    }}

    function collectScenario(section) {{
      return JSON.parse(section.dataset.scenario);
    }}

    function renderLabels() {{
      const labels = readLabels();
      let labeled = 0;
      document.querySelectorAll('.scenario').forEach(section => {{
        const scenario = collectScenario(section);
        const record = labels[scenario.id] || null;
        const current = record ? record.label : '';
        if (current) labeled += 1;
        section.dataset.currentLabel = current;
        section.querySelectorAll('input[type="radio"][data-label]').forEach(input => {{
          input.checked = input.dataset.label === current;
        }});
        const input = section.querySelector('input[type="text"]');
        input.value = record ? (record.note || '') : '';
      }});
      document.getElementById('progress').textContent = `${{labeled}} / ${{scenarios.length}} labeled`;
      document.getElementById('label-output').value = JSON.stringify(Object.values(labels), null, 2);
    }}

    document.querySelectorAll('.scenario').forEach(section => {{
      section.querySelectorAll('input[type="radio"][data-label]').forEach(input => {{
        input.addEventListener('change', () => {{
          const labels = readLabels();
          const scenario = collectScenario(section);
          const note = section.querySelector('input[type="text"]').value || '';
          labels[scenario.id] = {{...scenario, label: input.dataset.label, note}};
          writeLabels(labels);
        }});
      }});
      section.querySelector('input[type="text"]').addEventListener('change', event => {{
        const labels = readLabels();
        const scenario = collectScenario(section);
        const prior = labels[scenario.id] || {{...scenario, label: ''}};
        labels[scenario.id] = {{...prior, note: event.target.value || ''}};
        writeLabels(labels);
      }});
    }});

    document.getElementById('export-json').addEventListener('click', () => {{
      const payload = JSON.stringify(Object.values(readLabels()), null, 2);
      document.getElementById('label-output').value = payload;
      const blob = new Blob([payload], {{type: 'application/json'}});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'force_strike_labels.json';
      link.click();
      URL.revokeObjectURL(url);
    }});

    document.getElementById('copy-json').addEventListener('click', async () => {{
      const payload = JSON.stringify(Object.values(readLabels()), null, 2);
      document.getElementById('label-output').value = payload;
      await navigator.clipboard.writeText(payload);
    }});

    document.getElementById('clear-labels').addEventListener('click', () => {{
      if (confirm('Clear all labels saved for this page?')) writeLabels({{}});
    }});

    renderLabels();
  </script>
</body>
</html>
"""


def _load_symbol_frame(config, symbol: str) -> pd.DataFrame:
    raw = load_rates_csv(PROJECT_ROOT / config.data_dir, symbol=symbol, timeframe=config.timeframe)
    return build_features(raw, config.strategy, fallback_spread_points=config.costs.fallback_spread_points)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()] or config.symbols
    cards: list[str] = []
    scenarios: list[dict[str, object]] = []
    sequence = 1

    for symbol in symbols:
        frame = _load_symbol_frame(config, symbol)
        raw_signals = detect_force_strikes(
            frame,
            min_total_bars=config.strategy.min_total_bars,
            max_total_bars=config.strategy.max_total_bars,
            require_context=False,
        )
        current_signals = detect_force_strikes(
            frame,
            min_total_bars=config.strategy.min_total_bars,
            max_total_bars=config.strategy.max_total_bars,
            require_context=True,
            require_first_retracement_context=config.strategy.require_first_retracement_context,
            sma_touch_buffer_atr=float(args.sma_buffer),
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
        current_keys = {_signal_key(signal) for signal in current_signals}
        current_sample = _sample_signals(
            current_signals,
            max_count=min(int(args.current_per_symbol), int(args.max_per_symbol)),
            chronological=bool(args.chronological),
            seed=int(args.seed) + 1000 + sum(ord(char) for char in symbol),
        )
        selected_keys = {_signal_key(signal) for signal in current_sample}
        raw_pool = [signal for signal in raw_signals if _signal_key(signal) not in selected_keys]
        raw_sample = _sample_signals(
            raw_pool,
            max_count=max(0, int(args.max_per_symbol) - len(current_sample)),
            chronological=bool(args.chronological),
            seed=int(args.seed) + sum(ord(char) for char in symbol),
        )
        sampled = sorted(current_sample + raw_sample, key=lambda item: item.signal_index)
        for signal in sampled:
            diagnostics = _compute_diagnostics(frame, signal, config, float(args.sma_buffer))
            chart_frame, local_mother, local_signal = _slice_for_signal(
                frame,
                signal,
                bars_before=int(args.bars_before),
                bars_after=int(args.bars_after),
            )
            metadata = _scenario_metadata(
                signal,
                accepted_by_current_model=_signal_key(signal) in current_keys,
                sequence=sequence,
                diagnostics=diagnostics,
            )
            chart = _render_chart(
                chart_frame,
                signal=signal,
                local_mother_index=local_mother,
                local_signal_index=local_signal,
            )
            cards.append(_render_card(chart, metadata))
            scenarios.append(metadata)
            sequence += 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = PROJECT_ROOT / config.report_dir / config.timeframe / "labeling" / stamp
    output_root.mkdir(parents=True, exist_ok=True)
    index_path = output_root / "index.html"
    metadata_path = output_root / "scenarios.json"
    title = f"Force Strike {config.timeframe} Strategy Verification"
    index_path.write_text(
        _render_page(title=title, cards=cards, scenarios=scenarios, config=config, sma_buffer=float(args.sma_buffer)),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")

    latest_root = PROJECT_ROOT / config.report_dir / config.timeframe / "labeling" / "latest"
    latest_root.mkdir(parents=True, exist_ok=True)
    (latest_root / "index.html").write_text(index_path.read_text(encoding="utf-8"), encoding="utf-8")
    (latest_root / "scenarios.json").write_text(metadata_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("Pattern labeling pack exported")
    print(f"- scenarios: {len(scenarios)}")
    print(f"- html: {index_path}")
    print(f"- latest: {latest_root / 'index.html'}")
    print(f"- metadata: {metadata_path}")


if __name__ == "__main__":
    main()
