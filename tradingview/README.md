# TradingView Force Strike Indicator

Copy `force_strike_signal.pine` into TradingView's Pine Editor and add it to a chart.

Default behavior is intentionally clean:
- accepted Force Strike signals only
- mother range box
- 20/50 SMA lines
- no rejected raw patterns
- no diagnostic labels

The current visual filter is stricter than the original baseline: it expects a
clear 50 SMA slope plus a prior impulse followed by an opposite close
retracement before the Force Strike forms. For bullish setups, that means prior
upside first, then downside retracement into the moving-average area. Bearish is
the mirror image.

Useful validation toggles:
- `Show diagnostic label`: shows the main pass/fail context details.
- `Show rejected raw patterns`: shows raw Force Strike patterns that fail the current context gate.
- `Confirm on candle close`: keeps realtime signals from appearing before the signal candle closes.
- `Minimum 50-SMA slope ATR`: raises/lowers the flat-trend rejection threshold.
- `Minimum prior retrace close ATR`: controls how much close-based retracement is required after the prior swing.

Python remains the research source of truth for basket testing, fills, costs, candidate ranking, and reports. This Pine script is for client-facing visual verification on the chart that TradingView displays.

## Chart-Source Boundary

The indicator evaluates the same rule family on TradingView's active chart candles. The Python lab evaluates it on MT5-exported candles.

Both can be correct for their own chart stream. If TradingView and MT5 candles differ because of feed, timezone, session, or broker construction, the signal may appear on different bars or appear in one environment and not the other. That is expected behavior, not automatically a bug.

For client use, judge the TradingView signal against the TradingView chart being viewed. For statistical testing, use the Python reports.
