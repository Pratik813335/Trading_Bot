import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv_file(path):
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_file(BASE_DIR / ".env")


INITIAL_BALANCE = 10000
RISK_PER_TRADE = 0.02
MIN_CONFIRMATION_CONFIDENCE = 60
MIN_CONFIRMATIONS = 4
MIN_SIGNAL_GAP = 20
MIN_SCORE = 55


# Central Bank Interest Rates (for Carry Trade Strategy)
CURRENCY_INTEREST_RATES = {
    "USD": 5.25,
    "EUR": 3.75,
    "GBP": 5.00,
    "AUD": 4.35,
    "NZD": 5.25,
    "JPY": 0.25,
    "CHF": 1.25,
    "CAD": 4.75,
}

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD" , "AUDUSD" ,"USDJPY", "USDCHF", "USDCAD"]
TIMEFRAMES = ["1", "5", "15", "30", "60", "240", "D"]

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash").strip()
MT5_LOGIN = os.getenv("MT5_LOGIN", "").strip()
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "").strip()
MT5_SERVER = os.getenv("MT5_SERVER", "").strip()
DATA_CSV_PATH = BASE_DIR / "data.csv"
SIGNAL_HISTORY_PATH = BASE_DIR / "storage" / "signal_history.jsonl"
NEWS_SIGNAL_HISTORY_PATH = BASE_DIR / "storage" / "news_signal_history.jsonl"
FOREXFACTORY_CACHE_TTL = 300   # seconds — 5-minute cache for FF calendar
NEWS_MAX_AGE_MINUTES = 180     # risk gate: ignore events older than this


ALPHA_VANTAGE_INTERVALS = {
    "1": "1min",
    "5": "5min",
    "15": "15min",
    "30": "30min",
    "60": "60min",
}

REQUIRED_OHLC_COLUMNS = ["time", "open", "high", "low", "close"]
