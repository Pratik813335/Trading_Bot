from ai.explanation_service import AIExplanationService
from engine.models import AnalysisBundle, NewsSignal
from engine.session_engine import SessionEngine
from engine.session_strategy_engine import SessionStrategyEngine


class AnalysisOrchestrator:
    def __init__(
        self,
        market_feed,
        indicator_engine,
        structure_engine,
        zone_engine,
        signal_engine,
        renderer,
        signal_repository,
        forex_factory_feed=None,
        news_engine=None,
        news_signal_repository=None,
        session_engine=None,
        session_strategy_engine=None,
    ):
        self.market_feed = market_feed
        self.indicator_engine = indicator_engine
        self.structure_engine = structure_engine
        self.zone_engine = zone_engine
        self.signal_engine = signal_engine
        self.renderer = renderer
        self.signal_repository = signal_repository
        self.forex_factory_feed = forex_factory_feed
        self.news_engine = news_engine
        self.news_signal_repository = news_signal_repository
        self.session_engine = session_engine or SessionEngine()
        self.session_strategy_engine = session_strategy_engine or SessionStrategyEngine()
        self.ai_service = AIExplanationService()

    def _zone_summary(self, zones, zone_type):
        typed = [zone for zone in zones if zone.type == zone_type]
        if not typed:
            return None
        strongest = max(typed, key=lambda zone: zone.strength)
        return {
            "top": strongest.top,
            "bottom": strongest.bottom,
            "strength": strongest.strength,
        }

    def _build_trade_payload(self, signal, ai_explanation, zones):
        return {
            "signal": signal.signal,
            "confidence": signal.confidence,
            "provider": signal.feed_source,
            "timeframe": signal.timeframe,
            "candle_time": signal.candle_timestamp,
            "indicators": {
                "rsi": signal.indicators.get("rsi14"),
                "ema": {
                    "ema21": signal.indicators.get("ema21"),
                    "ema50": signal.indicators.get("ema50"),
                    "ema200": signal.indicators.get("ema200"),
                },
                "atr": signal.indicators.get("atr14"),
                "macd": {
                    "macd": signal.indicators.get("macd"),
                    "signal": signal.indicators.get("macd_signal"),
                    "hist": signal.indicators.get("macd_hist"),
                },
            },
            "structure": {
                "trend": signal.structure.get("trend"),
                "bos": signal.structure.get("bos") or "none",
                "choch": signal.structure.get("choch") or "none",
            },
            "zones": {
                "support": self._zone_summary(zones, "support"),
                "resistance": self._zone_summary(zones, "resistance"),
            },
            "risk": {
                "sl": signal.stop_loss,
                "tp": signal.tp1,
                "rr": signal.rr_ratio,
            },
            "explanation": ai_explanation.get("summary") or ai_explanation.get("explanation"),
        }

    def _find_missing_trade_fields(self, trade_payload):
        missing = []
        required_top_level = [
            "signal",
            "confidence",
            "provider",
            "timeframe",
            "candle_time",
            "indicators",
            "structure",
            "zones",
            "risk",
            "explanation",
        ]
        for field_name in required_top_level:
            value = trade_payload.get(field_name)
            if value is None or value == "" or value == {}:
                missing.append(field_name)

        indicators = trade_payload.get("indicators") or {}
        if indicators.get("rsi") is None:
            missing.append("indicators.rsi")
        ema = indicators.get("ema") or {}
        if any(ema.get(key) is None for key in ["ema21", "ema50", "ema200"]):
            missing.append("indicators.ema")
        if indicators.get("atr") is None:
            missing.append("indicators.atr")
        macd = indicators.get("macd") or {}
        if any(macd.get(key) is None for key in ["macd", "signal", "hist"]):
            missing.append("indicators.macd")

        structure = trade_payload.get("structure") or {}
        if any(structure.get(key) in [None, ""] for key in ["trend", "bos", "choch"]):
            missing.append("structure")

        zones = trade_payload.get("zones") or {}
        if zones.get("support") is None:
            missing.append("zones.support")
        if zones.get("resistance") is None:
            missing.append("zones.resistance")

        risk = trade_payload.get("risk") or {}
        if any(risk.get(key) in [None, ""] for key in ["sl", "tp", "rr"]):
            missing.append("risk")

        return missing

    def _enforce_trade_contract(self, signal, ai_explanation, zones):
        trade_payload = self._build_trade_payload(signal, ai_explanation, zones)
        missing_fields = self._find_missing_trade_fields(trade_payload)
        if not missing_fields:
            return signal, ai_explanation, trade_payload

        signal.signal = "NO_TRADE"
        signal.stop_loss = 0.0
        signal.tp1 = 0.0
        signal.tp2 = 0.0
        signal.rr_ratio = 0.0
        signal.reasons = ["ANALYSIS BLOCKED", "Missing required trade fields"]
        signal.warnings = [f"Missing fields: {', '.join(missing_fields)}"] + list(signal.warnings)

        ai_explanation = {
            **ai_explanation,
            "explanation": f"Trade rejected because required fields are missing: {', '.join(missing_fields)}.",
        }
        trade_payload = self._build_trade_payload(signal, ai_explanation, zones)
        return signal, ai_explanation, trade_payload

    def _build_analysis_contract(self, market_frame, indicator_snapshot, structure_state, sync_status, signal):
        return {
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "feed_source": f"{market_frame.metadata.provider}::{market_frame.metadata.provider_symbol} ({market_frame.metadata.cache_status})",
            "candle_timestamp": signal.candle_timestamp,
            "indicators": indicator_snapshot,
            "structure": {
                "trend": structure_state.trend,
                "phase": structure_state.phase,
                "strength": structure_state.strength,
                "bos": structure_state.bos,
                "choch": structure_state.choch,
                "liquidity_sweep": structure_state.liquidity_sweep,
                "breakout": structure_state.breakout,
                "pullback": structure_state.pullback,
            },
            "confidence": signal.confidence,
            "chart_sync": sync_status.match_percentage,
        }

    def analyze(self, symbol, timeframe):
        market_frame = self.market_feed.fetch(symbol, timeframe)
        if market_frame is None:
            return None

        candles, indicator_snapshot = self.indicator_engine.enrich(market_frame.candles)
        structure_state = self.structure_engine.analyze(candles)
        zones = self.zone_engine.analyze(candles, structure_state)
        sync_status = self.signal_engine.risk_engine.evaluate_feed_quality(symbol, timeframe, candles, market_frame.metadata)
        signal = self.signal_engine.generate(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            metadata=market_frame.metadata,
            sync_status=sync_status,
            indicators=indicator_snapshot,
            structure_state=structure_state,
            zones=zones,
        )
        provisional_ai = self.ai_service.explain(signal)
        provisional_trade_payload = self._build_trade_payload(signal, provisional_ai, zones)
        ai_explanation = self.ai_service.explain(
            signal,
            trade_payload=provisional_trade_payload,
            candles=candles,
            sync_status=sync_status,
        )
        if ai_explanation.get("summary"):
            signal.reasons = list(signal.reasons) + [f"Gemini: {ai_explanation['summary']}"]
        if ai_explanation.get("warnings"):
            signal.warnings = list(signal.warnings) + [f"Gemini: {warning}" for warning in ai_explanation["warnings"]]
        if ai_explanation.get("risks"):
            signal.warnings = list(signal.warnings) + [f"Gemini risk: {risk}" for risk in ai_explanation["risks"]]
        signal, ai_explanation, trade_payload = self._enforce_trade_contract(signal, ai_explanation, zones)
        chart_payload = self.renderer.build_chart_payload(symbol, timeframe, candles, zones, structure_state, signal, market_frame.metadata)
        analysis_contract = self._build_analysis_contract(
            market_frame=market_frame,
            indicator_snapshot=indicator_snapshot,
            structure_state=structure_state,
            sync_status=sync_status,
            signal=signal,
        )
        # ── Session analysis ─────────────────────────────────────────
        try:
            session_state = self.session_engine.detect()
            session_signal = self.session_strategy_engine.analyze(
                session=session_state,
                symbol=symbol,
                candles=candles,
                indicators=indicator_snapshot,
                zones=zones,
                structure=structure_state,
            )
        except Exception:
            session_signal = None

        return AnalysisBundle(
            candles=candles,
            metadata=market_frame.metadata,
            sync=sync_status,
            structure=structure_state,
            zones=zones,
            indicators=indicator_snapshot,
            signal=signal,
            ai_explanation=ai_explanation,
            chart_payload=chart_payload,
            analysis_contract=analysis_contract,
            trade_payload=trade_payload,
            news_signals=[],  # populated separately via analyze_news()
            session_signal=session_signal,
        )

    def analyze_news(
        self,
        symbol: str,
        timeframe: str,
        indicator_snapshot: dict | None = None,
    ) -> list[NewsSignal]:
        """
        Fetch ForexFactory events for the currencies in `symbol`,
        run the NewsIntelligenceEngine pipeline for each event/pair,
        persist results, and return the list of NewsSignals.

        Parameters
        ----------
        symbol            : e.g. 'EURUSD'
        timeframe         : e.g. '15'
        indicator_snapshot: dict from indicator_engine.enrich() — used for
                            Step 3 technical validation. If None, the method
                            fetches live market data to compute indicators.
        """
        if not self.forex_factory_feed or not self.news_engine:
            return []

        # Determine the currencies involved in this pair
        # Handle 6-char pairs (EURUSD) and commodity pairs (XAUUSD)
        base = symbol[:3].upper()
        quote = symbol[3:].upper() if len(symbol) >= 6 else ""
        currencies = list({base, quote} - {""})

        # ── Build live indicator dict ─────────────────────────────────
        # If a pre-computed snapshot is passed, use it directly.
        # Otherwise fetch live market data and compute indicators now.
        indicators: dict = {}
        if indicator_snapshot is not None and indicator_snapshot:
            # Use 'is not None' — never skip valid 0.0 float values via 'or'
            price_val = indicator_snapshot.get("price")
            if price_val is None:
                price_val = indicator_snapshot.get("close")
            indicators = {
                "price": price_val,
                "ema50":  indicator_snapshot.get("ema50"),
                "ema200": indicator_snapshot.get("ema200"),
                "rsi14":  indicator_snapshot.get("rsi14"),
                "atr14":  indicator_snapshot.get("atr14"),
            }
        else:
            # Live fallback: fetch market data and compute indicators fresh
            try:
                market_frame = self.market_feed.fetch(symbol, timeframe)
                if market_frame is not None and not market_frame.candles.empty:
                    _, live_snap = self.indicator_engine.enrich(market_frame.candles)
                    last_close = float(market_frame.candles["close"].iloc[-1])
                    indicators = {
                        "price":  last_close,
                        "ema50":  live_snap.get("ema50"),
                        "ema200": live_snap.get("ema200"),
                        "rsi14":  live_snap.get("rsi14"),
                        "atr14":  live_snap.get("atr14"),
                    }
            except Exception:
                indicators = {}

        # Collect events for all currencies in this pair
        all_events = []
        for currency in currencies:
            events = self.forex_factory_feed.fetch_for_currency(currency)
            all_events.extend(events)

        # Deduplicate events by event_name+currency
        seen = set()
        unique_events = []
        for ev in all_events:
            key = (ev.event_name, ev.currency)
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)

        signals: list[NewsSignal] = []
        for event in unique_events:
            if symbol.upper() not in event.affected_pairs:
                continue
            news_signal = self.news_engine.analyze(event, symbol, indicators)
            if self.news_signal_repository and not self.news_signal_repository.is_duplicate(news_signal):
                self.news_signal_repository.append(news_signal)
            signals.append(news_signal)

        return signals


    def log_signal(self, bundle: AnalysisBundle):
        payload = {
            "symbol": bundle.signal.symbol,
            "timeframe": bundle.signal.timeframe,
            "feed_source": bundle.signal.feed_source,
            "candle_timestamp": bundle.signal.candle_timestamp,
            "signal": bundle.signal.signal,
            "confidence": bundle.signal.confidence,
            "entry": bundle.signal.entry,
            "stop_loss": bundle.signal.stop_loss,
            "tp1": bundle.signal.tp1,
            "tp2": bundle.signal.tp2,
            "rr_ratio": bundle.signal.rr_ratio,
            "reasons": bundle.signal.reasons,
            "warnings": bundle.signal.warnings,
            "chart_sync": bundle.signal.chart_sync,
            "trade_payload": bundle.trade_payload,
        }
        # Skip if this exact signal for this candle was already saved
        if self.signal_repository.is_duplicate(payload):
            return
        self.signal_repository.append(payload)

