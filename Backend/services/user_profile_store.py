import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trades.db")


class UserProfileStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL,
                    username TEXT NOT NULL, phone TEXT NOT NULL, avatar_initials TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                    date TEXT NOT NULL, ticker TEXT NOT NULL, type TEXT NOT NULL,
                    qty INTEGER NOT NULL, price REAL NOT NULL, status TEXT, pnl REAL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_or_create_profile(self, user_id: str, values: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        values = values or {}
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM user_profiles WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO user_profiles VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, values.get("full_name", "John Doe"), values.get("email", "demo@virtuebyte.com"),
                     values.get("username", "johndoe"), values.get("phone", "9876543210"),
                     values.get("avatar_initials", "JD"), now),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM user_profiles WHERE id = ?", (user_id,)).fetchone()
            return dict(row)

    def update_profile(self, user_id: str, values: Dict[str, str]) -> Dict[str, Any]:
        profile = self.get_or_create_profile(user_id)
        full_name = values.get("full_name", profile["full_name"])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE user_profiles SET full_name = ?, email = ?, username = ?, phone = ?, avatar_initials = ? WHERE id = ?",
                (full_name, values.get("email", profile["email"]), values.get("username", profile["username"]),
                 values.get("phone", profile["phone"]), _initials(full_name), user_id),
            )
            conn.commit()
        return self.get_or_create_profile(user_id)

    def add_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        status = trade.get("status", "ACTIVE") if trade.get("pnl") is None else trade.get("status", "CLOSED")
        pnl_raw = trade.get("pnl")
        pnl_value = float(pnl_raw) if pnl_raw is not None else None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO user_trade_history (user_id, date, ticker, type, qty, price, status, pnl, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (trade["user_id"], trade["date"], trade["ticker"], trade["type"], trade["qty"], trade["price"], status, pnl_value, created_at),
            )
            conn.commit()
            trade_id = cursor.lastrowid
        return {**trade, "id": str(trade_id), "created_at": created_at, "status": status, "pnl": pnl_value}

    def close_trade(self, trade_id: int, exit_price: float) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM user_trade_history WHERE id = ?", (trade_id,)).fetchone()
            if not row:
                return None
            trade = dict(row)
            entry_price = float(trade["price"])
            qty = int(trade["qty"])
            trade_type = trade.get("type", "BUY").upper()
            if trade_type == "BUY":
                pnl = round((exit_price - entry_price) * qty, 2)
            else:
                pnl = round((entry_price - exit_price) * qty, 2)
            conn.execute(
                "UPDATE user_trade_history SET pnl = ?, status = 'CLOSED' WHERE id = ?",
                (pnl, trade_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM user_trade_history WHERE id = ?", (trade_id,)).fetchone()
            return dict(updated) if updated else None

    def get_trades(self, user_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM user_trade_history WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
            return [dict(row) for row in rows]


def _initials(full_name: str) -> str:
    parts = full_name.strip().split()
    if not parts:
        return "TR"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()


_profile_store: Optional[UserProfileStore] = None


def get_profile_store() -> UserProfileStore:
    global _profile_store
    if _profile_store is None:
        _profile_store = UserProfileStore()
    return _profile_store