from core.risk import MIN_RISK_REWARD, build_trade_plan, fibonacci_levels
from engine.models import SignalDecision
from config import MIN_CONFIRMATION_CONFIDENCE


class SignalEngineV2:
    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def _classify(self, confidence):
        if confidence >= 80:
            return "STRONG_BUY"
        if confidence >= MIN_CONFIRMATION_CONFIDENCE:
            return "BUY"
        if confidence >= 35:
            return "NEUTRAL"
        return "NO_TRADE"

    def generate(self, symbol, timeframe, candles, metadata, sync_status, indicators, structure_state, zones):
        last = candles.iloc[-1]
        price = float(last["close"])
        fib = fibonacci_levels(candles, structure_state.trend, None) or {}
        atr_value = float(last["atr14"])
        zone_supports = [zone for zone in zones if zone.type == "support"]
        zone_resistances = [zone for zone in zones if zone.type == "resistance"]

        confidence_breakdown = {}
        reasons = []
        warnings = []
        bullish = 0.0
        bearish = 0.0

        if price > indicators["ema50"] and price > indicators["ema200"]:
            bullish += 18
            confidence_breakdown["ema_trend"] = 18
            reasons.append("Price is above EMA50 and EMA200")
        elif price < indicators["ema50"] and price < indicators["ema200"]:
            bearish += 18
            confidence_breakdown["ema_trend"] = 18
            reasons.append("Price is below EMA50 and EMA200")
        else:
            warnings.append("EMA trend is mixed")

        structure_weight = round(structure_state.strength * 20, 2)
        confidence_breakdown["structure"] = structure_weight
        if structure_state.trend == "bullish":
            bullish += structure_weight
            reasons.append("Market structure is bullish")
        elif structure_state.trend == "bearish":
            bearish += structure_weight
            reasons.append("Market structure is bearish")
        else:
            warnings.append("Market structure is ranging")

        if structure_state.bos == "bullish_bos":
            bullish += 12
            confidence_breakdown["bos"] = 12
            reasons.append("Bullish BOS detected")
        elif structure_state.bos == "bearish_bos":
            bearish += 12
            confidence_breakdown["bos"] = 12
            reasons.append("Bearish BOS detected")

        if structure_state.liquidity_sweep == "liquidity_grab_buy":
            bullish += 10
            confidence_breakdown["liquidity"] = 10
            reasons.append("Sell-side liquidity sweep detected")
        elif structure_state.liquidity_sweep == "liquidity_grab_sell":
            bearish += 10
            confidence_breakdown["liquidity"] = 10
            reasons.append("Buy-side liquidity sweep detected")

        if indicators["macd"] > indicators["macd_signal"]:
            bullish += 8
            confidence_breakdown["macd"] = 8
            reasons.append("MACD supports bullish momentum")
        elif indicators["macd"] < indicators["macd_signal"]:
            bearish += 8
            confidence_breakdown["macd"] = 8
            reasons.append("MACD supports bearish momentum")

        if indicators["rsi14"] < 30:
            bullish += 5
            confidence_breakdown["rsi"] = 5
            reasons.append("RSI indicates oversold recovery potential")
        elif indicators["rsi14"] > 70:
            bearish += 5
            confidence_breakdown["rsi"] = 5
            reasons.append("RSI indicates overbought exhaustion risk")

        strongest_support = max(zone_supports, key=lambda z: z.strength) if zone_supports else None
        strongest_resistance = max(zone_resistances, key=lambda z: z.strength) if zone_resistances else None
        if strongest_support and abs(price - strongest_support.top) <= atr_value * 2.0:
            bullish += 8
            confidence_breakdown["support_zone"] = 8
            reasons.append("Price is trading near a validated support zone")
        if strongest_resistance and abs(price - strongest_resistance.bottom) <= atr_value * 2.0:
            bearish += 8
            confidence_breakdown["resistance_zone"] = 8
            reasons.append("Price is trading near a validated resistance zone")

        active_imbalances = structure_state.imbalances or []
        nearest_bullish_gap = next(
            (gap for gap in reversed(active_imbalances) if gap["type"] == "bullish" and abs(price - gap["avg"]) <= atr_value * 1.8),
            None,
        )
        nearest_bearish_gap = next(
            (gap for gap in reversed(active_imbalances) if gap["type"] == "bearish" and abs(price - gap["avg"]) <= atr_value * 1.8),
            None,
        )
        if nearest_bullish_gap:
            bullish += 7
            confidence_breakdown["bullish_fvg"] = 7
            reasons.append("Price is respecting a bullish FVG and its AVG midpoint")
        if nearest_bearish_gap:
            bearish += 7
            confidence_breakdown["bearish_fvg"] = 7
            reasons.append("Price is respecting a bearish FVG and its AVG midpoint")

        if fib:
            ote_low = fib.get("ote_low")
            ote_high = fib.get("ote_high")
            if ote_low is not None and ote_high is not None and ote_low <= price <= ote_high:
                if structure_state.trend == "bullish":
                    bullish += 10
                    confidence_breakdown["fibonacci"] = 10
                    reasons.append("Price is inside bullish OTE zone")
                elif structure_state.trend == "bearish":
                    bearish += 10
                    confidence_breakdown["fibonacci"] = 10
                    reasons.append("Price is inside bearish OTE zone")

        weighted_confidence = round(max(bullish, bearish), 2)
        direction = "BUY" if bullish > bearish else "SELL" if bearish > bullish else "NEUTRAL"
        label = self._classify(weighted_confidence)
        if label in ["NEUTRAL", "NO_TRADE"]:
            signal = label
        else:
            if direction == "BUY":
                signal = "STRONG_BUY" if label == "STRONG_BUY" else "BUY"
            elif direction == "SELL":
                signal = "STRONG_SELL" if label == "STRONG_BUY" else "SELL"
            else:
                signal = "NEUTRAL"

        stop_loss, tp1, rr = build_trade_plan("BUY" if bullish > bearish else "SELL", price, atr_value, [
            {"type": zone.type, "low": zone.bottom, "high": zone.top, "mid": (zone.top + zone.bottom) / 2}
            for zone in zones
        ], fib, lambda zone_list, zone_type, check_price, below=True: None)

        # TP2 = extend from TP1 by the same distance as Entry→TP1
        if bullish > bearish:
            # BUY: TP2 is above TP1 by (tp1 - price)
            tp2 = round(tp1 + (tp1 - price), 5) if tp1 > price else round(tp1, 5)
        else:
            # SELL: TP2 is below TP1 by (price - tp1)
            tp2 = round(tp1 - (price - tp1), 5) if tp1 < price else round(tp1, 5)

        rejection_reasons = self.risk_engine.should_reject_signal(sync_status)
        if rr < MIN_RISK_REWARD:
            rejection_reasons.append("Risk reward is below minimum threshold")
            signal = "NO_TRADE"
            reasons = ["ANALYSIS BLOCKED", "Risk reward below threshold"]
        if rejection_reasons:
            warnings.extend(rejection_reasons)

        invalidation = (
            f"Reject trade if price closes above {stop_loss}" if signal in ["SELL", "STRONG_SELL"]
            else f"Reject trade if price closes below {stop_loss}" if signal in ["BUY", "STRONG_BUY"]
            else "No trade until feed quality and structure improve"
        )

        # Always store levels when stop_loss and tp1 are valid (even for NO_TRADE — for analysis display)
        show_levels = stop_loss not in [None, 0, 0.0] and tp1 not in [None, 0, 0.0]

        return SignalDecision(
            symbol=symbol,
            timeframe=timeframe,
            feed_source=metadata.provider,
            candle_timestamp=str(candles["timestamp"].iloc[-1]),
            signal=signal,
            confidence=weighted_confidence,
            entry=round(price, 5),
            stop_loss=round(stop_loss, 5) if show_levels else 0.0,
            tp1=round(tp1, 5) if show_levels else 0.0,
            tp2=round(tp2, 5) if show_levels else 0.0,
            rr_ratio=round(rr, 2) if show_levels else 0.0,
            reasons=reasons[:8],
            invalidation=invalidation,
            indicators=indicators,
            structure={
                "trend": structure_state.trend,
                "phase": structure_state.phase,
                "strength": structure_state.strength,
                "bos": structure_state.bos,
                "choch": structure_state.choch,
                "liquidity_sweep": structure_state.liquidity_sweep,
                "breakout": structure_state.breakout,
                "pullback": structure_state.pullback,
                "imbalances": structure_state.imbalances,
            },
            chart_sync=sync_status.match_percentage,
            warnings=warnings[:8],
            confidence_breakdown=confidence_breakdown,
        )
