import json
import uuid

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import importlib
import storage.signal_repository_v2
import engine.analysis_orchestrator
import engine.signal_engine_v2
import core.signal_engine
import backend.service_container

for module in [storage.signal_repository_v2, engine.signal_engine_v2, core.signal_engine, engine.analysis_orchestrator, backend.service_container]:
    try:
        importlib.reload(module)
    except Exception:
        pass

from backend.service_container import build_container
from core.signal_engine import candle_pattern


SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "BTCUSD", "USDCAD"]
TIMEFRAMES = ["1", "5", "15", "30", "60", "240", "D"]


def init_session_state():
    defaults = {
        "analysis_bundle": None,
        "analysis_symbol": "XAUUSD",
        "analysis_timeframe": "5",
        "selected_strategy": "Auto (Session-Aware)",
        "chart_fullscreen": False,
        "chart_engine": "Lightweight Charts (Overlay)",
        # News Intel cache
        "news_signals": [],
        "news_signals_symbol": "",
        "news_signals_timeframe": "",
        "news_signals_fetched_at": 0.0,
        # Live analysis states
        "live_mode": False,
        "is_analyzing": False,
        "last_analysis_time": "Never",
        "last_analysis_time_dt": None,
        "last_price": None,
        "last_candle_time": None,
        "analysis_status": "STOPPED",
        "update_trigger_reason": "System Start",
        "refresh_sec": 5,
        "pips_thresh": 2.0,
        "trigger_mode": "Hybrid (Smart Triggers)",
        "session_uuid": str(uuid.uuid4()),
        "force_analyze": False,
        "last_active_position_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def inject_styles():
    st.markdown(
        """
        <style>
        /* Keep elements 100% opaque during reruns to avoid screen blurring/flashing */
        [data-testid="stAppViewBlockContainer"], 
        .element-container, 
        div[data-testid="stBlock"], 
        div[data-testid="stHorizontalBlock"], 
        div[data-testid="stVerticalBlock"], 
        div[data-testid="stTab"], 
        [data-baseweb="tab-panel"] {
            opacity: 1 !important;
            transition: none !important;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(20, 184, 166, 0.10), transparent 28%),
                radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 24%),
                linear-gradient(180deg, #f8fafc 0%, #eef4ff 100%);
        }

        .block-container {
            max-width: 1460px;
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }

        div[data-testid="stButton"] > button {
            border-radius: 999px;
            min-height: 2.85rem;
            font-weight: 700;
            border: 1px solid #cbd5e1;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08);
            transition: transform 0.1s ease, box-shadow 0.1s ease, background 0.15s ease, opacity 0.15s ease;
        }

        div[data-testid="stButton"] > button:active {
            transform: scale(0.96) translateY(2px) !important;
            box-shadow: 0 4px 10px rgba(15, 23, 42, 0.12) !important;
        }

        div[data-testid="stButton"] > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.12);
        }

        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #0f766e 0%, #1d4ed8 100%);
            border: none;
            color: white;
        }

        div[data-testid="stButton"] > button[kind="primary"]:active {
            background: linear-gradient(135deg, #0d5c56 0%, #173fa6 100%) !important;
        }

        /* Style top-level stHorizontalBlock for controls wrapper */
        div[data-testid="stAppViewBlockContainer"] div[data-testid="stHorizontalBlock"]:not(div[data-testid="stTab"] div[data-testid="stHorizontalBlock"]) {
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-radius: 24px;
            padding: 1.2rem 1.5rem 1.2rem 1.5rem;
            background: rgba(255, 255, 255, 0.88);
            box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08);
            backdrop-filter: blur(10px);
            margin-bottom: 1.5rem;
        }

        /* Align button vertically with selectbox inputs */
        div[data-testid="stAppViewBlockContainer"] div[data-testid="stHorizontalBlock"]:not(div[data-testid="stTab"] div[data-testid="stHorizontalBlock"]) div[data-testid="stButton"] {
            margin-top: 1.7rem !important;
        }

        /* Ensure labels are properly visible and high contrast */
        label[data-testid="stWidgetLabel"], label[data-testid="stWidgetLabel"] p {
            color: #0f172a !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
        }

        /* Enforce high contrast for title and header text */
        .stApp h1, h1#ai-trading-platform {
            color: #0f172a !important;
            font-weight: 800 !important;
        }

        div[data-testid="stCaptionContainer"] p {
            color: #475569 !important;
            font-weight: 500 !important;
        }

        .metric-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.8rem;
            margin: 0.65rem 0 1rem 0;
        }

        .metric-card {
            border-radius: 18px;
            padding: 0.9rem 1rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(241,245,249,0.92));
            border: 1px solid rgba(148, 163, 184, 0.24);
        }

        .metric-label {
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #64748b;
            margin-bottom: 0.28rem;
        }

        .metric-value {
            font-size: 1.05rem;
            font-weight: 700;
            color: #0f172a;
        }

        .content-card {
            border-radius: 20px;
            padding: 1rem 1.05rem;
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid rgba(148, 163, 184, 0.24);
            box-shadow: 0 16px 35px rgba(15, 23, 42, 0.08);
            color: #0f172a;
            margin-bottom: 1rem;
        }

        .content-title {
            font-size: 1rem;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 0.7rem;
        }

        .content-text {
            color: #1e293b;
            font-size: 0.95rem;
            line-height: 1.55;
        }

        .content-list {
            margin: 0;
            padding-left: 1rem;
            color: #1e293b;
        }

        .status-box {
            border-radius: 18px;
            padding: 0.95rem 1rem;
            font-weight: 700;
            margin-bottom: 0.9rem;
        }

        .status-box.warning {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
        }

        .status-box.success {
            background: #dcfce7;
            color: #166534;
            border: 1px solid #86efac;
        }

        .status-box.danger {
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
        }

        .section-title {
            margin-top: 0.35rem;
            margin-bottom: 0.15rem;
            color: #0f172a;
            font-size: 1.1rem;
            font-weight: 800;
        }

        .section-caption {
            color: #475569;
            margin-bottom: 0.95rem;
            font-size: 0.94rem;
        }

        /* Ensure tab labels are visible and high contrast */
        button[data-testid="stTab"] {
            color: #475569 !important;
            font-size: 0.95rem !important;
            font-weight: 600 !important;
        }

        button[data-testid="stTab"] p {
            color: inherit !important;
            font-size: inherit !important;
            font-weight: inherit !important;
        }

        button[data-testid="stTab"][aria-selected="true"] {
            color: #ff4b4b !important;
            font-weight: 700 !important;
        }

        button[data-testid="stTab"][aria-selected="true"] p {
            color: inherit !important;
            font-weight: inherit !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title, caption):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-caption">{caption}</div>', unsafe_allow_html=True)


def render_content_card(title, body_html):
    cleaned_body = "\n".join(line.strip() for line in body_html.splitlines())
    st.markdown(
        f'<div class="content-card"><div class="content-title">{title}</div><div class="content-text">{cleaned_body}</div></div>',
        unsafe_allow_html=True,
    )


def render_status_box(message, tone="warning"):
    st.markdown(f'<div class="status-box {tone}">{message}</div>', unsafe_allow_html=True)


def format_price(value):
    if value in [None, "", 0, 0.0]:
        return "--"
    try:
        return f"{float(value):,.5f}"
    except (TypeError, ValueError):
        return str(value)


def get_tradingview_symbol(symbol):
    return {
        "XAUUSD": "OANDA:XAUUSD",
        "EURUSD": "OANDA:EURUSD",
        "GBPUSD": "OANDA:GBPUSD",
        "AUDUSD": "OANDA:AUDUSD",
        "USDJPY": "OANDA:USDJPY",
        "USDCHF": "OANDA:USDCHF",
        "USDCAD": "OANDA:USDCAD",
    }.get(symbol, f"OANDA:{symbol}")


def get_tradingview_interval(timeframe):
    return {"5": "5", "15": "15", "30": "30", "60": "60", "240": "240", "D": "D"}.get(timeframe, "5")


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

    # Filter support_resistance and imbalances based on active signal confluences / reasons
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
            bullish_fvgs = [i for i in imbalances if i.get("type") == "bullish"]
            if bullish_fvgs:
                closest_fvg = min(bullish_fvgs, key=lambda i: abs(price - float(i.get("avg", 0.0))))
                filtered_imbalances.append(closest_fvg)
                
        if has_bearish_fvg_reason and signal in ["SELL", "STRONG_SELL"]:
            bearish_fvgs = [i for i in imbalances if i.get("type") == "bearish"]
            if bearish_fvgs:
                closest_fvg = min(bearish_fvgs, key=lambda i: abs(price - float(i.get("avg", 0.0))))
                filtered_imbalances.append(closest_fvg)

    # Let's rebuild the simple zone lines payload just in case anything else needs it
    zone_lines = []
    for index, zone in enumerate(filtered_sr):
        color = "#16a34a" if zone.get("type") == "support" else "#dc2626"
        zone_lines.extend(
            [
                {"title": f"{zone.get('type').title()} {index + 1} Top", "value": float(zone.get("top")), "color": color},
                {"title": f"{zone.get('type').title()} {index + 1} Bottom", "value": float(zone.get("bottom")), "color": color},
            ]
        )
    for index, imbalance in enumerate(filtered_imbalances):
        color = "#14b8a6" if imbalance.get("type") == "bullish" else "#f97316"
        zone_lines.extend(
            [
                {"title": f"{imbalance.get('type').title()} FVG {index + 1} High", "value": float(imbalance.get("high")), "color": color},
                {"title": f"{imbalance.get('type').title()} FVG {index + 1} Low", "value": float(imbalance.get("low")), "color": color},
            ]
        )

    trendlines = []
    hl_points = structure.get("swing_points", {}).get("hl") or []
    lh_points = structure.get("swing_points", {}).get("lh") or []
    if structure.get("trend") == "bullish" and len(hl_points) >= 2:
        first, second = hl_points[-2], hl_points[-1]
        trendlines.append(
            {
                "name": "Higher Lows",
                "color": "#16a34a",
                "points": [
                    {"time": int(pd.to_datetime(first["timestamp"], utc=True).timestamp()), "value": float(first["price"])},
                    {"time": int(pd.to_datetime(second["timestamp"], utc=True).timestamp()), "value": float(second["price"])},
                ],
            }
        )
    elif structure.get("trend") == "bearish" and len(lh_points) >= 2:
        first, second = lh_points[-2], lh_points[-1]
        trendlines.append(
            {
                "name": "Lower Highs",
                "color": "#dc2626",
                "points": [
                    {"time": int(pd.to_datetime(first["timestamp"], utc=True).timestamp()), "value": float(first["price"])},
                    {"time": int(pd.to_datetime(second["timestamp"], utc=True).timestamp()), "value": float(second["price"])},
                ],
            }
        )

    structure_labels = []
    for group_name, points in (structure.get("swing_points") or {}).items():
        color = {"hh": "#2563eb", "hl": "#16a34a", "lh": "#f97316", "ll": "#dc2626"}.get(group_name, "#475569")
        for point in points:
            structure_labels.append(
                {
                    "time": int(pd.to_datetime(point["timestamp"], utc=True).timestamp()),
                    "position": "aboveBar" if group_name in ["hh", "lh"] else "belowBar",
                    "color": color,
                    "shape": "circle",
                    "text": point["label"],
                }
            )

    fibonacci = overlays.get("fibonacci")
    filtered_fib = None
    if fibonacci and is_trade and any("ote" in r for r in reasons):
        filtered_fib = fibonacci

    return {
        "candles": candle_records,
        "levels": levels,
        "zone_lines": zone_lines,
        "support_resistance": filtered_sr,
        "imbalances": filtered_imbalances,
        "trendlines": trendlines,
        "pattern_markers": pattern_markers,
        "structure_labels": structure_labels,
        "fibonacci": filtered_fib,
    }


def render_lightweight_chart(symbol, timeframe, bundle):
    panel_payload = build_trade_panel_payload(bundle)
    draw_payload = build_chart_draw_payload(bundle)
    panel_json = json.dumps(panel_payload)
    draw_json = json.dumps(draw_payload)
    container_id = f"lw_chart_{symbol}_{timeframe}".replace(":", "_")
    panel_id = f"lw_panel_{symbol}_{timeframe}".replace(":", "_")

    html = f"""
    <div id="{container_id}_wrapper" style="height:760px;width:100%;position:relative;border:1px solid rgba(255,255,255,0.12);border-radius:22px;overflow:hidden;background:#131722;display:flex;flex-direction:column;font-family:Arial,sans-serif;box-shadow:0 25px 50px rgba(0,0,0,0.4);">
      <style>
        @keyframes pulse {{
          0% {{ opacity: 0.3; }}
          50% {{ opacity: 1; }}
          100% {{ opacity: 0.3; }}
        }}
        @keyframes spin {{
          0% {{ transform: rotate(0deg); }}
          100% {{ transform: rotate(360deg); }}
        }}
        .spinning {{
          display: inline-block !important;
          animation: spin 1s linear infinite;
        }}
        #{panel_id}::-webkit-resizer {{
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><path d="M10,0 L0,10 M10,3 L3,10 M10,6 L6,10" stroke="rgba(255,255,255,0.6)" stroke-width="1.5" stroke-linecap="round"/></svg>');
          background-repeat: no-repeat;
          background-position: bottom right;
          width: 14px;
          height: 14px;
        }}
      </style>
      
      <!-- Top Toolbar (TradingView Style) -->
      <div style="height:44px;background:#1c2030;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;align-items:center;justify-content:space-between;padding:0 16px;user-select:none;color:#d1d4dc;font-size:13px;font-weight:600;z-index:7;">
        <div style="display:flex;align-items:center;gap:14px;">
          <span style="color:#2962ff;font-size:15px;font-weight:900;display:flex;align-items:center;gap:5px;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2962ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
            TradingView Live
          </span>
          <span style="height:16px;width:1px;background:rgba(255,255,255,0.12);"></span>
          <span style="color:#ffffff;background:#2a2e39;padding:4px 10px;border-radius:6px;font-size:12px;letter-spacing:0.5px;">{symbol}</span>
          <span style="color:#94a3b8;font-size:12px;">{timeframe}m</span>
          <span style="height:16px;width:1px;background:rgba(255,255,255,0.12);"></span>
          <span style="color:#94a3b8;display:flex;align-items:center;gap:4px;font-size:12px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg> Indicators</span>
        </div>
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="color:#22c55e;font-size:11px;font-weight:700;background:rgba(34,197,94,0.12);padding:5px 10px;border-radius:999px;display:flex;align-items:center;gap:6px;">
            <span style="width:6px;height:6px;border-radius:50%;background:#22c55e;box-shadow:0 0 6px #22c55e;animation:pulse 1.5s infinite;"></span>LIVE DATA
          </span>
          <button type="button" id="{container_id}_fullscreen" style="border:none;border-radius:8px;padding:6px 14px;background:#2962ff;color:#fff;font-weight:700;font-size:12px;cursor:pointer;transition:background 0.2s;display:flex;align-items:center;gap:4px;">⛶ Fullscreen</button>
        </div>
      </div>

      <!-- Main Body: Sidebar + Chart -->
      <div style="display:flex;flex:1;position:relative;background:#131722;">
        <!-- Left Sidebar (Mock Drawings Tools) -->
        <div style="width:45px;background:#1c2030;border-right:1px solid rgba(255,255,255,0.08);display:flex;flex-direction:column;align-items:center;padding-top:14px;gap:20px;color:#848e9c;user-select:none;z-index:7;">
          <div title="Crosshair Cursor" style="cursor:pointer;color:#2962ff;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 2v20M2 12h20"/></svg></div>
          <div title="Trend Line" style="cursor:pointer;hover:color:#fff;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="20" x2="20" y2="4"/><circle cx="4" cy="20" r="1.5" fill="currentColor"/><circle cx="20" cy="4" r="1.5" fill="currentColor"/></svg></div>
          <div title="Fibonacci Retracement" style="cursor:pointer;hover:color:#fff;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/></svg></div>
          <div title="Brush" style="cursor:pointer;hover:color:#fff;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M6 12l4 4 8-8"/></svg></div>
          <div title="Text" style="cursor:pointer;hover:color:#fff;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg></div>
          <div title="Ruler" style="cursor:pointer;hover:color:#fff;"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21.3 8.11L15.89 2.7a1 1 0 0 0-1.41 0L2.7 14.48a1 1 0 0 0 0 1.41l5.41 5.41a1 1 0 0 0 1.42 0L21.3 9.53a1 1 0 0 0 0-1.42z"/></svg></div>
        </div>

        <!-- Floating Trading Panel -->
        <div id="{panel_id}" style="position:absolute;top:18px;left:18px;width:340px;height:440px;min-width:260px;min-height:200px;resize:both;overflow:auto;z-index:9;border-radius:24px;background:linear-gradient(180deg, rgba(15,23,42,0.9), rgba(30,41,59,0.85));color:#f8fafc;border:1px solid rgba(255,255,255,0.12);box-shadow:0 25px 50px rgba(0,0,0,0.5);font-family:Arial,sans-serif;backdrop-filter:blur(12px);"></div>
        
        <!-- Chart Container -->
        <div id="{container_id}" style="flex:1;height:100%;"></div>
      </div>
      <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4/dist/lightweight-charts.standalone.production.js"></script>
      <script>
        window.addEventListener('error', (event) => {{
          const errDiv = document.createElement('div');
          errDiv.style.color = '#dc2626';
          errDiv.style.background = '#fef2f2';
          errDiv.style.padding = '12px 16px';
          errDiv.style.border = '1px solid #fee2e2';
          errDiv.style.borderRadius = '12px';
          errDiv.style.position = 'absolute';
          errDiv.style.top = '70px';
          errDiv.style.left = '18px';
          errDiv.style.zIndex = '9999';
          errDiv.style.fontFamily = 'Arial, sans-serif';
          errDiv.style.fontSize = '13px';
          errDiv.style.boxShadow = '0 10px 15px -3px rgba(0,0,0,0.1)';
          errDiv.innerText = 'JS Error: ' + event.message + ' at ' + event.filename + ':' + event.lineno;
          document.body.appendChild(errDiv);
        }});

        const panelPayload = {panel_json};
        const drawPayload = {draw_json};
        const wrapper = document.getElementById("{container_id}_wrapper");
        const panel = document.getElementById("{panel_id}");
        const chartRoot = document.getElementById("{container_id}");

        let statusColor = "#22c55e";
        let signalBg = "rgba(34, 197, 94, 0.25)";
        let headerGradient = "linear-gradient(135deg, rgba(20,184,166,0.55), rgba(37,99,235,0.42))";

        if (panelPayload.signal === "TRADE_REMOVED") {{
          statusColor = "#ef4444";
          signalBg = "rgba(239, 68, 68, 0.35)";
          headerGradient = "linear-gradient(135deg, rgba(239, 68, 68, 0.6), rgba(220, 38, 38, 0.5))";
        }} else if (panelPayload.signal.includes("BUY")) {{
          statusColor = "#22c55e";
          signalBg = "rgba(34, 197, 94, 0.35)";
          headerGradient = "linear-gradient(135deg, rgba(16, 185, 129, 0.6), rgba(5, 150, 105, 0.5))";
        }} else if (panelPayload.signal.includes("SELL")) {{
          statusColor = "#f97316";
          signalBg = "rgba(249, 115, 22, 0.35)";
          headerGradient = "linear-gradient(135deg, rgba(249, 115, 22, 0.6), rgba(234, 88, 12, 0.5))";
        }} else {{
          statusColor = "#94a3b8";
          signalBg = "rgba(148, 163, 184, 0.25)";
          headerGradient = "linear-gradient(135deg, rgba(100, 116, 139, 0.55), rgba(71, 85, 105, 0.42))";
        }}

        panel.innerHTML = `
          <div id="{panel_id}_drag" style="padding:12px 16px;background:${{headerGradient}};font-size:16px;font-weight:700;position:sticky;top:0;display:flex;justify-content:space-between;align-items:center;cursor:move;user-select:none;border-top-left-radius:24px;border-top-right-radius:24px;">
            <span style="display:flex;align-items:center;gap:6px;">
              <span style="width:8px;height:8px;border-radius:50%;background:${{statusColor}};display:inline-block;box-shadow:0 0 8px ${{statusColor}};"></span>
              Trading Panel
            </span>
            <div style="display:flex;gap:6px;align-items:center;">
              <button type="button" id="{panel_id}_refresh" style="border:none;background:rgba(255,255,255,0.16);color:#fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:12px;transition:background 0.2s;" title="Refresh Panel">🔄</button>
              <button type="button" id="{panel_id}_minimise" style="border:none;background:rgba(255,255,255,0.16);color:#fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-weight:700;font-size:14px;transition:background 0.2s;">−</button>
            </div>
          </div>
          <div id="{panel_id}_content" style="padding:16px;">
            <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">
              <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:${{signalBg}};">${{panelPayload.signal}}</span>
              <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{panelPayload.confidence}}</span>
              <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{panelPayload.status}}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px;">
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Symbol</div><div style="font-size:15px;font-weight:700;">${{panelPayload.symbol}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Timeframe</div><div style="font-size:15px;font-weight:700;">${{panelPayload.timeframe}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Entry</div><div style="font-size:15px;font-weight:700;">${{panelPayload.entry}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Stop Loss</div><div style="font-size:15px;font-weight:700;">${{panelPayload.stop_loss}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 1</div><div style="font-size:15px;font-weight:700;">${{panelPayload.tp1}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 2</div><div style="font-size:15px;font-weight:700;">${{panelPayload.tp2}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 3</div><div style="font-size:15px;font-weight:700;">${{panelPayload.tp3}}</div></div>
            </div>
            <div style="display:grid;gap:8px;">
              <div style="padding:10px 12px;border-radius:16px;background:rgba(37,99,235,0.16);border:1px solid rgba(96,165,250,0.35);">
                <div style="font-size:11px;color:#bfdbfe;margin-bottom:4px;">Candle Pattern</div>
                <div style="font-size:14px;font-weight:700;color:#eff6ff;">${{panelPayload.pattern}}</div>
              </div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);">
                <div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Structure</div>
                <div style="font-size:13px;font-weight:700;">Trend: ${{panelPayload.trend}}</div>
                <div style="font-size:13px;font-weight:700;">Phase: ${{panelPayload.phase}}</div>
                <div style="font-size:13px;font-weight:700;">BOS / CHOCH: ${{panelPayload.bos}} / ${{panelPayload.choch}}</div>
              </div>
            </div>
          </div>`;

        const chart = LightweightCharts.createChart(chartRoot, {{
          width: chartRoot.clientWidth || 900,
          height: chartRoot.clientHeight || 700,
          layout: {{
            background: {{ color: '#131722' }},
            textColor: '#8f9aae',
          }},
          grid: {{
            vertLines: {{ color: 'rgba(42, 46, 57, 0.4)' }},
            horzLines: {{ color: 'rgba(42, 46, 57, 0.4)' }},
          }},
          rightPriceScale: {{
            borderColor: 'rgba(42, 46, 57, 0.6)',
          }},
          timeScale: {{
            borderColor: 'rgba(42, 46, 57, 0.6)',
            timeVisible: true,
            secondsVisible: false,
          }},
          crosshair: {{
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {{
              color: 'rgba(117, 134, 150, 0.6)',
              width: 1,
              style: LightweightCharts.LineStyle.Dashed,
            }},
            horzLine: {{
              color: 'rgba(117, 134, 150, 0.6)',
              width: 1,
              style: LightweightCharts.LineStyle.Dashed,
            }},
          }},
        }});

        const candleSeries = chart.addCandlestickSeries({{
          upColor: '#16a34a',
          downColor: '#dc2626',
          wickUpColor: '#16a34a',
          wickDownColor: '#dc2626',
          borderVisible: false,
        }});
        candleSeries.setData(drawPayload.candles || []);

        (drawPayload.levels || []).forEach((level) => {{
          candleSeries.createPriceLine({{
            price: level.value,
            color: level.color,
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: level.title,
          }});
        }});

        // support/resistance and imbalances are drawn as premium shaded zones on the canvas overlay instead of series price lines

        (drawPayload.trendlines || []).forEach((trendline) => {{
          const series = chart.addLineSeries({{
            color: trendline.color,
            lineWidth: 3,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          }});
          series.setData(trendline.points || []);
        }});

        const markers = []
          .concat(drawPayload.pattern_markers || [])
          .concat(drawPayload.structure_labels || []);
        if (markers.length) {{
          candleSeries.setMarkers(markers);
        }}

        const updatePanelContent = (data) => {{
          let statusColor = "#22c55e";
          let signalBg = "rgba(34, 197, 94, 0.25)";
          let headerGradient = "linear-gradient(135deg, rgba(20,184,166,0.55), rgba(37,99,235,0.42))";

          if (data.signal === "TRADE_REMOVED") {{
            statusColor = "#ef4444";
            signalBg = "rgba(239, 68, 68, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(239, 68, 68, 0.6), rgba(220, 38, 38, 0.5))";
          }} else if (data.signal.includes("BUY")) {{
            statusColor = "#22c55e";
            signalBg = "rgba(34, 197, 94, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(16, 185, 129, 0.6), rgba(5, 150, 105, 0.5))";
          }} else if (data.signal.includes("SELL")) {{
            statusColor = "#f97316";
            signalBg = "rgba(249, 115, 22, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(249, 115, 22, 0.6), rgba(234, 88, 12, 0.5))";
          }} else {{
            statusColor = "#94a3b8";
            signalBg = "rgba(148, 163, 184, 0.25)";
            headerGradient = "linear-gradient(135deg, rgba(100, 116, 139, 0.55), rgba(71, 85, 105, 0.42))";
          }}

          const dragHeader = document.getElementById("{panel_id}_drag");
          if (dragHeader) {{
            dragHeader.style.background = headerGradient;
          }}
          const statusDot = dragHeader ? dragHeader.querySelector('span > span') : null;
          if (statusDot) {{
            statusDot.style.background = statusColor;
            statusDot.style.boxShadow = `0 0 8px ${{statusColor}}`;
          }}

          const contentDiv = document.getElementById("{panel_id}_content");
          if (contentDiv) {{
            contentDiv.innerHTML = `
              <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:${{signalBg}};">${{data.signal}}</span>
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{data.confidence}}</span>
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{data.status}}</span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px;">
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Symbol</div><div style="font-size:15px;font-weight:700;">${{data.symbol}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Timeframe</div><div style="font-size:15px;font-weight:700;">${{data.timeframe}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Entry</div><div style="font-size:15px;font-weight:700;">${{data.entry}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Stop Loss</div><div style="font-size:15px;font-weight:700;">${{data.stop_loss}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 1</div><div style="font-size:15px;font-weight:700;">${{data.tp1}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 2</div><div style="font-size:15px;font-weight:700;">${{data.tp2}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 3</div><div style="font-size:15px;font-weight:700;">${{data.tp3}}</div></div>
              </div>
              <div style="display:grid;gap:8px;">
                <div style="padding:10px 12px;border-radius:16px;background:rgba(37,99,235,0.16);border:1px solid rgba(96,165,250,0.35);">
                  <div style="font-size:11px;color:#bfdbfe;margin-bottom:4px;">Candle Pattern</div>
                  <div style="font-size:14px;font-weight:700;color:#eff6ff;">${{data.pattern}}</div>
                </div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Structure</div>
                  <div style="font-size:13px;font-weight:700;">Trend: ${{data.trend}}</div>
                  <div style="font-size:13px;font-weight:700;">Phase: ${{data.phase}}</div>
                  <div style="font-size:13px;font-weight:700;">BOS / CHOCH: ${{data.bos}} / ${{data.choch}}</div>
                </div>
              </div>
            `;
          }}
        }};

        const triggerLocalRefresh = () => {{
          const refreshBtn = document.getElementById('{panel_id}_refresh');
          if (refreshBtn) {{
            refreshBtn.classList.add('spinning');
            refreshBtn.disabled = true;
          }}

          fetch(`http://127.0.0.1:8505/refresh?symbol=${{encodeURIComponent(panelPayload.symbol)}}&timeframe=${{encodeURIComponent(panelPayload.timeframe)}}`)
            .then(res => res.json())
            .then(data => {{
              if (data && !data.error) {{
                updatePanelContent(data);
              }} else {{
                console.error("Refresh error:", data ? data.error : "empty response");
              }}
            }})
            .catch(err => {{
              console.error("Fetch failed:", err);
            }})
            .finally(() => {{
              if (refreshBtn) {{
                refreshBtn.classList.remove('spinning');
                refreshBtn.disabled = false;
              }}
            }});
        }};

        document.getElementById('{panel_id}_refresh').onclick = triggerLocalRefresh;
        document.getElementById('{container_id}_fullscreen').onclick = () => {{
          if (!document.fullscreenElement) {{
            wrapper.requestFullscreen();
          }} else {{
            document.exitFullscreen();
          }}
        }};

        document.addEventListener('fullscreenchange', () => {{
          setTimeout(() => {{
            const w = wrapper.clientWidth || 900;
            const h = wrapper.clientHeight || 700;
            chart.resize(w, h);
            chart.timeScale().fitContent();
          }}, 100);
        }});

        // Minimise functionality
        const minimiseBtn = document.getElementById("{panel_id}_minimise");
        const panelContent = document.getElementById("{panel_id}_content");
        let isMinimised = false;
        let originalHeight = "440px";

        minimiseBtn.onclick = (e) => {{
          e.stopPropagation();
          isMinimised = !isMinimised;
          if (isMinimised) {{
            originalHeight = panel.style.height || "440px";
            panelContent.style.display = "none";
            panel.style.height = "48px";
            panel.style.minHeight = "48px";
            panel.style.resize = "none";
            minimiseBtn.innerText = "+";
            minimiseBtn.style.background = "rgba(255,255,255,0.3)";
          }} else {{
            panelContent.style.display = "block";
            panel.style.height = originalHeight;
            panel.style.minHeight = "200px";
            panel.style.resize = "both";
            minimiseBtn.innerText = "−";
            minimiseBtn.style.background = "rgba(255,255,255,0.16)";
          }}
        }};

        // Draggable functionality with boundaries
        let dragging = false;
        let offsetX = 0;
        let offsetY = 0;
        const dragHandle = document.getElementById('{panel_id}_drag');
        dragHandle.addEventListener('mousedown', (event) => {{
          dragging = true;
          const rect = panel.getBoundingClientRect();
          offsetX = event.clientX - rect.left;
          offsetY = event.clientY - rect.top;
          event.preventDefault();
        }});
        document.addEventListener('mousemove', (event) => {{
          if (!dragging) return;
          const wrapRect = wrapper.getBoundingClientRect();
          const maxLeft = wrapRect.width - panel.offsetWidth - 12;
          const maxTop = wrapRect.height - panel.offsetHeight - 12;
          panel.style.left = `${{Math.min(Math.max(12, event.clientX - wrapRect.left - offsetX), maxLeft)}}px`;
          panel.style.top = `${{Math.min(Math.max(12, event.clientY - wrapRect.top - offsetY), maxTop)}}px`;
        }});
        document.addEventListener('mouseup', () => {{
          dragging = false;
        }});

        // Canvas overlay for Entry, SL, and TP faded zones
        const overlayCanvas = document.createElement('canvas');
        overlayCanvas.style.position = 'absolute';
        overlayCanvas.style.top = '0';
        overlayCanvas.style.left = '0';
        overlayCanvas.style.width = '100%';
        overlayCanvas.style.height = '100%';
        overlayCanvas.style.zIndex = '5'; // Above chart grid/candles but below panel
        overlayCanvas.style.pointerEvents = 'none';
        wrapper.appendChild(overlayCanvas);

        const ctx = overlayCanvas.getContext('2d');

        function updateOverlay() {{
          overlayCanvas.width = wrapper.clientWidth;
          overlayCanvas.height = wrapper.clientHeight;
          ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

          // 1. Draw Support/Resistance Bands
          (drawPayload.support_resistance || []).forEach((zone, idx) => {{
            const topY = candleSeries.priceToCoordinate(parseFloat(zone.top));
            const bottomY = candleSeries.priceToCoordinate(parseFloat(zone.bottom));
            if (topY !== null && bottomY !== null) {{
              const isSupport = zone.type === 'support';
              const colorBg = isSupport ? 'rgba(34, 197, 94, 0.05)' : 'rgba(239, 68, 68, 0.05)';
              const colorBorder = isSupport ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.25)';
              
              ctx.fillStyle = colorBg;
              ctx.fillRect(0, Math.min(topY, bottomY), overlayCanvas.width, Math.abs(bottomY - topY));
              
              ctx.strokeStyle = colorBorder;
              ctx.lineWidth = 1;
              ctx.setLineDash([4, 4]);
              ctx.beginPath();
              ctx.moveTo(0, topY);
              ctx.lineTo(overlayCanvas.width, topY);
              ctx.moveTo(0, bottomY);
              ctx.lineTo(overlayCanvas.width, bottomY);
              ctx.stroke();
              
              ctx.setLineDash([]);
              ctx.fillStyle = isSupport ? '#22c55e' : '#f87171';
              ctx.font = 'bold 10px Arial, sans-serif';
              ctx.fillText(`${{zone.type.toUpperCase()}} ZONE #${{idx + 1}} (Str: ${{zone.strength || 1}})`, 60, Math.min(topY, bottomY) + 14);
            }}
          }});

          // 2. Draw Fair Value Gaps (FVG) Bands
          (drawPayload.imbalances || []).forEach((imbalance, idx) => {{
            const highY = candleSeries.priceToCoordinate(parseFloat(imbalance.high));
            const lowY = candleSeries.priceToCoordinate(parseFloat(imbalance.low));
            if (highY !== null && lowY !== null) {{
              const isBullish = imbalance.type === 'bullish';
              const colorBg = isBullish ? 'rgba(20, 184, 166, 0.05)' : 'rgba(249, 115, 22, 0.05)';
              const colorBorder = isBullish ? 'rgba(20, 184, 166, 0.25)' : 'rgba(249, 115, 22, 0.25)';
              
              ctx.fillStyle = colorBg;
              ctx.fillRect(0, Math.min(highY, lowY), overlayCanvas.width, Math.abs(lowY - highY));
              
              ctx.strokeStyle = colorBorder;
              ctx.lineWidth = 1;
              ctx.setLineDash([2, 2]);
              ctx.beginPath();
              ctx.moveTo(0, highY);
              ctx.lineTo(overlayCanvas.width, highY);
              ctx.moveTo(0, lowY);
              ctx.lineTo(overlayCanvas.width, lowY);
              ctx.stroke();
              
              ctx.setLineDash([]);
              ctx.fillStyle = isBullish ? '#14b8a6' : '#f97316';
              ctx.font = 'bold 10px Arial, sans-serif';
              ctx.fillText(`${{imbalance.type.toUpperCase()}} FVG`, 60, Math.min(highY, lowY) + 14);
            }}
          }});

          // 3. Draw Entry, SL, and TP Trade target zones (if entry & SL are set)
          const entryLvl = (drawPayload.levels || []).find(l => l.title === 'ENTRY');
          const slLvl = (drawPayload.levels || []).find(l => l.title === 'SL');
          const tpLvl = (drawPayload.levels || []).find(l => l.title === 'TP1' || l.title === 'TP');

          if (entryLvl && slLvl) {{
            const entryVal = parseFloat(entryLvl.value);
            const slVal = parseFloat(slLvl.value);
            const tpVal = tpLvl ? parseFloat(tpLvl.value) : null;

            if (!isNaN(entryVal) && !isNaN(slVal) && (tpVal === null || !isNaN(tpVal))) {{
              const yEntry = candleSeries.priceToCoordinate(entryVal);
              const ySL = candleSeries.priceToCoordinate(slVal);
              const yTP = tpVal !== null ? candleSeries.priceToCoordinate(tpVal) : null;

              if (yEntry !== null && ySL !== null && drawPayload.candles && drawPayload.candles.length > 0) {{
                const lastCandle = drawPayload.candles[drawPayload.candles.length - 1];
                let xStart = chart.timeScale().timeToCoordinate(lastCandle.time);
                if (xStart === null) {{
                  xStart = overlayCanvas.width * 0.65;
                }} else {{
                  xStart = Math.max(0, xStart - 120);
                }}
                const xEnd = overlayCanvas.width;
                const isBuy = slVal < entryVal;

                ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
                ctx.strokeStyle = 'rgba(239, 68, 68, 0.35)';
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 4]);

                ctx.beginPath();
                ctx.rect(xStart, yEntry, xEnd - xStart, ySL - yEntry);
                ctx.fill();
                ctx.stroke();

                if (yTP !== null) {{
                  ctx.fillStyle = 'rgba(34, 197, 94, 0.12)';
                  ctx.strokeStyle = 'rgba(34, 197, 94, 0.35)';
                  ctx.beginPath();
                  ctx.rect(xStart, yEntry, xEnd - xStart, yTP - yEntry);
                  ctx.fill();
                  ctx.stroke();
                }}

                ctx.setLineDash([]);
                ctx.font = 'bold 12px Arial, sans-serif';

                ctx.fillStyle = '#60a5fa';
                ctx.fillText(`Entry: ${{entryVal.toFixed(5)}}`, xStart + 12, yEntry - 6);

                ctx.fillStyle = '#f87171';
                const ySLText = isBuy ? ySL - 6 : ySL + 16;
                ctx.fillText(`Stop Loss: ${{slVal.toFixed(5)}}`, xStart + 12, ySLText);

                if (yTP !== null) {{
                  ctx.fillStyle = '#4ade80';
                  const yTPText = isBuy ? yTP + 16 : yTP - 6;
                  ctx.fillText(`Target (TP): ${{tpVal.toFixed(5)}}`, xStart + 12, yTPText);
                }}
              }}
            }}
          }}

          // 4. Draw Fibonacci Levels and OTE Zone
          const fib = drawPayload.fibonacci;
          if (fib && fib.swing_high !== undefined && fib.swing_low !== undefined) {{
            const shVal = parseFloat(fib.swing_high);
            const slVal = parseFloat(fib.swing_low);
            const oteL = parseFloat(fib.ote_low);
            const oteH = parseFloat(fib.ote_high);

            // Shaded OTE Zone
            if (!isNaN(oteL) && !isNaN(oteH)) {{
              const yOteL = candleSeries.priceToCoordinate(oteL);
              const yOteH = candleSeries.priceToCoordinate(oteH);
              if (yOteL !== null && yOteH !== null) {{
                ctx.fillStyle = 'rgba(139, 92, 246, 0.15)'; 
                ctx.fillRect(0, Math.min(yOteL, yOteH), overlayCanvas.width, Math.abs(yOteH - yOteL));
                
                // Label the OTE Zone
                ctx.fillStyle = '#c084fc';
                ctx.font = 'bold 11px Arial, sans-serif';
                ctx.fillText('Optimal Trade Entry (OTE) Zone [70.5% - 78.6%]', 30, Math.min(yOteL, yOteH) + 16);
              }}
            }}

            // Draw individual levels
            const fibLevels = [
              {{ name: '0.0', key: '0.0', color: '#94a3b8' }},
              {{ name: '0.236', key: '0.236', color: '#64748b' }},
              {{ name: '0.382', key: '0.382', color: '#475569' }},
              {{ name: '0.5', key: '0.5', color: '#f59e0b' }}, // Gold for Equilibrium
              {{ name: '0.618', key: '0.618', color: '#fb923c' }}, // Golden Pocket
              {{ name: '0.705', key: '0.705', color: '#a78bfa' }}, // OTE
              {{ name: '0.786', key: '0.786', color: '#a78bfa' }}, // OTE
              {{ name: '0.886', key: '0.886', color: '#c084fc' }}, // Deep retracement
              {{ name: '1.0', key: '1.0', color: '#94a3b8' }},
              {{ name: '1.272 Ext', key: 'ext_1.272', color: '#10b981' }}, // Profit Targets
              {{ name: '1.618 Ext', key: 'ext_1.618', color: '#059669' }}
            ];

            fibLevels.forEach((lvl) => {{
              const lvlVal = parseFloat(fib[lvl.key]);
              if (!isNaN(lvlVal)) {{
                const yLvl = candleSeries.priceToCoordinate(lvlVal);
                if (yLvl !== null) {{
                  ctx.strokeStyle = lvl.color;
                  ctx.lineWidth = (lvl.key === '0.618' || lvl.key === '0.5' || lvl.key.startsWith('ote') || lvl.key.includes('0.7')) ? 1.5 : 1;
                  ctx.setLineDash([5, 5]);
                  ctx.beginPath();
                  ctx.moveTo(0, yLvl);
                  ctx.lineTo(overlayCanvas.width, yLvl);
                  ctx.stroke();
                  ctx.setLineDash([]);

                  // Label on the right
                  ctx.fillStyle = lvl.color;
                  ctx.font = '10px Arial, sans-serif';
                  ctx.fillText(`${{lvl.name}}: ${{lvlVal.toFixed(5)}}`, overlayCanvas.width - 130, yLvl - 4);
                }}
              }}
            }});
          }}
        }}

        chart.timeScale().subscribeVisibleLogicalRangeChange(updateOverlay);
        const rightScale = chart.priceScale('right');
        if (rightScale && typeof rightScale.subscribePriceRangeChange === 'function') {{
          rightScale.subscribePriceRangeChange(updateOverlay);
        }}

        const resizeObserver = new ResizeObserver(() => {{
          const w = wrapper.clientWidth || 900;
          const h = wrapper.clientHeight || 700;
          chart.resize(w, h);
          updateOverlay();
        }});
        resizeObserver.observe(wrapper);

        const refreshIntervalMs = 5000;
        window.setInterval(triggerLocalRefresh, refreshIntervalMs);
        chart.timeScale().fitContent();
        setTimeout(updateOverlay, 300);
      </script>
    </div>
    """
    components.html(html, height=768)


def render_svg_chart(symbol, timeframe, bundle):
    panel_payload = build_trade_panel_payload(bundle)
    draw_payload = build_chart_draw_payload(bundle)
    panel_json = json.dumps(panel_payload)
    draw_json = json.dumps(draw_payload)
    container_id = f"svg_chart_{symbol}_{timeframe}".replace(":", "_")
    panel_id = f"svg_panel_{symbol}_{timeframe}".replace(":", "_")

    html = f"""
    <div id="{container_id}_wrapper" style="height:760px;width:100%;position:relative;border:1px solid rgba(148,163,184,0.35);border-radius:22px;overflow:hidden;background:#ffffff;">
      <style>
        @keyframes spin {{
          0% {{ transform: rotate(0deg); }}
          100% {{ transform: rotate(360deg); }}
        }}
        .spinning {{
          display: inline-block !important;
          animation: spin 1s linear infinite;
        }}
        #{panel_id}::-webkit-resizer {{
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><path d="M10,0 L0,10 M10,3 L3,10 M10,6 L6,10" stroke="rgba(255,255,255,0.6)" stroke-width="1.5" stroke-linecap="round"/></svg>');
          background-repeat: no-repeat;
          background-position: bottom right;
          width: 14px;
          height: 14px;
        }}
      </style>
      <div style="position:absolute;top:14px;right:14px;z-index:8;display:flex;gap:8px;">
        <button type="button" id="{container_id}_fullscreen" style="border:none;border-radius:999px;padding:10px 14px;background:rgba(15,23,42,0.88);color:#fff;font-weight:700;cursor:pointer;">Fullscreen</button>
      </div>
      <div id="{panel_id}" style="position:absolute;top:18px;left:18px;width:340px;height:440px;min-width:260px;min-height:200px;resize:both;overflow:auto;z-index:9;border-radius:24px;background:linear-gradient(180deg, rgba(15,23,42,0.86), rgba(30,41,59,0.82));color:#f8fafc;border:1px solid rgba(148,163,184,0.28);box-shadow:0 25px 50px rgba(15,23,42,0.35);font-family:Arial,sans-serif;backdrop-filter:blur(10px);"></div>
      <div id="{container_id}" style="height:100%;width:100%;"></div>
      <script>
        const panelPayload = {panel_json};
        const drawPayload = {draw_json};
        const wrapper = document.getElementById("{container_id}_wrapper");
        const panel = document.getElementById("{panel_id}");
        const chartRoot = document.getElementById("{container_id}");

        let statusColor = "#22c55e";
        let signalBg = "rgba(34, 197, 94, 0.25)";
        let headerGradient = "linear-gradient(135deg, rgba(20,184,166,0.55), rgba(37,99,235,0.42))";

        if (panelPayload.signal === "TRADE_REMOVED") {{
          statusColor = "#ef4444";
          signalBg = "rgba(239, 68, 68, 0.35)";
          headerGradient = "linear-gradient(135deg, rgba(239, 68, 68, 0.6), rgba(220, 38, 38, 0.5))";
        }} else if (panelPayload.signal.includes("BUY")) {{
          statusColor = "#22c55e";
          signalBg = "rgba(34, 197, 94, 0.35)";
          headerGradient = "linear-gradient(135deg, rgba(16, 185, 129, 0.6), rgba(5, 150, 105, 0.5))";
        }} else if (panelPayload.signal.includes("SELL")) {{
          statusColor = "#f97316";
          signalBg = "rgba(249, 115, 22, 0.35)";
          headerGradient = "linear-gradient(135deg, rgba(249, 115, 22, 0.6), rgba(234, 88, 12, 0.5))";
        }} else {{
          statusColor = "#94a3b8";
          signalBg = "rgba(148, 163, 184, 0.25)";
          headerGradient = "linear-gradient(135deg, rgba(100, 116, 139, 0.55), rgba(71, 85, 105, 0.42))";
        }}

        panel.innerHTML = `
          <div id="{panel_id}_drag" style="padding:14px 16px;background:${{headerGradient}};font-size:16px;font-weight:700;position:sticky;top:0;display:flex;justify-content:space-between;align-items:center;cursor:move;user-select:none;border-top-left-radius:24px;border-top-right-radius:24px;">
            <span style="display:flex;align-items:center;gap:6px;">
              <span style="width:8px;height:8px;border-radius:50%;background:${{statusColor}};display:inline-block;box-shadow:0 0 8px ${{statusColor}};"></span>
              Trading Panel
            </span>
            <div style="display:flex;gap:6px;align-items:center;">
              <button type="button" id="{panel_id}_refresh" style="border:none;background:rgba(255,255,255,0.16);color:#fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:12px;transition:background 0.2s;" title="Refresh Panel">🔄</button>
            </div>
          </div>
          <div id="{panel_id}_content" style="padding:16px;">
            <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">
              <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:${{signalBg}};">${{panelPayload.signal}}</span>
              <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{panelPayload.confidence}}</span>
              <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{panelPayload.status}}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px;">
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Symbol</div><div style="font-size:15px;font-weight:700;">${{panelPayload.symbol}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Timeframe</div><div style="font-size:15px;font-weight:700;">${{panelPayload.timeframe}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Entry</div><div style="font-size:15px;font-weight:700;">${{panelPayload.entry}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Stop Loss</div><div style="font-size:15px;font-weight:700;">${{panelPayload.stop_loss}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 1</div><div style="font-size:15px;font-weight:700;">${{panelPayload.tp1}}</div></div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 2</div><div style="font-size:15px;font-weight:700;">${{panelPayload.tp2}}</div></div>
            </div>
            <div style="display:grid;gap:8px;">
              <div style="padding:10px 12px;border-radius:16px;background:rgba(37,99,235,0.16);border:1px solid rgba(96,165,250,0.35);">
                <div style="font-size:11px;color:#bfdbfe;margin-bottom:4px;">Candle Pattern</div>
                <div style="font-size:14px;font-weight:700;color:#eff6ff;">${{panelPayload.pattern}}</div>
              </div>
              <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);">
                <div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Structure</div>
                <div style="font-size:13px;font-weight:700;">Trend: ${{panelPayload.trend}}</div>
                <div style="font-size:13px;font-weight:700;">Phase: ${{panelPayload.phase}}</div>
                <div style="font-size:13px;font-weight:700;">BOS / CHOCH: ${{panelPayload.bos}} / ${{panelPayload.choch}}</div>
              </div>
            </div>
          </div>`;

        const updatePanelContent = (data) => {{
          let statusColor = "#22c55e";
          let signalBg = "rgba(34, 197, 94, 0.25)";
          let headerGradient = "linear-gradient(135deg, rgba(20,184,166,0.55), rgba(37,99,235,0.42))";

          if (data.signal === "TRADE_REMOVED") {{
            statusColor = "#ef4444";
            signalBg = "rgba(239, 68, 68, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(239, 68, 68, 0.6), rgba(220, 38, 38, 0.5))";
          }} else if (data.signal.includes("BUY")) {{
            statusColor = "#22c55e";
            signalBg = "rgba(34, 197, 94, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(16, 185, 129, 0.6), rgba(5, 150, 105, 0.5))";
          }} else if (data.signal.includes("SELL")) {{
            statusColor = "#f97316";
            signalBg = "rgba(249, 115, 22, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(249, 115, 22, 0.6), rgba(234, 88, 12, 0.5))";
          }} else {{
            statusColor = "#94a3b8";
            signalBg = "rgba(148, 163, 184, 0.25)";
            headerGradient = "linear-gradient(135deg, rgba(100, 116, 139, 0.55), rgba(71, 85, 105, 0.42))";
          }}

          const dragHeader = document.getElementById("{panel_id}_drag");
          if (dragHeader) {{
            dragHeader.style.background = headerGradient;
          }}
          const statusDot = dragHeader ? dragHeader.querySelector('span > span') : null;
          if (statusDot) {{
            statusDot.style.background = statusColor;
            statusDot.style.boxShadow = `0 0 8px ${{statusColor}}`;
          }}

          const contentDiv = document.getElementById("{panel_id}_content");
          if (contentDiv) {{
            contentDiv.innerHTML = `
              <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:${{signalBg}};">${{data.signal}}</span>
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{data.confidence}}</span>
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">${{data.status}}</span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px;">
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Symbol</div><div style="font-size:15px;font-weight:700;">${{data.symbol}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Timeframe</div><div style="font-size:15px;font-weight:700;">${{data.timeframe}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Entry</div><div style="font-size:15px;font-weight:700;">${{data.entry}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Stop Loss</div><div style="font-size:15px;font-weight:700;">${{data.stop_loss}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 1</div><div style="font-size:15px;font-weight:700;">${{data.tp1}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 2</div><div style="font-size:15px;font-weight:700;">${{data.tp2}}</div></div>
              </div>
              <div style="display:grid;gap:8px;">
                <div style="padding:10px 12px;border-radius:16px;background:rgba(37,99,235,0.16);border:1px solid rgba(96,165,250,0.35);">
                  <div style="font-size:11px;color:#bfdbfe;margin-bottom:4px;">Candle Pattern</div>
                  <div style="font-size:14px;font-weight:700;color:#eff6ff;">${{data.pattern}}</div>
                </div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Structure</div>
                  <div style="font-size:13px;font-weight:700;">Trend: ${{data.trend}}</div>
                  <div style="font-size:13px;font-weight:700;">Phase: ${{data.phase}}</div>
                  <div style="font-size:13px;font-weight:700;">BOS / CHOCH: ${{data.bos}} / ${{data.choch}}</div>
                </div>
              </div>
            `;
          }}
        }};

        const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({{
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
        }})[ch]);

        const renderSvgChart = () => {{
          const candles = drawPayload.candles || [];
          if (!candles.length) {{
            chartRoot.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#64748b;font:600 15px Arial,sans-serif;">No chart data available.</div>';
            return;
          }}

          const width = Math.max(chartRoot.clientWidth || 900, 900);
          const height = Math.max(chartRoot.clientHeight || 700, 700);
          const leftPad = 78;
          const rightPad = 88;
          const topPad = 36;
          const bottomPad = 70;
          const plotWidth = width - leftPad - rightPad;
          const plotHeight = height - topPad - bottomPad;
          const prices = candles.flatMap((c) => [c.high, c.low]);
          (drawPayload.levels || []).forEach((l) => prices.push(l.value));
          (drawPayload.zone_lines || []).forEach((l) => prices.push(l.value));
          (drawPayload.trendlines || []).forEach((line) => (line.points || []).forEach((p) => prices.push(p.value)));
          const minPrice = Math.min(...prices);
          const maxPrice = Math.max(...prices);
          const priceRange = Math.max(maxPrice - minPrice, 1);
          const candleSpace = plotWidth / candles.length;
          const candleBody = Math.max(4, Math.min(12, candleSpace * 0.6));
          const timeLookup = new Map(candles.map((c, idx) => [c.time, idx]));

          const xForIndex = (idx) => leftPad + (idx + 0.5) * candleSpace;
          const xForTime = (time) => xForIndex(timeLookup.has(time) ? timeLookup.get(time) : candles.length - 1);
          const yForPrice = (price) => topPad + ((maxPrice - price) / priceRange) * plotHeight;

          let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="100%" preserveAspectRatio="none" style="display:block;background:#ffffff;font-family:Arial,sans-serif;">`;
          svg += `<rect x="0" y="0" width="${{width}}" height="${{height}}" fill="#ffffff" />`;

          for (let i = 0; i <= 5; i += 1) {{
            const y = topPad + (plotHeight / 5) * i;
            const price = maxPrice - (priceRange / 5) * i;
            svg += `<line x1="${{leftPad}}" y1="${{y}}" x2="${{width - rightPad}}" y2="${{y}}" stroke="rgba(148,163,184,0.28)" stroke-width="1" />`;
            svg += `<text x="${{width - rightPad + 10}}" y="${{y + 4}}" fill="#475569" font-size="12">${{price.toFixed(2)}}</text>`;
          }}

          const tickCount = Math.min(8, candles.length);
          for (let i = 0; i < tickCount; i += 1) {{
            const idx = Math.min(candles.length - 1, Math.round((candles.length - 1) * (i / Math.max(tickCount - 1, 1))));
            const candle = candles[idx];
            const x = xForIndex(idx);
            const label = new Date(candle.time * 1000).toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
            svg += `<line x1="${{x}}" y1="${{topPad}}" x2="${{x}}" y2="${{topPad + plotHeight}}" stroke="rgba(148,163,184,0.18)" stroke-width="1" />`;
            svg += `<text x="${{x}}" y="${{height - 28}}" fill="#475569" font-size="12" text-anchor="middle">${{escapeHtml(label)}}</text>`;
          }}

          candles.forEach((candle, idx) => {{
            const x = xForIndex(idx);
            const openY = yForPrice(candle.open);
            const closeY = yForPrice(candle.close);
            const highY = yForPrice(candle.high);
            const lowY = yForPrice(candle.low);
            const color = candle.close >= candle.open ? '#16a34a' : '#dc2626';
            const bodyY = Math.min(openY, closeY);
            const bodyHeight = Math.max(2, Math.abs(closeY - openY));
            svg += `<line x1="${{x}}" y1="${{highY}}" x2="${{x}}" y2="${{lowY}}" stroke="${{color}}" stroke-width="1.5" />`;
            svg += `<rect x="${{x - candleBody / 2}}" y="${{bodyY}}" width="${{candleBody}}" height="${{bodyHeight}}" fill="${{color}}" rx="1.5" />`;
          }});

          (drawPayload.zone_lines || []).forEach((line) => {{
            const y = yForPrice(line.value);
            svg += `<line x1="${{leftPad}}" y1="${{y}}" x2="${{width - rightPad}}" y2="${{y}}" stroke="${{line.color}}" stroke-width="1" stroke-dasharray="4 5" opacity="0.6" />`;
          }});

          (drawPayload.levels || []).forEach((line) => {{
            const y = yForPrice(line.value);
            svg += `<line x1="${{leftPad}}" y1="${{y}}" x2="${{width - rightPad}}" y2="${{y}}" stroke="${{line.color}}" stroke-width="2" stroke-dasharray="8 6" />`;
            svg += `<rect x="${{width - rightPad + 8}}" y="${{y - 11}}" width="52" height="20" rx="10" fill="${{line.color}}" />`;
            svg += `<text x="${{width - rightPad + 34}}" y="${{y + 4}}" fill="#ffffff" font-size="11" font-weight="700" text-anchor="middle">${{escapeHtml(line.title)}}</text>`;
          }});

          (drawPayload.trendlines || []).forEach((line) => {{
            const points = (line.points || []).map((point) => `${{xForTime(point.time)}},${{yForPrice(point.value)}}`).join(' ');
            if (points) {{
              svg += `<polyline points="${{points}}" fill="none" stroke="${{line.color}}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />`;
            }}
          }});

          const markers = [].concat(drawPayload.pattern_markers || []).concat(drawPayload.structure_labels || []);
          markers.forEach((marker) => {{
            const idx = timeLookup.has(marker.time) ? timeLookup.get(marker.time) : candles.length - 1;
            const candle = candles[idx];
            const x = xForIndex(idx);
            const basePrice = marker.position === 'belowBar' ? candle.low : candle.high;
            const y = yForPrice(basePrice) + (marker.position === 'belowBar' ? 22 : -22);
            svg += `<circle cx="${{x}}" cy="${{y}}" r="8" fill="${{marker.color || '#334155'}}" />`;
            svg += `<text x="${{x}}" y="${{y + 4}}" fill="#ffffff" font-size="9" font-weight="700" text-anchor="middle">${{escapeHtml(marker.text || '')}}</text>`;
          }});

          svg += `<text x="${{leftPad}}" y="22" fill="#0f172a" font-size="16" font-weight="700">${{escapeHtml(panelPayload.symbol)}} · ${{escapeHtml(panelPayload.timeframe)}}m</text>`;
          svg += `</svg>`;
          chartRoot.innerHTML = svg;
        }};

        const triggerLocalRefresh = () => {{
          const refreshBtn = document.getElementById('{panel_id}_refresh');
          if (refreshBtn) {{
            refreshBtn.classList.add('spinning');
            refreshBtn.disabled = true;
          }}

          fetch(`http://127.0.0.1:8505/refresh?symbol=${{encodeURIComponent(panelPayload.symbol)}}&timeframe=${{encodeURIComponent(panelPayload.timeframe)}}`)
            .then(res => res.json())
            .then(data => {{
              if (data && !data.error) {{
                updatePanelContent(data);
              }} else {{
                console.error("Refresh error:", data ? data.error : "empty response");
              }}
            }})
            .catch(err => {{
              console.error("Fetch failed:", err);
            }})
            .finally(() => {{
              if (refreshBtn) {{
                refreshBtn.classList.remove('spinning');
                refreshBtn.disabled = false;
              }}
            }});
        }};

        document.getElementById('{panel_id}_refresh').onclick = triggerLocalRefresh;
        document.getElementById('{container_id}_fullscreen').onclick = () => {{
          if (!document.fullscreenElement) {{
            wrapper.requestFullscreen();
          }} else {{
            document.exitFullscreen();
          }}
        }};

        document.addEventListener('fullscreenchange', () => {{
          renderSvgChart();
        }});
        window.addEventListener('resize', renderSvgChart);

        let dragging = false;
        let offsetX = 0;
        let offsetY = 0;
        const dragHandle = document.getElementById('{panel_id}_drag');
        dragHandle.addEventListener('mousedown', (event) => {{
          dragging = true;
          const rect = panel.getBoundingClientRect();
          offsetX = event.clientX - rect.left;
          offsetY = event.clientY - rect.top;
          event.preventDefault();
        }});
        document.addEventListener('mousemove', (event) => {{
          if (!dragging) return;
          const wrapRect = wrapper.getBoundingClientRect();
          panel.style.left = `${{Math.max(12, event.clientX - wrapRect.left - offsetX)}}px`;
          panel.style.top = `${{Math.max(12, event.clientY - wrapRect.top - offsetY)}}px`;
        }});
        document.addEventListener('mouseup', () => {{
          dragging = false;
        }});

        window.setInterval(triggerLocalRefresh, 5000);
        renderSvgChart();
      </script>
    </div>
    """
    components.html(html, height=768)


def render_tradingview_widget(symbol, timeframe, bundle):
    tv_symbol = get_tradingview_symbol(symbol)
    tv_interval = get_tradingview_interval(timeframe)
    container_id = f"tv_chart_clean_{symbol}_{timeframe}".replace(":", "_")
    panel_id = f"tv_panel_clean_{symbol}_{timeframe}".replace(":", "_")
    session_id = st.session_state.session_uuid

    html = f"""
    <div id="{container_id}_shell" style="height:760px;width:100%;position:relative;border:1px solid rgba(148,163,184,0.35);border-radius:22px;overflow:hidden;background:#ffffff;">
      <style>
        @keyframes spin {{
          0% {{ transform: rotate(0deg); }}
          100% {{ transform: rotate(360deg); }}
        }}
        .spinning {{
          display: inline-block !important;
          animation: spin 1s linear infinite;
        }}
        #{panel_id}::-webkit-resizer {{
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><path d="M10,0 L0,10 M10,3 L3,10 M10,6 L6,10" stroke="rgba(255,255,255,0.6)" stroke-width="1.5" stroke-linecap="round"/></svg>');
          background-repeat: no-repeat;
          background-position: bottom right;
          width: 14px;
          height: 14px;
        }}
      </style>
      <div style="position:absolute;top:14px;right:14px;z-index:8;display:flex;gap:10px;align-items:center;">
        <div id="news_badge_container">
          <div style="padding:10px 14px;background:#22c55e;color:#fff;font-weight:700;border-radius:999px;font-size:13px;box-shadow:0 4px 12px rgba(34,197,94,0.2);display:flex;align-items:center;gap:6px;font-family:Arial,sans-serif;">
            <span>🟢 News Clear</span>
          </div>
        </div>
        <button type="button" id="{container_id}_fullscreen" style="border:none;border-radius:999px;padding:10px 14px;background:rgba(15,23,42,0.88);color:#fff;font-weight:700;cursor:pointer;">Fullscreen</button>
      </div>
      <div id="{panel_id}" style="position:absolute;top:18px;left:18px;width:340px;height:440px;min-width:260px;min-height:200px;resize:both;overflow:auto;z-index:9;border-radius:24px;background:linear-gradient(180deg, rgba(15,23,42,0.86), rgba(30,41,59,0.82));color:#f8fafc;border:1px solid rgba(148,163,184,0.28);box-shadow:0 25px 50px rgba(15,23,42,0.35);font-family:Arial,sans-serif;backdrop-filter:blur(10px);"></div>
      <div id="{container_id}" style="height:100%;width:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        const shell = document.getElementById("{container_id}_shell");
        const chartNode = document.getElementById("{container_id}");
        const panel = document.getElementById("{panel_id}");
        const fullscreenButton = document.getElementById("{container_id}_fullscreen");

        let statusColor = "#94a3b8";
        let signalBg = "rgba(148, 163, 184, 0.25)";
        let headerGradient = "linear-gradient(135deg, rgba(100, 116, 139, 0.55), rgba(71, 85, 105, 0.42))";

        panel.innerHTML = `
          <div id="{panel_id}_drag" style="padding:12px 16px;background:\${{headerGradient}};font-size:16px;font-weight:700;position:sticky;top:0;display:flex;justify-content:space-between;align-items:center;cursor:move;user-select:none;border-top-left-radius:24px;border-top-right-radius:24px;">
            <span style="display:flex;align-items:center;gap:6px;">
              <span style="width:8px;height:8px;border-radius:50%;background:\${{statusColor}};display:inline-block;box-shadow:0 0 8px \${{statusColor}};"></span>
              Trading Panel
            </span>
            <div style="display:flex;gap:6px;align-items:center;">
              <button type="button" id="{panel_id}_minimise" style="border:none;background:rgba(255,255,255,0.16);color:#fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-weight:700;font-size:14px;transition:background 0.2s;">−</button>
            </div>
          </div>
          <div id="{panel_id}_content" style="padding:16px;">
            <div style="color:#cbd5e1;font-size:14px;font-weight:600;">Connecting to Live Analysis Engine...</div>
          </div>
        `;

        const showError = (message) => {{
          chartNode.innerHTML = `<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#64748b;font:600 15px Arial,sans-serif;">\${{message}}</div>`;
        }};

        const updatePanelContent = (data) => {{
          let statusColor = "#22c55e";
          let signalBg = "rgba(34, 197, 94, 0.25)";
          let headerGradient = "linear-gradient(135deg, rgba(20,184,166,0.55), rgba(37,99,235,0.42))";

          if (data.signal === "TRADE_REMOVED") {{
            statusColor = "#ef4444";
            signalBg = "rgba(239, 68, 68, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(239, 68, 68, 0.6), rgba(220, 38, 38, 0.5))";
          }} else if (data.signal.includes("BUY")) {{
            statusColor = "#22c55e";
            signalBg = "rgba(34, 197, 94, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(16, 185, 129, 0.6), rgba(5, 150, 105, 0.5))";
          }} else if (data.signal.includes("SELL")) {{
            statusColor = "#f97316";
            signalBg = "rgba(249, 115, 22, 0.35)";
            headerGradient = "linear-gradient(135deg, rgba(249, 115, 22, 0.6), rgba(234, 88, 12, 0.5))";
          }} else {{
            statusColor = "#94a3b8";
            signalBg = "rgba(148, 163, 184, 0.25)";
            headerGradient = "linear-gradient(135deg, rgba(100, 116, 139, 0.55), rgba(71, 85, 105, 0.42))";
          }}

          const dragHeader = document.getElementById("{panel_id}_drag");
          if (dragHeader) {{
            dragHeader.style.background = headerGradient;
          }}
          const statusDot = dragHeader ? dragHeader.querySelector('span > span') : null;
          if (statusDot) {{
            statusDot.style.background = statusColor;
            statusDot.style.boxShadow = `0 0 8px \${{statusColor}}`;
          }}

          const contentDiv = document.getElementById("{panel_id}_content");
          if (contentDiv) {{
            contentDiv.innerHTML = `
              <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:\${{signalBg}};">\${{data.signal}}</span>
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">\${{data.confidence}}</span>
                <span style="padding:7px 10px;border-radius:999px;font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);">\${{data.status}}</span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px;">
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Symbol</div><div style="font-size:15px;font-weight:700;">\${{data.symbol}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Timeframe</div><div style="font-size:15px;font-weight:700;">\${{data.timeframe}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Entry</div><div style="font-size:15px;font-weight:700;">\${{data.entry}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Stop Loss</div><div style="font-size:15px;font-weight:700;">\${{data.stop_loss}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 1</div><div style="font-size:15px;font-weight:700;">\${{data.tp1}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 2</div><div style="font-size:15px;font-weight:700;">\${{data.tp2}}</div></div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);"><div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Take Profit 3</div><div style="font-size:15px;font-weight:700;">\${{data.tp3}}</div></div>
              </div>
              <div style="display:grid;gap:8px;">
                <div style="padding:10px 12px;border-radius:16px;background:rgba(37,99,235,0.16);border:1px solid rgba(96,165,250,0.35);">
                  <div style="font-size:11px;color:#bfdbfe;margin-bottom:4px;">Candle Pattern</div>
                  <div style="font-size:14px;font-weight:700;color:#eff6ff;">\${{data.pattern}}</div>
                </div>
                <div style="padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.08);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:11px;color:#cbd5e1;margin-bottom:4px;">Structure</div>
                  <div style="font-size:13px;font-weight:700;">Trend: \${{data.trend}}</div>
                  <div style="font-size:13px;font-weight:700;">Phase: \${{data.phase}}</div>
                  <div style="font-size:13px;font-weight:700;">BOS / CHOCH: \${{data.bos}} / \${{data.choch}}</div>
                </div>
              </div>
            `;
          }}
        }};

        const updateNewsBadge = (newsText) => {{
          const badgeContainer = document.getElementById("news_badge_container");
          if (!badgeContainer) return;
          if (newsText) {{
            badgeContainer.innerHTML = `
              <div style="padding:10px 14px;background:#ef4444;color:#fff;font-weight:700;border-radius:999px;font-size:13px;box-shadow:0 4px 12px rgba(239,68,68,0.3);display:flex;align-items:center;gap:6px;font-family:Arial,sans-serif;">
                <span style="width:8px;height:8px;border-radius:50%;background:#fff;display:inline-block;"></span>
                <span>⚠️ \${{newsText}}</span>
              </div>
            `;
          }} else {{
            badgeContainer.innerHTML = `
              <div style="padding:10px 14px;background:#22c55e;color:#fff;font-weight:700;border-radius:999px;font-size:13px;box-shadow:0 4px 12px rgba(34,197,94,0.2);display:flex;align-items:center;gap:6px;font-family:Arial,sans-serif;">
                <span>🟢 News Clear</span>
              </div>
            `;
          }}
        }};

        const mountWidget = () => {{
          if (!window.TradingView) {{
            showError("TradingView failed to load.");
            return;
          }}

          chartNode.innerHTML = "";
          new window.TradingView.widget({{
            autosize: true,
            symbol: "{tv_symbol}",
            interval: "{tv_interval}",
            timezone: "Asia/Kolkata",
            theme: "dark",
            style: "1",
            locale: "en",
            withdateranges: true,
            hide_side_toolbar: false,
            hide_top_toolbar: false,
            allow_symbol_change: false,
            details: true,
            hotlist: false,
            calendar: false,
            studies: [],
            container_id: "{container_id}"
          }});
        }};

        fullscreenButton.onclick = () => {{
          if (!document.fullscreenElement) {{
            shell.requestFullscreen();
          }} else {{
            document.exitFullscreen();
          }}
        }};

        // Connect WebSocket client
        const connectWs = () => {{
          const wsUrl = `ws://127.0.0.1:8505/ws?symbol=\${{encodeURIComponent("{symbol}")}}&timeframe=\${{encodeURIComponent("{timeframe}")}}&session_id=\${{encodeURIComponent("{session_id}")}}`;
          const socket = new WebSocket(wsUrl);

          socket.onmessage = function(event) {{
            try {{
              const data = JSON.parse(event.data);
              if (data && data.panelPayload) {{
                updatePanelContent(data.panelPayload);
                updateNewsBadge(data.newsCountdown);
              }}
            }} catch (e) {{
              console.error("Error parsing ws update:", e);
            }}
          }};

          socket.onclose = function() {{
            console.log("WebSocket closed, retrying in 2 seconds...");
            setTimeout(connectWs, 2000);
          }};

          socket.onerror = function() {{
            socket.close();
          }};
        }};

        connectWs();

        // Minimise functionality
        const minimiseBtn = document.getElementById("{panel_id}_minimise");
        const panelContent = document.getElementById("{panel_id}_content");
        let isMinimised = false;
        let originalHeight = "440px";

        minimiseBtn.onclick = (e) => {{
          e.stopPropagation();
          isMinimised = !isMinimised;
          if (isMinimised) {{
            originalHeight = panel.style.height || "440px";
            panelContent.style.display = "none";
            panel.style.height = "48px";
            panel.style.minHeight = "48px";
            panel.style.resize = "none";
            minimiseBtn.innerText = "+";
            minimiseBtn.style.background = "rgba(255,255,255,0.3)";
          }} else {{
            panelContent.style.display = "block";
            panel.style.height = originalHeight;
            panel.style.minHeight = "200px";
            panel.style.resize = "both";
            minimiseBtn.innerText = "−";
            minimiseBtn.style.background = "rgba(255,255,255,0.16)";
          }}
        }};

        // Draggable functionality with boundaries
        let dragging = false;
        let offsetX = 0;
        let offsetY = 0;
        const dragHandle = document.getElementById("{panel_id}_drag");
        dragHandle.addEventListener('mousedown', (event) => {{
          dragging = true;
          const rect = panel.getBoundingClientRect();
          offsetX = event.clientX - rect.left;
          offsetY = event.clientY - rect.top;
          event.preventDefault();
        }});
        document.addEventListener('mousemove', (event) => {{
          if (!dragging) return;
          const wrapRect = shell.getBoundingClientRect();
          const maxLeft = wrapRect.width - panel.offsetWidth - 12;
          const maxTop = wrapRect.height - panel.offsetHeight - 12;
          panel.style.left = `${{Math.min(Math.max(12, event.clientX - wrapRect.left - offsetX), maxLeft)}}px`;
          panel.style.top = `${{Math.min(Math.max(12, event.clientY - wrapRect.top - offsetY), maxTop)}}px`;
        }});
        document.addEventListener('mouseup', () => {{
          dragging = false;
        }});

        let attempts = 0;
        const loader = window.setInterval(() => {{
          attempts += 1;
          if (window.TradingView) {{
            window.clearInterval(loader);
            mountWidget();
          }} else if (attempts >= 40) {{
            window.clearInterval(loader);
            showError("TradingView failed to load.");
          }}
        }}, 250);
      </script>
    </div>
    """
    components.html(html, height=768)


def _conf_gauge_html(confidence: float, height: str = "8px", font_size: str = "13px") -> str:
    """Return an animated confidence bar + numeric label as raw HTML."""
    pct   = min(max(float(confidence), 0), 100)
    color = ("#16a34a" if pct >= 70 else ("#f59e0b" if pct >= 45 else "#dc2626"))
    label_color = color
    html = f"""
    <div style='display:flex;align-items:center;gap:8px;'>
      <div style='flex:1;background:rgba(148,163,184,0.18);border-radius:999px;height:{height};overflow:hidden;'>
        <div style='width:{pct:.1f}%;height:100%;background:{color};border-radius:999px;
                    transition:width 0.6s cubic-bezier(.4,0,.2,1);'></div>
      </div>
      <span style='font-size:{font_size};font-weight:800;color:{label_color};min-width:42px;text-align:right;'>{pct:.1f}%</span>
    </div>
    """
    return "\n".join(line.strip() for line in html.splitlines())


def render_metric_strip(bundle):
    structure  = bundle.chart_payload.get("overlays", {}).get("structure", {})
    conf       = float(bundle.signal.confidence)
    conf_color = "#16a34a" if conf >= 70 else ("#f59e0b" if conf >= 45 else "#dc2626")
    conf_pct   = min(max(conf, 0), 100)

    signal_val = bundle.signal.signal
    sig_color  = {"BUY": "#16a34a", "STRONG_BUY": "#15803d",
                  "SELL": "#dc2626", "STRONG_SELL": "#b91c1c"}.get(signal_val, "#475569")

    trend_val  = structure.get("trend", "n/a")
    trend_col  = "#16a34a" if trend_val == "bullish" else ("#dc2626" if trend_val == "bearish" else "#64748b")
    sync_val   = bundle.sync.match_percentage
    sync_col   = "#16a34a" if sync_val >= 80 else ("#f59e0b" if sync_val >= 50 else "#dc2626")

    # Count MTF alignment
    align_count = 0
    total_tf_count = 0
    primary_dir = "BUY" if "BUY" in signal_val else "SELL" if "SELL" in signal_val else None
    display_dir = primary_dir
    if not display_dir and trend_val in ["bullish", "bearish"]:
        display_dir = "BUY" if trend_val == "bullish" else "SELL"
    
    if display_dir and bundle.mtf_analysis:
        for tf, tf_data in bundle.mtf_analysis.items():
            if tf in ["5", "15", "60", "240", "D"]:
                total_tf_count += 1
                trend = tf_data.get("trend")
                if display_dir == "BUY" and trend == "bullish":
                    align_count += 1
                elif display_dir == "SELL" and trend == "bearish":
                    align_count += 1
                    
    mtf_text = "--"
    mtf_color = "#64748b"
    if display_dir:
        mtf_text = f"{align_count}/{total_tf_count} Aligned"
        mtf_color = "#16a34a" if align_count >= 4 else ("#f59e0b" if align_count == 3 else "#dc2626")
        
    mtf_badge_card = f'<div class="metric-card"><div class="metric-label">MTF Alignment</div><div class="metric-value" style="color:{mtf_color};">{mtf_text}</div></div>'

    # Build the confidence gauge cell separately
    conf_gauge = f"""
    <div class="metric-card">
      <div class="metric-label">Confidence</div>
      <div style='margin-top:6px;'>
        <div style='background:rgba(148,163,184,0.18);border-radius:999px;height:10px;overflow:hidden;'>
          <div style='width:{conf_pct:.1f}%;height:100%;background:{conf_color};border-radius:999px;
                      transition:width 0.6s cubic-bezier(.4,0,.2,1);'></div>
        </div>
        <div style='margin-top:5px;font-size:20px;font-weight:900;color:{conf_color};letter-spacing:-.5px;'>{conf_pct:.1f}%</div>
      </div>
    </div>
    """

    other_cards = [
        f'<div class="metric-card"><div class="metric-label">Signal</div><div class="metric-value" style="color:{sig_color};">{signal_val}</div></div>',
        conf_gauge,
        mtf_badge_card,
        f'<div class="metric-card"><div class="metric-label">Trend</div><div class="metric-value" style="color:{trend_col};">{trend_val.upper() if trend_val != "n/a" else "N/A"}</div></div>',
        f'<div class="metric-card"><div class="metric-label">Phase</div><div class="metric-value">{structure.get("phase", "n/a").title()}</div></div>',
        f'<div class="metric-card"><div class="metric-label">Sync</div><div class="metric-value" style="color:{sync_col};">{sync_val}%</div></div>',
        f'<div class="metric-card"><div class="metric-label">BOS / CHOCH</div><div class="metric-value" style="font-size:12px;">{structure.get("bos") or "none"} / {structure.get("choch") or "none"}</div></div>',
    ]
    st.markdown(f'<div class="metric-strip">{"".join(other_cards)}</div>', unsafe_allow_html=True)


def build_structure_tables(bundle):
    structure = bundle.chart_payload.get("overlays", {}).get("structure", {})
    swing_rows = []
    for group_name, points in (structure.get("swing_points") or {}).items():
        for point in points:
            swing_rows.append(
                {
                    "Point": point.get("label"),
                    "Timestamp": point.get("timestamp"),
                    "Price": point.get("price"),
                    "Family": group_name.upper(),
                }
            )
    imbalance_rows = []
    for imbalance in bundle.chart_payload.get("overlays", {}).get("imbalances") or []:
        imbalance_rows.append(
            {
                "Type": imbalance.get("type"),
                "Start": imbalance.get("start_timestamp"),
                "End": imbalance.get("end_timestamp"),
                "Low": imbalance.get("low"),
                "High": imbalance.get("high"),
                "AVG": imbalance.get("avg"),
                "Size": imbalance.get("size"),
            }
        )
    return pd.DataFrame(swing_rows), pd.DataFrame(imbalance_rows)


st.set_page_config(page_title="AI Trading Platform", layout="wide")
init_session_state()
inject_styles()

st.title("AI Trading Platform")
st.caption("TradingView-only workspace with local rule-based analysis and chart overlays.")

import http.server
import socketserver
import threading
import urllib.parse

# Starlette Live Engine API integration is used instead of http.server

from backend.live_analysis_engine import start_engine_api_server, live_analysis_manager

@st.cache_resource
def start_panel_api_server():
    container = _get_container_v2()
    orch = container["analysis_orchestrator"]
    return start_engine_api_server(orch)

@st.cache_resource
def _get_container_v2():
    return build_container()

container = _get_container_v2()
orchestrator = container["analysis_orchestrator"]
signal_repository = container["signal_repository"]
news_signal_repository = container.get("news_signal_repository")
forex_factory_feed = container.get("forex_factory_feed")

start_panel_api_server()

def adjust_live_engine_config(symbol, timeframe):
    """
    Dynamically auto-adjusts Live Engine parameters (refresh_sec, pips_thresh, trigger_mode)
    based on timeframe, volatility (ATR), trading session activity, and news releases.
    Runs silently in the background.
    """
    from datetime import datetime, timezone
    
    # Timeframe base configurations
    tf_configs = {
        "1": {"refresh": 2, "pips": 1.0},
        "5": {"refresh": 4, "pips": 1.5},
        "15": {"refresh": 8, "pips": 2.5},
        "30": {"refresh": 12, "pips": 4.0},
        "60": {"refresh": 15, "pips": 6.0},
        "1H": {"refresh": 15, "pips": 6.0},
        "240": {"refresh": 30, "pips": 12.0},
        "4H": {"refresh": 30, "pips": 12.0},
        "D": {"refresh": 60, "pips": 25.0},
        "1440": {"refresh": 60, "pips": 25.0},
    }
    
    config = tf_configs.get(timeframe, {"refresh": 5, "pips": 2.0})
    refresh_sec = config["refresh"]
    pips_thresh = config["pips"]
    trigger_mode = "Hybrid (Smart Triggers)"
    
    # ATR Volatility adaptation
    bundle = st.session_state.get("analysis_bundle")
    pip_size = 0.0001
    if symbol == "XAUUSD" or "JPY" in symbol or "BTC" in symbol:
        pip_size = 0.01

    if bundle and hasattr(bundle, "chart_payload") and bundle.chart_payload:
        atr_val = bundle.chart_payload.get("indicators", {}).get("atr")
        if atr_val is not None:
            atr_pips = float(atr_val) / pip_size
            if atr_pips > 0:
                pips_thresh = max(1.0, min(15.0, atr_pips * 0.20))
                
    # Session time activity scaling
    now_utc = datetime.now(timezone.utc)
    current_hour = now_utc.hour
    if 12 <= current_hour <= 17:
        refresh_sec = max(2, refresh_sec - 1)
    elif 21 <= current_hour or current_hour <= 1:
        refresh_sec = refresh_sec + 3
        
    # High-impact news boost
    news_boost = False
    global orchestrator
    forex_factory_feed = getattr(orchestrator, "forex_factory_feed", None)
    if forex_factory_feed:
        try:
            currency = symbol[:3]
            events = forex_factory_feed.fetch_for_currency(currency) or []
            if len(symbol) >= 6:
                other_curr = symbol[3:6]
                events += (forex_factory_feed.fetch_for_currency(other_curr) or [])
                
            for event in events:
                if getattr(event, "impact_level", "LOW") == "HIGH" and event.publication_time:
                    pub_str = event.publication_time.replace("Z", "+00:00")
                    pub_dt = datetime.fromisoformat(pub_str)
                    time_diff = (pub_dt - now_utc).total_seconds()
                    if -900 <= time_diff <= 1800:
                        news_boost = True
                        break
        except Exception:
            pass

    if news_boost:
        refresh_sec = 2
        pips_thresh = max(1.0, pips_thresh * 0.75)
        
    st.session_state.refresh_sec = refresh_sec
    st.session_state.pips_thresh = pips_thresh


def check_reanalysis_triggers(symbol, timeframe, forced_strategy):
    # Check if active position has closed (SL/TP hit or early close) in local signal repository (no network!)
    current_active = signal_repository.get_active_position(symbol)
    current_active_id = current_active.get("logged_at") if current_active else None
    prev_active_id = st.session_state.get("last_active_position_id")
    
    if prev_active_id is not None and current_active_id is None:
        st.session_state.last_active_position_id = None
        return True, "Active position closed (SL/TP hit or invalidated)"
        
    st.session_state.last_active_position_id = current_active_id

    # Check if time interval elapsed since last run
    last_analysis_time_dt = st.session_state.get("last_analysis_time_dt")
    if last_analysis_time_dt is not None:
        from datetime import datetime, timezone
        elapsed = (datetime.now(timezone.utc) - last_analysis_time_dt).total_seconds()
        refresh_sec = int(st.session_state.get("refresh_sec", 5))
        if elapsed >= refresh_sec:
            return True, f"Timer elapsed ({refresh_sec}s)"
            
    return False, "No trigger met"

with st.container():
    control_cols = st.columns([1.0, 0.8, 1.5, 1.0], gap="medium")
    with control_cols[0]:
        symbol = st.selectbox("Symbol", SYMBOLS, index=SYMBOLS.index(st.session_state.analysis_symbol))
    with control_cols[1]:
        timeframe = st.selectbox("Timeframe", TIMEFRAMES, index=TIMEFRAMES.index(st.session_state.analysis_timeframe))
    with control_cols[2]:
        strategies = ["Auto (Session-Aware)", "Trend Following", "Quick Scalper", "Range Trader", "Breakout Trader", "Carry Trader"]
        selected_strategy = st.selectbox(
            "Strategy Selection",
            strategies,
            index=strategies.index(st.session_state.get("selected_strategy", "Auto (Session-Aware)"))
        )
    with control_cols[3]:
        # Synced Toggle for Live Analysis (no custom state key to prevent lockups)
        current_live_mode = st.session_state.get("live_mode", False)
        live_toggle = st.toggle("Live Analysis", value=current_live_mode)
        
        st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
        if live_toggle:
            if st.button("Stop Analysis", type="secondary", use_container_width=True):
                st.session_state.live_mode = False
                st.session_state.analysis_running = False
                st.session_state.analysis_status = "STOPPED"
                st.session_state.update_trigger_reason = "Manual Stop"
                st.rerun()
        else:
            if st.button("Run Analysis", type="primary", use_container_width=True):
                st.session_state.live_mode = True
                st.session_state.analysis_running = True
                st.session_state.analysis_status = "LIVE"
                st.session_state.update_trigger_reason = "Manual Run"
                st.rerun()

        # If the toggle value itself changed directly by the user clicking the toggle widget
        if live_toggle != current_live_mode:
            st.session_state.live_mode = live_toggle
            if live_toggle:
                st.session_state.analysis_running = True
                st.session_state.analysis_status = "LIVE"
                st.session_state.update_trigger_reason = "Live Analysis Enabled"
            else:
                st.session_state.analysis_running = False
                st.session_state.analysis_status = "STOPPED"
                st.session_state.update_trigger_reason = "Live Analysis Disabled"
            st.rerun()

# Live Engine settings are auto-adjusted in the background
adjust_live_engine_config(symbol, timeframe)
trigger_mode = st.session_state.get("trigger_mode", "Hybrid (Smart Triggers)")
refresh_sec = int(st.session_state.get("refresh_sec", 5))
pips_thresh = float(st.session_state.get("pips_thresh", 2.0))


# 1. Reset trackers if settings changed
settings_changed = (
    st.session_state.analysis_symbol != symbol or 
    st.session_state.analysis_timeframe != timeframe or 
    st.session_state.get("selected_strategy") != selected_strategy
)

if settings_changed:
    st.session_state.selected_strategy = selected_strategy
    st.session_state.analysis_symbol = symbol
    st.session_state.analysis_timeframe = timeframe
    st.session_state.last_candle_time = None
    st.session_state.last_price = None
    st.session_state.force_analyze = True
    st.session_state.update_trigger_reason = "Settings Changed"
    st.session_state.analysis_bundle = None

# 2. Perform live or manual analysis
from datetime import datetime, timezone

if st.session_state.live_mode:
    # Render the custom websocket listener component to trigger script rerun on websocket pushes
    import os
    import streamlit.components.v1 as components
    
    WS_LISTENER_PATH = os.path.join(os.path.dirname(__file__), "backend", "ws_listener")
    ws_listener_component = components.declare_component("ws_listener", path=WS_LISTENER_PATH)
    
    # Render component silently (0 height)
    last_update_ts = ws_listener_component(
        symbol=symbol,
        timeframe=timeframe,
        session_id=st.session_state.session_uuid,
        key="ws_listener_instance"
    )
    
    # If a new websocket update was triggered
    if last_update_ts and last_update_ts != st.session_state.get("last_ws_update_ts"):
        st.session_state.last_ws_update_ts = last_update_ts
        st.session_state.update_trigger_reason = "WebSocket Push"
        st.session_state.last_analysis_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.last_analysis_time_dt = datetime.now(timezone.utc)
    
    # Retrieve the latest bundle from the backend manager
    bundle = live_analysis_manager.get_latest_analysis(symbol, timeframe)
    
    if bundle is None:
        st.info("⏳ Connecting to Live Analysis Engine and waiting for initial analysis from backend...")
        st.stop()
        
    st.session_state.analysis_bundle = bundle
    last_row = bundle.candles.iloc[-1]
    st.session_state.last_price = float(last_row["close"])
    st.session_state.last_candle_time = last_row.name.isoformat() if isinstance(last_row.name, pd.Timestamp) else str(last_row.name)
    st.session_state.analysis_status = "LIVE"
        
else:
    # Live mode is stopped/inactive
    bundle = st.session_state.get("analysis_bundle")
    if bundle is None:
        st.info("Select a symbol and timeframe, then click `Run Analysis` to start live backend-driven analysis.")
        st.stop()

# ── Visibility component injection ──
session_id_js = st.session_state.session_uuid
components.html(
    f"""
    <script>
        const sessionId = "{session_id_js}";
        const endpoint = "http://127.0.0.1:8505/visibility";
        
        function sendVisibility(state) {{
            fetch(`${{endpoint}}?session_id=${{sessionId}}&state=${{state}}`, {{ mode: "no-cors" }})
                .catch(err => console.error("Visibility post failed", err));
        }}
        
        if (window.parent && window.parent.document) {{
            sendVisibility(window.parent.document.visibilityState);
            window.parent.document.addEventListener("visibilitychange", () => {{
                sendVisibility(window.parent.document.visibilityState);
            }});
        }} else {{
            sendVisibility(document.visibilityState);
            document.addEventListener("visibilitychange", () => {{
                sendVisibility(document.visibilityState);
            }});
        }}
    </script>
    """,
    height=0,
    width=0
)

# ── Premium Live Analysis Dashboard Card ──
status_label = st.session_state.get("analysis_status", "STOPPED")
reason = st.session_state.get("update_trigger_reason", "System Start")
last_time = st.session_state.get("last_analysis_time", "Never")

current_sig = bundle.signal.signal if bundle else "--"
current_conf = f"{bundle.signal.confidence:.2f}%" if bundle and bundle.signal.confidence is not None else "--"
current_bias = bundle.chart_payload.get("overlays", {}).get("structure", {}).get("trend", "n/a").upper() if bundle else "--"

badge_color = {
    "LIVE": "#0284c7",
    "ANALYZING": "#fb7185",
    "IDLE": "#10b981",
    "STOPPED": "#64748b",
    "ERROR": "#ef4444"
}.get(status_label, "#64748b")

st.markdown(
    f"""
    <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 15px; margin-bottom: 20px; padding: 16px; background: rgba(255, 255, 255, 0.95); border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 20px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04); backdrop-filter: blur(10px);'>
        <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
            <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>Engine Status</div>
            <div style='display: flex; align-items: center; gap: 6px; margin-top: 4px;'>
                <span style='height: 8px; width: 8px; border-radius: 50%; background-color: {badge_color}; display: inline-block;'></span>
                <span style='font-size: 15px; font-weight: 800; color: {badge_color};'>{status_label}</span>
            </div>
        </div>
        <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
            <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>Last Update Reason</div>
            <div style='font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 4px;'>{reason}</div>
        </div>
        <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
            <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>Last Analysis Time</div>
            <div style='font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 4px;'>{last_time}</div>
        </div>
        <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
            <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>Market Bias</div>
            <div style='font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 4px;'>{current_bias}</div>
        </div>
        <div>
            <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>Signal / Confidence</div>
            <div style='font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 4px;'>{current_sig} ({current_conf})</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

render_section_header("Chart Workspace", "Live interactive trading chart with AI analysis panel — signal, entry, SL, TP and structure overlaid in real time.")
render_metric_strip(bundle)

# Render TradingView Live Chart Widget
render_tradingview_widget(st.session_state.analysis_symbol, st.session_state.analysis_timeframe, bundle)

overview_tab, mtf_tab, structure_tab, sessions_tab, news_tab, history_tab, levels_tab = st.tabs(
    ["📊 Overview", "🔄 Multi-Timeframe", "🏗️ Structure Logic", "🌍 Sessions", "📰 News Intel", "📜 Trade History", "📐 SMC Intel & Levels"]
)

with overview_tab:
    has_mismatch = any("Feed mismatch" in w or "mismatch" in w.lower() for w in bundle.signal.warnings)
    approved_trade = (bundle.signal.signal in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"]
                      and bundle.signal.stop_loss not in [None, 0, 0.0])
    show_levels = approved_trade and bundle.signal.entry not in [None, 0, 0.0]

    # Status banner
    if bundle.signal.signal == "TRADE_REMOVED":
        reason = bundle.signal.reasons[0] if bundle.signal.reasons else "Active trade invalidated"
        render_status_box(f"❌ TRADE REMOVED. Reason: {reason}", tone="danger")
    elif approved_trade:
        render_status_box("✅ Trade setup passed the quality checks and is eligible for display.", tone="success")
    elif has_mismatch:
        render_status_box("⚠️ The setup has a feed synchronization warning. Execution is blocked, but analysis is displayed.", tone="warning")
    else:
        render_status_box("🚫 The engine is blocking execution because the current setup is weak or confirmations are insufficient.", tone="warning")

    left_col, right_col = st.columns([1.1, 1], gap="large")
    with left_col:
        explanation_html = bundle.ai_explanation.get("explanation", "No explanation returned.")
        render_content_card("Decision Summary", explanation_html)

        # Warnings block
        if bundle.signal.warnings:
            warnings_html = "".join(f"<li style='color:#92400e;margin-bottom:4px;'>{w}</li>" for w in bundle.signal.warnings)
            render_content_card("⚠️ Warnings", f"<ul class='content-list'>{warnings_html}</ul>")

        # Reasons block
        if approved_trade and bundle.signal.reasons:
            reasons_html = "".join(f"<li style='margin-bottom:4px;'>{r}</li>" for r in bundle.signal.reasons)
            render_content_card("📌 Signal Reasons", f"<ul class='content-list'>{reasons_html}</ul>")

    with right_col:
        # Trade levels
        trade_levels_html = "".join(
            [
                f"<li><b>Entry:</b> {format_price(bundle.signal.entry) if show_levels else '--'}</li>",
                f"<li><b>Stop Loss:</b> {format_price(bundle.signal.stop_loss) if show_levels else '--'}</li>",
                f"<li><b>Take Profit 1:</b> {format_price(bundle.signal.tp1) if show_levels else '--'}</li>",
                f"<li><b>Take Profit 2:</b> {format_price(bundle.signal.tp2) if show_levels else '--'}</li>",
                f"<li><b>Take Profit 3:</b> {format_price(getattr(bundle.signal, 'tp3', 0.0)) if show_levels else '--'}</li>",
                f"<li><b>Risk / Reward:</b> {bundle.signal.rr_ratio if show_levels and bundle.signal.rr_ratio not in [0, 0.0] else '--'}</li>",
            ]
        )
        render_content_card("Trade Levels", f"<ul class='content-list'>{trade_levels_html}</ul>")

        # Signal summary
        breakdown_html = ""
        if getattr(bundle.signal, "confidence_breakdown", None):
            breakdown_items = []
            for name, val in bundle.signal.confidence_breakdown.items():
                breakdown_items.append(f"<span style='font-size:10px;font-weight:700;color:#475569;'>{name}: {val:.1f}</span>")
            breakdown_html = f"<div style='display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;border-top:1px solid rgba(148,163,184,0.15);padding-top:6px;'>{' | '.join(breakdown_items)}</div>"

        signal_color = {"BUY": "#16a34a", "STRONG_BUY": "#15803d", "SELL": "#dc2626", "STRONG_SELL": "#b91c1c"}.get(bundle.signal.signal, "#475569")
        summary_html = f"""
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;'>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Signal</div>
            <div style='font-size:17px;font-weight:800;color:{signal_color};'>{bundle.signal.signal}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);grid-column:span 2;'>
            <div style='font-size:11px;color:#64748b;margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em;'>Confidence</div>
            {_conf_gauge_html(bundle.signal.confidence, height='12px', font_size='18px')}
            {breakdown_html}
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Symbol</div>
            <div style='font-size:15px;font-weight:700;color:#0f172a;'>{bundle.signal.symbol}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Timeframe</div>
            <div style='font-size:15px;font-weight:700;color:#0f172a;'>{bundle.signal.timeframe}m</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Feed Source</div>
            <div style='font-size:13px;font-weight:600;color:#0f172a;word-break:break-word;'>{bundle.signal.feed_source or '--'}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Chart Sync</div>
            <div style='font-size:15px;font-weight:700;color:#0f172a;'>{bundle.sync.match_percentage}%</div>
          </div>
        </div>
        """
        render_content_card("Signal Summary", summary_html)

with mtf_tab:
    if hasattr(bundle, "mtf_analysis") and bundle.mtf_analysis:
        st.markdown('<div class="section-title">Multi-Timeframe Analysis Grid</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">Simultaneous analysis of 1M, 5M, 15M, 1H (60M), and 1D timeframes. Higher timeframes dictate the macro trend, while lower timeframes confirm entry momentum.</div>', unsafe_allow_html=True)

        rows = []
        for tf, data in bundle.mtf_analysis.items():
            # Color trend
            trend_val = data["trend"].upper()
            trend_color = "#16a34a" if data["trend"] == "bullish" else ("#dc2626" if data["trend"] == "bearish" else "#64748b")
            trend_badge = f'<span style="padding:4px 8px;border-radius:8px;font-size:11px;font-weight:700;background:{trend_color}22;color:{trend_color};border:1px solid {trend_color}44;">{trend_val}</span>'

            # Color signal
            sig_val = data["signal"]
            sig_color = {"BUY": "#16a34a", "STRONG_BUY": "#15803d", "SELL": "#dc2626", "STRONG_SELL": "#b91c1c"}.get(sig_val, "#64748b")
            sig_badge = f'<span style="padding:4px 8px;border-radius:8px;font-size:11px;font-weight:700;background:{sig_color}22;color:{sig_color};border:1px solid {sig_color}44;">{sig_val}</span>'

            # EMA Status
            ema_val = data["ema_status"]
            ema_color = "#16a34a" if ema_val == "Above EMAs" else ("#dc2626" if ema_val == "Below EMAs" else "#f59e0b")
            ema_badge = f'<span style="color:{ema_color};font-weight:600;">{ema_val}</span>'

            # RSI Status
            rsi_val = data["rsi_status"]
            rsi_color = "#dc2626" if "Overbought" in rsi_val else ("#16a34a" if "Oversold" in rsi_val else "#475569")
            rsi_badge = f'<span style="color:{rsi_color};font-weight:600;">{rsi_val}</span>'

            # MACD Status
            macd_val = data["macd_status"]
            macd_color = "#16a34a" if macd_val == "Bullish Cross" else ("#dc2626" if macd_val == "Bearish Cross" else "#64748b")
            macd_badge = f'<span style="color:{macd_color};font-weight:600;">{macd_val}</span>'

            # Conf
            conf_val = data["confidence"]
            conf_gauge = f"""
            <div style=\'display:flex;align-items:center;gap:6px;min-width:100px;\'>
              <div style=\'flex:1;background:rgba(148,163,184,0.18);border-radius:999px;height:6px;overflow:hidden;\'>
                <div style=\'width:{conf_val:.0f}%;height:100%;background:{sig_color};border-radius:999px;\'></div>
              </div>
              <span style=\'font-size:11px;font-weight:700;color:{sig_color};\'>{conf_val:.1f}%</span>
            </div>
            """

            tf_display = f"1m (1-Minute)" if tf == "1" else f"5m (5-Minute)" if tf == "5" else f"15m (15-Minute)" if tf == "15" else f"1h (1-Hour)" if tf == "60" else f"1d (1-Day)" if tf == "D" else f"{tf}m"

            rows.append(f"""
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.12); transition: background-color 0.2s;">
              <td style="padding: 12px 16px; font-weight: 700; color: #0f172a;">{tf_display}</td>
              <td style="padding: 12px 16px;">{trend_badge}</td>
              <td style="padding: 12px 16px; font-size: 13px; font-weight: 600; color: #334155;">{data["phase"].title()}</td>
              <td style="padding: 12px 16px; font-size: 13px;">{ema_badge}</td>
              <td style="padding: 12px 16px; font-size: 13px;">{rsi_badge}</td>
              <td style="padding: 12px 16px; font-size: 13px;">{macd_badge}</td>
              <td style="padding: 12px 16px;">{sig_badge}</td>
              <td style="padding: 12px 16px;">{conf_gauge}</td>
            </tr>
            """)

        table_html = f"""
        <div style="border: 1px solid rgba(148, 163, 184, 0.24); border-radius: 20px; overflow: hidden; background: white; box-shadow: 0 16px 35px rgba(15, 23, 42, 0.08); margin-bottom: 1.5rem;">
          <table style="width: 100%; border-collapse: collapse; text-align: left; font-family: inherit;">
            <thead>
              <tr style="background: #f8fafc; border-bottom: 1.5px solid rgba(148, 163, 184, 0.24);">
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Timeframe</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Trend Bias</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Structure Phase</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">EMA Trend</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">RSI Indicator</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">MACD Momentum</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Timeframe Signal</th>
                <th style="padding: 14px 16px; font-weight: 700; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {"".join(rows)}
            </tbody>
          </table>
        </div>
        """
        cleaned_table_html = "\n".join(line.strip() for line in table_html.splitlines())
        st.markdown(cleaned_table_html, unsafe_allow_html=True)
    else:
        st.info("Multi-timeframe data is not available. Please make sure all target feeds are active.")

with structure_tab:
    structure = bundle.chart_payload.get("overlays", {}).get("structure", {})
    swing_df, imbalance_df = build_structure_tables(bundle)

    st_left, st_right = st.columns([1, 1], gap="large")
    with st_left:
        trend_val = structure.get('trend', 'n/a')
        trend_color = '#16a34a' if trend_val == 'bullish' else ('#dc2626' if trend_val == 'bearish' else '#64748b')
        phase_val = structure.get('phase', 'n/a')
        strength_val = structure.get('strength', 'n/a')
        bos_val = structure.get('bos') or 'none'
        choch_val = structure.get('choch') or 'none'
        sweep_val = structure.get('liquidity_sweep') or 'none'
        breakout_val = structure.get('breakout') or 'none'
        pullback_val = structure.get('pullback') or 'none'

        struct_html = f"""
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;'>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Trend</div>
            <div style='font-size:17px;font-weight:800;color:{trend_color};'>{trend_val.upper() if trend_val != 'n/a' else 'N/A'}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Phase</div>
            <div style='font-size:15px;font-weight:700;color:#0f172a;'>{phase_val.title() if phase_val != 'n/a' else 'N/A'}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Strength</div>
            <div style='font-size:15px;font-weight:700;color:#0f172a;'>{strength_val}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>BOS</div>
            <div style='font-size:15px;font-weight:700;color:{"#2563eb" if bos_val != "none" else "#94a3b8"};'>{bos_val.upper()}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>CHOCH</div>
            <div style='font-size:15px;font-weight:700;color:{"#7c3aed" if choch_val != "none" else "#94a3b8"};'>{choch_val.upper()}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Liquidity Sweep</div>
            <div style='font-size:15px;font-weight:700;color:{"#f97316" if sweep_val != "none" else "#94a3b8"};'>{sweep_val.title()}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Breakout</div>
            <div style='font-size:14px;font-weight:700;color:#0f172a;'>{str(breakout_val).title()}</div>
          </div>
          <div style='padding:12px;border-radius:14px;background:rgba(15,23,42,0.05);border:1px solid rgba(148,163,184,0.2);'>
            <div style='font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em;'>Pullback</div>
            <div style='font-size:14px;font-weight:700;color:#0f172a;'>{str(pullback_val).title()}</div>
          </div>
        </div>
        """
        render_content_card("Market Structure State", struct_html)

    with st_right:
        render_content_card("Swing Points", "Latest detected Higher Highs (HH), Higher Lows (HL), Lower Highs (LH), Lower Lows (LL).")
        if swing_df.empty:
            st.info("No swing points were detected.")
        else:
            st.dataframe(swing_df, use_container_width=True)

    render_content_card("Fair Value Gaps & Imbalance Zones",
        "Detected FVG / AVG imbalance zones with entry bounds and average midpoint. These represent inefficiencies in price delivery.")
    if imbalance_df.empty:
        st.info("No fair value gaps passed the minimum displacement filter.")
    else:
        st.dataframe(imbalance_df, use_container_width=True)



with sessions_tab:
    from engine.session_engine import SessionEngine as _SE, _SESSION_WINDOWS as _SW
    import datetime as _dt_sess

    _utc_now = _dt_sess.datetime.now(_dt_sess.timezone.utc)
    _se = _SE()
    _session = _se.detect(_utc_now)
    _timeline = _se.build_session_timeline(_utc_now)
    _ss = bundle.session_signal

    render_section_header(
        "🌍 Market Session Intelligence",
        "Live session detection — Asian Range | London Breakout | NY Reversal | Overlap. Strategy auto-switches per active session."
    )

    # ── Live clock + active session banner ───────────────────────────────
    _utc_str = _utc_now.strftime("%H:%M UTC")
    _sess_color = _session.color
    _sess_name = _session.name
    _sess_emoji = _session.emoji
    _vol_colors = {"LOW": "#22c55e", "HIGH": "#f97316", "EXTREME": "#dc2626", "MEDIUM": "#f59e0b", "MINIMAL": "#64748b"}
    _vol_color = _vol_colors.get(_session.volatility, "#64748b")

    _clock_html = f"""
    <div style="border-radius:22px;padding:1.2rem 1.5rem;background:linear-gradient(135deg,{_sess_color}22,{_sess_color}08);
         border:2px solid {_sess_color}55;margin-bottom:1.2rem;display:flex;align-items:center;gap:1.2rem;flex-wrap:wrap;">
      <div style="font-size:2.8rem;line-height:1;">{_sess_emoji}</div>
      <div style="flex:1;min-width:200px;">
        <div style="font-size:1.35rem;font-weight:900;color:#0f172a;">{_sess_name} Session</div>
        <div style="font-size:0.85rem;color:#475569;margin-top:2px;">{_session.description}</div>
      </div>
      <div style="text-align:right;">
        <div style="font-size:1.6rem;font-weight:800;color:{_sess_color};">{_utc_str}</div>
        <div style="font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;background:{_vol_color};color:#fff;display:inline-block;margin-top:4px;">{_session.volatility} VOLATILITY</div>
      </div>
    </div>
    """
    st.markdown(_clock_html, unsafe_allow_html=True)

    # ── Session timeline bar ──────────────────────────────────────────────
    _tl_cols = st.columns(len(_timeline))
    for _i, _tl in enumerate(_timeline):
        _bg = f"linear-gradient(135deg,{_tl['color']}33,{_tl['color']}11)" if _tl["active"] else "rgba(148,163,184,0.08)"
        _border = _tl["color"] if _tl["active"] else "rgba(148,163,184,0.22)"
        _text_color = _tl["color"] if _tl["active"] else "#94a3b8"
        with _tl_cols[_i]:
            st.markdown(f"""
            <div style="padding:12px 8px;border-radius:16px;background:{_bg};border:2px solid {_border};
                 text-align:center;margin-bottom:4px;">
              <div style="font-size:1.3rem;">{_tl['emoji']}</div>
              <div style="font-size:12px;font-weight:800;color:{_text_color};">{_tl['name']}</div>
              <div style="font-size:10px;color:#94a3b8;">{_tl['start']:02d}:00–{_tl['end']:02d}:00</div>
              {'<div style="font-size:10px;font-weight:700;color:' + _tl["color"] + ';margin-top:4px;">▶ ACTIVE</div>' if _tl["active"] else '<div style="font-size:10px;color:#cbd5e1;margin-top:4px;">inactive</div>'}
            </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)

    # ── Two-column layout ─────────────────────────────────────────────────
    _sl, _sr = st.columns([1.3, 1], gap="large")

    with _sl:
        # Signal card
        if _ss is not None:
            _act_color = {"BUY": "#16a34a", "SELL": "#dc2626", "WAIT": "#f59e0b"}.get(_ss.trade_action, "#64748b")
            _gate_bg = "rgba(22,163,74,0.08)" if _ss.is_actionable else "rgba(245,158,11,0.10)"
            _gate_border = "#86efac" if _ss.is_actionable else "#fcd34d"
            _gate_icon = "✅ ACTIONABLE — Entry conditions met" if _ss.is_actionable else "⚠️ WAIT — Insufficient confluences or no setup"
            _gate_color = "#166534" if _ss.is_actionable else "#92400e"
            _conf_bar_color = "#16a34a" if _ss.confidence >= 70 else ("#f59e0b" if _ss.confidence >= 45 else "#dc2626")
            _rr_color = "#16a34a" if _ss.rr_ratio >= 2 else ("#f59e0b" if _ss.rr_ratio >= 1 else "#dc2626")

            _sig_html = f"""
            <div style="border-radius:22px;padding:1.3rem 1.4rem;background:rgba(255,255,255,0.97);
                 border:1px solid rgba(148,163,184,0.28);box-shadow:0 16px 40px rgba(15,23,42,0.08);margin-bottom:1rem;">

              <!-- Header -->
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;flex-wrap:wrap;gap:8px;">
                <div>
                  <div style="font-size:1.1rem;font-weight:900;color:#0f172a;">Session Signal</div>
                  <div style="font-size:12px;color:#64748b;margin-top:2px;">{_ss.strategy_used}</div>
                </div>
                <span style="padding:8px 16px;border-radius:999px;font-size:14px;font-weight:800;
                     background:{_act_color};color:#fff;">{_ss.trade_action}</span>
              </div>

              <!-- Gate -->
              <div style="padding:10px 14px;border-radius:14px;background:{_gate_bg};border:1px solid {_gate_border};
                   font-size:12px;font-weight:700;color:{_gate_color};margin-bottom:1rem;">
                {_gate_icon}
              </div>

              <!-- Confidence bar -->
              <div style="margin-bottom:1rem;">
                <div style="display:flex;justify-content:space-between;font-size:11px;color:#64748b;margin-bottom:4px;">
                  <span>Confidence</span><span style="font-weight:800;color:{_conf_bar_color};">{_ss.confidence}/100</span>
                </div>
                <div style="height:8px;border-radius:999px;background:rgba(148,163,184,0.18);">
                  <div style="height:100%;width:{_ss.confidence}%;background:{_conf_bar_color};border-radius:999px;transition:width .4s;"></div>
                </div>
              </div>

              <!-- Mandatory output grid -->
              <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-bottom:1rem;">
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Pair</div>
                  <div style="font-size:14px;font-weight:800;color:#0f172a;">{_ss.pair}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Session</div>
                  <div style="font-size:14px;font-weight:800;color:{_sess_color};">{_ss.session} {_sess_emoji}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Entry Price</div>
                  <div style="font-size:14px;font-weight:800;color:#0f172a;">{"--" if not _ss.is_actionable else f"{_ss.entry_price:.5f}"}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Stop Loss</div>
                  <div style="font-size:14px;font-weight:800;color:#dc2626;">{"--" if not _ss.is_actionable else f"{_ss.stop_loss:.5f}"}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Take Profit 1</div>
                  <div style="font-size:14px;font-weight:800;color:#16a34a;">{"--" if not _ss.is_actionable else f"{_ss.take_profit_1:.5f}"}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Take Profit 2</div>
                  <div style="font-size:14px;font-weight:800;color:#16a34a;">{"--" if not _ss.is_actionable else f"{_ss.take_profit_2:.5f}"}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Risk : Reward</div>
                  <div style="font-size:14px;font-weight:800;color:{_rr_color};">{"--" if not _ss.is_actionable else f"1 : {_ss.rr_ratio:.2f}"}</div>
                </div>
                <div style="padding:10px 12px;border-radius:15px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                  <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Strategy Used</div>
                  <div style="font-size:12px;font-weight:700;color:#0f172a;">{_ss.strategy_used}</div>
                </div>
              </div>

              <!-- Reasoning -->
              <div style="padding:12px 14px;border-radius:14px;background:rgba(37,99,235,0.07);border:1px solid rgba(96,165,250,0.28);margin-bottom:0.75rem;">
                <div style="font-size:10px;color:#3b82f6;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;font-weight:700;">Reasoning</div>
                <div style="font-size:13px;color:#1e3a5f;line-height:1.5;">{_ss.reasoning}</div>
              </div>

              <!-- Pip targets -->
              <div style="font-size:11px;color:#64748b;">
                Pip targets for {_session.name}: <b>{_session.pip_target_min}–{_session.pip_target_max} pips</b> &nbsp;|&nbsp;
                Risk per trade: <b>max 1–2% of account</b>
              </div>
            </div>
            """
            st.markdown(_sig_html, unsafe_allow_html=True)
        else:
            st.info("Session signal not yet computed. Run an analysis first.")

    with _sr:
        # Confluence checklist
        render_content_card("✅ Confluence Checklist", f"Minimum 2 confluences required for {_session.name} session entry")
        if _ss is not None and _ss.confluences:
            for _conf in _ss.confluences:
                st.markdown(
                    f"<div style='padding:8px 12px;border-radius:12px;background:rgba(22,163,74,0.08);"
                    f"border:1px solid #86efac;margin-bottom:6px;font-size:13px;color:#166534;font-weight:600;'>"
                    f"&#10003; {_conf}</div>",
                    unsafe_allow_html=True
                )
        elif _ss is not None:
            st.info("No confluences detected for this setup.")

        # Warnings
        if _ss is not None and _ss.warnings:
            render_content_card("⚠️ Execution Filters", "Blocked conditions")
            for _w in _ss.warnings[:5]:
                st.markdown(
                    f"<div style='padding:8px 12px;border-radius:12px;background:rgba(245,158,11,0.08);"
                    f"border:1px solid #fcd34d;margin-bottom:6px;font-size:12px;color:#92400e;'>"
                    f"&#9888; {_w}</div>",
                    unsafe_allow_html=True
                )

        # Asian range display
        if _ss is not None and _ss.asian_range_high is not None:
            _ar_pips_val = round(abs(_ss.asian_range_high - (_ss.asian_range_low or 0)) / (_ss.pip_size or 0.0001), 1)
            render_content_card("📐 Asian Session Range", "Used by London strategy for breakout level")
            st.markdown(f"""
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
              <div style="padding:10px;border-radius:14px;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);text-align:center;">
                <div style="font-size:10px;color:#3b82f6;text-transform:uppercase;margin-bottom:3px;">High</div>
                <div style="font-size:13px;font-weight:800;color:#1e40af;">{_ss.asian_range_high:.5f}</div>
              </div>
              <div style="padding:10px;border-radius:14px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);text-align:center;">
                <div style="font-size:10px;color:#ef4444;text-transform:uppercase;margin-bottom:3px;">Low</div>
                <div style="font-size:13px;font-weight:800;color:#991b1b;">{(_ss.asian_range_low or 0):.5f}</div>
              </div>
              <div style="padding:10px;border-radius:14px;background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);text-align:center;">
                <div style="font-size:10px;color:#7c3aed;text-transform:uppercase;margin-bottom:3px;">Range</div>
                <div style="font-size:13px;font-weight:800;color:#4c1d95;">{_ar_pips_val} pips</div>
              </div>
            </div>""", unsafe_allow_html=True)

        # Session rules reminder
        _rules = {
            "Asian":    ["🔵 Buy near support", "🔵 Sell near resistance", "🔵 Avoid breakouts unless confirmed", "🔵 Small targets: 5–15 pips"],
            "London":   ["🟡 Wait for Asian H/L breakout", "🟡 Confirm with momentum candle", "🟡 Use EMA50/200 trend filter", "🟡 Larger targets: 15–50+ pips"],
            "New York": ["🔴 Monitor London trend direction", "🔴 Look for reversals at key levels", "🔴 Identify stop hunts / liquidity grabs", "🔴 Price action required: engulfing / pin bar"],
            "Overlap":  ["⚡ All strategies active", "⚡ Highest-confidence setup wins", "⚡ Best liquidity + spread conditions", "⚡ Targets: 30–100 pips"],
        }
        _session_rules = _rules.get(_session.name, ["⏳ Low-priority session — wait for next active window"])
        render_content_card(f"{_sess_emoji} {_session.name} Strategy Rules", "Active playbook for current session")
        for _rule in _session_rules:
            st.markdown(f"<div style='font-size:13px;color:#334155;padding:5px 0;'>{_rule}</div>", unsafe_allow_html=True)


with news_tab:
    import datetime as _dt_news

    render_section_header(
        "📰 Forex Macro News Intelligence",
        "ForexFactory economic events → 6-step probability pipeline → structured BUY/SELL/WAIT bias signals."
    )

    # ── Fetch news signals for the current symbol (cached 5 min) ──────
    import time as _time
    _NEWS_TTL = 300  # seconds — match ForexFactory feed cache
    _indicator_snap = dict(bundle.indicators) if bundle and bundle.indicators else {}
    # Inject live price for Step 3 technical validation
    if bundle and not bundle.candles.empty:
        _indicator_snap["price"] = float(bundle.candles["close"].iloc[-1])

    _news_stale = (
        st.session_state.news_signals_symbol != symbol
        or st.session_state.news_signals_timeframe != timeframe
        or (_time.monotonic() - st.session_state.news_signals_fetched_at) > _NEWS_TTL
    )
    if _news_stale:
        with st.spinner("Fetching ForexFactory calendar…"):
            try:
                _news_signals = orchestrator.analyze_news(
                    symbol=symbol,
                    timeframe=timeframe,
                    indicator_snapshot=_indicator_snap,
                )
                st.session_state.news_signals = _news_signals
                st.session_state.news_signals_symbol = symbol
                st.session_state.news_signals_timeframe = timeframe
                st.session_state.news_signals_fetched_at = _time.monotonic()
            except Exception as _ne:
                _news_signals = st.session_state.news_signals
                st.warning(f"News fetch error: {_ne}")
    else:
        _news_signals = st.session_state.news_signals

    # ── Raw calendar events sidebar panel ─────────────────────────────
    _feed_error = ""
    if forex_factory_feed:
        try:
            _all_events = forex_factory_feed.fetch_events()
            _feed_error = forex_factory_feed.last_fetch_error
        except Exception as _fe:
            _all_events = []
            _feed_error = str(_fe)
    else:
        _all_events = []

    _high_events = [e for e in _all_events if e.impact_level == "HIGH"]
    _pair_events = [e for e in _all_events if symbol.upper() in e.affected_pairs]

    _nc_left, _nc_right = st.columns([1.3, 1], gap="large")

    with _nc_left:
        # Show feed error banner if any
        if _feed_error:
            st.warning(f"⚠️ ForexFactory feed: {_feed_error}")
        # Signal cards
        if not _news_signals:
            if _feed_error:
                st.info("No signals available. The calendar feed will auto-retry — check back in a moment.")
            else:
                st.info(f"No ForexFactory events found this week for {symbol}. HIGH-impact news will appear here automatically.")
        else:
            for _ns in _news_signals:
                _action_color = {
                    "BUY": "#16a34a", "SELL": "#dc2626", "WAIT": "#f59e0b"
                }.get(_ns.trade_action, "#64748b")
                _sentiment_color = {
                    "BULLISH": "#16a34a", "BEARISH": "#dc2626", "NEUTRAL": "#64748b"
                }.get(_ns.sentiment, "#64748b")
                _impact_color = {
                    "HIGH": "#dc2626", "MEDIUM": "#f59e0b", "LOW": "#22c55e"
                }.get(_ns.impact, "#64748b")
                _risk_color = {
                    "LOW": "#16a34a", "MEDIUM": "#f59e0b", "HIGH": "#dc2626"
                }.get(_ns.risk, "#64748b")
                _gate_bg = "rgba(22,163,74,0.08)" if _ns.entry_allowed else "rgba(245,158,11,0.10)"
                _gate_border = "#86efac" if _ns.entry_allowed else "#fcd34d"
                _gate_icon = "✅ Entry Allowed" if _ns.entry_allowed else "⚠️ WAIT — Gate Blocked"
                _gate_text_color = "#166534" if _ns.entry_allowed else "#92400e"
                _conf_bar_color = "#16a34a" if _ns.confidence >= 80 else ("#f59e0b" if _ns.confidence >= 60 else "#dc2626")

                _surprise_display = f"{_ns.surprise_pct * 100:.1f}%" if getattr(_ns, "surprise_pct", None) is not None else "--"
                _contrarian_display = getattr(_ns, "contrarian_bias", "--") or "--"
                _strength_display = f"{_ns.currency_strength_score:.1f}" if getattr(_ns, "currency_strength_score", None) is not None else "--"
                _fundamental_display = f"{_ns.fundamental_score:.1f}" if getattr(_ns, "fundamental_score", None) is not None else "--"
                _risk_score_display = f"{_ns.risk_score:.1f}" if getattr(_ns, "risk_score", None) is not None else "--"

                _signal_card_html = f"""
                <div style="border-radius:20px;padding:1.1rem 1.2rem;background:rgba(255,255,255,0.96);border:1px solid rgba(148,163,184,0.28);box-shadow:0 12px 30px rgba(15,23,42,0.07);margin-bottom:1rem;">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;flex-wrap:wrap;gap:8px;">
                    <div style="font-size:1rem;font-weight:800;color:#0f172a;">{_ns.event_name}</div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;">
                      <span style="padding:5px 10px;border-radius:999px;font-size:11px;font-weight:700;background:{_impact_color};color:#fff;">{_ns.impact}</span>
                      <span style="padding:5px 10px;border-radius:999px;font-size:11px;font-weight:700;background:{_sentiment_color};color:#fff;">{_ns.sentiment}</span>
                      <span style="padding:5px 10px;border-radius:999px;font-size:12px;font-weight:800;background:{_action_color};color:#fff;">{_ns.trade_action}</span>
                    </div>
                  </div>

                  <!-- Confidence bar -->
                  <div style="margin-bottom:0.75rem;">
                    <div style="display:flex;justify-content:space-between;font-size:11px;color:#64748b;margin-bottom:4px;">
                      <span>Confidence</span><span style="font-weight:700;color:{_conf_bar_color};">{_ns.confidence}/100</span>
                    </div>
                    <div style="height:7px;border-radius:999px;background:rgba(148,163,184,0.2);overflow:hidden;">
                      <div style="height:100%;width:{_ns.confidence}%;background:{_conf_bar_color};border-radius:999px;transition:width .4s;"></div>
                    </div>
                  </div>

                  <!-- Gate status -->
                  <div style="padding:9px 12px;border-radius:12px;background:{_gate_bg};border:1px solid {_gate_border};font-size:12px;font-weight:700;color:{_gate_text_color};margin-bottom:0.75rem;">
                    {_gate_icon}
                  </div>

                  <!-- Details grid -->
                  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:0.75rem;">
                    <div style="padding:9px 10px;border-radius:14px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Pair</div>
                      <div style="font-size:13px;font-weight:700;color:#0f172a;">{_ns.pair}</div>
                    </div>
                    <div style="padding:9px 10px;border-radius:14px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Risk</div>
                      <div style="font-size:13px;font-weight:700;color:{_risk_color};">{_ns.risk}</div>
                    </div>
                    <div style="padding:9px 10px;border-radius:14px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Duration</div>
                      <div style="font-size:13px;font-weight:700;color:#0f172a;">{_ns.expected_duration}</div>
                    </div>
                    <div style="padding:9px 10px;border-radius:14px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Hold</div>
                      <div style="font-size:13px;font-weight:700;color:#0f172a;">{_ns.holding_minutes}m</div>
                    </div>
                    <div style="padding:9px 10px;border-radius:14px;background:rgba(15,23,42,0.04);border:1px solid rgba(148,163,184,0.16);">
                      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Tech Confirm</div>
                      <div style="font-size:13px;font-weight:700;color:{'#16a34a' if _ns.technical_confirmation else '#dc2626'};">{'Yes' if _ns.technical_confirmation else 'No'}</div>
                    </div>
                  </div>

                  <!-- Macro Intelligence details -->
                  <div style="margin-top:0.5rem;margin-bottom:0.75rem;border-top:1px solid rgba(148,163,184,0.15);padding-top:0.5rem;">
                    <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px;">Forex Factory Macro Intel</div>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
                      <div style="padding:8px 9px;border-radius:12px;background:rgba(15,23,42,0.03);border:1px solid rgba(148,163,184,0.12);">
                        <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:2px;">Surprise</div>
                        <div style="font-size:12px;font-weight:700;color:#0f172a;">{_surprise_display}</div>
                      </div>
                      <div style="padding:8px 9px;border-radius:12px;background:rgba(15,23,42,0.03);border:1px solid rgba(148,163,184,0.12);">
                        <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:2px;">Contrarian Bias</div>
                        <div style="font-size:12px;font-weight:700;color:{'#16a34a' if _contrarian_display == 'BULLISH' else ('#dc2626' if _contrarian_display == 'BEARISH' else '#64748b')};">{_contrarian_display}</div>
                      </div>
                      <div style="padding:8px 9px;border-radius:12px;background:rgba(15,23,42,0.03);border:1px solid rgba(148,163,184,0.12);">
                        <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:2px;">Currency Str</div>
                        <div style="font-size:12px;font-weight:700;color:#0f172a;">{_strength_display}</div>
                      </div>
                      <div style="padding:8px 9px;border-radius:12px;background:rgba(15,23,42,0.03);border:1px solid rgba(148,163,184,0.12);">
                        <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:2px;">Fundamental Sc</div>
                        <div style="font-size:12px;font-weight:700;color:#0f172a;">{_fundamental_display}</div>
                      </div>
                      <div style="padding:8px 9px;border-radius:12px;background:rgba(15,23,42,0.03);border:1px solid rgba(148,163,184,0.12);">
                        <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:2px;">Risk Score</div>
                        <div style="font-size:12px;font-weight:700;color:#0f172a;">{_risk_score_display}</div>
                      </div>
                    </div>
                  </div>

                  <!-- Reason -->
                  <div style="font-size:12px;color:#334155;line-height:1.5;margin-bottom:0.5rem;">
                    <span style="font-weight:700;">Reason:</span> {_ns.reason}
                  </div>

                  <!-- Warnings -->
                  {('<div style="font-size:11px;color:#92400e;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.3);border-radius:10px;padding:8px 10px;">' + ''.join(f'<div>⚠ {w}</div>' for w in _ns.warnings[:4]) + '</div>') if _ns.warnings else ''}
                </div>
                """
                st.markdown(_signal_card_html, unsafe_allow_html=True)

    with _nc_right:
        # Calendar event list
        render_content_card(
            "📅 This Week's HIGH-Impact Events",
            f"Showing {len(_high_events)} high-impact events from ForexFactory."
        )
        if _high_events:
            for _ev in _high_events[:20]:
                _ev_pairs = ", ".join(_ev.affected_pairs[:4]) or "—"
                _time_display = _ev.publication_time[:16].replace("T", " ") if _ev.publication_time else "—"
                _cat_color = {
                    "Interest Rate": "#2563eb", "CPI": "#7c3aed", "GDP": "#0891b2",
                    "Employment": "#16a34a", "Central Bank": "#dc2626",
                    "Geopolitical": "#ea580c", "Commodity": "#ca8a04",
                    "Market Sentiment": "#0f766e", "Other": "#64748b",
                }.get(_ev.category, "#64748b")
                _val_html = ""
                if _ev.actual is not None or _ev.forecast is not None:
                    _val_html = f"<span style='font-size:11px;color:#475569;'> | A:{_ev.actual} F:{_ev.forecast} P:{_ev.previous}</span>"
                st.markdown(
                    f"""<div style="padding:9px 12px;border-radius:14px;background:rgba(255,255,255,0.92);"
                    f"border:1px solid rgba(148,163,184,0.24);margin-bottom:6px;">"
                    f"<div style='font-size:12px;font-weight:700;color:#0f172a;'>{_ev.event_name}</div>"
                    f"<div style='font-size:11px;color:#64748b;margin-top:2px;'>"
                    f"<span style='background:{_cat_color};color:#fff;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:700;'>{_ev.category}</span>"
                    f" {_ev.currency} · {_ev_pairs}{_val_html}"
                    f"</div>"
                    f"<div style='font-size:10px;color:#94a3b8;margin-top:2px;'>🕐 {_time_display} UTC</div>"
                    f"</div>""",
                    unsafe_allow_html=True
                )
        else:
            st.info("No HIGH-impact events this week, or the calendar is temporarily unavailable.")

        # All-pair events for this symbol
        if _pair_events:
            render_content_card(
                f"📌 All Events for {symbol} This Week",
                f"{len(_pair_events)} event(s) affecting {symbol}"
            )
            for _ev in _pair_events:
                _time_display = _ev.publication_time[:16].replace("T", " ") if _ev.publication_time else "—"
                _imp_c = {"HIGH": "#dc2626", "MEDIUM": "#f59e0b", "LOW": "#22c55e"}.get(_ev.impact_level, "#64748b")
                st.markdown(
                    f"""<div style="padding:8px 12px;border-radius:12px;background:rgba(255,255,255,0.88);"
                    f"border:1px solid rgba(148,163,184,0.2);margin-bottom:5px;display:flex;justify-content:space-between;align-items:center;">"
                    f"<div>"
                    f"<span style='font-size:12px;font-weight:700;color:#0f172a;'>{_ev.event_name}</span>"
                    f" <span style='font-size:10px;font-weight:700;color:{_imp_c};'>[{_ev.impact_level}]</span>"
                    f"<div style='font-size:10px;color:#94a3b8;'>🕐 {_time_display} UTC · {_ev.category}</div>"
                    f"</div>"
                    f"</div>""",
                    unsafe_allow_html=True
                )

    # ── News signal history ────────────────────────────────────────────
    st.markdown("---")
    render_content_card(
        "📋 News Signal History",
        "Recent news signals logged by the intelligence engine for all pairs."
    )
    if news_signal_repository:
        _news_hist = news_signal_repository.read_recent(limit=100)
        if _news_hist:
            _news_rows = []
            for _r in _news_hist:
                _raw_ts = _r.get("logged_at", "")
                try:
                    _ts = _dt_news.datetime.fromisoformat(_raw_ts.replace("Z", "+00:00"))
                    _ts_str = _ts.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    _ts_str = _raw_ts[:16] if _raw_ts else "--"
                _news_rows.append({
                    "Logged": _ts_str,
                    "Event": _r.get("event_name", "--"),
                    "Pair": _r.get("pair", "--"),
                    "Impact": _r.get("impact", "--"),
                    "Sentiment": _r.get("sentiment", "--"),
                    "Confidence": _r.get("confidence", 0),
                    "Action": _r.get("trade_action", "--"),
                    "Entry Allowed": "Yes" if _r.get("entry_allowed") else "No",
                    "Risk": _r.get("risk", "--"),
                    "Duration": _r.get("expected_duration", "--"),
                })
            if _news_rows:
                st.dataframe(pd.DataFrame(_news_rows), use_container_width=True, height=400)
        else:
            st.info("No news signals logged yet.")
    else:
        st.info("News signal repository not available.")


with history_tab:
    import datetime as _dt

    all_records = signal_repository.read_recent(limit=500)

    # Only show real directional trade signals
    base_trade_records = [
        r for r in all_records
        if r.get("signal") in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]
    ]

    if not base_trade_records:
        st.info("No trade signals recorded yet. Run an analysis to start logging BUY/SELL signals.")
    else:
        # Resolve active date range from session state or default values
        today = _dt.date.today()
        default_start = today - _dt.timedelta(days=30)
        
        if "date_filter_val" not in st.session_state:
            st.session_state.date_filter_val = (default_start, today)
            
        if "history_date_filter" in st.session_state and st.session_state["history_date_filter"] is not None:
            date_range = st.session_state["history_date_filter"]
        else:
            date_range = st.session_state.date_filter_val
            
        # Handle streamlit date range tuple lengths (can be 1 or 2 during selection)
        if isinstance(date_range, tuple) and len(date_range) == 2:
            filter_start, filter_end = date_range
        elif isinstance(date_range, tuple) and len(date_range) == 1:
            filter_start = date_range[0]
            filter_end = today
        else:
            filter_start = date_range
            filter_end = today

        # Filter base_trade_records by date range
        trade_records = []
        for r in base_trade_records:
            raw_open = r.get("logged_at", "")
            if raw_open:
                try:
                    open_date = _dt.datetime.fromisoformat(raw_open.replace("Z", "+00:00")).date()
                    if filter_start <= open_date <= filter_end:
                        trade_records.append(r)
                except Exception:
                    trade_records.append(r)
            else:
                trade_records.append(r)

        # ── Counters ──────────────────────────────────────────────────────
        tp_hit_count  = sum(1 for r in trade_records if r.get("outcome") == "TP_HIT")
        sl_hit_count  = sum(1 for r in trade_records if r.get("outcome") == "SL_HIT")
        changed_count = sum(1 for r in trade_records if r.get("outcome") == "CLOSED_BY_SIGNAL_CHANGE")
        open_count    = sum(1 for r in trade_records if r.get("outcome") in (None, "", "OPEN"))
        total_trades  = len(trade_records)
        resolved      = tp_hit_count + sl_hit_count
        success_rate  = (tp_hit_count / resolved * 100) if resolved > 0 else None
        avg_conf      = sum(float(r.get("confidence", 0) or 0) for r in trade_records) / max(total_trades, 1)

        success_display = f"{success_rate:.1f}%" if success_rate is not None else "Pending"
        success_color   = "#15803d" if (success_rate or 0) >= 50 else "#b91c1c"
        if success_rate is None:
            success_color = "#7c3aed"
        _sr_rgb = ("22,163,74" if (success_rate or 0) >= 50
                   else ("220,38,38" if success_rate is not None else "124,58,237"))

        stat_html = f"""
        <div style='display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:1.2rem;'>
          <div style='padding:14px;border-radius:18px;background:linear-gradient(135deg,rgba(37,99,235,0.12),rgba(37,99,235,0.04));border:1px solid rgba(37,99,235,0.3);text-align:center;'>
            <div style='font-size:10px;color:#3b82f6;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;font-weight:700;'>Total</div>
            <div style='font-size:26px;font-weight:800;color:#1d4ed8;'>{total_trades}</div>
          </div>
          <div style='padding:14px;border-radius:18px;background:linear-gradient(135deg,rgba(124,58,237,0.12),rgba(124,58,237,0.04));border:1px solid rgba(124,58,237,0.3);text-align:center;'>
            <div style='font-size:10px;color:#7c3aed;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;font-weight:700;'>🔵 Active</div>
            <div style='font-size:26px;font-weight:800;color:#6d28d9;'>{open_count}</div>
          </div>
          <div style='padding:14px;border-radius:18px;background:linear-gradient(135deg,rgba(22,163,74,0.12),rgba(22,163,74,0.04));border:1px solid rgba(22,163,74,0.3);text-align:center;'>
            <div style='font-size:10px;color:#16a34a;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;font-weight:700;'>✅ TP Hit</div>
            <div style='font-size:26px;font-weight:800;color:#15803d;'>{tp_hit_count}</div>
          </div>
          <div style='padding:14px;border-radius:18px;background:linear-gradient(135deg,rgba(220,38,38,0.12),rgba(220,38,38,0.04));border:1px solid rgba(220,38,38,0.3);text-align:center;'>
            <div style='font-size:10px;color:#dc2626;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;font-weight:700;'>❌ SL Hit</div>
            <div style='font-size:26px;font-weight:800;color:#b91c1c;'>{sl_hit_count}</div>
          </div>
          <div style='padding:14px;border-radius:18px;background:linear-gradient(135deg,rgba(245,158,11,0.12),rgba(245,158,11,0.04));border:1px solid rgba(245,158,11,0.3);text-align:center;'>
            <div style='font-size:10px;color:#d97706;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;font-weight:700;'>🔄 Changed</div>
            <div style='font-size:26px;font-weight:800;color:#b45309;'>{changed_count}</div>
          </div>
          <div style='padding:14px;border-radius:18px;background:linear-gradient(135deg,rgba({_sr_rgb},0.12),rgba({_sr_rgb},0.04));border:1px solid rgba({_sr_rgb},0.3);text-align:center;'>
            <div style='font-size:10px;color:{success_color};text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;font-weight:700;'>Win Rate</div>
            <div style='font-size:26px;font-weight:800;color:{success_color};'>{success_display}</div>
          </div>
        </div>
        <div style='font-size:12px;color:#64748b;margin-top:4px;'>Avg Confidence: <b>{avg_conf:.1f}%</b></div>
        """
        render_content_card("Trade Performance Summary", stat_html)

        # Date filter UI
        col1, col2, col3 = st.columns([1.5, 0.8, 2.7])
        with col1:
            st.date_input(
                "Filter History by Date",
                value=st.session_state.date_filter_val,
                max_value=today,
                key="history_date_filter"
            )
        with col2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Reset Filter", type="secondary", use_container_width=True):
                st.session_state.date_filter_val = (default_start, today)
                if "history_date_filter" in st.session_state:
                    del st.session_state["history_date_filter"]
                st.rerun()

        if not trade_records:
            st.info("No trade signals found in the selected date range.")
        else:

            # ── Build table rows ──────────────────────────────────────────────
            rows = []
            for r in trade_records:
                # Opened timestamp
                raw_open = r.get("logged_at", "")
                try:
                    open_dt  = _dt.datetime.fromisoformat(raw_open.replace("Z", "+00:00"))
                    open_str = open_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    open_str = raw_open[:16] if len(raw_open) >= 16 else (raw_open or "--")
                    open_dt  = None

                # Closed timestamp & duration
                raw_close = r.get("closed_at", "")
                if raw_close:
                    try:
                        close_dt  = _dt.datetime.fromisoformat(raw_close.replace("Z", "+00:00"))
                        close_str = close_dt.strftime("%Y-%m-%d %H:%M UTC")
                        if open_dt:
                            total_min    = int((close_dt - open_dt).total_seconds() // 60)
                            duration_str = (f"{total_min // 60}h {total_min % 60}m"
                                            if total_min >= 60 else f"{total_min}m")
                        else:
                            duration_str = "--"
                    except Exception:
                        close_str    = raw_close[:16] if len(raw_close) >= 16 else "--"
                        duration_str = "--"
                else:
                    close_str    = "—"
                    duration_str = "Active"

                # Status
                outcome    = r.get("outcome", "OPEN") or "OPEN"
                status_map = {
                    "OPEN":                    "🔵 Active",
                    "TP_HIT":                  "✅ TP Hit",
                    "SL_HIT":                  "❌ SL Hit",
                    "CLOSED_BY_SIGNAL_CHANGE": "🔄 Signal Changed",
                }
                status_str = status_map.get(outcome, f"⏳ {outcome}")

                sig    = r.get("signal", "--")
                conf   = float(r.get("confidence", 0) or 0)
                rr_val = r.get("rr_ratio") or 0

                rows.append({
                    "Opened":     open_str,
                    "Closed":     close_str,
                    "Duration":   duration_str,
                    "Currency":   r.get("symbol", "--"),
                    "Trade":      sig,
                    "Confidence": f"{conf:.1f}%",
                    "Entry":      format_price(r.get("entry")),
                    "Stop Loss":  format_price(r.get("stop_loss")),
                    "TP1":        format_price(r.get("tp1")),
                    "TP2":        format_price(r.get("tp2")),
                    "R : R":      f"{float(rr_val):.2f}" if rr_val else "--",
                    "Status":     status_str,
                })

            hist_df = pd.DataFrame(rows)

            # ── Styling ───────────────────────────────────────────────────────
            _SIG_COLORS = {
                "BUY":         "color: #15803d; font-weight: 700",
                "STRONG_BUY":  "color: #166534; font-weight: 800",
                "SELL":        "color: #b91c1c; font-weight: 700",
                "STRONG_SELL": "color: #991b1b; font-weight: 800",
            }

            def _style_cell(val):
                v = str(val)
                if v in _SIG_COLORS:
                    return _SIG_COLORS[v]
                if "TP Hit" in v:
                    return "color: #15803d; font-weight: 700"
                if "SL Hit" in v:
                    return "color: #b91c1c; font-weight: 700"
                if "Active" in v:
                    return "color: #6d28d9; font-weight: 700"
                if "Signal Changed" in v:
                    return "color: #b45309; font-weight: 700"
                return ""

            try:
                styled = hist_df.style.map(_style_cell, subset=["Trade", "Status"])
            except AttributeError:
                styled = hist_df.style.applymap(_style_cell, subset=["Trade", "Status"])  # type: ignore[attr-defined]

            render_content_card(
                f"📋 Trade Signal Log — {total_trades} position(s) · {open_count} active",
                "One row per unique trade. Active positions stay open until SL/TP is hit or the signal direction flips."
            )
            st.dataframe(styled, use_container_width=True, height=540)

with levels_tab:
    render_section_header(
        "📐 Smart Money Concepts (SMC) & Levels",
        "Deep structural intelligence — Support/Resistance zones, Fair Value Gaps (FVG), Order Blocks (OB), Liquidity Sweeps, and BOS/CHOCH structural breaks."
    )

    # Top stats grid: Trend, Phase, BOS, CHOCH
    _trend_col = bundle.structure.trend.upper() if bundle.structure.trend else "N/A"
    _phase_col = bundle.structure.phase.upper() if bundle.structure.phase else "N/A"
    _bos_col = bundle.structure.bos.upper().replace("_", " ") if bundle.structure.bos else "NONE"
    _choch_col = bundle.structure.choch.upper().replace("_", " ") if bundle.structure.choch else "NONE"
    _liq_col = bundle.structure.liquidity_sweep.upper().replace("_", " ") if bundle.structure.liquidity_sweep else "NONE"

    st.markdown(
        f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; padding: 16px; background: rgba(255, 255, 255, 0.95); border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 20px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04); backdrop-filter: blur(10px);'>
            <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
                <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;'>SMC Trend</div>
                <div style='font-size: 16px; font-weight: 800; color: {"#16a34a" if "BULLISH" in _trend_col else ("#dc2626" if "BEARISH" in _trend_col else "#64748b")}; margin-top: 4px;'>{_trend_col}</div>
            </div>
            <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
                <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;'>Market Phase</div>
                <div style='font-size: 16px; font-weight: 800; color: #0f172a; margin-top: 4px;'>{_phase_col}</div>
            </div>
            <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
                <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;'>BOS State</div>
                <div style='font-size: 15px; font-weight: 800; color: {"#16a34a" if "BULLISH" in _bos_col else ("#dc2626" if "BEARISH" in _bos_col else "#475569")}; margin-top: 4px;'>{_bos_col}</div>
            </div>
            <div style='border-right: 1px solid rgba(148, 163, 184, 0.15); padding-right: 10px;'>
                <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;'>CHOCH State</div>
                <div style='font-size: 15px; font-weight: 800; color: {"#16a34a" if "BULLISH" in _choch_col else ("#dc2626" if "BEARISH" in _choch_col else "#475569")}; margin-top: 4px;'>{_choch_col}</div>
            </div>
            <div>
                <div style='font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;'>Liquidity Sweep</div>
                <div style='font-size: 14px; font-weight: 800; color: {"#16a34a" if "BUY" in _liq_col else ("#dc2626" if "SELL" in _liq_col else "#475569")}; margin-top: 4px;'>{_liq_col}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    _levels_left, _levels_right = st.columns([1.1, 1], gap="large")

    with _levels_left:
        # Support & Resistance Zones
        render_content_card(
            "🧱 Supply & Demand Order Zones (S/R)",
            "Key institutional horizontal support and resistance zones. Touches indicate level strength."
        )
        if bundle.zones:
            _zone_rows = []
            for z in bundle.zones:
                _zone_rows.append({
                    "Type": "Resistance 🔴" if z.type == "resistance" else "Support 🟢",
                    "Top Bound": f"{z.top:.5f}",
                    "Bottom Bound": f"{z.bottom:.5f}",
                    "Strength": f"{z.strength:.1f}",
                    "Touches": z.touches,
                    "HTF Aligned": "Yes ✅" if z.htf_aligned else "No",
                    "Vol Validated": "Yes ✅" if z.volume_validated else "No"
                })
            st.dataframe(pd.DataFrame(_zone_rows), use_container_width=True, height=220)
        else:
            st.info("No S/R zones detected in this lookback region.")

        # Order Blocks (OB)
        render_content_card(
            "📦 SMC Order Blocks (OB)",
            "Areas where institutional market makers place heavy block orders before a breakout."
        )
        _ob_list = bundle.structure.order_blocks or []
        if _ob_list:
            _ob_rows = []
            for ob in _ob_list:
                _ob_rows.append({
                    "Type": "Bullish OB 🟢" if ob.get("type") == "bullish_ob" else "Bearish OB 🔴",
                    "High Price": f"{float(ob.get('high', 0.0)):.5f}",
                    "Low Price": f"{float(ob.get('low', 0.0)):.5f}",
                    "Mitigation Index": ob.get("index", "unmitigated")
                })
            st.dataframe(pd.DataFrame(_ob_rows), use_container_width=True, height=200)
        else:
            st.info("No active Order Blocks detected in the current range.")

    with _levels_right:
        # Fair Value Gaps (FVG)
        render_content_card(
            "⚡ Fair Value Gaps (FVG) / Imbalances",
            "Inefficient candle spreads left by rapid market expansion. Often retested or filled."
        )
        _fvg_list = bundle.structure.imbalances or []
        if _fvg_list:
            _fvg_rows = []
            for fvg in _fvg_list:
                _fvg_rows.append({
                    "Type": "Bullish FVG 🟢" if fvg.get("type") == "bullish" else "Bearish FVG 🔴",
                    "Gap Low": f"{float(fvg.get('low', 0.0)):.5f}",
                    "Gap High": f"{float(fvg.get('high', 0.0)):.5f}",
                    "Gap Midpoint": f"{float(fvg.get('avg', 0.0)):.5f}",
                })
            st.dataframe(pd.DataFrame(_fvg_rows), use_container_width=True, height=220)
        else:
            st.info("No Fair Value Gaps (FVG) detected in this price leg.")

        # Swing Highs & Lows (Swing Structure)
        render_content_card(
            "📐 Swing Points History",
            "Recent key swing points (HH/HL/LH/LL) mapping the market structure profile."
        )
        _swings = bundle.structure.swing_points or {}
        _swing_rows = []
        for grp, pts in _swings.items():
            for p in pts:
                _swing_rows.append({
                    "Point Type": p.get("label", "").upper(),
                    "Price Level": f"{float(p.get('price', 0.0)):.5f}",
                    "Bar Timestamp": p.get("timestamp", "").replace("T", " ")[:16]
                })
        if _swing_rows:
            _swing_rows = sorted(_swing_rows, key=lambda s: s["Bar Timestamp"], reverse=True)
            st.dataframe(pd.DataFrame(_swing_rows[:20]), use_container_width=True, height=200)
        else:
            st.info("No swing points logged in this window.")

# ── Live Mode Auto-Refresh Loop ──
if st.session_state.get("live_mode", False):
    sess_id = st.session_state.get("session_uuid")
    visibility_state = live_analysis_manager.tab_visibility.get(sess_id, "visible")
    
    if visibility_state == "hidden":
        sleep_duration = 15.0
    else:
        sleep_duration = 1.0
        
    import time
    time.sleep(sleep_duration)
    st.rerun()
