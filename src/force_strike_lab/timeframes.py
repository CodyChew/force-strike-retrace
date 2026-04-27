"""Supported timeframe registry for Force Strike research."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TimeframeSpec:
    label: str
    mt5_constant_name: str
    pandas_freq: str
    expected_delta: pd.Timedelta
    default_history_years: int


SUPPORTED_TIMEFRAMES: dict[str, TimeframeSpec] = {
    "M30": TimeframeSpec(
        label="M30",
        mt5_constant_name="TIMEFRAME_M30",
        pandas_freq="30min",
        expected_delta=pd.Timedelta(minutes=30),
        default_history_years=3,
    ),
    "H4": TimeframeSpec(
        label="H4",
        mt5_constant_name="TIMEFRAME_H4",
        pandas_freq="4h",
        expected_delta=pd.Timedelta(hours=4),
        default_history_years=5,
    ),
    "D1": TimeframeSpec(
        label="D1",
        mt5_constant_name="TIMEFRAME_D1",
        pandas_freq="1D",
        expected_delta=pd.Timedelta(days=1),
        default_history_years=10,
    ),
}


def normalize_timeframe(value: str) -> str:
    """Return the canonical supported timeframe label."""

    label = str(value).strip().upper()
    aliases = {
        "30": "M30",
        "30M": "M30",
        "30MIN": "M30",
        "M30": "M30",
        "240": "H4",
        "4H": "H4",
        "H4": "H4",
        "1D": "D1",
        "D": "D1",
        "D1": "D1",
        "DAILY": "D1",
    }
    if label not in aliases:
        raise ValueError(f"Unsupported timeframe {value!r}; supported: {sorted(SUPPORTED_TIMEFRAMES)}")
    return aliases[label]


def get_timeframe_spec(value: str) -> TimeframeSpec:
    """Return the registry entry for a supported timeframe."""

    return SUPPORTED_TIMEFRAMES[normalize_timeframe(value)]


def mt5_timeframe_value(mt5_module, timeframe: str) -> int:
    """Resolve a supported timeframe to a MetaTrader5 constant."""

    spec = get_timeframe_spec(timeframe)
    if not hasattr(mt5_module, spec.mt5_constant_name):
        raise ValueError(f"MetaTrader5 module does not expose {spec.mt5_constant_name}.")
    return int(getattr(mt5_module, spec.mt5_constant_name))

