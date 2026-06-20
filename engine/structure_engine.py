from core.market_structure import detect_bos, detect_liquidity, find_swings
from engine.models import StructureState


class StructureEngine:
    def _format_swing_point(self, label, swing, candles):
        candle = candles.iloc[int(swing["index"])]
        return {
            "label": label,
            "index": int(swing["index"]),
            "price": round(float(swing["price"]), 5),
            "timestamp": str(candle["timestamp"]),
        }

    def _detect_imbalances(self, candles):
        imbalances = []
        if len(candles) < 3:
            return imbalances

        atr_reference = float(candles["atr14"].tail(20).mean()) if "atr14" in candles else 0.0
        minimum_gap = max(atr_reference * 0.15, 0.0001)

        for index in range(2, len(candles)):
            left = candles.iloc[index - 2]
            middle = candles.iloc[index - 1]
            right = candles.iloc[index]

            if float(left["high"]) < float(right["low"]):
                gap_low = float(left["high"])
                gap_high = float(right["low"])
                gap_type = "bullish"
            elif float(left["low"]) > float(right["high"]):
                gap_low = float(right["high"])
                gap_high = float(left["low"])
                gap_type = "bearish"
            else:
                continue

            gap_size = gap_high - gap_low
            if gap_size < minimum_gap:
                continue

            imbalances.append(
                {
                    "type": gap_type,
                    "start_index": index - 2,
                    "end_index": index,
                    "start_timestamp": str(left["timestamp"]),
                    "end_timestamp": str(right["timestamp"]),
                    "low": round(gap_low, 5),
                    "high": round(gap_high, 5),
                    "avg": round((gap_low + gap_high) / 2, 5),
                    "size": round(gap_size, 5),
                    "midpoint_source": "avg",
                    "displacement": round(abs(float(middle["close"]) - float(middle["open"])), 5),
                }
            )

        return imbalances[-6:]

    def analyze(self, candles):
        swings = find_swings(candles)
        swing_highs = [s for s in swings if s["type"] == "high"]
        swing_lows = [s for s in swings if s["type"] == "low"]
        hh, hl, lh, ll = [], [], [], []
        swing_points = {"hh": [], "hl": [], "lh": [], "ll": []}

        for first, second in zip(swing_highs[:-1], swing_highs[1:]):
            if second["price"] > first["price"]:
                hh.append(second["price"])
                swing_points["hh"].append(self._format_swing_point("HH", second, candles))
            else:
                lh.append(second["price"])
                swing_points["lh"].append(self._format_swing_point("LH", second, candles))

        for first, second in zip(swing_lows[:-1], swing_lows[1:]):
            if second["price"] > first["price"]:
                hl.append(second["price"])
                swing_points["hl"].append(self._format_swing_point("HL", second, candles))
            else:
                ll.append(second["price"])
                swing_points["ll"].append(self._format_swing_point("LL", second, candles))

        if hh and hl and len(hh) >= len(lh):
            trend = "bullish"
        elif lh and ll and len(ll) >= len(hl):
            trend = "bearish"
        else:
            trend = "range"

        bos = detect_bos(candles)
        liquidity = detect_liquidity(candles)
        choch = None
        if trend == "bullish" and ll:
            choch = "bearish_choch"
        elif trend == "bearish" and hh:
            choch = "bullish_choch"

        last = candles.iloc[-1]
        breakout = bool(bos)
        pullback = abs(float(last["close"]) - float(last["ema21"])) <= float(last["atr14"]) * 1.5
        phase = "breakout" if breakout else "pullback" if pullback else "continuation" if trend != "range" else "consolidation"

        aligned_points = len(hh) + len(hl) + len(lh) + len(ll)
        strength = round(min(1.0, aligned_points / 6), 2)
        imbalances = self._detect_imbalances(candles)

        return StructureState(
            trend=trend,
            phase=phase,
            strength=strength,
            hh=hh[-3:],
            hl=hl[-3:],
            lh=lh[-3:],
            ll=ll[-3:],
            swing_points={key: value[-4:] for key, value in swing_points.items()},
            imbalances=imbalances,
            bos=bos,
            choch=choch,
            liquidity_sweep=liquidity,
            breakout=breakout,
            pullback=pullback,
        )
