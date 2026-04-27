from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from force_strike_lab.config import load_config
from force_strike_lab.data import load_rates_csv
from force_strike_lab.features import build_features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export visual Force Strike trade review charts.")
    parser.add_argument(
        "--report-dir",
        default=str(PROJECT_ROOT / "reports" / "force_strike" / "M30" / "latest"),
        help="Research report directory containing trades.csv, candidate_summary.csv, and config_used.json.",
    )
    parser.add_argument(
        "--candidate-id",
        default="",
        help="Candidate to review. Defaults to the first row in candidate_summary.csv.",
    )
    parser.add_argument("--bars-before", type=int, default=70, help="Bars to show before the mother bar.")
    parser.add_argument("--bars-after", type=int, default=30, help="Bars to show after the exit bar.")
    parser.add_argument("--limit", type=int, default=60, help="Maximum charts to render.")
    parser.add_argument(
        "--sort",
        choices=["time", "worst", "best", "duration"],
        default="time",
        help="Trade ordering in the review page.",
    )
    return parser.parse_args()


def _selected_candidate(report_dir: Path, candidate_id: str) -> str:
    if candidate_id:
        return candidate_id
    summary = pd.read_csv(report_dir / "candidate_summary.csv")
    if summary.empty:
        raise ValueError("candidate_summary.csv is empty.")
    return str(summary.iloc[0]["candidate_id"])


def _candidate_metrics(report_dir: Path, candidate_id: str) -> dict[str, str]:
    summary = pd.read_csv(report_dir / "candidate_summary.csv")
    matched = summary.loc[summary["candidate_id"].astype(str) == candidate_id]
    if matched.empty:
        return {}
    row = matched.iloc[0]
    keys = [
        "full_net_r",
        "holdout_net_r",
        "full_profit_factor",
        "holdout_profit_factor",
        "full_trades",
        "full_win_rate",
        "full_max_drawdown_r",
    ]
    return {key: str(row[key]) for key in keys if key in row.index}


def _sort_trades(trades: pd.DataFrame, sort_key: str) -> pd.DataFrame:
    if sort_key == "worst":
        return trades.sort_values(["net_r", "entry_time_utc"], ascending=[True, True])
    if sort_key == "best":
        return trades.sort_values(["net_r", "entry_time_utc"], ascending=[False, True])
    if sort_key == "duration":
        return trades.sort_values(["bars_held", "entry_time_utc"], ascending=[False, True])
    return trades.sort_values("entry_time_utc")


def _load_feature_frames(config_path: Path) -> dict[str, pd.DataFrame]:
    config = load_config(config_path)
    data_root = PROJECT_ROOT / config.data_dir
    frames: dict[str, pd.DataFrame] = {}
    for symbol in config.symbols:
        raw = load_rates_csv(data_root, symbol=symbol, timeframe=config.timeframe)
        frames[symbol] = build_features(
            raw,
            config.strategy,
            fallback_spread_points=config.costs.fallback_spread_points,
        )
    return frames


def _format_number(value: object, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return escape(str(value))
    return f"{number:.{digits}f}"


def _polyline_path(points: Iterable[tuple[float, float]]) -> str:
    parts = []
    for index, (x_pos, y_pos) in enumerate(points):
        command = "M" if index == 0 else "L"
        parts.append(f"{command}{x_pos:.2f},{y_pos:.2f}")
    return " ".join(parts)


def _render_chart(frame: pd.DataFrame, *, start_index: int, trade: pd.Series) -> str:
    width = 1180
    height = 430
    margin_left = 70
    margin_right = 18
    margin_top = 20
    margin_bottom = 36
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    levels = [
        float(frame["low"].min()),
        float(frame["high"].max()),
        float(trade["entry_reference_price"]),
        float(trade["stop_price"]),
        float(trade["target_price"]),
        float(trade["mother_high"]),
        float(trade["mother_low"]),
    ]
    for column in ("sma_fast", "sma_slow"):
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if not series.empty:
            levels.extend([float(series.min()), float(series.max())])
    price_min = min(levels)
    price_max = max(levels)
    pad = max((price_max - price_min) * 0.06, 0.00001)
    price_min -= pad
    price_max += pad

    def x_at(local_index: int) -> float:
        if len(frame) <= 1:
            return margin_left + plot_width / 2
        return margin_left + (local_index / (len(frame) - 1)) * plot_width

    def y_at(price: float) -> float:
        return margin_top + ((price_max - price) / (price_max - price_min)) * plot_height

    candle_width = max(3.0, min(10.0, plot_width / max(len(frame), 1) * 0.62))
    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="trade chart">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fafafa" stroke="#ddd"/>',
    ]

    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        price = price_min + (price_max - price_min) * fraction
        y_pos = y_at(price)
        svg_parts.append(f'<line x1="{margin_left}" x2="{width - margin_right}" y1="{y_pos:.2f}" y2="{y_pos:.2f}" stroke="#eee"/>')
        svg_parts.append(f'<text x="8" y="{y_pos + 4:.2f}" font-size="11" fill="#666">{price:.5f}</text>')

    def hline(price: float, color: str, label: str, dash: str = "") -> None:
        y_pos = y_at(price)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        svg_parts.append(
            f'<line x1="{margin_left}" x2="{width - margin_right}" y1="{y_pos:.2f}" y2="{y_pos:.2f}" '
            f'stroke="{color}" stroke-width="1.5"{dash_attr}/>'
        )
        svg_parts.append(f'<text x="{width - 132}" y="{y_pos - 5:.2f}" font-size="11" fill="{color}">{escape(label)}</text>')

    mother_start = int(trade["signal_index_local"]) - int(trade["total_bars"]) + 1
    signal_local = int(trade["signal_index_local"])
    if 0 <= mother_start < len(frame) and 0 <= signal_local < len(frame):
        y_top = y_at(float(trade["mother_high"]))
        y_bottom = y_at(float(trade["mother_low"]))
        x_left = x_at(mother_start) - candle_width
        x_right = x_at(signal_local) + candle_width
        svg_parts.append(
            f'<rect x="{x_left:.2f}" y="{min(y_top, y_bottom):.2f}" width="{x_right - x_left:.2f}" '
            f'height="{abs(y_bottom - y_top):.2f}" fill="#2f80ed" opacity="0.08" stroke="#2f80ed" stroke-dasharray="4 3"/>'
        )

    hline(float(trade["mother_high"]), "#2f80ed", "mother high", "4 3")
    hline(float(trade["mother_low"]), "#2f80ed", "mother low", "4 3")
    hline(float(trade["entry_reference_price"]), "#111", "entry")
    hline(float(trade["stop_price"]), "#c62828", "stop")
    hline(float(trade["target_price"]), "#1b7f3a", "target")

    for column, color, label in (("sma_fast", "#f0a202", "20 SMA"), ("sma_slow", "#d33f49", "50 SMA")):
        points = []
        for local_index, (_, row) in enumerate(frame.iterrows()):
            value = row[column]
            if pd.notna(value):
                points.append((x_at(local_index), y_at(float(value))))
        if points:
            svg_parts.append(f'<path d="{_polyline_path(points)}" fill="none" stroke="{color}" stroke-width="1.6"/>')
            svg_parts.append(f'<text x="{margin_left + 8}" y="{margin_top + (16 if column == "sma_fast" else 32)}" font-size="12" fill="{color}">{label}</text>')

    for local_index, (_, row) in enumerate(frame.iterrows()):
        x_pos = x_at(local_index)
        open_price = float(row["open"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        close_price = float(row["close"])
        color = "#168a45" if close_price >= open_price else "#b8332a"
        svg_parts.append(
            f'<line x1="{x_pos:.2f}" x2="{x_pos:.2f}" y1="{y_at(high_price):.2f}" y2="{y_at(low_price):.2f}" '
            f'stroke="{color}" stroke-width="1"/>'
        )
        body_top = y_at(max(open_price, close_price))
        body_bottom = y_at(min(open_price, close_price))
        body_height = max(2.0, body_bottom - body_top)
        svg_parts.append(
            f'<rect x="{x_pos - candle_width / 2:.2f}" y="{body_top:.2f}" width="{candle_width:.2f}" '
            f'height="{body_height:.2f}" fill="{color}" opacity="0.82"/>'
        )

    def vline(local_index: int, color: str, label: str) -> None:
        if local_index < 0 or local_index >= len(frame):
            return
        x_pos = x_at(local_index)
        svg_parts.append(
            f'<line x1="{x_pos:.2f}" x2="{x_pos:.2f}" y1="{margin_top}" y2="{height - margin_bottom}" '
            f'stroke="{color}" stroke-width="1.3" stroke-dasharray="3 3"/>'
        )
        svg_parts.append(f'<text x="{x_pos + 4:.2f}" y="{height - 14}" font-size="11" fill="{color}">{escape(label)}</text>')

    vline(mother_start, "#2f80ed", "mother")
    vline(signal_local, "#6d3fc0", "signal")
    vline(int(trade["entry_index_local"]), "#111", "entry")
    vline(int(trade["exit_index_local"]), "#444", "exit")

    first_time = pd.Timestamp(frame["time_utc"].iloc[0]).strftime("%Y-%m-%d")
    last_time = pd.Timestamp(frame["time_utc"].iloc[-1]).strftime("%Y-%m-%d")
    svg_parts.append(f'<text x="{margin_left}" y="{height - 4}" font-size="11" fill="#666">{first_time}</text>')
    svg_parts.append(f'<text x="{width - 96}" y="{height - 4}" font-size="11" fill="#666">{last_time}</text>')
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _render_trade_card(frame: pd.DataFrame, *, start_index: int, trade: pd.Series, number: int) -> str:
    chart = _render_chart(frame, start_index=start_index, trade=trade)
    side = "Bullish" if int(trade["side"]) > 0 else "Bearish"
    klass = "win" if float(trade["net_r"]) > 0 else "loss"
    title = (
        f"#{number} {escape(str(trade['symbol']))} {side} "
        f"{escape(str(trade['entry_time_utc']))} netR={_format_number(trade['net_r'], 2)}"
    )
    meta = [
        ("candidate", trade["candidate_id"]),
        ("exit", trade["exit_reason"]),
        ("entry mode", trade["entry_mode"]),
        ("bars held", trade["bars_held"]),
        ("gross R", _format_number(trade["gross_r"], 2)),
        ("cost R", _format_number(trade["cost_r"], 2)),
        ("signal", trade["signal_time_utc"]),
    ]
    meta_html = "".join(f"<span><b>{escape(str(key))}</b>: {escape(str(value))}</span>" for key, value in meta)
    return f"""
<section class="trade-card {klass}" id="trade-{number}">
  <h2>{title}</h2>
  <div class="meta">{meta_html}</div>
  {chart}
</section>
"""


def _prepare_chart_slice(frame: pd.DataFrame, trade: pd.Series, bars_before: int, bars_after: int) -> tuple[pd.DataFrame, int, pd.Series]:
    times = pd.to_datetime(frame["time_utc"], utc=True)
    signal_time = pd.Timestamp(trade["signal_time_utc"])
    entry_time = pd.Timestamp(trade["entry_time_utc"])
    exit_time = pd.Timestamp(trade["exit_time_utc"])
    signal_matches = frame.index[times == signal_time].tolist()
    entry_matches = frame.index[times == entry_time].tolist()
    exit_matches = frame.index[times == exit_time].tolist()
    if not signal_matches or not entry_matches or not exit_matches:
        raise ValueError(f"Could not align trade times for {trade['symbol']} {trade['signal_time_utc']}.")
    signal_index = int(signal_matches[0])
    entry_index = int(entry_matches[0])
    exit_index = int(exit_matches[0])
    mother_index = signal_index - int(trade["total_bars"]) + 1
    start_index = max(0, mother_index - int(bars_before))
    end_index = min(len(frame) - 1, max(exit_index, signal_index) + int(bars_after))
    enriched = trade.copy()
    enriched["signal_index_local"] = signal_index - start_index
    enriched["entry_index_local"] = entry_index - start_index
    enriched["exit_index_local"] = exit_index - start_index
    return frame.iloc[start_index : end_index + 1].reset_index(drop=True), start_index, enriched


def _render_index(*, candidate_id: str, metrics: dict[str, str], cards: list[str], trades: pd.DataFrame) -> str:
    metric_html = "".join(f"<span><b>{escape(key)}</b>: {escape(value)}</span>" for key, value in metrics.items())
    rows = []
    for index, row in trades.reset_index(drop=True).iterrows():
        rows.append(
            "<tr>"
            f"<td><a href=\"#trade-{index + 1}\">{index + 1}</a></td>"
            f"<td>{escape(str(row['symbol']))}</td>"
            f"<td>{'Long' if int(row['side']) > 0 else 'Short'}</td>"
            f"<td>{escape(str(row['entry_time_utc']))}</td>"
            f"<td>{escape(str(row['exit_reason']))}</td>"
            f"<td>{_format_number(row['net_r'], 2)}</td>"
            f"<td>{escape(str(row['bars_held']))}</td>"
            "</tr>"
        )
    table = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Force Strike Trade Review - {escape(candidate_id)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; background: #f4f5f7; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    h2 {{ font-size: 17px; margin: 0 0 8px; }}
    .summary, .trade-card {{ background: white; border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin-bottom: 18px; }}
    .metrics, .meta {{ display: flex; flex-wrap: wrap; gap: 10px 18px; font-size: 13px; color: #444; }}
    .metrics span, .meta span {{ white-space: nowrap; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 14px; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e5e5e5; padding: 6px 8px; text-align: left; }}
    th {{ background: #fafafa; }}
    a {{ color: #1f5fbf; }}
    .trade-card.win {{ border-left: 5px solid #168a45; }}
    .trade-card.loss {{ border-left: 5px solid #b8332a; }}
    svg {{ width: 100%; height: auto; display: block; margin-top: 10px; }}
  </style>
</head>
<body>
  <section class="summary">
    <h1>Force Strike Trade Review</h1>
    <div class="metrics"><span><b>candidate</b>: {escape(candidate_id)}</span>{metric_html}</div>
    <table>
      <thead><tr><th>#</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>Net R</th><th>Bars</th></tr></thead>
      <tbody>{table}</tbody>
    </table>
  </section>
  {''.join(cards)}
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        cwd_candidate = Path.cwd() / report_dir
        report_dir = cwd_candidate if cwd_candidate.exists() else PROJECT_ROOT / report_dir
    candidate_id = _selected_candidate(report_dir, args.candidate_id)
    trades = pd.read_csv(report_dir / "trades.csv")
    selected = trades.loc[trades["candidate_id"].astype(str) == candidate_id].copy()
    if selected.empty:
        raise ValueError(f"No trades found for candidate {candidate_id!r}.")
    selected = _sort_trades(selected, args.sort).head(int(args.limit)).reset_index(drop=True)
    frames = _load_feature_frames(report_dir / "config_used.json")

    cards: list[str] = []
    rendered_rows = []
    for index, trade in selected.iterrows():
        symbol = str(trade["symbol"])
        chart_frame, start_index, enriched = _prepare_chart_slice(
            frames[symbol],
            trade,
            bars_before=args.bars_before,
            bars_after=args.bars_after,
        )
        cards.append(_render_trade_card(chart_frame, start_index=start_index, trade=enriched, number=index + 1))
        rendered_rows.append(trade)

    output_dir = report_dir / "review" / candidate_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_trades = pd.DataFrame(rendered_rows)
    output_trades.to_csv(output_dir / "review_trades.csv", index=False)
    html = _render_index(
        candidate_id=candidate_id,
        metrics=_candidate_metrics(report_dir, candidate_id),
        cards=cards,
        trades=output_trades,
    )
    output_path = output_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print("Trade review exported")
    print(f"- candidate: {candidate_id}")
    print(f"- charts: {len(cards)}")
    print(f"- html: {output_path}")
    print(f"- trades: {output_dir / 'review_trades.csv'}")


if __name__ == "__main__":
    main()
