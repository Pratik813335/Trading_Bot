class TradingViewRenderer:
    def build_chart_payload(self, symbol, timeframe, candles, zones, structure_state, signal, metadata):
        from core.risk import fibonacci_levels
        raw_swings = []
        for key, points in (structure_state.swing_points or {}).items():
            for p in points:
                raw_swings.append({
                    "type": "high" if key in ["hh", "lh"] else "low",
                    "price": float(p["price"]),
                    "index": int(p["index"])
                })
        fib = fibonacci_levels(candles, structure_state.trend, raw_swings)

        records = []
        for _, row in candles.tail(300).iterrows():
            records.append(
                {
                    "timestamp": str(row["timestamp"]),
                    "open": round(float(row["open"]), 5),
                    "high": round(float(row["high"]), 5),
                    "low": round(float(row["low"]), 5),
                    "close": round(float(row["close"]), 5),
                    "volume": round(float(row.get("volume", 0)), 2),
                    "source": row.get("source", metadata.provider),
                }
            )

        overlays = {
            "support_resistance": [
                {
                    "type": zone.type,
                    "top": zone.top,
                    "bottom": zone.bottom,
                    "strength": zone.strength,
                }
                for zone in zones
            ],
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "tp1": signal.tp1,
            "tp2": signal.tp2,
            "tp3": getattr(signal, "tp3", 0.0),
            "structure": {
                "trend": structure_state.trend,
                "phase": structure_state.phase,
                "strength": structure_state.strength,
                "bos": structure_state.bos,
                "choch": structure_state.choch,
                "liquidity_sweep": structure_state.liquidity_sweep,
                "hh": structure_state.hh,
                "hl": structure_state.hl,
                "lh": structure_state.lh,
                "ll": structure_state.ll,
                "swing_points": structure_state.swing_points,
            },
            "imbalances": structure_state.imbalances,
            "fibonacci": fib,
        }

        return {
            "chart_source": "single_source_renderer",
            "provider": metadata.provider,
            "provider_symbol": metadata.provider_symbol,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": records,
            "overlays": overlays,
        }
