"""MT5-direct data pulls for Force Strike research."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ResearchConfig
from .data import manifest_path, normalize_rates_frame, rates_csv_path, validate_rates_frame, write_json, write_rates_csv
from .timeframes import mt5_timeframe_value


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_utc_datetime(value: str) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def resolve_date_window(config: ResearchConfig) -> tuple[datetime, datetime]:
    """Resolve the UTC pull window from explicit dates or history_years."""

    end = (
        datetime.now(timezone.utc)
        if config.date_end_utc is None
        else _to_utc_datetime(config.date_end_utc)
    )
    if config.date_start_utc is not None:
        start = _to_utc_datetime(config.date_start_utc)
    else:
        years = config.history_years if config.history_years is not None else 3
        start = end - timedelta(days=int(years) * 365)
    if end <= start:
        raise ValueError("Resolved date_end_utc must be later than date_start_utc.")
    return start, end


def ensure_symbol(mt5_module: Any, symbol: str) -> Any:
    """Select one MT5 symbol and return symbol_info."""

    info = mt5_module.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info unavailable for {symbol}: {mt5_module.last_error()}")
    if not getattr(info, "visible", True) and not mt5_module.symbol_select(symbol, True):
        raise RuntimeError(f"symbol_select failed for {symbol}: {mt5_module.last_error()}")
    return info


def symbol_capabilities(info: Any, symbol: str) -> dict[str, Any]:
    """Extract a stable subset of MT5 symbol metadata."""

    return {
        "symbol": str(symbol).upper(),
        "digits": _safe_int(getattr(info, "digits", None)),
        "point": _safe_float(getattr(info, "point", None)),
        "spread_points": _safe_int(getattr(info, "spread", None)),
        "spread_float": bool(getattr(info, "spread_float", False)),
        "trade_tick_value": _safe_float(getattr(info, "trade_tick_value", None)),
        "trade_tick_size": _safe_float(getattr(info, "trade_tick_size", None)),
        "volume_min": _safe_float(getattr(info, "volume_min", None)),
        "volume_max": _safe_float(getattr(info, "volume_max", None)),
        "volume_step": _safe_float(getattr(info, "volume_step", None)),
    }


def _point_value_per_lot(info: Any) -> float:
    tick_value = _safe_float(getattr(info, "trade_tick_value", None))
    tick_size = _safe_float(getattr(info, "trade_tick_size", None))
    point = _safe_float(getattr(info, "point", None))
    if tick_size <= 0 or point <= 0:
        return 0.0
    return tick_value * (point / tick_size)


def estimate_commission_points(mt5_module: Any, symbol: str, info: Any, lookback_days: int = 365) -> dict[str, Any]:
    """Estimate round-turn commission in points from MT5 deal history when possible."""

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    deals = mt5_module.history_deals_get(start, end)
    if deals is None:
        return {
            "source": "history",
            "positions_considered": 0,
            "round_turn_commission_per_lot": 0.0,
            "round_turn_commission_points": 0.0,
            "history_error": mt5_module.last_error(),
        }
    by_position: dict[int, dict[str, float]] = {}
    for deal in deals:
        if str(getattr(deal, "symbol", "") or "").upper() != symbol.upper():
            continue
        position_id = _safe_int(getattr(deal, "position_id", None), default=0)
        if position_id == 0:
            continue
        row = by_position.setdefault(position_id, {"commission": 0.0, "volume": 0.0})
        row["commission"] += abs(_safe_float(getattr(deal, "commission", 0.0)))
        row["volume"] = max(row["volume"], _safe_float(getattr(deal, "volume", 0.0)))
    per_lot = [row["commission"] / row["volume"] for row in by_position.values() if row["volume"] > 0]
    avg_per_lot = float(pd.Series(per_lot).mean()) if per_lot else 0.0
    point_value = _point_value_per_lot(info)
    return {
        "source": "history",
        "positions_considered": len(per_lot),
        "round_turn_commission_per_lot": avg_per_lot,
        "round_turn_commission_points": avg_per_lot / point_value if point_value > 0 else 0.0,
    }


def pull_symbol_rates(
    mt5_module: Any,
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Pull one symbol/timeframe from MT5 and return a canonical rates frame."""

    raw = mt5_module.copy_rates_range(symbol, mt5_timeframe_value(mt5_module, timeframe), start, end)
    if raw is None:
        raise RuntimeError(f"copy_rates_range failed for {symbol} {timeframe}: {mt5_module.last_error()}")
    return normalize_rates_frame(pd.DataFrame(raw), symbol=symbol, timeframe=timeframe)


def pull_mt5_data(config: ResearchConfig, *, project_root: str | Path, mt5_module: Any | None = None) -> dict[str, Any]:
    """Pull the configured basket directly from MT5 into local CSV files."""

    if mt5_module is None:
        import MetaTrader5 as mt5_module  # type: ignore

    if not mt5_module.initialize():
        raise RuntimeError(f"MetaTrader5 initialize failed: {mt5_module.last_error()}")

    start, end = resolve_date_window(config)
    root = Path(project_root)
    data_root = root / config.data_dir
    results: list[dict[str, Any]] = []
    try:
        account = mt5_module.account_info()
        terminal = mt5_module.terminal_info()
        for symbol in config.symbols:
            info = ensure_symbol(mt5_module, symbol)
            frame = pull_symbol_rates(mt5_module, symbol=symbol, timeframe=config.timeframe, start=start, end=end)
            validate_rates_frame(frame, symbol=symbol, timeframe=config.timeframe)
            csv_path = write_rates_csv(data_root, frame, symbol=symbol, timeframe=config.timeframe)
            capabilities = symbol_capabilities(info, symbol)
            commission = estimate_commission_points(mt5_module, symbol, info)
            manifest = {
                "symbol": symbol,
                "timeframe": config.timeframe,
                "requested_start_utc": start.isoformat(),
                "requested_end_utc": end.isoformat(),
                "rows": int(len(frame)),
                "coverage_start_utc": None if frame.empty else str(frame["time_utc"].iloc[0]),
                "coverage_end_utc": None if frame.empty else str(frame["time_utc"].iloc[-1]),
                "path": str(csv_path),
                "capabilities": capabilities,
                "commission_estimate": commission,
                "account": None if account is None else {
                    "login": _safe_int(getattr(account, "login", None)),
                    "server": getattr(account, "server", None),
                    "currency": getattr(account, "currency", None),
                },
                "terminal": None if terminal is None else {
                    "path": getattr(terminal, "path", None),
                    "company": getattr(terminal, "company", None),
                    "name": getattr(terminal, "name", None),
                },
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            manifest_file = write_json(manifest_path(data_root, symbol, config.timeframe), manifest)
            results.append({"symbol": symbol, "rows": len(frame), "csv_path": str(csv_path), "manifest_path": str(manifest_file)})
        return {
            "timeframe": config.timeframe,
            "requested_start_utc": start.isoformat(),
            "requested_end_utc": end.isoformat(),
            "files": results,
        }
    finally:
        mt5_module.shutdown()


def local_data_status(config: ResearchConfig, *, project_root: str | Path) -> list[dict[str, Any]]:
    """Return local data-file existence and coverage info without querying MT5."""

    root = Path(project_root) / config.data_dir
    rows = []
    for symbol in config.symbols:
        path = rates_csv_path(root, symbol, config.timeframe)
        rows.append({"symbol": symbol, "timeframe": config.timeframe, "exists": path.exists(), "path": str(path)})
    return rows
