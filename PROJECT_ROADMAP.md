# AI Forex Trading Platform Roadmap

## 1. Project Goal

Build a professional Python-based trading signal platform that analyzes forex and gold markets, generates high-quality trade signals, explains the reason for each signal, and applies strict risk management.

The first version will stay in Python and Streamlit. A React frontend or separate backend can be added later after the signal engine is stable.

Important constraint:

- Do not use paid APIs or paid market-data services.
- TradingView should be used as the visual charting screen.
- Trade analysis, entry, stop loss, take profit, confidence, and warnings must be calculated by our own Python engine using free/local data sources.
- Do not depend on scraping TradingView widget internals for candles or signals.

## 2. Current Project State

The current project is an early Streamlit app with:

- TradingView chart display
- Basic live data fetch through Alpha Vantage
- Basic signal generation using EMA, trend, support/resistance, FVG, BOS, liquidity, and candle pattern checks
- Basic risk calculation using account balance and risk percentage

Current important files:

- `app.py` - Streamlit user interface
- `analysis.py` - signal logic
- `live_data.py` - live forex data fetch
- `Trading.py` - trade sizing and execution placeholder
- `config.py` - symbols, timeframes, balance, risk settings
- `TRADING_RULES.md` - source of truth for strategy, risk, MTF, SMC, and Fibonacci rules
- `requirements.txt` - Python dependencies

## 3. Target Pro Platform

The professional version should include:

- Signal engine that strictly follows `TRADING_RULES.md`
- Clean dashboard with chart, signal panel, market status, and signal history
- Strong rule-based signal engine
- Multi-timeframe analysis
- Smart Money Concepts analysis
- Fibonacci and OTE zone analysis
- Indicator confirmation
- ATR-based stop loss
- Risk:Reward validation
- Confidence score
- Trade journal/history
- Backtesting support
- AI prompt integration later
- Optional screenshot + OHLCV AI analysis later

## 3A. Professional Readiness Checklist

The platform should not be called professional or strong in real use until these items are implemented and tested without paid APIs:

- Clean candle data source using free/local data only
- Proper indicator calculations:
  - EMA
  - RSI
  - MACD
  - ATR
- Real market structure detection:
  - Higher Highs
  - Higher Lows
  - Lower Highs
  - Lower Lows
- Zone-based support and resistance
- Fibonacci swing detection
- Fibonacci retracement and extension validation
- OTE zone validation
- Scoring system for confidence
- Backtesting on at least 200 historical trades
- Signal history and trade journal
- Warnings when market conditions are bad
- No-trade logic when risk:reward, structure, spread, or timeframe alignment is poor
- Clear disclaimer that this is decision support, not guaranteed profit

## 3B. Free Research And Regulation Resources

Rules and risk controls can be improved from free and official sources only.

Primary free resources:

- `AI_Forex_Master_Guide_v3 (1).docx` - current strategy reference
- `TRADING_RULES.md` - project source of truth
- TradingView free chart and public educational material for visual study
- Free/local CSV candle data for testing
- User-collected/backtested trade journal data

Official regulation and risk-awareness references:

- RBI guidance on authorised forex electronic trading platforms and unauthorised platform alert lists
- SEBI investor education, investor charter, derivatives risk disclosure, and registered intermediary guidance
- CFTC forex fraud and retail forex risk advisories
- NFA/CFTC registration checks before using any broker or advisory service

Rules:

- Do not copy paid strategies or depend on paid signal services.
- Do not treat social media signals as strategy rules.
- Any new trading rule must be written into `TRADING_RULES.md` before code changes.
- Any regulation-related feature must be treated as informational only, not legal advice.

## 4. Build Strategy

We should not jump directly into AI or real trading execution.

Recommended order:

1. Clean Python project structure
2. Improve live data handling
3. Build a strong rule-based strategy engine
4. Add multi-timeframe analysis
5. Add risk management and signal validation
6. Add signal history and journal
7. Add backtesting
8. Add AI prompt integration
9. Add real broker execution only after testing

## 5. Phase 1 - Project Structure

Goal: make the code easy to grow.

Possible future structure:

```text
Trading_Bot/
  app.py
  config.py
  requirements.txt
  data.csv
  core/
    indicators.py
    market_structure.py
    smc.py
    fibonacci.py
    risk.py
    signal_engine.py
  data/
    live_feed.py
    sample_loader.py
  ai/
    prompts.py
    ai_analyzer.py
  storage/
    signal_history.py
  tests/
    test_signal_engine.py
```

No need to create all files at once. We create them step by step.

## 6. Phase 2 - Data Layer

Goal: get clean OHLCV candles.

Required candle columns:

- `time`
- `open`
- `high`
- `low`
- `close`
- `volume`

Rules:

- Every strategy function should receive clean candles.
- If live API fails, app can use sample data.
- Timeframes must be mapped correctly.
- XAUUSD, forex pairs, and broker-specific symbols may need separate handling.

Possible data sources:

- Local/sample CSV data for development
- Free public data sources where allowed
- User-imported CSV candle data
- TradingView widget for visual chart display only
- MetaTrader 5 later
- Broker API later only if free/demo and explicitly approved
- TradingView chart only for visual display

## 7. Phase 3 - Indicator Engine

Indicators to calculate:

- EMA 21
- EMA 50
- EMA 200
- RSI 14
- MACD
- ATR 14
- Bollinger Bands
- Volume average

Rules:

- Indicators should be calculated before signal generation.
- Signal engine should not guess indicator values.
- ATR must be used for stop loss calculation in live OHLCV mode.

## 8. Phase 4 - Market Structure

Market structure must detect:

- Uptrend: Higher Highs and Higher Lows
- Downtrend: Lower Highs and Lower Lows
- Sideways/range market
- Break of Structure
- Change of Character

Rules:

- Higher timeframe structure is more important than lower timeframe noise.
- Avoid signals when structure is unclear.
- If structure conflicts with indicator direction, confidence should drop.

## 9. Phase 5 - Support And Resistance

Support/resistance should be zone-based, not exact-line based.

Strong zones need:

- Multiple touches
- Recent reaction
- Higher timeframe importance
- Volume spike if available
- Role reversal after breakout

Signal rules:

- BUY is stronger near support.
- SELL is stronger near resistance.
- Avoid buying directly into strong resistance.
- Avoid selling directly into strong support.

## 10. Phase 6 - Smart Money Concepts

SMC rules to implement:

- Liquidity above swing highs
- Liquidity below swing lows
- Order blocks
- Fair Value Gaps
- Break of Structure
- Change of Character

Signal rules:

- BUY setup improves if sell-side liquidity was swept and price reclaims structure.
- SELL setup improves if buy-side liquidity was swept and price rejects.
- FVG and order block should be treated as zones.
- Unmitigated zones are stronger than already-tested zones.

## 11. Phase 7 - Fibonacci Rules

Fibonacci must use meaningful swing high and swing low from market structure.

Important retracement levels:

- `0.382`
- `0.5`
- `0.618`
- `0.705`
- `0.786`

Smart Money OTE zone:

- `0.705` to `0.79`

BUY rules:

- Main trend is bullish.
- Price pulls back into discount area or OTE zone.
- Fib zone aligns with support, order block, or FVG.
- Entry requires candle confirmation or structure confirmation.

SELL rules:

- Main trend is bearish.
- Price pulls back into premium area or OTE zone.
- Fib zone aligns with resistance, order block, or FVG.
- Entry requires candle confirmation or structure confirmation.

Take profit can use:

- Next support/resistance
- Next liquidity zone
- Fibonacci extension `1.272`
- Fibonacci extension `1.618`

Important rule:

- Fibonacci alone must never create a signal. It is only one confirmation.

## 12. Phase 8 - Multi-Timeframe Analysis

Recommended MTF model:

- D1: macro bias
- H4: market structure
- H1: setup area
- M15/M5: entry timing

For swing/day trading:

- D1 + H4 + H1 alignment is preferred.

For scalping:

- H4 + H1 + M15 or H1 + M15 + M5 can be used.

Rules:

- Higher timeframe bias should control signal direction.
- Lower timeframe gives entry timing only.
- If timeframes conflict, confidence should drop.
- If conflict is strong, signal should be HOLD.

## 13. Phase 9 - Signal Scoring

Each signal should be scored by confirmations.

Example confirmations:

- Trend aligned
- Higher timeframe aligned
- EMA aligned
- RSI supports direction
- MACD supports direction
- Price near support/resistance
- Fibonacci zone confluence
- FVG/order block confluence
- BOS/CHOCH confirmation
- Candle pattern confirmation
- ATR-based stop loss valid
- Minimum risk reward achieved

Suggested confidence:

- 80-100: strong setup
- 60-79: good setup
- 40-59: weak/moderate setup
- Below 40: skip trade

Rules:

- BUY/SELL should require minimum confirmations.
- HOLD should be returned when quality is low.
- Confidence should reduce when signals conflict.

## 14. Phase 10 - Risk Management

Mandatory risk rules:

- Never risk more than 1-2 percent per trade.
- Stop loss is required for every signal.
- Minimum Risk:Reward should be 1:2 unless user changes it.
- ATR-based stop loss should be used for live data.
- Avoid trade if stop loss distance is too small or too large.
- Avoid trade during high spread or unclear market conditions.

Future risk features:

- Daily loss limit
- Max trades per day
- Max open risk
- Correlated pair warning
- News filter

## 15. Phase 11 - AI Prompt Integration

AI should be added after the rule-based engine is stable.

AI modes:

- Screenshot analysis
- Live OHLCV analysis
- Multi-timeframe OHLCV analysis
- Combined screenshot + OHLCV analysis

AI output must be valid JSON and include:

- pair
- timeframe
- trend
- structure
- support zones
- resistance zones
- candle patterns
- indicators
- entry
- stop_loss
- take_profit
- risk_reward
- confidence
- data_source
- explanation
- risk_warning

Rules:

- AI should support decision-making, not blindly control trades.
- App should validate AI output before displaying or executing signals.
- AI confidence should be compared with rule-based confidence.

## 16. Phase 12 - Dashboard

Dashboard should show:

- TradingView chart
- Current pair and timeframe
- Current signal
- Confidence score
- Entry, SL, TP
- Risk:Reward
- Main reasons for signal
- Warning messages
- Signal history
- Start/stop monitoring controls

Later dashboard features:

- Multi-timeframe table
- Strategy checklist
- Backtest results
- Trade journal
- Export to CSV
- Alert sound/notification

## 17. Phase 13 - Backtesting

Backtesting is required before live trading.

Rules:

- Test at least 200 historical trades.
- Track win rate.
- Track average risk reward.
- Track drawdown.
- Track best/worst pairs.
- Track best/worst timeframes.

Metrics:

- Total trades
- Win rate
- Profit factor
- Max drawdown
- Average R
- Consecutive losses

## 18. Phase 14 - Execution

Execution should be the final step, not the first step.

Execution stages:

1. Signal only
2. Paper trading
3. Demo account execution
4. Micro-lot live trading
5. Full live trading only after proof

Rules:

- Never auto-execute real trades until backtesting and demo testing are complete.
- User must confirm real execution mode.
- Every executed trade must be logged.

## 19. Recommended Immediate Next Steps

Step 1:
Finalize the strategy checklist and signal scoring rules.

Step 2:
Decide if we keep Streamlit for the MVP.

Step 3:
Refactor `analysis.py` into cleaner modules only after the rules are final.

Step 4:
Improve indicators and risk logic.

Step 5:
Add multi-timeframe support.

Step 6:
Add AI prompt integration.

## 20. First Coding Task Recommendation

The first actual coding task should be:

Create a clean signal result format.

Example:

```python
{
    "signal": "BUY",
    "confidence": 82,
    "entry": 1.0850,
    "stop_loss": 1.0807,
    "take_profit": 1.0934,
    "risk_reward": 2.0,
    "trend": "bullish",
    "reasons": [
        "Price above EMA50 and EMA200",
        "Bullish BOS confirmed",
        "Pullback into Fibonacci OTE zone",
        "RSI bullish but not overbought"
    ],
    "warnings": []
}
```

This makes the app professional because every signal has structure, reasoning, and validation.

## 21. Important Disclaimer

This platform should be treated as a trading decision-support system, not a guaranteed profit machine.

AI and technical analysis can improve decision quality, but they cannot remove market risk. All strategies must be backtested and forward-tested before real money trading.

## 22. Current Progress Status

Overall estimated progress for demo readiness:

- MVP/demo readiness: `70%`
- Full professional production readiness: `45%`

Current active development zone:

- Main focus is between `Phase 8` and `Phase 13`
- The platform is now strong enough for a guided demo
- The platform is not yet ready for unattended real-money execution

### Phase Status Table

| Phase | Name | Status | Notes |
| --- | --- | --- | --- |
| 1 | Project Structure | Completed | Core modules now split into `core/`, `data/`, `ai/`, and `storage/` |
| 2 | Data Layer | Completed | Live fetch, sample fallback, OHLC validation, and local `.env` support are in place |
| 3 | Indicator Engine | Completed | EMA, RSI, MACD, ATR, Bollinger bands, and volume average are implemented |
| 4 | Market Structure | In Progress | Swing logic, trend detection, BOS, and liquidity checks exist; CHOCH needs improvement |
| 5 | Support And Resistance | In Progress | Zone-based support and resistance are implemented, but ranking can improve |
| 6 | Smart Money Concepts | In Progress | FVG, BOS, and liquidity logic exist; order blocks and deeper SMC rules are still pending |
| 7 | Fibonacci Rules | In Progress | Fibonacci retracement and OTE logic are implemented; confluence rules can be expanded |
| 8 | Multi-Timeframe Analysis | In Progress | Timeframe builder and first-pass MTF alignment are implemented |
| 9 | Signal Scoring | In Progress | Confidence scoring, HOLD logic, and rule-based confirmations are implemented |
| 10 | Risk Management | In Progress | ATR-aware SL/TP logic, risk:reward checks, and basic position sizing are implemented |
| 11 | AI Prompt Integration | In Progress | AI prompt scaffolding exists, but no live AI provider is connected yet |
| 12 | Dashboard | In Progress | Trade panel shows signal, confidence, reasons, warnings, history, and backtest summary |
| 13 | Backtesting | In Progress | First backtesting engine and summary metrics are implemented |
| 14 | Execution | Pending | Real broker execution workflow is intentionally not complete |

### Completed For Demo

- Structured signal output
- Rule-based signal engine
- Live or fallback candle loading
- Support/resistance zones
- Fibonacci OTE checks
- BOS, liquidity, and candle confirmation logic
- Multi-timeframe dataset preparation
- Basic backtesting metrics
- Signal history logging
- Demo-safe panel output with reasons and warnings

### Still Pending Before Full Production Use

- Real AI model integration
- More robust higher-timeframe confluence logic
- Order block and deeper CHOCH logic
- Full backtesting validation over at least 200 high-quality trades
- Trade journal UI and export workflows
- News filter and spread-aware trade filter
- Demo-account and broker execution workflow

### Demo Guidance For Tomorrow

- Prefer `EURUSD` first for the live-candle demo
- Confirm panel data source says `Free/live candle feed`
- Treat backtest output as simulated strategy validation, not broker-realized P&L
- Keep `XAUUSD` demo as secondary because symbol handling can vary by data source
