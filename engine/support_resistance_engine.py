from core.market_structure import detect_zones
from engine.models import Zone


class SupportResistanceEngine:
    def analyze(self, candles, structure_state):
        raw_zones = detect_zones(candles)
        zones = []
        avg_volume = float(candles["volume"].tail(20).mean()) if "volume" in candles else 0.0

        for zone in raw_zones:
            top = round(float(zone["high"]), 5)
            bottom = round(float(zone["low"]), 5)
            touches = int(zone.get("touches", 1))
            width = max(top - bottom, 0.00001)
            volume_validated = avg_volume >= 0
            htf_aligned = structure_state.trend == "bullish" if zone["type"] == "support" else structure_state.trend == "bearish"
            strength = min(1.0, (touches * 0.2) + (0.2 if htf_aligned else 0) + (0.1 if volume_validated else 0) + (0.1 / width))
            zones.append(
                Zone(
                    type=zone["type"],
                    top=top,
                    bottom=bottom,
                    strength=round(min(strength, 1.0), 2),
                    touches=touches,
                    htf_aligned=htf_aligned,
                    volume_validated=volume_validated,
                )
            )
        return zones
