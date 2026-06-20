import sqlite3
import pandas as pd
from datetime import datetime
import os

class TradeJournal:
    def __init__(self, db_path="trades.db"):
        os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            type TEXT,
            entry_price REAL,
            sl REAL,
            tp REAL,
            exit_price REAL,
            pnl REAL,
            status TEXT,
            open_time TEXT,
            close_time TEXT
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    def log_trade(self, symbol, type, entry_price, sl, tp, exit_price, pnl, status):
        query = """
        INSERT INTO trades (symbol, type, entry_price, sl, tp, exit_price, pnl, status, open_time, close_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(query, (symbol, type, entry_price, sl, tp, exit_price, pnl, status, now, now))
        self.conn.commit()

    def get_all_trades(self):
        try:
            return pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", self.conn)
        except Exception:
            return pd.DataFrame()