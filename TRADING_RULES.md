# Trading Rules

These rules are the source of truth for the signal engine. Code changes in `analysis.py`, future `core/` modules, and the Streamlit signal panel must follow these rules.

## Core Constraints

- Do not use paid APIs or paid market-data services.
- Use TradingView as the visual chart screen only.
- Calculate signals, entry, stop loss, take profit, confidence, and warnings inside our own Python engine.
- Use free/local candle data sources only, such as sample CSV, user-imported CSV, or free data sources that are allowed.
- Treat every signal as decision support, not guaranteed profit.

## Allowed Markets

- XAUUSD
- EURUSD
- GBPUSD
- AUDUSD
- USDJPY
- USDCHF
- USDCAD

## Candle Rules

- Every candle must include open, high, low, close, and time.
- Candle patterns are confirmations, not standalone trade signals.
- Important candle patterns:
  - Hammer: bullish reversal near support.
  - Shooting Star: bearish reversal near resistance.
  - Doji: indecision; use only with context.
  - Bullish Engulfing: bullish reversal confirmation.
  - Bearish Engulfing: bearish reversal confirmation.
  - 3 White Soldiers: bullish continuation.
  - 3 Black Crows: bearish continuation.

## Support And Resistance Rules

- Support and resistance must be treated as zones, not exact single prices.
- Strong zones should have multiple touches, ideally 3 or more.
- Higher timeframe zones are stronger than lower timeframe zones.
- Broken support can become resistance.
- Broken resistance can become support.
- BUY setups are stronger near support.
- SELL setups are stronger near resistance.
- Avoid BUY directly below strong resistance.
- Avoid SELL directly above strong support.

## Market Structure Rules

- Uptrend: higher highs and higher lows.
- Downtrend: lower highs and lower lows.
- Range: price moving between clear support and resistance.
- In an uptrend, prefer BUY on pullback to higher low/support.
- In a downtrend, prefer SELL on pullback to lower high/resistance.
- If market structure is unclear, signal should be HOLD.
- Break of Structure confirms continuation.
- Change of Character warns of possible reversal.

## Smart Money Concept Rules

- Liquidity exists above swing highs and below swing lows.
- A liquidity sweep followed by reclaim/rejection improves signal quality.
- Order blocks are zones from the last candle before a strong move.
- Fair Value Gaps are imbalance zones where price may return before continuation.
- BOS confirms trend continuation.
- CHOCH warns bias may be changing.
- SMC signals must align with structure or confidence should be reduced.

## Indicator Rules

- EMA 50 and EMA 200 define trend bias.
- Price above EMA 50 and EMA 200 supports bullish bias.
- Price below EMA 50 and EMA 200 supports bearish bias.
- RSI above 70 means overbought risk.
- RSI below 30 means oversold risk.
- RSI divergence is stronger than RSI level alone.
- MACD crossover can confirm momentum.
- ATR is used for volatility-based stop loss.
- Bollinger Band squeeze can warn of expansion but is not an entry by itself.

## Fibonacci Rules

- Fibonacci must be drawn from a meaningful swing high and swing low from market structure.
- Fibonacci alone must never create a BUY or SELL signal.
- Important retracement levels:
  - 0.382
  - 0.5
  - 0.618
  - 0.705
  - 0.786
- Smart Money OTE zone is 0.705 to 0.79.
- BUY Fibonacci setup:
  - Higher timeframe bias is bullish.
  - Price pulls back into discount or OTE zone.
  - Fibonacci zone aligns with support, order block, or FVG.
  - Entry requires candle confirmation, BOS, or CHOCH confirmation.
- SELL Fibonacci setup:
  - Higher timeframe bias is bearish.
  - Price pulls back into premium or OTE zone.
  - Fibonacci zone aligns with resistance, order block, or FVG.
  - Entry requires candle confirmation, BOS, or CHOCH confirmation.
- Take profit can target next support/resistance, next liquidity zone, FVG, or Fibonacci extension.
- Preferred Fibonacci extension targets:
  - 1.272
  - 1.618

## Multi-Timeframe Rules

- Never rely on a single timeframe for strong signals.
- D1: macro bias.
- H4: key structure and major S/R.
- H1: setup area and confirmation.
- M15: entry timing.
- M5: scalping entry timing only.
- Higher timeframe bias controls trade direction.
- Lower timeframe gives entry timing.
- If timeframes conflict, reduce confidence.
- If conflict is strong, signal should be HOLD.

## Risk Management Rules

- Never risk more than 1-2 percent on one trade.
- Stop loss is required for every BUY or SELL signal.
- Minimum risk:reward should be 1:2.
- Never move stop loss to a worse position.
- Avoid revenge trading logic or repeated entries after loss.
- Backtest at least 200 historical trades before trusting any strategy.
- Start with paper/demo testing before any live trading.

## Signal Decision Rules

- BUY or SELL requires multiple confirmations.
- HOLD is the default when quality is low.
- Confidence should increase when trend, structure, S/R, SMC, Fibonacci, candle pattern, and indicators align.
- Confidence should decrease when signals conflict.
- No trade should be taken when:
  - Structure is unclear.
  - Price is in the middle of a range.
  - Risk:reward is below 1:2.
  - Stop loss cannot be placed logically.
  - Higher timeframe bias strongly conflicts with entry direction.

