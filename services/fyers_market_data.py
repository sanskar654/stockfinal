"""
FYERS Real-Time Market Data Service & Market Hours Engine.
Handles Indian Stock Market timezone logic (Asia/Kolkata), exponential backoff reconnection,
runtime token expiration recovery, and real-time NIFTY 50 data streaming for backend endpoints.
Now integrates FyersDataSocket for millisecond-accurate live tick prices for all NIFTY 50 stocks.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional

from services.fyers_auth import get_token_manager, FYERS_AUTHENTICATED
from config.settings import FYERS

logger = logging.getLogger(__name__)

MARKET_TZ = ZoneInfo("Asia/Kolkata")


def get_market_status(now_dt: datetime | None = None) -> str:
    """Calculates Indian Equity Market status based on Asia/Kolkata timezone."""
    if now_dt is None:
        now_dt = datetime.now(MARKET_TZ)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=MARKET_TZ)
    else:
        now_dt = now_dt.astimezone(MARKET_TZ)

    # Saturday (5) & Sunday (6) are market holidays
    if now_dt.weekday() >= 5:
        return "CLOSED"

    t = now_dt.time()
    pre_start = dtime(9, 0)
    open_start = dtime(9, 15)
    market_close = dtime(15, 30)

    if pre_start <= t < open_start:
        return "PRE_MARKET"
    elif open_start <= t <= market_close:
        return "OPEN"
    else:
        return "CLOSED"


class FyersMarketDataManager:
    """Server-side market data connection manager with exponential backoff, runtime token recovery,
    and a FyersDataSocket live tick stream for millisecond-accurate prices across all NIFTY 50 stocks."""

    def __init__(self):
        self.token_manager = get_token_manager()
        self.fyers_model = None
        self.retry_count = 0
        self.max_backoff_seconds = 30
        self.last_quote_cache: Dict[str, Any] = {}

        # --- Live Tick WebSocket state ---
        # Maps "NSE:COALINDIA-EQ" -> latest LTP float from the WebSocket stream
        self._live_prices: Dict[str, float] = {}
        self._live_prices_lock = threading.Lock()
        self._ws_client = None
        self._ws_running = False
        self._subscribed_symbols: set = set()

    # ──────────────────────────────────────────────────────────────────
    # REST Model (fallback / initialization)
    # ──────────────────────────────────────────────────────────────────

    def _init_fyers_model(self) -> bool:
        """Initializes or refreshes the underlying FYERS SDK model instance."""
        if not self.token_manager.is_access_token_valid():
            logger.info("[INFO] Access token invalid/expired. Attempting token refresh...")
            if not self.token_manager.refresh_access_token():
                self.fyers_model = None
                return False

        try:
            from fyers_apiv3 import fyersModel
            model = fyersModel.FyersModel(
                client_id=FYERS.app_id,
                is_async=False,
                token=self.token_manager.access_token,
                log_path=str(FYERS.token_store_path.parent)
            )
            self.fyers_model = model
            self.retry_count = 0
            logger.info("[INFO] FYERS Market Data Model initialized successfully.")
            return True
        except Exception as e:
            logger.error("[ERROR] Failed to initialize FYERS Model: %s", e)
            self.fyers_model = None
            return False

    # ──────────────────────────────────────────────────────────────────
    # Live Tick WebSocket (primary price source)
    # ──────────────────────────────────────────────────────────────────

    def _on_ws_message(self, message: dict):
        """Called by FyersDataSocket for every incoming tick. Updates in-memory live price cache."""
        try:
            if isinstance(message, list):
                # Batch tick messages
                for tick in message:
                    self._process_tick(tick)
            elif isinstance(message, dict):
                self._process_tick(message)
        except Exception as e:
            logger.debug("[WS] Error processing tick message: %s", e)

    def _process_tick(self, tick: dict):
        """Extracts LTP from a single tick and stores it keyed by symbol."""
        symbol = tick.get("symbol")
        ltp = tick.get("ltp")
        if symbol and ltp is not None:
            with self._live_prices_lock:
                self._live_prices[symbol] = float(ltp)

    def _on_ws_error(self, message):
        logger.warning("[WS] FyersDataSocket error: %s", message)

    def _on_ws_close(self, message):
        logger.warning("[WS] FyersDataSocket closed: %s. Will attempt reconnect.", message)
        self._ws_running = False
        # Attempt reconnect after 10 seconds
        time.sleep(10)
        if self.token_manager.is_access_token_valid():
            self._connect_websocket()

    def _on_ws_open(self, message):
        logger.info("[WS] FyersDataSocket connected. Subscribing to %d symbols.", len(self._subscribed_symbols))
        # Re-subscribe if this is a reconnect
        if self._subscribed_symbols and self._ws_client:
            try:
                self._ws_client.subscribe(
                    symbols=list(self._subscribed_symbols),
                    data_type="SymbolUpdate"
                )
            except Exception as e:
                logger.error("[WS] Failed to re-subscribe on open: %s", e)

    def _connect_websocket(self):
        """Creates and connects the FyersDataSocket client in a background daemon thread."""
        try:
            from fyers_apiv3.FyersWebsocket import data_ws
            access_token = self.token_manager.access_token
            if not access_token:
                logger.warning("[WS] No access token available. Cannot start DataSocket.")
                return

            # FyersDataSocket expects token in "appid:accesstoken" format
            full_token = f"{FYERS.app_id}:{access_token}"

            self._ws_client = data_ws.FyersDataSocket(
                access_token=full_token,
                log_path=str(FYERS.token_store_path.parent),
                litemode=False,
                write_to_file=False,
                reconnect=True,
                on_connect=self._on_ws_open,
                on_close=self._on_ws_close,
                on_error=self._on_ws_error,
                on_message=self._on_ws_message,
            )
            self._ws_running = True
            # connect() is blocking — run in a daemon thread
            t = threading.Thread(target=self._ws_client.connect, daemon=True)
            t.start()
            logger.info("[WS] FyersDataSocket daemon thread started.")
        except Exception as e:
            logger.error("[WS] Failed to initialize FyersDataSocket: %s", e)
            self._ws_running = False

    def start_data_websocket(self):
        """Public entry point: starts the live data WebSocket stream.
        Called once at server startup. Safe to call multiple times."""
        if self._ws_running:
            return
        if not self.token_manager.is_access_token_valid():
            logger.warning("[WS] Skipping DataSocket start — access token is not valid.")
            return
        logger.info("[WS] Starting FyersDataSocket live tick stream...")
        self._connect_websocket()

    def subscribe_symbols(self, symbols: list):
        """Subscribes to live ticks for a list of Fyers symbols (e.g. 'NSE:COALINDIA-EQ').
        Call this after a user clicks Analyze to ensure that stock's price is streamed."""
        to_add = [s for s in symbols if s not in self._subscribed_symbols]
        if not to_add:
            return

        for s in to_add:
            self._subscribed_symbols.add(s)

        if self._ws_client and self._ws_running:
            try:
                self._ws_client.subscribe(symbols=to_add, data_type="SymbolUpdate")
                logger.info("[WS] Subscribed to live ticks for: %s", to_add)
            except Exception as e:
                logger.warning("[WS] Failed to subscribe symbols %s: %s", to_add, e)
        else:
            logger.info("[WS] Socket not yet running; symbols queued for subscription on connect: %s", to_add)

    def get_live_price(self, symbol: str) -> Optional[float]:
        """Returns the latest WebSocket tick price for a symbol, or None if not yet received."""
        with self._live_prices_lock:
            return self._live_prices.get(symbol)

    # ──────────────────────────────────────────────────────────────────
    # Unified Quote Fetcher (WebSocket-first, REST fallback)
    # ──────────────────────────────────────────────────────────────────

    def fetch_quote_with_retry(self, symbol: str = "NSE:NIFTY50-INDEX") -> Dict[str, Any]:
        """Fetches live market quote for symbol.
        Priority: 1) FyersDataSocket live tick (instant, exact), 2) REST API fallback."""
        clean_symbol = symbol if ":" in symbol else f"NSE:{symbol}-EQ"

        # ── Priority 1: WebSocket live price (millisecond accurate) ──
        ws_price = self.get_live_price(clean_symbol)
        if ws_price is not None:
            cached = self.last_quote_cache.get(clean_symbol, {})
            prev_close = cached.get("prev_close", ws_price)
            chg = round(ws_price - prev_close, 2)
            chg_pct = round((chg / prev_close * 100.0) if prev_close else 0.0, 2)
            quote_data = {
                "symbol": clean_symbol,
                "price": round(ws_price, 2),
                "change": chg,
                "change_percent": chg_pct,
                "open": cached.get("open", ws_price),
                "high": cached.get("high", ws_price),
                "low": cached.get("low", ws_price),
                "volume": cached.get("volume", 0),
                "timestamp": datetime.now(MARKET_TZ).isoformat(),
                "market_status": get_market_status(),
                "auth_status": self.token_manager.status,
                "is_live_fyers": True,
                "source": "websocket"
            }
            # Update cache with latest tick price
            self.last_quote_cache[clean_symbol] = {**self.last_quote_cache.get(clean_symbol, {}), **quote_data}
            return quote_data

        # ── Priority 2: REST API (legacy fallback) ──
        if not self.fyers_model:
            if not self._init_fyers_model():
                return self._fallback_quote(clean_symbol)

        backoff = min(2 ** self.retry_count, self.max_backoff_seconds)
        try:
            res = self.fyers_model.quotes({"symbols": clean_symbol})

            # Check if response indicates token expiration at runtime
            if isinstance(res, dict) and res.get("s") == "error":
                code = res.get("code")
                msg = str(res.get("message", "")).lower()
                if code in [-14, 401, 403] or "token" in msg or "expired" in msg:
                    logger.warning("[WARNING] Token expired during runtime. Refreshing FYERS token...")
                    if self.token_manager.refresh_access_token():
                        self._init_fyers_model()
                        res = self.fyers_model.quotes({"symbols": clean_symbol})

            if isinstance(res, dict) and res.get("s") == "ok" and res.get("d"):
                v = res["d"][0]["v"]
                lp = float(v.get("lp", v.get("prev_close_price", 0.0)))
                prev_close = float(v.get("prev_close_price", lp))
                chg = float(v.get("ch", lp - prev_close))
                chg_pct = float(v.get("chp", (chg / prev_close * 100.0) if prev_close else 0.0))

                quote_data = {
                    "symbol": clean_symbol,
                    "price": round(lp, 2),
                    "change": round(chg, 2),
                    "change_percent": round(chg_pct, 2),
                    "open": float(v.get("open_price", lp)),
                    "high": float(v.get("high_price", lp)),
                    "low": float(v.get("low_price", lp)),
                    "volume": int(v.get("volume", 0)),
                    "prev_close": prev_close,
                    "timestamp": datetime.now(MARKET_TZ).isoformat(),
                    "market_status": get_market_status(),
                    "auth_status": self.token_manager.status,
                    "is_live_fyers": True,
                    "source": "rest"
                }
                self.last_quote_cache[clean_symbol] = quote_data
                self.retry_count = 0
                return quote_data
            else:
                logger.warning("[WARNING] FYERS quote fetch returned non-ok: %s", res)
                self.retry_count += 1
                time.sleep(min(backoff, 2))
        except Exception as e:
            logger.error("[ERROR] FYERS connection failed during quote fetch: %s", e)
            self.retry_count += 1
            time.sleep(min(backoff, 2))

        return self._fallback_quote(clean_symbol)

    def _fallback_quote(self, symbol: str) -> Dict[str, Any]:
        """Provides graceful fallback quote using cached price or realistic baseline data when market is closed or unauthenticated."""
        if symbol in self.last_quote_cache:
            cached = self.last_quote_cache[symbol].copy()
            cached["is_live_fyers"] = False
            cached["market_status"] = get_market_status()
            cached["auth_status"] = self.token_manager.status
            return cached

        clean_symbol = symbol.replace("NSE:", "").replace("-EQ", "")
        price = None
        prev_close = None
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{clean_symbol}.NS")
            hist = ticker.history(period="5d", interval="1d")
            if not hist.empty:
                close_series = hist["Close"].dropna()
                if not close_series.empty:
                    prev_close = float(close_series.iloc[-2]) if len(close_series) > 1 else float(close_series.iloc[-1])
                    price = float(close_series.iloc[-1])
            if price is None:
                price = float(getattr(ticker.fast_info, "last_price", 0.0) or 0.0)
        except Exception:
            price = None

        if price is None or price <= 0:
            realistic_map = {
                "NIFTY50-INDEX": 24570.65,
                "ADANIENT": 3150.0,
                "ADANIPORTS": 1480.0,
                "ASIANPAINT": 2950.0,
                "AXISBANK": 1180.0,
                "BAJFINANCE": 6850.0,
                "BHARTIARTL": 1939.1,
                "BPCL": 560.0,
                "CIPLA": 1458.8,
                "COALINDIA": 495.2,
                "HDFCBANK": 1680.0,
                "ICICIBANK": 1220.0,
                "INFY": 1850.0,
                "ITC": 278.5,
                "JSWSTEEL": 980.0,
                "KOTAKBANK": 1780.0,
                "LT": 3650.0,
                "M&M": 2850.0,
                "MARUTI": 12400.0,
                "RELIANCE": 1317.0,
                "SBIN": 840.0,
                "SUNPHARMA": 1720.0,
                "TATAMOTORS": 1020.0,
                "TATASTEEL": 160.0,
                "TCS": 2375.0,
                "TECHM": 1470.0,
                "TITAN": 3450.0,
                "ULTRACEMCO": 11200.0,
                "WIPRO": 183.1,
            }
            price = float(realistic_map.get(clean_symbol, realistic_map.get("NIFTY50-INDEX", 500.0)))
            prev_close = price * 0.995

        if prev_close is None or prev_close <= 0:
            prev_close = price

        change = round(price - prev_close, 2)
        chg_pct = round((change / prev_close * 100.0) if prev_close else 0.0, 2)

        quote = {
            "symbol": symbol,
            "price": round(price, 2),
            "change": change,
            "change_percent": chg_pct,
            "timestamp": datetime.now(MARKET_TZ).isoformat(),
            "market_status": get_market_status(),
            "auth_status": self.token_manager.status,
            "is_live_fyers": False,
            "source": "fallback"
        }
        self.last_quote_cache[symbol] = quote
        return quote

    def get_nifty50_summary(self) -> Dict[str, Any]:
        """Returns clean NIFTY 50 market data payload for backend REST API endpoints."""
        quote = self.fetch_quote_with_retry("NSE:NIFTY50-INDEX")
        return {
            "symbol": quote["symbol"],
            "price": quote["price"],
            "change": quote["change"],
            "change_percent": quote["change_percent"],
            "timestamp": quote["timestamp"],
            "market_status": quote["market_status"],
            "auth_status": quote["auth_status"],
            "is_live": quote.get("is_live_fyers", False),
            "source": quote.get("source", "unknown")
        }


# Global Singleton Market Data Manager
_market_data_manager_instance: FyersMarketDataManager | None = None

def get_market_data_manager() -> FyersMarketDataManager:
    global _market_data_manager_instance
    if _market_data_manager_instance is None:
        _market_data_manager_instance = FyersMarketDataManager()
    return _market_data_manager_instance
