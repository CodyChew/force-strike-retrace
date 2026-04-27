"""Analytics helpers for Force Strike research reports."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from .backtest import TradeRecord


def trades_to_frame(trades: list[TradeRecord]) -> pd.DataFrame:
    """Convert trade records to a DataFrame."""

    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([trade.to_dict() for trade in trades])


def _profit_factor(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    gross_profit = float(values.loc[values > 0].sum())
    gross_loss = float(-values.loc[values < 0].sum())
    if gross_loss <= 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    equity = values.cumsum()
    peak = equity.cummax()
    return float((peak - equity).max())


def contribution_concentration(frame: pd.DataFrame, group_column: str) -> float:
    """Return largest positive group contribution divided by total positive contribution."""

    if frame.empty or group_column not in frame.columns:
        return 1.0
    grouped = frame.groupby(group_column)["net_r"].sum()
    positive = grouped.clip(lower=0.0)
    total = float(positive.sum())
    if total <= 0:
        return 1.0
    return float(positive.max() / total)


def summarize_trades(frame: pd.DataFrame, *, signal_count: int = 0, pending_cancelled: int = 0) -> dict[str, Any]:
    """Compute compact R-multiple metrics."""

    if frame.empty:
        return {
            "signals": int(signal_count),
            "trades": 0,
            "pending_cancelled": int(pending_cancelled),
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "net_r": 0.0,
            "avg_r": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_r": 0.0,
            "avg_holding_bars": 0.0,
            "median_holding_bars": 0.0,
            "end_of_data_trades": 0,
        }
    values = pd.to_numeric(frame["net_r"], errors="coerce").fillna(0.0)
    wins = int((values > 0).sum())
    losses = int((values < 0).sum())
    return {
        "signals": int(signal_count),
        "trades": int(len(frame)),
        "pending_cancelled": int(pending_cancelled),
        "wins": wins,
        "losses": losses,
        "win_rate": float(wins / len(frame)),
        "net_r": float(values.sum()),
        "avg_r": float(values.mean()),
        "profit_factor": _profit_factor(values),
        "max_drawdown_r": _max_drawdown(values),
        "avg_holding_bars": float(pd.to_numeric(frame["bars_held"], errors="coerce").mean()),
        "median_holding_bars": float(pd.to_numeric(frame["bars_held"], errors="coerce").median()),
        "end_of_data_trades": int((frame["exit_reason"] == "end_of_data").sum()),
    }


def add_time_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add datetime, year, and day labels to a trade frame."""

    if frame.empty:
        return frame.copy()
    data = frame.copy()
    data["entry_time_utc"] = pd.to_datetime(data["entry_time_utc"], utc=True)
    data["exit_time_utc"] = pd.to_datetime(data["exit_time_utc"], utc=True)
    data["entry_year"] = data["entry_time_utc"].dt.year.astype(int)
    data["entry_day"] = data["entry_time_utc"].dt.strftime("%Y-%m-%d")
    return data


def yearly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize trades by candidate, symbol, and calendar year."""

    if frame.empty:
        return pd.DataFrame()
    data = add_time_columns(frame)
    rows = []
    for (candidate_id, symbol, year), group in data.groupby(["candidate_id", "symbol", "entry_year"]):
        summary = summarize_trades(group)
        summary.update({"candidate_id": candidate_id, "symbol": symbol, "year": int(year)})
        rows.append(summary)
    return pd.DataFrame(rows)


def rolling_summary(frame: pd.DataFrame, *, window_days: int = 180, step_days: int = 90) -> pd.DataFrame:
    """Build rolling-window candidate summaries across the basket."""

    if frame.empty:
        return pd.DataFrame()
    data = add_time_columns(frame)
    rows = []
    for candidate_id, candidate_trades in data.groupby("candidate_id"):
        start = candidate_trades["entry_time_utc"].min().normalize()
        end = candidate_trades["entry_time_utc"].max()
        cursor = start
        while cursor + pd.Timedelta(days=window_days) <= end:
            window_end = cursor + pd.Timedelta(days=window_days)
            window = candidate_trades.loc[
                (candidate_trades["entry_time_utc"] >= cursor) & (candidate_trades["entry_time_utc"] < window_end)
            ]
            summary = summarize_trades(window)
            summary.update(
                {
                    "candidate_id": candidate_id,
                    "window_start_utc": cursor.isoformat(),
                    "window_end_utc": window_end.isoformat(),
                }
            )
            rows.append(summary)
            cursor += pd.Timedelta(days=step_days)
    return pd.DataFrame(rows)


def split_trade_frame(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split trades chronologically into discovery, selection, and holdout blocks."""

    if frame.empty:
        return {"discovery": frame.copy(), "selection": frame.copy(), "holdout": frame.copy()}
    data = add_time_columns(frame).sort_values("entry_time_utc").reset_index(drop=True)
    start = data["entry_time_utc"].min()
    end = data["entry_time_utc"].max()
    span = end - start
    discovery_end = start + span * 0.60
    selection_end = start + span * 0.80
    return {
        "discovery": data.loc[data["entry_time_utc"] <= discovery_end].copy(),
        "selection": data.loc[(data["entry_time_utc"] > discovery_end) & (data["entry_time_utc"] <= selection_end)].copy(),
        "holdout": data.loc[data["entry_time_utc"] > selection_end].copy(),
    }


def candidate_summary(frame: pd.DataFrame, *, signal_counts: dict[str, int], pending_counts: dict[str, int]) -> pd.DataFrame:
    """Build one row per candidate with full and split metrics."""

    candidate_ids = sorted(set(signal_counts) | set(frame["candidate_id"].unique().tolist() if not frame.empty else []))
    rows = []
    for candidate_id in candidate_ids:
        candidate_trades = frame.loc[frame["candidate_id"] == candidate_id].copy() if not frame.empty else pd.DataFrame()
        full = summarize_trades(
            candidate_trades,
            signal_count=signal_counts.get(candidate_id, 0),
            pending_cancelled=pending_counts.get(candidate_id, 0),
        )
        row: dict[str, Any] = {"candidate_id": candidate_id, **{f"full_{key}": value for key, value in full.items()}}
        for split_name, split_frame in split_trade_frame(candidate_trades).items():
            summary = summarize_trades(split_frame)
            for key, value in summary.items():
                row[f"{split_name}_{key}"] = value
        if not candidate_trades.empty:
            days = max(
                1,
                int(
                    (
                        pd.to_datetime(candidate_trades["entry_time_utc"], utc=True).max()
                        - pd.to_datetime(candidate_trades["entry_time_utc"], utc=True).min()
                    ).days
                ),
            )
            row["full_trades_per_day"] = float(len(candidate_trades) / days)
            row["symbol_concentration"] = contribution_concentration(candidate_trades, "symbol")
            by_year = add_time_columns(candidate_trades)
            row["year_concentration"] = contribution_concentration(by_year, "entry_year")
        else:
            row["full_trades_per_day"] = 0.0
            row["symbol_concentration"] = 1.0
            row["year_concentration"] = 1.0
        rows.append(row)
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(
        by=[
            "holdout_net_r",
            "holdout_profit_factor",
            "full_net_r",
            "full_max_drawdown_r",
            "symbol_concentration",
            "year_concentration",
        ],
        ascending=[False, False, False, True, True, True],
    ).reset_index(drop=True)


def render_markdown_report(*, title: str, summary: pd.DataFrame, output_files: dict[str, str]) -> str:
    """Render a concise markdown report."""

    lines = [f"# {title}", ""]
    lines.append("## Output Files")
    for label, path in output_files.items():
        lines.append(f"- {label}: `{path}`")
    lines.extend(["", "## Top Candidates"])
    if summary.empty:
        lines.append("- No candidates were evaluated.")
    else:
        for _, row in summary.head(10).iterrows():
            pf = row.get("holdout_profit_factor", 0.0)
            pf_text = "inf" if isinstance(pf, float) and math.isinf(pf) else f"{float(pf):.3f}"
            lines.append(
                f"- `{row['candidate_id']}` | holdout_net_r=`{float(row.get('holdout_net_r', 0.0)):.2f}` | "
                f"holdout_pf=`{pf_text}` | full_net_r=`{float(row.get('full_net_r', 0.0)):.2f}` | "
                f"trades=`{int(row.get('full_trades', 0))}` | dd=`{float(row.get('full_max_drawdown_r', 0.0)):.2f}R` | "
                f"trades/day=`{float(row.get('full_trades_per_day', 0.0)):.2f}`"
            )
    return "\n".join(lines)

