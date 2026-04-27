# TradingView Force Strike Indicator

Copy `force_strike_signal.pine` into TradingView's Pine Editor and add it to a chart.

Default behavior is intentionally clean:
- accepted Force Strike signals only
- mother range box
- 20/50 SMA lines
- no rejected raw patterns
- no diagnostic labels

The default visual filter is the current legacy baseline. It expects a valid
Force Strike pattern around the 20/50 SMA retracement area, a valid 50 SMA
anchor, meaningful impulse, trend-side agreement, pre-mother retracement, and
recent progress. The experimental retrace-close extra is available but disabled
by default.

Useful validation toggles:
- `Show diagnostic label`: shows the main pass/fail context details.
- `Show rejected raw patterns`: shows raw Force Strike patterns that fail the current context gate.
- `Confirm on candle close`: keeps realtime signals from appearing before the signal candle closes.
- `Minimum 50-SMA slope ATR`: raises/lowers the flat-trend rejection threshold.
- `Use experimental retrace-close extra`: enables the archived swing/retrace-style close retracement check.
- `Minimum prior retrace close ATR`: controls that optional close-based retracement check.

Python remains the research source of truth for basket testing, fills, costs, candidate ranking, and reports. This Pine script is for client-facing visual verification on the chart that TradingView displays.

## Chart-Source Boundary

The indicator evaluates the same rule family on TradingView's active chart candles. The Python lab evaluates it on MT5-exported candles.

Both can be correct for their own chart stream. If TradingView and MT5 candles differ because of feed, timezone, session, or broker construction, the signal may appear on different bars or appear in one environment and not the other. That is expected behavior, not automatically a bug.

For client use, judge the TradingView signal against the TradingView chart being viewed. For statistical testing, use the Python reports.
