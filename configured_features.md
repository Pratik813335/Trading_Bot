# Configured & Implemented Components (End-to-End)

Below is the complete list of modules and features implemented in the platform. You can find the spreadsheet export file here: **[implemented_components.csv](file:///d:/Trading_Bot/implemented_components.csv)**.

| Component / Layer | File Path | Feature / Functionality | Implementation Details | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Dashboard UI** | [app.py](file:///d:/Trading_Bot/app.py) | Streamlit Frontend | Interactive UI for symbol/timeframe selection; renders custom Lightweight Charts overlay; displays live AI explanation; signal reasons; warnings; metric strip; and tabs. | **Completed** |
| **View Logic** | [frontend/presenter.py](file:///d:/Trading_Bot/frontend/presenter.py) | Presenter Rows Mapping | Formats signal bundle fields into presenter-friendly rows for display in the sidebar or metrics strip. | **Completed** |
| **Analysis Orchestrator** | [engine/analysis_orchestrator.py](file:///d:/Trading_Bot/engine/analysis_orchestrator.py) | Multi-Timeframe Orchestrator | Orchestrates the data fetch; calls the SMC; indicators; session; and risk engines; validates the signal; and caches responses. | **Completed** |
| **Signal Engine** | [engine/signal_engine_v2.py](file:///d:/Trading_Bot/engine/signal_engine_v2.py) | Signal Rule Engine | Computes final BUY/SELL/HOLD signals; aggregates confidence scores; and sets initial trade levels based on strategy confirmations. | **Completed** |
| **Market Structure** | [engine/structure_engine.py](file:///d:/Trading_Bot/engine/structure_engine.py) | SMC Structure Detection | Identifies swing points (HH, HL, LH, LL); detects Break of Structure (BOS); and draws structure trend lines. | **Completed** |
| **Support & Resistance** | [engine/support_resistance_engine.py](file:///d:/Trading_Bot/engine/support_resistance_engine.py) | Zone-based S&R Detection | Identifies major support and resistance zones based on historical touch points and candle bodies. | **Completed** |
| **Session Engine** | [engine/session_engine.py](file:///d:/Trading_Bot/engine/session_engine.py) | Market Sessions Tracker | Tracks active trading sessions (Sydney, Tokyo, London, New York) and identifies session high/low breakouts. | **Completed** |
| **Session Strategies** | [engine/session_strategy_engine.py](file:///d:/Trading_Bot/engine/session_strategy_engine.py) | Session-specific Rules | Applies tailored strategies (e.g., London breakout, NY trend ride) depending on active sessions. | **Completed** |
| **Technical Indicators** | [core/indicators.py](file:///d:/Trading_Bot/core/indicators.py) | Indicator Math Calculations | Calculates indicators locally (EMA 21/50/200, RSI 14, MACD, ATR 14, Bollinger Bands, Volume Averages). | **Completed** |
| **Technical Indicators** | [engine/indicator_engine.py](file:///d:/Trading_Bot/engine/indicator_engine.py) | Indicator Engine Wrapper | Calculates and maps indicator states (bullish/bearish/neutral) to support decision logic. | **Completed** |
| **Risk Management** | [core/risk.py](file:///d:/Trading_Bot/core/risk.py) | Position Sizing & Rules | Determines position size based on account balance and risk %; checks risk-reward ratios; and flags distance limit breaches. | **Completed** |
| **Risk Engine** | [engine/risk_engine.py](file:///d:/Trading_Bot/engine/risk_engine.py) | Risk Management Engine | Calculates ATR-based stop loss and take profit targets; validates trade feasibility; and ensures R:R >= 1:2. | **Completed** |
| **Market Data** | [backend/market_feed.py](file:///d:/Trading_Bot/backend/market_feed.py) | Candle Ingestion Feed | Handles live candle feeds; aggregates timeframes; and applies local CSV file fallback data if APIs fail. | **Completed** |
| **Economic News** | [backend/forex_factory_feed.py](file:///d:/Trading_Bot/backend/forex_factory_feed.py) | Forex Factory calendar feed | Fetches and parses macroeconomic events from Forex Factory to highlight news risk zones. | **Completed** |
| **News Engine** | [engine/news_intelligence_engine.py](file:///d:/Trading_Bot/engine/news_intelligence_engine.py) | Macro Event Impact Engine | Evaluates news release schedules to block or flag trades during high-impact news windows. | **Completed** |
| **Service Management** | [backend/service_container.py](file:///d:/Trading_Bot/backend/service_container.py) | Dependency Injection | Bootstraps database repositories; market data feeds; and orchestrator services into a central container. | **Completed** |
| **MetaTrader 5 Bridge** | [mt5_data.py](file:///d:/Trading_Bot/mt5_data.py) | MetaTrader 5 Integration | Connects directly to local MetaTrader 5 terminal to retrieve tick data and candles. | **Completed** |
| **AI Explanation** | [ai/explanation_service.py](file:///d:/Trading_Bot/ai/explanation_service.py) | LLM Trade Explanation | Sends technical analysis data to Gemini/LLM to generate a detailed trade rationale explanation. | **Completed** |
| **AI Analyzer** | [ai/ai_analyzer.py](file:///d:/Trading_Bot/ai/ai_analyzer.py) | AI Signal Validation | Runs LLM prompt validation on technical outputs to double-check structural trade bias. | **Completed** |
| **AI Prompts** | [ai/prompts.py](file:///d:/Trading_Bot/ai/prompts.py) | LLM Prompt Templates | Templates defining the exact prompt structure, JSON format, and constraints for the AI model. | **Completed** |
| **Persistence** | [storage/signal_repository_v2.py](file:///d:/Trading_Bot/storage/signal_repository_v2.py) | Signal DB Repository | Saves and loads active and historic trading signals to JSONL database records. | **Completed** |
| **Persistence** | [storage/news_signal_repository.py](file:///d:/Trading_Bot/storage/news_signal_repository.py) | News Events Repository | Saves and retrieves historical economic calendar releases. | **Completed** |
| **Persistence** | [storage/trade_journal.py](file:///d:/Trading_Bot/storage/trade_journal.py) | Trade Log Journal | Logs simulated or executed trades, entry/exit timestamps, and P&L results. | **Completed** |
| **Backtesting** | [core/backtesting.py](file:///d:/Trading_Bot/core/backtesting.py) | Historical Backtester | Simulates strategy rules against historical candle data; returns win rate, profit factor, drawdown, and average R:R. | **Completed** |
| **System Config** | [config.py](file:///d:/Trading_Bot/config.py) | Global Configurations | Centralizes definitions for SYMBOLS, TIMEFRAMES, account balances, risk parameters, and environment paths. | **Completed** |
| **System Config** | [.env](file:///d:/Trading_Bot/.env) | API Keys & Environment | Stores private API keys, local MT5 credentials, and platform flags. | **Completed** |

---
*Note: You can open the [implemented_components.csv](file:///d:/Trading_Bot/implemented_components.csv) directly in Microsoft Excel, Google Sheets, or LibreOffice Calc.*
