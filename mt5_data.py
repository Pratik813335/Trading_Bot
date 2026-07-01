import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH

MT5_TIMEFRAMES = {
    "1": mt5.TIMEFRAME_M1,
    "5": mt5.TIMEFRAME_M5,
    "15": mt5.TIMEFRAME_M15,
    "30": mt5.TIMEFRAME_M30,
    "60": mt5.TIMEFRAME_H1,
    "240": mt5.TIMEFRAME_H4,
    "D": mt5.TIMEFRAME_D1,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1
}

_mt5_available = True
_last_mt5_attempt_time = 0.0
_mt5_cooldown_seconds = 30.0

def find_mt5_symbol(symbol):
    try:
        initialize_mt5()
    except Exception as e:
        print(f"MT5 find_mt5_symbol initialization failed: {e}")
        return symbol
        
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return symbol
        
    symbol_upper = symbol.upper()
    # Check for exact match first
    for s in all_symbols:
        if s.name.upper() == symbol_upper:
            return s.name
            
    # Check for suffix/prefix match
    for s in all_symbols:
        if symbol_upper in s.name.upper():
            return s.name
            
    return symbol


def initialize_mt5():
    global _mt5_available, _last_mt5_attempt_time
    now = time.time()
    
    if not _mt5_available:
        if now - _last_mt5_attempt_time < _mt5_cooldown_seconds:
            remaining = int(_mt5_cooldown_seconds - (now - _last_mt5_attempt_time))
            raise Exception(f"MT5 is in cooldown (retrying in {remaining}s)")
        _mt5_available = True
        
    _last_mt5_attempt_time = now
    
    init_kwargs = {}
    if MT5_PATH:
        init_kwargs["path"] = MT5_PATH
        
    if not mt5.initialize(**init_kwargs):
        _mt5_available = False
        err_msg = f"MT5 initialize() failed, error code = {mt5.last_error()}"
        print(f"MT5 Error: {err_msg}")
        raise Exception(err_msg)
        
    # Connect to the specific account if credentials are provided
    if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
        try:
            login_id = int(MT5_LOGIN)
        except ValueError:
            raise Exception(f"MT5 Login Error: You provided an email ('{MT5_LOGIN}'). MT5 requires a numeric Account Number.")
            
        # Optimization: Skip login if already connected to this account
        acc_info = mt5.account_info()
        if acc_info is not None and getattr(acc_info, "login", None) == login_id:
            return True
            
        authorized = mt5.login(
            login=login_id,
            password=MT5_PASSWORD,
            server=MT5_SERVER
        )
        if not authorized:
            _mt5_available = False
            err_msg = f"Failed to connect MT5 account #{MT5_LOGIN} on server '{MT5_SERVER}'. Verify credentials. Error code: {mt5.last_error()}"
            print(f"MT5 Error: {err_msg}")
            raise Exception(err_msg)
    return True

def get_mt5_candles(symbol, timeframe="5", num_candles=500):
    # This will now raise a specific exception if login fails
    initialize_mt5()
    
    matched_symbol = find_mt5_symbol(symbol)
    mt5_tf = MT5_TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_M5)
    
    # Fetch rates from MT5
    rates = mt5.copy_rates_from_pos(matched_symbol, mt5_tf, 0, num_candles)

    if rates is None or len(rates) == 0:
        raise Exception(f"Failed to get real data for {symbol}. Make sure the symbol matches your broker exactly (e.g., 'EURUSDm' or 'XAUUSD.ex'). Error: {mt5.last_error()}")
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
    
    df.attrs["data_source"] = "mt5_live"
    return df