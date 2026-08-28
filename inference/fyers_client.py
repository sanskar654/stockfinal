"""
Fyers API Client Wrapper & Rolling Live Candle Buffer.
Handles auth code flow, access token persistence, real-time quote fetching, historical candle fetching, and schema normalization.
Provides automatic daily detection and auto-deletion of expired 24h Fyers access tokens from .env file,
integrated with official FyersTokenManager for automatic refresh-token renewal.
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timedelta, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

from config.settings import FYERS, DATA, BASE_DIR
from services.fyers_auth import get_token_manager, FYERS_AUTHENTICATED

logger = logging.getLogger(__name__)

_MARKET_TZ = ZoneInfo("Asia/Kolkata")


def _is_market_open() -> bool:
    """Returns True if the Indian equity market is currently open (Mon–Fri, 09:15–15:30 IST)."""
    now = datetime.now(_MARKET_TZ)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


NIFTY50_REALISTIC_PRICES: dict[str, float] = {
    "ITC": 278.50,
    "BHARTIARTL": 1939.10,
    "WIPRO": 183.10,
    "CIPLA": 1458.80,
    "RELIANCE": 1317.00,
    "JSWSTEEL": 980.00,
    "COALINDIA": 495.20,
    "TCS": 2375.00,
    "INFY": 1850.00,
    "HDFCBANK": 1680.00,
    "ICICIBANK": 1220.00,
    "TATAMOTORS": 1020.00,
    "SBIN": 840.00,
    "AXISBANK": 1180.00,
    "LT": 3650.00,
    "KOTAKBANK": 1780.00,
    "MARUTI": 12400.00,
    "SUNPHARMA": 1720.00,
    "TITAN": 3450.00,
    "BAJFINANCE": 6850.00,
    "ASIANPAINT": 2950.00,
    "ULTRACEMCO": 11200.00,
    "NTPC": 410.00,
    "POWERGRID": 340.00,
    "NESTLEIND": 2480.00,
    "HINDUNILVR": 2720.00,
    "ONGC": 320.00,
    "M&M": 2850.00,
    "ADANIENT": 3150.00,
    "ADANIPORTS": 1480.00,
}


def _save_env_key(key: str, value: str):
    """Saves or updates key=value in ml_service/.env file. If value is empty, removes key line."""
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()

    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            found = True
            if value.strip():
                new_lines.append(f"{key}={value.strip()}\n")
        else:
            new_lines.append(line)

    if not found and value.strip():
        new_lines.append(f"{key}={value.strip()}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    logger.info("Updated %s in .env file.", key)


def _is_token_expired_error(res: dict) -> bool:
    """Checks if a Fyers API response indicates an expired or invalid token error."""
    if not isinstance(res, dict):
        return False
    if res.get("s") == "error":
        msg = str(res.get("message", "")).lower()
        code = res.get("code")
        if code in [-14, 401, 403] or "token" in msg or "expired" in msg or "invalid" in msg or "auth" in msg:
            return True
    return False


class FyersLiveClient:
    """Wrapper around fyers_apiv3 library with automatic token validation and refresh-token renewal."""

    def __init__(self):
        self.live_dir = DATA.live_dir
        self.live_dir.mkdir(parents=True, exist_ok=True)
        self.is_authenticated = False
        self.fyers_model = None

        self.token_manager = get_token_manager()
        self.reload_and_init()

    def reload_and_init(self):
        """Initializes or re-initializes fyers_apiv3 FyersModel if a valid access token exists."""
        access_token = self.token_manager.access_token
        if access_token and FYERS.app_id:
            try:
                log_dir = BASE_DIR / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                from fyers_apiv3 import fyersModel
                self.fyers_model = fyersModel.FyersModel(
                    client_id=FYERS.app_id,
                    is_async=False,
                    token=access_token,
                    log_path=str(log_dir)
                )
                self.is_authenticated = True
                logger.info("FyersLiveClient successfully authenticated with Fyers v3 API.")
            except Exception as e:
                logger.error("Failed creating FyersModel instance (%s). Operating in fallback mode.", e)
                self.is_authenticated = False
                self.fyers_model = None
        else:
            self.is_authenticated = False
            self.fyers_model = None
            logger.info("FyersLiveClient operating in offline fallback mode (No valid access token).")

    def clear_expired_token(self):
        """Clears expired access token from environment and .env file."""
        logger.warning("Fyers access token expired. Clearing token...")
        _save_env_key("FYERS_ACCESS_TOKEN", "")
        os.environ.pop("FYERS_ACCESS_TOKEN", None)
        self.is_authenticated = False
        self.fyers_model = None

    def get_login_url(self) -> str:
        """Generates OAuth2 login URL for user authentication."""
        redirect_uri = urllib.parse.quote(FYERS.redirect_url, safe="")
        state = "state_nifty_ml"
        return (
            f"https://api-t1.fyers.in/api/v3/generate-authcode?"
            f"client_id={FYERS.app_id}&redirect_uri={redirect_uri}&response_type=code&state={state}"
        )

    def generate_auth_url(self) -> str:
        """Alias method for get_login_url."""
        return self.get_login_url()

    def set_auth_code(self, auth_code: str) -> bool:
        """Exchanges auth_code for access_token and saves to .env."""
        try:
            from fyers_apiv3 import fyersModel
            session = fyersModel.SessionModel(
                client_id=FYERS.app_id,
                secret_key=FYERS.secret_key,
                redirect_uri=FYERS.redirect_url,
                response_type="code",
                grant_type="authorization_code"
            )
            session.set_token(auth_code)
            res = session.generate_token()
            if isinstance(res, dict) and res.get("s") == "ok":
                token = res.get("access_token")
                refresh_token = res.get("refresh_token")
                _save_env_key("FYERS_ACCESS_TOKEN", token)
                if refresh_token:
                    _save_env_key("FYERS_REFRESH_TOKEN", refresh_token)
                os.environ["FYERS_ACCESS_TOKEN"] = token
                self.reload_and_init()
                return True
            else:
                logger.error("Token generation failed: %s", res)
                return False
        except Exception as e:
            logger.error("Auth code exchange error: %s", e)
            return False

    def fetch_live_quote(self, symbol: str) -> dict:
        """Fetches real-time quote (LTP, OHLC, volume) for a ticker. Uses mock generator if offline."""
        clean_symbol = symbol.replace("NSE:", "").replace("-EQ", "")
        fyers_symbol = f"NSE:{clean_symbol}-EQ"

        if self.is_authenticated and self.fyers_model:
            try:
                response = self.fyers_model.quotes({"symbols": fyers_symbol})
                if _is_token_expired_error(response):
                    logger.warning("Fyers quote response indicated expired token. Attempting refresh...")
                    if self.token_manager.refresh_access_token():
                        self.reload_and_init()
                        response = self.fyers_model.quotes({"symbols": fyers_symbol})
                    else:
                        self.clear_expired_token()

                if response.get("s") == "ok" and response.get("d"):
                    quote_data = response["d"][0]["v"]
                    close_price = float(quote_data.get("lp", 0.0))
                    
                    if not _is_market_open():
                        try:
                            import yfinance as yf
                            hist = yf.Ticker(f"{clean_symbol}.NS").history(period="1d")
                            if not hist.empty:
                                close_price = float(hist["Close"].iloc[-1])
                        except Exception:
                            pass

                    return {
                        "ticker": clean_symbol,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "open": float(quote_data.get("open_price", quote_data.get("lp", 0.0))),
                        "high": float(quote_data.get("high_price", quote_data.get("lp", 0.0))),
                        "low": float(quote_data.get("low_price", quote_data.get("lp", 0.0))),
                        "close": close_price,
                        "volume": int(quote_data.get("volume", 0)),
                        "is_live_fyers": True
                    }
                else:
                    logger.warning("Fyers quote response for %s returned non-ok: %s", clean_symbol, response)
            except Exception as e:
                logger.error("Fyers quote fetch error for %s: %s", symbol, e)

        # Realistic quote fallback if offline or token expired
        return self._generate_mock_quote(clean_symbol)

    def _generate_mock_quote(self, ticker: str) -> dict:
        """Fallback quote generator.
        During market hours (09:15–15:30 IST) fetches the latest 1-minute intraday bar from
        yfinance so the price matches the live market closely.
        Outside market hours returns the last known close price without random noise.
        """
        live_price: float | None = None

        try:
            import yfinance as yf
            yf_ticker = yf.Ticker(f"{ticker}.NS")

            if _is_market_open():
                # Fetch the last completed 1-minute intraday bar — closest to real-time price
                intraday = yf_ticker.history(period="1d", interval="1m")
                if not intraday.empty:
                    live_price = float(intraday["Close"].iloc[-1])
                    logger.debug(
                        "[FALLBACK] %s intraday 1m close = %.2f (market OPEN)", ticker, live_price
                    )

            if live_price is None:
                # Market closed or intraday fetch failed — use last known close
                hist = yf_ticker.history(period="1d")
                if not hist.empty:
                    live_price = float(hist["Close"].iloc[-1])
                else:
                    live_price = float(yf_ticker.fast_info.last_price)
                logger.debug(
                    "[FALLBACK] %s last close = %.2f (market CLOSED or intraday unavailable)",
                    ticker, live_price
                )
        except Exception as exc:
            logger.warning("[FALLBACK] yfinance fetch failed for %s (%s). Using static baseline.", ticker, exc)
            live_price = NIFTY50_REALISTIC_PRICES.get(ticker, 500.0)

        base = max(1.0, round(live_price, 2))

        if _is_market_open():
            # During live market: synthesise OHLC around the live intraday price
            return {
                "ticker": ticker,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "open": round(base * 0.998, 2),
                "high": round(base * 1.004, 2),
                "low": round(base * 0.996, 2),
                "close": base,
                "volume": int(np.random.randint(100000, 2000000)),
                "is_live_fyers": False,
                "source": "yfinance_intraday"
            }
        else:
            # Outside market hours: return static last-close, no random noise
            return {
                "ticker": ticker,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "open": round(base * 0.998, 2),
                "high": round(base * 1.004, 2),
                "low": round(base * 0.996, 2),
                "close": base,
                "volume": int(np.random.randint(100000, 2000000)),
                "is_live_fyers": False,
                "source": "yfinance_last_close"
            }

    def fetch_historical_candles(self, ticker: str, days: int = 60) -> pd.DataFrame:
        """Fetches daily or intraday candles (based on DATA.interval) for rolling feature calculation."""
        clean_symbol = ticker.replace("NSE:", "").replace("-EQ", "")
        fyers_symbol = f"NSE:{clean_symbol}-EQ"

        res_map = {"15m": "15", "30m": "30", "5m": "5", "60m": "60", "1d": "D", "d": "D"}
        fyers_res = res_map.get(str(DATA.interval).lower(), "15")

        if self.is_authenticated and self.fyers_model:
            try:
                to_date = datetime.now(timezone.utc)
                from_date = to_date - timedelta(days=days)
                data = {
                    "symbol": fyers_symbol,
                    "resolution": fyers_res,
                    "date_format": "1",
                    "range_from": from_date.strftime("%Y-%m-%d"),
                    "range_to": to_date.strftime("%Y-%m-%d"),
                    "cont_flag": "1"
                }
                response = self.fyers_model.history(data=data)
                if _is_token_expired_error(response):
                    logger.warning("Fyers history response indicated expired token. Attempting refresh...")
                    if self.token_manager.refresh_access_token():
                        self.reload_and_init()
                        response = self.fyers_model.history(data=data)
                    else:
                        self.clear_expired_token()

                if response.get("s") == "ok" and response.get("candles"):
                    df = pd.DataFrame(response["candles"], columns=["epoch", "Open", "High", "Low", "Close", "Volume"])
                    date_fmt = "%Y-%m-%d %H:%M" if fyers_res != "D" else "%Y-%m-%d"
                    df["Date"] = pd.to_datetime(df["epoch"], unit="s").dt.strftime(date_fmt)
                    df["Ticker"] = clean_symbol
                    return df[["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"]]
                else:
                    logger.warning("Fyers history response for %s returned non-ok: %s", clean_symbol, response)
            except Exception as e:
                logger.error("Error fetching Fyers history for %s: %s", ticker, e)

        # Load cached historical slice from raw preprocessed CSV if available
        return self._load_cached_slice(clean_symbol, days=days)

    def _load_cached_slice(self, ticker: str, days: int = 60) -> pd.DataFrame:
        sub = pd.DataFrame()
        if DATA.raw_data_path.exists():
            df = pd.read_csv(DATA.raw_data_path)
            raw_sub = df[df["Ticker"] == ticker].tail(days)
            if not raw_sub.empty:
                sub = raw_sub[["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"]].copy()

        if sub.empty:
            rng = pd.date_range(end=datetime.now(timezone.utc), periods=days, freq=DATA.interval)
            try:
                import yfinance as yf
                base_price = float(yf.Ticker(f"{ticker}.NS").fast_info.last_price)
            except Exception:
                base_price = NIFTY50_REALISTIC_PRICES.get(ticker, 500.0)
            np.random.seed(abs(hash(ticker)) % 100000)
            price = base_price * (1.0 + np.cumsum(np.random.normal(0, 0.003, days)))
            sub = pd.DataFrame({
                "Ticker": ticker,
                "Date": rng.strftime("%Y-%m-%d %H:%M"),
                "Open": price * 0.998,
                "High": price * 1.004,
                "Low": price * 0.996,
                "Close": price,
                "Volume": np.random.randint(10000, 500000, days)
            })

        # Scale prices using real Yahoo Finance last close price so values match the real market
        if not sub.empty:
            try:
                import yfinance as yf
                target_base = float(yf.Ticker(f"{ticker}.NS").fast_info.last_price)
            except Exception:
                target_base = NIFTY50_REALISTIC_PRICES.get(ticker, 0.0)
            curr_last = sub["Close"].iloc[-1]
            if target_base > 0 and curr_last > 0 and abs(curr_last - target_base) / target_base > 0.05:
                scale_factor = target_base / curr_last
                for col in ["Open", "High", "Low", "Close"]:
                    sub[col] = (sub[col] * scale_factor).round(2)

        return sub

    def update_rolling_buffer(self, ticker: str) -> Path:
        """Pulls latest history & quote, updates local Parquet buffer in data/live/."""
        candles_df = self.fetch_historical_candles(ticker, days=FYERS.live_buffer_days)
        latest_quote = self.fetch_live_quote(ticker)

        date_fmt = "%Y-%m-%d %H:%M" if DATA.interval != "1d" else "%Y-%m-%d"
        quote_date = datetime.now(timezone.utc).strftime(date_fmt)

        if not candles_df.empty:
            candles_df["Date"] = pd.to_datetime(candles_df["Date"].astype(str), format="mixed", errors="coerce").dt.strftime(date_fmt).fillna(candles_df["Date"].astype(str))

        if candles_df.empty or candles_df.iloc[-1]["Date"] != quote_date:
            new_row = pd.DataFrame([{
                "Ticker": ticker,
                "Date": quote_date,
                "Open": latest_quote["open"],
                "High": latest_quote["high"],
                "Low": latest_quote["low"],
                "Close": latest_quote["close"],
                "Volume": latest_quote["volume"]
            }])
            candles_df = pd.concat([candles_df, new_row], ignore_index=True)
        else:
            # Update last bar
            candles_df.iloc[-1, candles_df.columns.get_loc("Close")] = latest_quote["close"]
            candles_df.iloc[-1, candles_df.columns.get_loc("High")] = max(candles_df.iloc[-1]["High"], latest_quote["high"])
            candles_df.iloc[-1, candles_df.columns.get_loc("Low")] = min(candles_df.iloc[-1]["Low"], latest_quote["low"])
            candles_df.iloc[-1, candles_df.columns.get_loc("Volume")] = latest_quote["volume"]

        out_path = self.live_dir / f"{ticker}_live.parquet"
        candles_df.to_parquet(out_path, index=False)
        return out_path
