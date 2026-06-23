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

    def analyze(self, symbol, timeframe, forced_strategy=None):
        market_frame = self.market_feed.fetch(symbol, timeframe)
        if market_frame is None:
            return None

        candles, indicator_snapshot = self.indicator_engine.enrich(market_frame.candles)
        structure_state = self.structure_engine.analyze(candles)
        from core.market_structure import detect_order_blocks
        structure_state.order_blocks = detect_order_blocks(candles, n_candles=50)
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

        # --- Active Trade Invalidation Check ---
        active = self.signal_repository.get_active_position(symbol)
        invalidation_reason = None
        
        if active is not None:
            active_dir = self._signal_direction(active.get("signal", ""))
            active_sl = float(active.get("stop_loss") or 0.0)
            active_tp1 = float(active.get("tp1") or 0.0)
            
            last_candle = candles.iloc[-1]
            current_close = float(last_candle["close"])
            current_high = float(last_candle["high"])
            current_low = float(last_candle["low"])
            current_open = float(last_candle["open"])
            atr = float(last_candle["atr14"]) if "atr14" in last_candle else 0.0001
            
            # 1. Confirmation Failure
            if signal.signal in ["NEUTRAL", "HOLD", "NO_TRADE"]:
                invalidation_reason = f"Confirmation Failure: Primary signal is now {signal.signal}"
            
            # 2. Opposite Market Structure
            if invalidation_reason is None:
                if active_dir == "BUY":
                    if structure_state.trend == "bearish" or structure_state.bos == "bearish_bos":
                        invalidation_reason = "Opposite Market Structure: Bearish trend or BOS detected"
                elif active_dir == "SELL":
                    if structure_state.trend == "bullish" or structure_state.bos == "bullish_bos":
                        invalidation_reason = "Opposite Market Structure: Bullish trend or BOS detected"

            # 3. Indicator Reversal
            if invalidation_reason is None:
                macd = indicator_snapshot.get("macd")
                macd_sig = indicator_snapshot.get("macd_signal")
                ema50 = indicator_snapshot.get("ema50")
                
                if active_dir == "BUY":
                    if (macd is not None and macd_sig is not None and macd < macd_sig) or \
                       (ema50 is not None and current_close < ema50):
                        invalidation_reason = "Indicator Reversal: Momentum shifted bearish (MACD cross or below EMA50)"
                elif active_dir == "SELL":
                    if (macd is not None and macd_sig is not None and macd > macd_sig) or \
                       (ema50 is not None and current_close > ema50):
                        invalidation_reason = "Indicator Reversal: Momentum shifted bullish (MACD cross or above EMA50)"

            # 4. Fake Breakout / Trap Detection
            if invalidation_reason is None:
                if active_dir == "BUY" and structure_state.liquidity_sweep == "liquidity_grab_sell":
                    invalidation_reason = "Fake Breakout: Buy-side liquidity sweep & rejection detected"
                elif active_dir == "SELL" and structure_state.liquidity_sweep == "liquidity_grab_buy":
                    invalidation_reason = "Fake Breakout: Sell-side liquidity sweep & reclaim detected"

            # 5. Strong Opposite Momentum
            if invalidation_reason is None:
                candle_body = abs(current_close - current_open)
                if atr > 0.0 and candle_body > atr * 2.5:
                    if active_dir == "BUY" and current_close < current_open:
                        invalidation_reason = "Strong Opposite Momentum: Large bearish candle body against trade"
                    elif active_dir == "SELL" and current_close > current_open:
                        invalidation_reason = "Strong Opposite Momentum: Large bullish candle body against trade"

            # 6. Time-Based Invalidation (sideways/choppy after entry)
            if invalidation_reason is None:
                logged_at_str = active.get("logged_at", "")
                if logged_at_str:
                    try:
                        from datetime import datetime, timezone
                        from data.timeframe_builder import TIMEFRAME_TO_MINUTES
                        logged_dt = datetime.fromisoformat(logged_at_str)
                        time_minutes = TIMEFRAME_TO_MINUTES.get(timeframe, 5)
                        elapsed_seconds = (datetime.now(timezone.utc) - logged_dt).total_seconds()
                        if elapsed_seconds > (time_minutes * 60 * 15):
                            entry_price = float(active.get("entry") or current_close)
                            if abs(current_close - entry_price) <= atr * 0.8:
                                invalidation_reason = "Time-Based Invalidation: Market became sideways/choppy post-entry"
                    except Exception:
                        pass

            # 7. Risk Protection
            if invalidation_reason is None and active_sl > 0.0:
                if active_dir == "BUY" and current_close - active_sl <= atr * 0.2:
                    invalidation_reason = "Risk Protection: Price is too close to Stop Loss without reaction"
                elif active_dir == "SELL" and active_sl - current_close <= atr * 0.2:
                    invalidation_reason = "Risk Protection: Price is too close to Stop Loss without reaction"

        if invalidation_reason is not None:
            opposite_signal_confirmed = False
            if active_dir == "BUY" and signal.signal in ["SELL", "STRONG_SELL"]:
                opposite_signal_confirmed = True
            elif active_dir == "SELL" and signal.signal in ["BUY", "STRONG_BUY"]:
                opposite_signal_confirmed = True

            signal.signal = "TRADE_REMOVED"
            signal.stop_loss = 0.0
            signal.tp1 = 0.0
            signal.tp2 = 0.0
            signal.rr_ratio = 0.0
            signal.reasons = [invalidation_reason] + [r for r in signal.reasons if r != "ANALYSIS BLOCKED"]
            if opposite_signal_confirmed:
                signal.reasons.append("Suggest Reverse Trade: High-probability opposite setup confirmed")
            signal.warnings = ["❌ TRADE REMOVED: " + invalidation_reason] + list(signal.warnings)
            
            # Close the position in the repository
            self.signal_repository.close_position(active["logged_at"], "TRADE_REMOVED")

        # --- Multi-Timeframe Analysis ---
        target_timeframes = ["1", "5", "15", "60", "240", "D"]
        mtf_results = {}
        
        for tf in target_timeframes:
            try:
                if tf == timeframe:
                    tf_market_frame = market_frame
                else:
                    tf_market_frame = self.market_feed.fetch(symbol, tf)
                
                if tf_market_frame is not None and not tf_market_frame.candles.empty:
                    tf_candles, tf_indicators = self.indicator_engine.enrich(tf_market_frame.candles)
                    tf_structure = self.structure_engine.analyze(tf_candles)
                    from core.market_structure import detect_order_blocks
                    tf_structure.order_blocks = detect_order_blocks(tf_candles, n_candles=50)
                    tf_zones = self.zone_engine.analyze(tf_candles, tf_structure)
                    tf_sync = self.signal_engine.risk_engine.evaluate_feed_quality(
                        symbol, tf, tf_candles, tf_market_frame.metadata
                    )
                    tf_signal = self.signal_engine.generate(
                        symbol=symbol,
                        timeframe=tf,
                        candles=tf_candles,
                        metadata=tf_market_frame.metadata,
                        sync_status=tf_sync,
                        indicators=tf_indicators,
                        structure_state=tf_structure,
                        zones=tf_zones,
                    )
                    mtf_results[tf] = {
                        "signal": tf_signal,
                        "indicators": tf_indicators,
                        "structure": tf_structure,
                        "zones": tf_zones,
                        "sync": tf_sync,
                        "candles": tf_candles,
                    }
            except Exception as e:
                print(f"Error analyzing timeframe {tf}: {e}")

        # Multi-timeframe rules evaluation (5-TF consensus score weighting)
        primary_dir = None
        if signal.signal in ["BUY", "STRONG_BUY"]:
            primary_dir = "BUY"
        elif signal.signal in ["SELL", "STRONG_SELL"]:
            primary_dir = "SELL"

        if primary_dir is not None:
            TF_WEIGHTS = {'D': 5, '240': 4, '60': 3, '15': 2, '5': 1, '1': 1}
            align_score = 0
            conflict_score = 0
            
            for tf, res in mtf_results.items():
                w = TF_WEIGHTS.get(tf, 1)
                trend = res.get("structure").trend if res.get("structure") else "ranging"
                sig = res.get("signal").signal if res.get("signal") else "NEUTRAL"
                
                is_aligned = False
                is_conflicting = False
                
                if primary_dir == "BUY":
                    if trend == "bullish" or sig in ["BUY", "STRONG_BUY"]:
                        is_aligned = True
                    elif trend == "bearish" or sig in ["SELL", "STRONG_SELL"]:
                        is_conflicting = True
                elif primary_dir == "SELL":
                    if trend == "bearish" or sig in ["SELL", "STRONG_SELL"]:
                        is_aligned = True
                    elif trend == "bullish" or sig in ["BUY", "STRONG_BUY"]:
                        is_conflicting = True
                        
                if is_aligned:
                    align_score += w
                elif is_conflicting:
                    conflict_score += w

            # Apply consensus rules
            if conflict_score >= 8:
                signal.signal = "NO_TRADE"
                signal.stop_loss = 0.0
                signal.tp1 = 0.0
                signal.tp2 = 0.0
                signal.rr_ratio = 0.0
                signal.reasons = ["HTF Bias Conflict"] + [r for r in signal.reasons if r != "ANALYSIS BLOCKED"]
                signal.warnings = [f"No trade: Multi-timeframe conflict score {conflict_score} >= 8 conflicts with entry direction"] + list(signal.warnings)
            else:
                if align_score >= 10:
                    signal.confidence = min(95.0, signal.confidence + 15.0)
                    signal.reasons = ["Strong HTF alignment (+15)"] + list(signal.reasons)
                elif align_score >= 7:
                    signal.confidence = min(95.0, signal.confidence + 8.0)
                    signal.reasons = ["HTF alignment (+8)"] + list(signal.reasons)
                    
                if 5 <= conflict_score < 7:
                    signal.confidence = max(0.0, signal.confidence - 20.0)
                    signal.warnings = ["MTF conflict penalty: -20 confidence (conflict score 5-6)"] + list(signal.warnings)
                elif 3 <= conflict_score < 5:
                    signal.confidence = max(0.0, signal.confidence - 10.0)
                    signal.warnings = ["MTF conflict penalty: -10 confidence (conflict score 3-4)"] + list(signal.warnings)

        # Build multi-timeframe analysis summaries
        mtf_analysis = {}
        for tf in target_timeframes:
            if tf in mtf_results:
                res = mtf_results[tf]
                tf_sig = res["signal"]
                tf_ind = res["indicators"]
                tf_struct = res["structure"]
                tf_candles = res["candles"]
                
                price = float(tf_candles["close"].iloc[-1])
                
                ema50 = tf_ind.get("ema50")
                ema200 = tf_ind.get("ema200")
                if ema50 is not None and ema200 is not None:
                    if price > ema50 and price > ema200:
                        ema_status = "Above EMAs"
                    elif price < ema50 and price < ema200:
                        ema_status = "Below EMAs"
                    else:
                        ema_status = "Between EMAs"
                else:
                    ema_status = "N/A"

                rsi = tf_ind.get("rsi14")
                if rsi is not None:
                    if rsi > 70:
                        rsi_status = f"Overbought ({rsi:.1f})"
                    elif rsi < 30:
                        rsi_status = f"Oversold ({rsi:.1f})"
                    else:
                        rsi_status = f"Neutral ({rsi:.1f})"
                else:
                    rsi_status = "N/A"

                macd = tf_ind.get("macd")
                macd_sig = tf_ind.get("macd_signal")
                if macd is not None and macd_sig is not None:
                    macd_status = "Bullish Cross" if macd > macd_sig else "Bearish Cross"
                else:
                    macd_status = "N/A"

                mtf_analysis[tf] = {
                    "timeframe": tf,
                    "signal": tf_sig.signal,
                    "confidence": tf_sig.confidence,
                    "trend": tf_struct.trend,
                    "phase": tf_struct.phase,
                    "ema_status": ema_status,
                    "rsi_status": rsi_status,
                    "macd_status": macd_status,
                }

        # Fetch news signals for G8 validation and UI rendering
        news_signals = []
        if self.forex_factory_feed and self.news_engine:
            try:
                news_signals = self.analyze_news(symbol, timeframe, indicator_snapshot)
            except Exception:
                pass

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

        # ── 10-Gate Quality Validator Check ──
        self.validate_10_gates(
            signal=signal,
            sync_status=sync_status,
            structure_state=structure_state,
            indicators=indicator_snapshot,
            zones=zones,
            news_signals=news_signals,
            ai_explanation=ai_explanation,
            forced_strategy=forced_strategy
        )

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
            forced = forced_strategy or getattr(self, "forced_strategy", None)
            session_signal = self.session_strategy_engine.analyze(
                session=session_state,
                symbol=symbol,
                candles=candles,
                indicators=indicator_snapshot,
                zones=zones,
                structure=structure_state,
                forced_strategy=forced,
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
            news_signals=news_signals,
            session_signal=session_signal,
            mtf_analysis=mtf_analysis,
        )

    def validate_10_gates(self, signal, sync_status, structure_state, indicators, zones, news_signals, ai_explanation, forced_strategy=None):
        gate_failures = []
        gate_warnings = []
        
        # G1: Data Quality
        from data.timeframe_builder import TIMEFRAME_TO_MINUTES
        tf_minutes = TIMEFRAME_TO_MINUTES.get(signal.timeframe, 5)
        if tf_minutes == 'D':
            tf_minutes = 1440
        else:
            try:
                tf_minutes = int(tf_minutes)
            except Exception:
                tf_minutes = 5
        data_age_minutes = (sync_status.data_age_seconds or 0.0) / 60.0
        if data_age_minutes > 3 * tf_minutes:
            gate_failures.append(f"G1 Fail: Stale Data ({data_age_minutes:.1f}m old, max {3 * tf_minutes}m)")

        # G2: Market Structure (Skip structure check if we are explicitly running Range Trader strategy)
        if signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            if forced_strategy != "Range Trader":
                if structure_state.trend in ["range", "ranging", "mixed"]:
                    gate_failures.append("G2 Fail: Ranging Market structure trend")

        # G3: HTF Bias
        if signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            if "HTF Bias Conflict" in signal.reasons:
                gate_failures.append("G3 Fail: HTF Bias Conflict")

        # G4: Min Confluences
        if signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            active_conf = sum(1 for v in signal.confidence_breakdown.values() if v > 0)
            from config import MIN_CONFIRMATIONS
            if active_conf < MIN_CONFIRMATIONS:
                gate_failures.append(f"G4 Fail: Insufficient Confluence ({active_conf} < {MIN_CONFIRMATIONS})")

        # G5: Score Gap
        if signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            if "Insufficient confluence" in "".join(signal.warnings) and "gap" in "".join(signal.warnings):
                gate_failures.append("G5 Fail: Score gap below threshold")

        # G6: ADX Trend Strength
        adx = indicators.get("adx14", 0.0)
        if signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            if adx < 20:
                gate_warnings.append(f"G6 Warning: Weak Trend Strength (ADX: {adx:.1f} < 20)")

        # G7: Risk-Reward
        if signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            from core.risk import MIN_RISK_REWARD
            if signal.rr_ratio < MIN_RISK_REWARD:
                gate_failures.append(f"G7 Fail: Risk:Reward too low ({signal.rr_ratio:.2f} < {MIN_RISK_REWARD})")

        # G8: News Filter
        for ns in news_signals:
            if ns.impact == "HIGH" and not ns.entry_allowed:
                gate_failures.append(f"G8 Fail: High-impact news event '{ns.event_name}' in block window")

        # G9: AI Validation
        ai_score = ai_explanation.get("quality_score")
        if ai_score is not None:
            try:
                if float(ai_score) < 60:
                    signal.confidence = max(0.0, signal.confidence - 15.0)
                    gate_warnings.append(f"G9 Warning: AI score below threshold ({ai_score} < 60), confidence -15")
            except Exception:
                pass

        # G10: Pattern Check
        pattern = signal.structure.get("candle_pattern") or signal.structure.get("pattern")
        if signal.signal in ["BUY", "STRONG_BUY"] and pattern in ["bearish_engulfing", "shooting_star", "three_black_crows"]:
            signal.confidence = max(0.0, signal.confidence - 5.0)
            gate_warnings.append(f"G10 Warning: Conflicting pattern '{pattern}' on BUY, confidence -5")
        elif signal.signal in ["SELL", "STRONG_SELL"] and pattern in ["bullish_engulfing", "hammer", "three_white_soldiers"]:
            signal.confidence = max(0.0, signal.confidence - 5.0)
            gate_warnings.append(f"G10 Warning: Conflicting pattern '{pattern}' on SELL, confidence -5")
        elif pattern == "doji" and signal.signal in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]:
            signal.confidence = max(0.0, signal.confidence - 5.0)
            gate_warnings.append("G10 Warning: Doji candle at entry, confidence -5")

        # Apply gate failure actions
        if gate_failures:
            signal.signal = "NO_TRADE"
            signal.stop_loss = 0.0
            signal.tp1 = 0.0
            signal.tp2 = 0.0
            signal.rr_ratio = 0.0
            for fail in gate_failures:
                if fail not in signal.reasons:
                    signal.reasons.append(fail)
                if fail not in signal.warnings:
                    signal.warnings.append(fail)
                    
        for warn in gate_warnings:
            if warn not in signal.warnings:
                signal.warnings.append(warn)

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


    # Signals that represent an active directional trade
    _TRADE_SIGNALS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}

    @staticmethod
    def _signal_direction(signal_str: str) -> str | None:
        s = str(signal_str).upper()
        if s in ("BUY", "STRONG_BUY"):
            return "BUY"
        if s in ("SELL", "STRONG_SELL"):
            return "SELL"
        return None

    def log_signal(self, bundle: AnalysisBundle):
        """Manage the full position lifecycle for trade history.

        Rules
        -----
        1. Only BUY / STRONG_BUY / SELL / STRONG_SELL signals are ever logged.
        2. One active position per symbol at a time — no duplicates.
        3. On every refresh, check whether the current price has hit the SL or
           TP of the open position and close it with the correct outcome.
        4. If the signal direction flips *before* SL/TP is hit, close the old
           position as CLOSED_BY_SIGNAL_CHANGE and open the new one.
        5. If the direction stays the same, do nothing (the existing entry
           stays open — no duplicate is created).
        """
        new_signal = bundle.signal.signal
        symbol     = bundle.signal.symbol

        # Rule 1: only process real directional signals
        if new_signal not in self._TRADE_SIGNALS:
            return

        new_dir = self._signal_direction(new_signal)

        # Current market price from the latest closed candle
        try:
            current_price = float(bundle.candles["close"].iloc[-1])
        except Exception:
            current_price = None

        # ── Step A: Check SL / TP on the existing open position ──────────
        active = self.signal_repository.get_active_position(symbol)

        if active is not None:
            active_sl  = float(active.get("stop_loss") or 0)
            active_tp1 = float(active.get("tp1") or 0)
            active_dir = self._signal_direction(active.get("signal", ""))
            logged_at  = active.get("logged_at", "")

            if current_price is not None and active_sl and active_tp1:
                if active_dir == "BUY":
                    sl_hit = current_price <= active_sl
                    tp_hit = current_price >= active_tp1
                else:  # SELL
                    sl_hit = current_price >= active_sl
                    tp_hit = current_price <= active_tp1

                if sl_hit:
                    self.signal_repository.close_position(logged_at, "SL_HIT")
                    active = None  # position is now closed
                elif tp_hit:
                    self.signal_repository.close_position(logged_at, "TP_HIT")
                    active = None  # position is now closed

        # ── Step B: Evaluate the new signal against the (still open) position ──
        if active is not None:
            active_dir = self._signal_direction(active.get("signal", ""))
            logged_at  = active.get("logged_at", "")

            if active_dir == new_dir:
                # Rule 5: same direction — position still live, do nothing
                return

            # Rule 4: direction changed before SL/TP → close old, open new
            self.signal_repository.close_position(logged_at, "CLOSED_BY_SIGNAL_CHANGE")

        # ── Step C: Open the new position ────────────────────────────────
        payload = {
            "symbol":            symbol,
            "timeframe":         bundle.signal.timeframe,
            "feed_source":       bundle.signal.feed_source,
            "candle_timestamp":  bundle.signal.candle_timestamp,
            "signal":            new_signal,
            "confidence":        bundle.signal.confidence,
            "entry":             bundle.signal.entry,
            "stop_loss":         bundle.signal.stop_loss,
            "tp1":               bundle.signal.tp1,
            "tp2":               bundle.signal.tp2,
            "rr_ratio":          bundle.signal.rr_ratio,
            "reasons":           bundle.signal.reasons,
            "warnings":          bundle.signal.warnings,
            "chart_sync":        bundle.signal.chart_sync,
            "trade_payload":     bundle.trade_payload,
        }
        self.signal_repository.append(payload)

