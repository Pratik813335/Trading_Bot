import asyncio
import logging
import threading
import time
import json
from datetime import datetime, timezone
import pandas as pd

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect, WebSocketState

from core.signal_engine import candle_pattern
from engine.models import AnalysisBundle

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LiveAnalysisEngine")

# Helpers for formatting and building payloads (copied to avoid importing app.py)
def format_price(value):
    if value in [None, "", 0, 0.0]:
        return "--"
    try:
        return f"{float(value):,.5f}"
    except (TypeError, ValueError):
        return str(value)

def build_trade_panel_payload(bundle):
    structure = bundle.chart_payload.get("overlays", {}).get("structure", {})
    pattern = candle_pattern(bundle.candles)
    has_mismatch = any("Feed mismatch" in w or "mismatch" in w.lower() for w in bundle.signal.warnings)
    is_trade_removed = bundle.signal.signal == "TRADE_REMOVED"
    actionable = (bundle.signal.signal in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"] 
                  and bundle.signal.stop_loss not in [None, 0, 0.0])
    show_levels = actionable and bundle.signal.entry not in [None, 0, 0.0]
    
    if is_trade_removed:
        status = "TRADE REMOVED"
    else:
        if actionable:
            status = "Approved (Warning)" if has_mismatch else "Approved"
        else:
            status = "Blocked / Feed Mismatch" if has_mismatch else "Blocked / No Trade"
        
    reasons = [r for r in (bundle.signal.reasons or []) if not r.startswith("Gemini:")]
    return {
        "symbol": bundle.signal.symbol,
        "timeframe": bundle.signal.timeframe,
        "signal": bundle.signal.signal,
        "confidence": f"{bundle.signal.confidence:.2f}%" if bundle.signal.confidence is not None else "--",
        "status": status,
        "entry": format_price(bundle.signal.entry) if show_levels else "--",
        "stop_loss": format_price(bundle.signal.stop_loss) if show_levels else "--",
        "tp1": format_price(bundle.signal.tp1) if show_levels else "--",
        "tp2": format_price(bundle.signal.tp2) if show_levels else "--",
        "rr": "--" if not show_levels or bundle.signal.rr_ratio in [0, 0.0] else f"{bundle.signal.rr_ratio:.2f}",
        "trend": structure.get("trend", "n/a"),
        "phase": structure.get("phase", "n/a"),
        "bos": structure.get("bos") or "none",
        "choch": structure.get("choch") or "none",
        "pattern": pattern.replace("_", " ").title() if pattern else "No clear pattern",
        "warnings": bundle.signal.warnings[:4],
        "sync": f"{bundle.sync.match_percentage}%" if bundle.sync else "100%",
        "actionable": actionable,
        "reasons": reasons,
    }

def build_chart_draw_payload(bundle):
    candles = pd.DataFrame(bundle.chart_payload.get("candles") or [])
    if candles.empty:
        return {}

    candles["timestamp"] = pd.to_datetime(candles["timestamp"], utc=True, errors="coerce")
    candle_records = []
    for _, row in candles.dropna(subset=["timestamp"]).iterrows():
        candle_records.append(
            {
                "time": int(row["timestamp"].timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )

    overlays = bundle.chart_payload.get("overlays") or {}
    structure = overlays.get("structure") or {}
    pattern = candle_pattern(bundle.candles)
    pattern_markers = []
    if pattern and candle_records:
        last_candle = candle_records[-1]
        marker_text = "BREAKOUT" if structure.get("phase") == "breakout" else "REVERSAL"
        pattern_markers.append(
            {
                "time": last_candle["time"],
                "position": "aboveBar",
                "color": "#7c3aed",
                "shape": "arrowDown",
                "text": marker_text,
            }
        )

    if bundle.signal.signal == "TRADE_REMOVED" and candle_records:
        last_candle = candle_records[-1]
        pattern_markers.append(
            {
                "time": last_candle["time"],
                "position": "aboveBar",
                "color": "#dc2626",
                "shape": "arrowDown",
                "text": "INVALIDATED",
            }
        )

    levels = []
    has_mismatch = any("Feed mismatch" in w or "mismatch" in w.lower() for w in bundle.signal.warnings)
    actionable = (bundle.signal.signal in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"] 
                  and bundle.signal.stop_loss not in [None, 0, 0.0] 
                  and not has_mismatch)
    if actionable:
        for label, value, color in [
            ("ENTRY", overlays.get("entry"), "#2563eb"),
            ("SL", overlays.get("stop_loss"), "#dc2626"),
            ("TP1", overlays.get("tp1"), "#16a34a"),
            ("TP2", overlays.get("tp2"), "#166534"),
        ]:
            if value not in [None, 0, 0.0, ""]:
                levels.append({"title": label, "value": float(value), "color": color})

    sr_zones = overlays.get("support_resistance") or []
    imbalances = overlays.get("imbalances") or []
    
    filtered_sr = []
    filtered_imbalances = []
    
    signal = bundle.signal.signal
    reasons = [r.lower() for r in (bundle.signal.reasons or [])]
    is_trade = signal in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"]
    
    if is_trade:
        has_support_reason = any("support" in r for r in reasons)
        has_resistance_reason = any("resistance" in r for r in reasons)
        has_bullish_fvg_reason = any("bullish fvg" in r or "imbalance" in r for r in reasons)
        has_bearish_fvg_reason = any("bearish fvg" in r or "imbalance" in r for r in reasons)
        
        price = float(candle_records[-1]["close"]) if candle_records else 0.0
        
        if has_support_reason and signal in ["BUY", "STRONG_BUY"]:
            supports = [z for z in sr_zones if z.get("type") == "support"]
            if supports:
                closest_support = min(supports, key=lambda z: abs(price - float(z.get("top", 0.0))))
                filtered_sr.append(closest_support)
                
        if has_resistance_reason and signal in ["SELL", "STRONG_SELL"]:
            resistances = [z for z in sr_zones if z.get("type") == "resistance"]
            if resistances:
                closest_resistance = min(resistances, key=lambda z: abs(price - float(z.get("bottom", 0.0))))
                filtered_sr.append(closest_resistance)
                
        if has_bullish_fvg_reason and signal in ["BUY", "STRONG_BUY"]:
            bull_fvgs = [z for z in imbalances if z.get("type") == "bullish"]
            if bull_fvgs:
                closest_fvg = min(bull_fvgs, key=lambda z: abs(price - float(z.get("avg", 0.0))))
                filtered_imbalances.append(closest_fvg)
                
        if has_bearish_fvg_reason and signal in ["SELL", "STRONG_SELL"]:
            bear_fvgs = [z for z in imbalances if z.get("type") == "bearish"]
            if bear_fvgs:
                closest_fvg = min(bear_fvgs, key=lambda z: abs(price - float(z.get("avg", 0.0))))
                filtered_imbalances.append(closest_fvg)
    else:
        # For non-active states, draw the top 2 strength zones and FVG
        supports = [z for z in sr_zones if z.get("type") == "support"]
        resistances = [z for z in sr_zones if z.get("type") == "resistance"]
        if supports:
            filtered_sr.append(max(supports, key=lambda z: float(z.get("strength", 0.0))))
        if resistances:
            filtered_sr.append(max(resistances, key=lambda z: float(z.get("strength", 0.0))))
            
        bull_fvgs = [z for z in imbalances if z.get("type") == "bullish"]
        bear_fvgs = [z for z in imbalances if z.get("type") == "bearish"]
        if bull_fvgs:
            filtered_imbalances.append(max(bull_fvgs, key=lambda z: float(z.get("size", 0.0))))
        if bear_fvgs:
            filtered_imbalances.append(max(bear_fvgs, key=lambda z: float(z.get("size", 0.0))))

    return {
        "candles": candle_records,
        "levels": levels,
        "pattern_markers": pattern_markers,
        "structure_labels": overlays.get("structure_labels") or [],
        "trendlines": overlays.get("trendlines") or [],
        "support_resistance": filtered_sr,
        "imbalances": filtered_imbalances,
    }

def get_news_countdown_text(symbol, orchestrator):
    from datetime import datetime, timezone
    try:
        forex_factory_feed = getattr(orchestrator, "forex_factory_feed", None)
        if forex_factory_feed:
            base = symbol[:3].upper()
            quote = symbol[3:].upper() if len(symbol) >= 6 else ""
            symbol_currencies = {base, quote} - {""}
            
            all_events = forex_factory_feed.fetch_events() or []
            now_utc = datetime.now(timezone.utc)
            
            upcoming_high_events = []
            for ev in all_events:
                if ev.impact_level == "HIGH" and ev.currency in symbol_currencies:
                    try:
                        pub_time = datetime.fromisoformat(ev.publication_time.replace("Z", "+00:00"))
                        if pub_time > now_utc:
                            upcoming_high_events.append((pub_time, ev.event_name))
                    except Exception:
                        pass
            
            if upcoming_high_events:
                upcoming_high_events.sort(key=lambda x: x[0])
                next_high_news_time, next_high_news_name = upcoming_high_events[0]
                
                time_diff = next_high_news_time - now_utc
                diff_seconds = time_diff.total_seconds()
                diff_hours = int(diff_seconds // 3600)
                diff_mins = int((diff_seconds % 3600) // 60)
                
                if diff_hours > 0:
                    return f"{next_high_news_name} in {diff_hours}h {diff_mins}m"
                else:
                    return f"{next_high_news_name} in {diff_mins}m"
    except Exception:
        pass
    return ""


class LiveAnalysisSession:
    def __init__(self, symbol: str, timeframe: str, manager):
        self.symbol = symbol
        self.timeframe = timeframe
        self.manager = manager
        self.active = False
        self.thread = None
        self.latest_bundle = None
        self.lock = threading.Lock()
        self.clients = set()
        self.error_count = 0

    def start(self):
        with self.lock:
            if not self.active:
                self.active = True
                self.thread = threading.Thread(target=self.run_loop, daemon=True)
                self.thread.start()
                logger.info(f"Started background live analysis thread for {self.symbol} {self.timeframe}")

    def stop(self):
        with self.lock:
            self.active = False
            logger.info(f"Stopping background live analysis thread for {self.symbol} {self.timeframe}")

    def run_loop(self):
        while self.active:
            start_time = time.time()
            logger.info(f"Triggering analysis refresh for {self.symbol} {self.timeframe}...")
            
            try:
                # Perform the full market analysis (bypassing cache!)
                bundle = self.manager.orchestrator.analyze(
                    self.symbol, self.timeframe, force_refresh=True
                )
                
                if bundle is not None:
                    # Log signal to storage repository
                    self.manager.orchestrator.log_signal(bundle)
                    
                    # Update local state
                    with self.lock:
                        self.latest_bundle = bundle
                        self.error_count = 0
                    
                    # Broadcast the new analysis to all WebSocket clients
                    self.broadcast_bundle(bundle)
                    logger.info(f"Analysis complete and pushed for {self.symbol} {self.timeframe}")
                else:
                    raise Exception("Orchestrator returned None")
                    
            except Exception as e:
                logger.error(f"Error in analysis cycle for {self.symbol} {self.timeframe}: {e}")
                self.error_count += 1
                
                # In case of failure, continue displaying the last successful analysis if available
                if self.latest_bundle is not None:
                    logger.info(f"Broadcasting last successful analysis for {self.symbol} {self.timeframe} due to refresh error")
                    self.broadcast_bundle(self.latest_bundle)
            
            # Prevent overlapping analysis: wait exactly remaining time or yields thread
            elapsed = time.time() - start_time
            sleep_time = max(0.01, 3.0 - elapsed)
            time.sleep(sleep_time)

    def broadcast_bundle(self, bundle):
        timestamp = datetime.now(timezone.utc).isoformat()
        news_text = get_news_countdown_text(self.symbol, self.manager.orchestrator)
        payload = {
            "timestamp": timestamp,
            "panelPayload": build_trade_panel_payload(bundle),
            "drawPayload": build_chart_draw_payload(bundle),
            "newsCountdown": news_text,
        }
        self.broadcast(payload)

    def broadcast(self, data):
        if not self.clients or self.manager.loop is None:
            return
        # Schedule the async send in the Starlette event loop
        asyncio.run_coroutine_threadsafe(self._async_broadcast(data), self.manager.loop)

    async def _async_broadcast(self, data):
        disconnected = []
        tasks = []
        for client in list(self.clients):
            if client.client_state == WebSocketState.CONNECTED:
                tasks.append(client.send_json(data))
            else:
                disconnected.append(client)
                
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        for client in disconnected:
            self.clients.discard(client)


class LiveAnalysisManager:
    def __init__(self):
        self.orchestrator = None
        self.loop = None
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        self.tab_visibility = {}

    def initialize(self, orchestrator):
        self.orchestrator = orchestrator

    def get_latest_analysis(self, symbol: str, timeframe: str) -> AnalysisBundle | None:
        key = (symbol, timeframe)
        with self.sessions_lock:
            session = self.sessions.get(key)
            if session:
                return session.latest_bundle
        return None

    def set_latest_analysis(self, symbol: str, timeframe: str, bundle: AnalysisBundle):
        key = (symbol, timeframe)
        with self.sessions_lock:
            session = self.sessions.get(key)
            if session:
                session.latest_bundle = bundle

    async def register_client(self, symbol: str, timeframe: str, websocket):
        key = (symbol, timeframe)
        logger.info(f"Registering client for {symbol} {timeframe}")
        
        with self.sessions_lock:
            session = self.sessions.get(key)
            if not session:
                session = LiveAnalysisSession(symbol, timeframe, self)
                self.sessions[key] = session
                session.start()
            
            session.clients.add(websocket)
            
            # Send immediate update on connection if available
            if session.latest_bundle is not None:
                # Run the sending in the current asyncio context
                news_text = get_news_countdown_text(symbol, self.orchestrator)
                await websocket.send_json({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "panelPayload": build_trade_panel_payload(session.latest_bundle),
                    "drawPayload": build_chart_draw_payload(session.latest_bundle),
                    "newsCountdown": news_text,
                })

    async def unregister_client(self, symbol: str, timeframe: str, websocket):
        key = (symbol, timeframe)
        logger.info(f"Unregistering client for {symbol} {timeframe}")
        
        with self.sessions_lock:
            session = self.sessions.get(key)
            if session:
                session.clients.discard(websocket)
                if not session.clients:
                    session.stop()
                    del self.sessions[key]
                    logger.info(f"Terminated analysis session for {symbol} {timeframe} because all clients disconnected.")



# Singleton manager
live_analysis_manager = LiveAnalysisManager()

async def http_refresh(request):
    symbol = request.query_params.get("symbol")
    timeframe = request.query_params.get("timeframe")
    if not symbol or not timeframe:
        return JSONResponse({"error": "Missing symbol or timeframe"}, status_code=400)
    
    bundle = live_analysis_manager.get_latest_analysis(symbol, timeframe)
    if bundle is None:
        # Fallback: run a synchronous analysis on request
        if live_analysis_manager.orchestrator:
            try:
                bundle = live_analysis_manager.orchestrator.analyze(symbol, timeframe, force_refresh=True)
                if bundle is not None:
                    live_analysis_manager.orchestrator.log_signal(bundle)
                    # If a session exists, update it
                    live_analysis_manager.set_latest_analysis(symbol, timeframe, bundle)
            except Exception as e:
                logger.error(f"Fallback HTTP refresh failed: {e}")
                bundle = None
                
    if bundle is None:
        return JSONResponse({"error": "Analysis failed"}, status_code=500)
        
    payload = build_trade_panel_payload(bundle)
    return JSONResponse(payload, headers={"Access-Control-Allow-Origin": "*"})

async def http_visibility(request):
    state = request.query_params.get("state", "visible")
    session_id = request.query_params.get("session_id", "default")
    live_analysis_manager.tab_visibility[session_id] = state
    return JSONResponse({"status": "ok"}, headers={"Access-Control-Allow-Origin": "*"})

async def websocket_endpoint(websocket):
    await websocket.accept()
    query_params = websocket.query_params
    symbol = query_params.get("symbol")
    timeframe = query_params.get("timeframe")
    
    if not symbol or not timeframe:
        await websocket.close(code=4000)
        return
        
    await live_analysis_manager.register_client(symbol, timeframe, websocket)
    
    try:
        # Keep client connection open
        while True:
            # Just read to keep connection alive and receive disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await live_analysis_manager.unregister_client(symbol, timeframe, websocket)

# Instantiate Starlette App with explicit routes
from starlette.routing import Route, WebSocketRoute

app = Starlette(
    routes=[
        Route("/refresh", http_refresh, methods=["GET"]),
        Route("/visibility", http_visibility, methods=["GET", "OPTIONS"]),
        WebSocketRoute("/ws", websocket_endpoint)
    ]
)



def start_engine_api_server(orchestrator):
    live_analysis_manager.initialize(orchestrator)
    
    def run_server():
        # Setup event loop in background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        live_analysis_manager.loop = loop
        
        config = uvicorn.Config(app, host="127.0.0.1", port=8505, log_level="error")
        server = uvicorn.Server(config)
        
        logger.info("Starting Starlette API and WebSocket server on port 8505...")
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    return t
