from core.signal_engine import generate_mtf_signal, generate_signal
from data.timeframe_builder import build_timeframe_map


def _resolve_trade_outcome(signal_result, future_candles, max_holding_bars=12):
    signal = signal_result["signal"]
    if signal not in ["BUY", "SELL"]:
        return None

    entry = signal_result["entry"]
    stop_loss = signal_result["stop_loss"]
    take_profit = signal_result["take_profit"]
    rr = signal_result["risk_reward"]
    if not stop_loss or not take_profit:
        return None

    future_window = future_candles.head(max_holding_bars)
    if future_window.empty:
        return None

    for _, candle in future_window.iterrows():
        high = float(candle["high"])
        low = float(candle["low"])

        if signal == "BUY":
            stop_hit = low <= stop_loss
            target_hit = high >= take_profit
            if stop_hit and target_hit:
                return {"result": "loss", "r_multiple": -1.0}
            if stop_hit:
                return {"result": "loss", "r_multiple": -1.0}
            if target_hit:
                return {"result": "win", "r_multiple": rr}
        else:
            stop_hit = high >= stop_loss
            target_hit = low <= take_profit
            if stop_hit and target_hit:
                return {"result": "loss", "r_multiple": -1.0}
            if stop_hit:
                return {"result": "loss", "r_multiple": -1.0}
            if target_hit:
                return {"result": "win", "r_multiple": rr}

    last_close = float(future_window.iloc[-1]["close"])
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return None

    if signal == "BUY":
        r_multiple = (last_close - entry) / risk
    else:
        r_multiple = (entry - last_close) / risk

    return {
        "result": "open" if r_multiple >= 0 else "loss",
        "r_multiple": round(r_multiple, 2),
    }


def run_backtest(df, timeframe="5", symbol="UNKNOWN", strategy_name="Auto", warmup_bars=50, max_holding_bars=12):
    candles = df.reset_index(drop=True).copy()
    trades = []
    equity_r = 0.0
    peak_equity_r = 0.0
    max_drawdown_r = 0.0
    consecutive_losses = 0
    max_consecutive_losses = 0

    for end_index in range(warmup_bars, len(candles) - 1):
        window = candles.iloc[: end_index + 1].copy()
        timeframe_map = build_timeframe_map(window, timeframe)
        signal_result = generate_mtf_signal(timeframe_map) if len(timeframe_map) > 1 else generate_signal(window)
        outcome = _resolve_trade_outcome(signal_result, candles.iloc[end_index + 1 :], max_holding_bars=max_holding_bars)
        if not outcome:
            continue

        trade_record = {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy_name,
            "index": end_index,
            "signal": signal_result["signal"],
            "confidence": signal_result["confidence"],
            "entry": signal_result["entry"],
            "stop_loss": signal_result["stop_loss"],
            "take_profit": signal_result["take_profit"],
            "risk_reward": signal_result["risk_reward"],
            "result": outcome["result"],
            "r_multiple": outcome["r_multiple"],
        }
        trades.append(trade_record)

        equity_r += outcome["r_multiple"]
        peak_equity_r = max(peak_equity_r, equity_r)
        max_drawdown_r = min(max_drawdown_r, equity_r - peak_equity_r)

        if outcome["r_multiple"] < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0

    # Calculate metrics
    wins = [trade for trade in trades if trade["r_multiple"] > 0]
    losses = [trade for trade in trades if trade["r_multiple"] < 0]
    
    avg_win = sum(trade["r_multiple"] for trade in wins) / len(wins) if wins else 0.0
    avg_loss = sum(trade["r_multiple"] for trade in losses) / len(losses) if losses else 0.0
    
    win_rate = (len(wins) / len(trades)) * 100 if trades else 0.0
    loss_rate = 100.0 - win_rate
    
    # Expectancy: (Win% * Avg Win R) + (Loss% * Avg Loss R)
    expectancy = (win_rate / 100.0 * avg_win) + (loss_rate / 100.0 * avg_loss)

    gross_profit = sum(trade["r_multiple"] for trade in wins)
    gross_loss = abs(sum(trade["r_multiple"] for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit else 0.0)

    # 200+ trade requirement check
    passed_200_gate = len(trades) >= 200
    requirement_warning = ""
    if not passed_200_gate:
        requirement_warning = f"Backtesting warning: {len(trades)} trades completed. At least 200+ trades are required before trusting strategy results."

    # Group by confidence buckets: High (>=70), Medium (55-69), Low (<55)
    buckets = {"high": [], "medium": [], "low": []}
    for t in trades:
        conf = t["confidence"]
        if conf >= 70:
            buckets["high"].append(t)
        elif conf >= 55:
            buckets["medium"].append(t)
        else:
            buckets["low"].append(t)
            
    bucket_stats = {}
    for name, b_trades in buckets.items():
        b_wins = len([t for t in b_trades if t["r_multiple"] > 0])
        b_total = len(b_trades)
        bucket_stats[name] = {
            "total": b_total,
            "win_rate": round((b_wins / b_total) * 100, 2) if b_total else 0.0
        }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy_name,
        "total_trades": len(trades),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_r": round(abs(max_drawdown_r), 2),
        "average_r": round(sum(trade["r_multiple"] for trade in trades) / len(trades), 2) if trades else 0.0,
        "consecutive_losses": max_consecutive_losses,
        "wins": len(wins),
        "losses": len(losses),
        "open_or_flat": len([trade for trade in trades if trade["r_multiple"] == 0]),
        "expectancy_r": round(expectancy, 2),
        "passed_200_gate": passed_200_gate,
        "requirement_warning": requirement_warning,
        "confidence_buckets": bucket_stats,
        "trades": trades[-25:],
    }
