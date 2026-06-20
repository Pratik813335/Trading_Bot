import csv
import os
import subprocess
from pathlib import Path


COMMON_TIMEFRAME_MAP = {
    "1": "M1",
    "5": "M5",
    "15": "M15",
    "30": "M30",
    "60": "H1",
    "240": "H4",
    "D": "D1",
    "D1": "D1",
}


def _format_ts(value):
    if value in [None, ""]:
        return ""
    text = str(value)
    if "T" in text:
        text = text.replace("T", " ")
    return text.replace("Z", "").split("+")[0].strip()


def _hex_color(value):
    rgb = value.lstrip("#")
    if len(rgb) != 6:
        return "#FFFFFF"
    return f"#{rgb.upper()}"


def find_mt5_terminal():
    candidates = [
        os.getenv("MT5_TERMINAL_PATH", "").strip(),
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files\MetaTrader 5\terminal.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def get_mt5_common_files_dir():
    appdata = os.getenv("APPDATA", "")
    if not appdata:
        return None
    common_dir = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "codex_analysis"
    return common_dir


def build_mt5_objects(chart_payload):
    overlays = chart_payload.get("overlays") or {}
    candles = chart_payload.get("candles") or []
    if not candles:
        return []

    chart_start = _format_ts(candles[0].get("timestamp"))
    chart_end = _format_ts(candles[-1].get("timestamp"))
    objects = []

    def add_hline(name, price, color, text):
        if price in [None, "", 0, 0.0]:
            return
        objects.append(
            {
                "kind": "hline",
                "name": name,
                "time1": "",
                "price1": float(price),
                "time2": "",
                "price2": "",
                "color": _hex_color(color),
                "text": text,
            }
        )

    def add_rect(name, time1, price1, time2, price2, color, text):
        if price1 in [None, "", 0, 0.0] or price2 in [None, "", 0, 0.0]:
            return
        objects.append(
            {
                "kind": "rect",
                "name": name,
                "time1": _format_ts(time1),
                "price1": float(price1),
                "time2": _format_ts(time2),
                "price2": float(price2),
                "color": _hex_color(color),
                "text": text,
            }
        )

    def add_label(name, time1, price1, color, text):
        if price1 in [None, "", 0, 0.0]:
            return
        objects.append(
            {
                "kind": "label",
                "name": name,
                "time1": _format_ts(time1),
                "price1": float(price1),
                "time2": "",
                "price2": "",
                "color": _hex_color(color),
                "text": text,
            }
        )

    entry = overlays.get("entry")
    stop_loss = overlays.get("stop_loss")
    tp1 = overlays.get("tp1")
    tp2 = overlays.get("tp2")

    add_hline("entry", entry, "#2563EB", "Entry")
    add_hline("stop_loss", stop_loss, "#DC2626", "Stop Loss")
    add_hline("tp1", tp1, "#16A34A", "Take Profit 1")
    add_hline("tp2", tp2, "#15803D", "Take Profit 2")

    if entry not in [None, "", 0, 0.0] and stop_loss not in [None, "", 0, 0.0]:
        add_rect("entry_sl", chart_start, entry, chart_end, stop_loss, "#DC2626", "Entry to SL")

    for name, target in [("entry_tp1", tp1), ("entry_tp2", tp2)]:
        if entry not in [None, "", 0, 0.0] and target not in [None, "", 0, 0.0]:
            add_rect(name, chart_start, entry, chart_end, target, "#16A34A", name.replace("_", " ").title())

    for index, zone in enumerate(overlays.get("support_resistance") or []):
        color = "#16A34A" if zone.get("type") == "support" else "#DC2626"
        add_rect(
            f"{zone.get('type', 'zone')}_{index + 1}",
            chart_start,
            zone.get("bottom"),
            chart_end,
            zone.get("top"),
            color,
            f"{zone.get('type', 'zone').title()} {index + 1}",
        )

    for index, imbalance in enumerate(overlays.get("imbalances") or []):
        color = "#14B8A6" if imbalance.get("type") == "bullish" else "#F97316"
        add_rect(
            f"{imbalance.get('type', 'fvg')}_fvg_{index + 1}",
            imbalance.get("start_timestamp") or chart_start,
            imbalance.get("low"),
            chart_end,
            imbalance.get("high"),
            color,
            f"{imbalance.get('type', 'fvg').title()} FVG {index + 1}",
        )
        add_hline(
            f"{imbalance.get('type', 'fvg')}_avg_{index + 1}",
            imbalance.get("avg"),
            "#7C3AED",
            f"{imbalance.get('type', 'fvg').title()} AVG {index + 1}",
        )

    structure = ((overlays.get("structure") or {}).get("swing_points")) or {}
    swing_colors = {
        "hh": "#2563EB",
        "hl": "#16A34A",
        "lh": "#F97316",
        "ll": "#DC2626",
    }
    for group_name, points in structure.items():
        for index, point in enumerate(points):
            add_label(
                f"{group_name}_{index + 1}",
                point.get("timestamp"),
                point.get("price"),
                swing_colors.get(group_name, "#FFFFFF"),
                point.get("label", group_name.upper()),
            )

    return objects


def export_analysis_to_mt5(chart_payload, symbol, timeframe, export_root="storage/mt5_bridge"):
    objects = build_mt5_objects(chart_payload)
    export_dir = Path(export_root)
    export_dir.mkdir(parents=True, exist_ok=True)

    payload_path = export_dir / "analysis_payload.json"
    csv_path = export_dir / "mt5_objects.csv"
    manifest_path = export_dir / "manifest.txt"

    payload_path.write_text(
        __import__("json").dumps(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "mt5_timeframe": COMMON_TIMEFRAME_MAP.get(timeframe, timeframe),
                "chart_payload": chart_payload,
                "objects": objects,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["kind", "name", "time1", "price1", "time2", "price2", "color", "text"],
        )
        writer.writeheader()
        writer.writerows(objects)

    manifest_path.write_text(
        "\n".join(
            [
                f"symbol={symbol}",
                f"timeframe={timeframe}",
                f"mt5_timeframe={COMMON_TIMEFRAME_MAP.get(timeframe, timeframe)}",
                f"objects={len(objects)}",
                f"csv={csv_path.resolve()}",
                f"payload={payload_path.resolve()}",
            ]
        ),
        encoding="utf-8",
    )

    common_dir = get_mt5_common_files_dir()
    common_csv_path = None
    if common_dir is not None:
        common_dir.mkdir(parents=True, exist_ok=True)
        common_csv_path = common_dir / "mt5_objects.csv"
        common_payload_path = common_dir / "analysis_payload.json"
        common_manifest_path = common_dir / "manifest.txt"
        common_csv_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
        common_payload_path.write_text(payload_path.read_text(encoding="utf-8"), encoding="utf-8")
        common_manifest_path.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "object_count": len(objects),
        "csv_path": str(csv_path.resolve()),
        "payload_path": str(payload_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "common_csv_path": str(common_csv_path.resolve()) if common_csv_path else None,
        "terminal_path": find_mt5_terminal(),
    }


def open_mt5_terminal():
    terminal_path = find_mt5_terminal()
    if not terminal_path:
        return {"opened": False, "terminal_path": None, "message": "MetaTrader 5 terminal was not found in the default install paths."}

    subprocess.Popen([terminal_path], shell=False)
    return {"opened": True, "terminal_path": terminal_path, "message": "MetaTrader 5 launched."}
