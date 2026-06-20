from datetime import datetime, timezone

from data.timeframe_builder import TIMEFRAME_TO_MINUTES
from engine.models import SyncStatus


class RiskEngine:
    def evaluate_feed_quality(self, symbol, timeframe, candles, metadata):
        provider = metadata.provider
        if candles is None or len(candles) < 20:
            return SyncStatus(
                provider=provider,
                timeframe=timeframe,
                total_bars=0,
                matched=0,
                mismatch=0,
                latency_ms=round(metadata.latency_seconds * 1000, 2),
                chart_source=f"TradingViewRenderer::{provider}",
                analysis_source=provider,
                match_percentage=0.0,
                missing_candles=999,
                data_age_seconds=9999.0,
                ohlc_diff=0.0,
                checks={"candles": "insufficient"},
                warning="Chart and analysis are not synchronized",
            )

        candles = candles.sort_values("timestamp").reset_index(drop=True)
        timeframe_minutes = TIMEFRAME_TO_MINUTES.get(timeframe, 5)
        expected_delta_seconds = timeframe_minutes * 60
        # Only check the last 20 candles for gaps so we don't accidentally count weekends or overnight closures
        recent_deltas = candles["timestamp"].tail(20).diff().dropna().dt.total_seconds()
        missing_candle_gaps = int((recent_deltas > expected_delta_seconds * 1.5).sum()) if not recent_deltas.empty else 0

        last_ts = candles["timestamp"].iloc[-1]
        if getattr(last_ts, "tzinfo", None) is None:
            last_ts = last_ts.tz_localize("UTC")
        now_utc = datetime.now(timezone.utc)
        data_age_seconds = max(0.0, (now_utc - last_ts.to_pydatetime()).total_seconds())

        total_bars = len(candles)
        mismatch = missing_candle_gaps
        matched = max(0, total_bars - mismatch)
        match_percentage = round((matched / total_bars) * 100, 2) if total_bars else 0.0
        latency_ms = round(metadata.latency_seconds * 1000, 2)

        checks = {
            "symbol_mapping": f"{symbol}->{metadata.provider_symbol}",
            "timezone": "utc_normalized",
            "ohlc_values": "single_source",
            "candle_close_time": "single_source",
            "missing_candles": str(missing_candle_gaps),
            "data_latency": f"{latency_ms}ms",
            "broker_differences": "none_in_single_source_pipeline",
        }

        warning = ""
        if match_percentage < 99 or missing_candle_gaps > 2 or latency_ms > 3000:
            warning = "Chart and analysis are not synchronized"

        return SyncStatus(
            provider=provider,
            timeframe=timeframe,
            total_bars=total_bars,
            matched=matched,
            mismatch=mismatch,
            latency_ms=latency_ms,
            chart_source=f"TradingViewRenderer::{provider}",
            analysis_source=provider,
            match_percentage=match_percentage,
            missing_candles=missing_candle_gaps,
            data_age_seconds=round(data_age_seconds, 2),
            ohlc_diff=0.0,
            checks=checks,
            warning=warning,
        )

    def should_reject_signal(self, sync_status: SyncStatus):
        reasons = []
        if sync_status.match_percentage < 99:
            reasons.append(f"Feed mismatch: sync {sync_status.match_percentage}% is below 99%")
        if sync_status.missing_candles > 2:
            reasons.append(f"Feed mismatch: missing bars {sync_status.missing_candles} exceed 2")
        if sync_status.latency_ms > 3000:
            reasons.append(f"Feed mismatch: latency {sync_status.latency_ms}ms exceeds 3000ms")
        return reasons
