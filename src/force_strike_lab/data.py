"""Local OHLC data loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .timeframes import get_timeframe_spec, normalize_timeframe


REQUIRED_COLUMNS = [
    "time_utc",
    "symbol",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread_points",
    "real_volume",
]


def symbol_timeframe_dir(root: str | Path, symbol: str, timeframe: str) -> Path:
    """Return the data directory for one symbol/timeframe."""

    return Path(root) / str(symbol).upper() / normalize_timeframe(timeframe)


def rates_csv_path(root: str | Path, symbol: str, timeframe: str) -> Path:
    """Return the canonical local CSV path for one rates file."""

    label = normalize_timeframe(timeframe)
    return symbol_timeframe_dir(root, symbol, label) / f"{str(symbol).upper()}_{label}.csv"


def manifest_path(root: str | Path, symbol: str, timeframe: str) -> Path:
    """Return the local manifest path for one symbol/timeframe."""

    return symbol_timeframe_dir(root, symbol, timeframe) / "manifest.json"


def normalize_rates_frame(raw: pd.DataFrame, *, symbol: str, timeframe: str) -> pd.DataFrame:
    """Normalize a raw rates frame into the lab's canonical schema."""

    label = normalize_timeframe(timeframe)
    data = raw.copy()
    if "time_utc" not in data.columns:
        if "time" not in data.columns:
            raise ValueError("Rates frame must contain either time_utc or time.")
        data["time_utc"] = pd.to_datetime(data["time"], unit="s", utc=True)
    else:
        data["time_utc"] = pd.to_datetime(data["time_utc"], utc=True)

    rename = {
        "tick_volume": "tick_volume",
        "real_volume": "real_volume",
        "spread": "spread_points",
    }
    for source, target in rename.items():
        if source in data.columns and target not in data.columns:
            data[target] = data[source]

    data["symbol"] = str(symbol).upper()
    data["timeframe"] = label
    for column in ("tick_volume", "spread_points", "real_volume"):
        if column not in data.columns:
            data[column] = pd.NA
    keep = REQUIRED_COLUMNS
    for column in ("open", "high", "low", "close"):
        if column not in data.columns:
            raise ValueError(f"Rates frame missing required OHLC column {column!r}.")
    data = data.loc[:, keep].sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)
    return data


def validate_rates_frame(frame: pd.DataFrame, *, symbol: str, timeframe: str) -> None:
    """Raise if a canonical rates frame is not suitable for research."""

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Rates frame missing columns: {missing}")
    label = normalize_timeframe(timeframe)
    if frame.empty:
        raise ValueError(f"No rows available for {symbol} {label}.")
    if set(frame["symbol"].astype(str).str.upper()) != {str(symbol).upper()}:
        raise ValueError(f"Rates frame contains symbols other than {symbol}.")
    if set(frame["timeframe"].astype(str).str.upper()) != {label}:
        raise ValueError(f"Rates frame contains timeframes other than {label}.")
    timestamps = pd.to_datetime(frame["time_utc"], utc=True)
    if timestamps.duplicated().any():
        raise ValueError("Rates frame contains duplicate timestamps.")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("Rates frame timestamps must be increasing.")
    for column in ("open", "high", "low", "close"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"Rates frame contains non-numeric {column} values.")
    if ((frame["high"] < frame["low"]) | (frame["high"] < frame["open"]) | (frame["high"] < frame["close"])).any():
        raise ValueError("Rates frame contains invalid high values.")
    if ((frame["low"] > frame["open"]) | (frame["low"] > frame["close"])).any():
        raise ValueError("Rates frame contains invalid low values.")
    deltas = timestamps.diff().dropna()
    if not deltas.empty:
        expected = get_timeframe_spec(label).expected_delta
        median = pd.to_timedelta(deltas.median())
        if median != expected:
            raise ValueError(f"Median bar spacing {median} does not match {label} ({expected}).")


def write_rates_csv(root: str | Path, frame: pd.DataFrame, *, symbol: str, timeframe: str) -> Path:
    """Write canonical rates data to the local lab path."""

    target = rates_csv_path(root, symbol, timeframe)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def load_rates_csv(root: str | Path, *, symbol: str, timeframe: str) -> pd.DataFrame:
    """Load one canonical rates CSV from the lab data directory."""

    path = rates_csv_path(root, symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"Missing data file: {path}")
    frame = pd.read_csv(path)
    frame = normalize_rates_frame(frame, symbol=symbol, timeframe=timeframe)
    validate_rates_frame(frame, symbol=symbol, timeframe=timeframe)
    return frame


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON using a small local helper."""

    import json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target

