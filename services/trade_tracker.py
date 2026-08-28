import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trades.db")

class TradeTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database and creates the trades table if it doesn't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    qty INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    initial_stop_loss REAL NOT NULL,
                    current_stop_loss REAL NOT NULL,
                    target_price REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            conn.commit()

    def add_trade(self, ticker: str, entry_price: float, qty: int, direction: str, 
                  stop_loss: float, target_price: float) -> int:
        """Adds a new active trade to be monitored."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (ticker, entry_price, qty, direction, initial_stop_loss, 
                                   current_stop_loss, target_price, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, entry_price, qty, direction, stop_loss, stop_loss, target_price, 'ACTIVE', now, now))
            conn.commit()
            return cursor.lastrowid

    def get_active_trades(self) -> List[Dict[str, Any]]:
        """Returns all currently active trades."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status = 'ACTIVE'")
            return [dict(row) for row in cursor.fetchall()]
            
    def get_all_trades(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def update_stop_loss(self, trade_id: int, new_stop_loss: float):
        """Updates the trailing stop loss for a trade."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades 
                SET current_stop_loss = ?, updated_at = ?
                WHERE id = ?
            ''', (new_stop_loss, now, trade_id))
            conn.commit()
            
    def update_status(self, trade_id: int, new_status: str):
        """Updates the status of a trade (e.g. CLOSED_PROFIT, CLOSED_LOSS, EXITED_REVERSAL)."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades 
                SET status = ?, updated_at = ?
                WHERE id = ?
            ''', (new_status, now, trade_id))
            conn.commit()

_trade_tracker = None

def get_trade_tracker() -> TradeTracker:
    global _trade_tracker
    if _trade_tracker is None:
        _trade_tracker = TradeTracker()
    return _trade_tracker
