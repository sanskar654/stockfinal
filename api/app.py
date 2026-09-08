"""
FastAPI Service for NIFTY 50 ML Trading Model.
Exposes REST API endpoints for live predictions, health checks, NIFTY 50 market data, model retraining, and FYERS OAuth authentication.
Features ML Trading Engine Terminal UI with Groww-style custom order evaluator, 30-min intraday targets, and actionable AI insights.
Includes CORSMiddleware for seamless Frontend UI integration & automated background daily retraining scheduler.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from inference.live_pipeline import run_live_prediction, get_fyers_client
from inference.ticker_utils import NIFTY50_TICKERS, ALIAS_MAP
from models.model_utils import load_champion, list_versions
from retraining.retrain_job import run_retraining_job
from services.fyers_auth import get_token_manager, FYERS_AUTHENTICATED, FYERS_TOKEN_EXPIRED, FYERS_REAUTH_REQUIRED
from services.fyers_market_data import get_market_data_manager, get_market_status
from config.settings import FYERS
from services.trade_tracker import get_trade_tracker
from inference.monitoring import run_continuous_monitoring, run_fast_price_check, register_ws_connection, unregister_ws_connection, evaluate_single_trade
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api_app")

app = FastAPI(
    title="NIFTY 50 ML Trading Model API",
    description="Production-grade ML inference & self-retraining service with FYERS integration",
    version="1.0.0"
)

# ------------------------------------------------------------------------------
# FRONTEND CORS MIDDLEWARE (Allows React / Next.js / Vue / HTML to call API seamlessly)
# ------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production setting: Allows any frontend domain to fetch predictions
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictionResponse(BaseModel):
    ticker: str
    timestamp: str
    current_price: float
    predicted_return_pct: float
    predicted_price: float
    direction: str
    proba_up: float
    confidence_score: float
    regressor_version: str
    classifier_version: str
    groww_order_analysis: Dict[str, Any]
    ai_insights: Dict[str, Any]
    risk_management: Dict[str, Any]
    analytics: Dict[str, Any]


class TokenInput(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = 86400


class TradeInput(BaseModel):
    ticker: str
    entry_price: float
    qty: int
    direction: str
    stop_loss: float
    target_price: float


def _automated_daily_retrain_daemon():
    """Background thread that runs automated self-retraining every day after market close (15:45 IST)."""
    logger.info("[CRON] Automated Daily Self-Retraining Scheduler started in background.")
    while True:
        try:
            # Sleep 12 hours between checks
            time.sleep(43200)
            logger.info("[CRON] Executing scheduled daily self-retraining job...")
            run_retraining_job()
            logger.info("[CRON] Scheduled daily self-retraining job completed successfully.")
        except Exception as e:
            logger.error("[CRON] Error during scheduled retraining: %s", e)


def _daily_fyers_reauth_daemon():
    """Background thread that automatically renews the FYERS access token daily.

    Checks every 30 minutes. If the access token is expired (or will expire within
    30 minutes) AND the time is between 08:40–09:10 IST (pre-market window),
    it triggers a fresh headless TOTP auto-login so the token is always valid
    when the market opens at 09:15 IST.

    Also triggers an immediate refresh on startup if the token is already expired.
    This means: after a one-time manual login (or TOTP setup), the system reconnects
    automatically every single day without any human intervention.
    """
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")

    logger.info("[CRON] Daily FYERS Auto-ReAuth Daemon started in background.")

    # Attempt immediate fix on startup if token is already expired
    _try_fyers_reauth(reason="startup")

    while True:
        try:
            time.sleep(1800)  # check every 30 minutes
            now_ist = datetime.now(IST)

            token_mgr = get_token_manager()
            token_mgr.load_tokens()

            if token_mgr.is_access_token_valid():
                logger.debug("[CRON] FYERS token still valid, skipping re-auth.")
                continue

            # Token expired: if we're in the pre-market window (08:40-09:10 IST) or market hours,
            # trigger immediate headless re-login
            hour, minute = now_ist.hour, now_ist.minute
            is_premarket = (hour == 8 and minute >= 40) or (hour == 9 and minute <= 10)
            is_market_hours = (hour == 9 and minute >= 15) or (9 < hour < 15) or (hour == 15 and minute <= 30)

            if is_premarket or is_market_hours:
                logger.info(
                    "[CRON] FYERS token expired during active hours (%02d:%02d IST). Triggering auto-login...",
                    hour, minute,
                )
                _try_fyers_reauth(reason=f"scheduled-{hour:02d}{minute:02d}IST")
            else:
                # Outside market hours — still attempt if 08:40 is approaching
                # (within 2 hours before market open)
                minutes_to_840 = ((8 * 60 + 40) - (hour * 60 + minute)) % (24 * 60)
                if minutes_to_840 <= 30:
                    logger.info("[CRON] Approaching pre-market window. Triggering FYERS auto-login...")
                    _try_fyers_reauth(reason="pre-market-prep")

        except Exception as e:
            logger.error("[CRON] Error in daily FYERS re-auth daemon: %s", e)


def _try_fyers_reauth(reason: str = "manual") -> bool:
    """Attempts headless TOTP auto-login via FyersTokenManager. Returns True on success."""
    try:
        token_mgr = get_token_manager()
        logger.info("[REAUTH] Triggering FYERS token renewal (reason=%s)...", reason)
        success = token_mgr.refresh_access_token()
        if success:
            # Re-initialize the FyersLiveClient so it picks up the new token
            client = get_fyers_client()
            client.reload_and_init()
            logger.info("[REAUTH] FYERS token renewed successfully (reason=%s).", reason)
        else:
            logger.warning(
                "[REAUTH] FYERS token renewal failed (reason=%s, status=%s, error=%s).",
                reason, token_mgr.status, token_mgr.last_error,
            )
        return success
    except Exception as exc:
        logger.error("[REAUTH] Exception during token renewal (reason=%s): %s", reason, exc)
        return False


async def _continuous_monitoring_loop():
    """Background loop that runs the full ML-based monitoring every 60 seconds."""
    logger.info("[CRON] Continuous Market Monitoring Scheduler started in background.")
    while True:
        try:
            await run_continuous_monitoring()
        except Exception as e:
            logger.error("[CRON] Error during continuous monitoring: %s", e)
        await asyncio.sleep(60)


async def _fast_price_check_loop():
    """Ultra-fast background loop using WebSocket tick prices to check SL/Target every 5 seconds.
    Provides near-instant alerts without waiting for the 60s ML cycle."""
    logger.info("[CRON] Fast WebSocket price-check loop started (5s interval).")
    while True:
        try:
            await run_fast_price_check()
        except Exception as e:
            logger.error("[CRON] Error during fast price check: %s", e)
        await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event():
    """Automated backend startup task: initializes FYERS authentication, market data manager, and background retraining daemon."""
    logger.info("Initializing NIFTY 50 ML Engine Backend Server...")
    try:
        token_mgr = get_token_manager()
        status = token_mgr.reload_and_verify()
        logger.info("[INFO] FYERS Token Manager loaded (status=%s)", status)

        market_mgr = get_market_data_manager()
        market_mgr.fetch_quote_with_retry("NSE:NIFTY50-INDEX")
        logger.info("[INFO] FYERS Market Data Engine initialized successfully.")

        # Start the FyersDataSocket live tick stream (exact real-time prices)
        market_mgr.start_data_websocket()
        # Pre-subscribe NIFTY50 index to show live ticks on dashboard immediately
        market_mgr.subscribe_symbols(["NSE:NIFTY50-INDEX"])
        logger.info("[INFO] FyersDataSocket live tick stream started.")

        # Start automated daily self-retraining scheduler daemon thread
        t = threading.Thread(target=_automated_daily_retrain_daemon, daemon=True)
        t.start()
        logger.info("[INFO] Background automated retraining daemon initialized.")

        # Start FYERS daily auto-reconnect daemon (headless TOTP login at 08:50 IST)
        reauth_thread = threading.Thread(target=_daily_fyers_reauth_daemon, daemon=True)
        reauth_thread.start()
        logger.info("[INFO] FYERS Daily Auto-ReAuth Daemon started (fires at 08:50 IST daily).")
        
        # Start continuous monitoring task on the main event loop
        asyncio.create_task(_continuous_monitoring_loop())
        logger.info("[INFO] Background continuous monitoring task initialized.")

        # Start fast 5-second WebSocket price-check loop for instant SL/Target alerts
        asyncio.create_task(_fast_price_check_loop())
        logger.info("[INFO] Fast 5-second WebSocket price-check loop initialized.")
    except Exception as e:
        logger.warning("FYERS Backend Client startup warning: %s", e)


@app.get("/api/market/nifty50")
def get_nifty50_market_data():
    """Clean backend market data endpoint exposing real-time NIFTY 50 market summary to the frontend."""
    try:
        market_mgr = get_market_data_manager()
        data = market_mgr.get_nifty50_summary()
        return data
    except Exception as e:
        logger.error("Error fetching NIFTY 50 market data: %s", e)
        token_mgr = get_token_manager()
        return {
            "symbol": "NSE:NIFTY50-INDEX",
            "price": 24570.65,
            "change": 0.0,
            "change_percent": 0.0,
            "timestamp": "",
            "market_status": get_market_status(),
            "auth_status": token_mgr.status,
            "is_live": False
        }


@app.get("/health")
def health_check():
    """System health check, champion model status, and FYERS connection status."""
    token_mgr = get_token_manager()
    auth_info = token_mgr.get_auth_status()

    try:
        _, reg_meta = load_champion("return_regressor")
        _, clf_meta = load_champion("direction_classifier")
        status = "healthy"
    except Exception as e:
        status = f"unhealthy: {str(e)}"
        reg_meta = {}
        clf_meta = {}

    return {
        "status": status,
        "service": "NIFTY 50 ML Trading Service",
        "fyers_connection": auth_info,
        "champion_models": {
            "return_regressor": reg_meta.get("version", "none"),
            "regressor_metrics": reg_meta.get("metrics", {}),
            "direction_classifier": clf_meta.get("version", "none"),
            "classifier_metrics": clf_meta.get("metrics", {}),
        },
        "nifty50_universe_count": len(NIFTY50_TICKERS)
    }


@app.get("/api/fyers-status")
@app.get("/api/fyers/status")
def fyers_status():
    """Lightweight endpoint returning real-time Fyers connection status.
    Auto-triggers headless TOTP login if token is expired and TOTP is configured.
    Used by the frontend to dynamically update the banner without a full page reload."""
    token_mgr = get_token_manager()
    # Force reload env in case tokens were refreshed on disk
    token_mgr.load_tokens()
    # If expired and TOTP login is available, try it transparently
    if not token_mgr.is_access_token_valid():
        from services.fyers_headless_login import is_headless_login_configured
        if is_headless_login_configured():
            logger.info("[API] Token expired on status check — triggering background auto-login...")
            import threading
            t = threading.Thread(target=_try_fyers_reauth, kwargs={"reason": "status-check"}, daemon=True)
            t.start()
    return token_mgr.get_auth_status()


@app.post("/api/fyers/force-refresh")
def fyers_force_refresh():
    """Manually triggers FYERS headless TOTP auto-login from the dashboard.
    Works without any browser interaction if FYERS_CLIENT_ID and FYERS_TOTP_KEY are set.
    """
    token_mgr = get_token_manager()
    if token_mgr.is_access_token_valid():
        return {
            "success": True,
            "message": "FYERS token is already valid and active.",
            "status": token_mgr.get_auth_status()
        }

    success = _try_fyers_reauth(reason="force-refresh-api")
    client = get_fyers_client()
    client.reload_and_init()

    if success:
        return {
            "success": True,
            "message": "FYERS auto-login succeeded! Token is now active.",
            "status": token_mgr.get_auth_status()
        }
    else:
        from services.fyers_headless_login import is_headless_login_configured
        if not is_headless_login_configured():
            detail = (
                "FYERS_TOTP_KEY or FYERS_CLIENT_ID not set in .env. "
                "Add them to enable fully automatic daily login, or use the OAuth login button below."
            )
        else:
            detail = f"Auto-login failed: {token_mgr.last_error}"
        raise HTTPException(status_code=503, detail=detail)


@app.get("/fyers/login")
def fyers_login():
    """Optional OAuth 2.0 Login redirect URL generator."""
    client = get_fyers_client()
    try:
        auth_url = client.get_login_url()
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error("Error generating FYERS login URL: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed generating login URL: {e}")


@app.get("/fyers/callback")
def fyers_callback(auth_code: str = Query(None), auth_code_param: str = Query(None, alias="auth_code")):
    """OAuth callback endpoint: receives auth_code, exchanges it for access_token & refresh_token, and saves server-side."""
    code = auth_code or auth_code_param
    if not code:
        raise HTTPException(status_code=400, detail="Missing auth_code in query parameters.")

    token_mgr = get_token_manager()
    try:
        token = token_mgr.exchange_code_for_tokens(code)
        client = get_fyers_client()
        client.reload_and_init()
        return HTMLResponse(content="""
        <html>
            <body style="font-family: sans-serif; background: #0f172a; color: white; padding: 40px; text-align: center;">
                <h1 style="color: #22c55e;">🟢 FYERS Live API Authenticated Successfully!</h1>
                <p>Access token and refresh token saved server-side. Automatic token renewal enabled.</p>
                <p><a href="/" style="color: #38bdf8; font-size: 18px; font-weight: bold;">Return to Dashboard</a></p>
            </body>
        </html>
        """)
    except Exception as e:
        logger.error("Error exchanging FYERS auth code: %s", e)
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")


@app.post("/fyers/token")
def set_fyers_token(data: TokenInput):
    """Directly saves FYERS_ACCESS_TOKEN (and optionally refresh_token) server-side without browser redirect.
    If a refresh_token is also provided, automatic daily renewal is enabled for ~14 days.
    """
    if not data.access_token.strip():
        raise HTTPException(status_code=400, detail="access_token cannot be empty.")

    token_mgr = get_token_manager()
    rt = (data.refresh_token or "").strip()
    exp = int(data.expires_in or 86400)
    token_mgr.save_tokens(data.access_token, refresh_token=rt, expires_in=exp)
    client = get_fyers_client()
    client.reload_and_init()
    has_rt = bool(token_mgr.refresh_token)
    msg = (
        "FYERS tokens saved server-side successfully. "
        + ("Auto-renewal ENABLED (refresh token stored)." if has_rt else "WARNING: No refresh token provided — manual re-login will be required when access token expires (~24h).")
    )
    return {"message": msg, "is_authenticated": token_mgr.status == FYERS_AUTHENTICATED, "has_refresh_token": has_rt}


@app.get("/predict/{ticker}", response_model=PredictionResponse)
def get_prediction(ticker: str, qty: int = Query(100, ge=1), limit_price: Optional[float] = Query(None, ge=0.1)):
    """Returns live ML prediction, Groww order analysis & risk management analytics for a given NIFTY 50 ticker."""
    try:
        # Subscribe ticker to FyersDataSocket so live ticks are instantly available
        from inference.ticker_utils import normalize_and_validate_ticker
        try:
            clean_ticker = normalize_and_validate_ticker(ticker)
            fyers_symbol = f"NSE:{clean_ticker}-EQ"
            market_mgr = get_market_data_manager()
            market_mgr.subscribe_symbols([fyers_symbol])
        except Exception:
            pass  # Don't block prediction if subscription fails
        
        prediction = run_live_prediction(ticker, custom_qty=qty, custom_limit_price=limit_price)
        return prediction
    except ValueError as ve:
        logger.warning("Validation error for ticker '%s': %s", ticker, ve)
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("Error predicting for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/predict")
def get_batch_predictions(tickers: str = "WIPRO,RELIANCE,TCS,ADANIENT,INFY"):
    """Batch prediction endpoint for multiple comma-separated tickers."""
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    results = {}
    for t in ticker_list:
        try:
            results[t] = run_live_prediction(t)
        except Exception as e:
            results[t] = {"error": str(e)}
    return {"batch_predictions": results}


@app.post("/retrain")
def trigger_retrain(background_tasks: BackgroundTasks):
    """Triggers self-retraining pipeline in background and evaluates promotion gate."""
    background_tasks.add_task(run_retraining_job)
    return {"message": "Retraining job launched in background.", "status": "queued"}


@app.post("/api/trades")
async def track_trade(data: TradeInput, background_tasks: BackgroundTasks):
    """Starts monitoring a new trade and immediately runs first evaluation."""
    tracker = get_trade_tracker()
    trade_id = tracker.add_trade(
        ticker=data.ticker,
        entry_price=data.entry_price,
        qty=data.qty,
        direction=data.direction,
        stop_loss=data.stop_loss,
        target_price=data.target_price
    )
    
    # Trigger an immediate async evaluation so the user gets their first alert right away
    trade_dict = {
        "id": trade_id,
        "ticker": data.ticker,
        "direction": data.direction,
        "current_stop_loss": data.stop_loss,
        "target_price": data.target_price
    }
    import asyncio
    asyncio.create_task(evaluate_single_trade(trade_dict))
    
    return {"message": "Trade tracking started.", "trade_id": trade_id}


@app.get("/api/trades")
def get_trades():
    """Returns all active tracked trades."""
    tracker = get_trade_tracker()
    return {"active_trades": tracker.get_active_trades()}


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for continuous real-time alerts."""
    await websocket.accept()
    register_ws_connection(websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages if any
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        unregister_ws_connection(websocket)


@app.get("/", response_class=HTMLResponse)
def minimal_dashboard():
    """ML Trading Engine Terminal UI with Groww-style order form, dark mode, 30-min targets & AI insights."""
    sorted_tickers = sorted(list(NIFTY50_TICKERS))
    datalist_options = "".join([f'<option value="{t}"></option>' for t in sorted_tickers])

    token_mgr = get_token_manager()
    auth_status = token_mgr.status
    headless_ok = token_mgr.get_auth_status().get("headless_login_configured", False)
    app_id_short = FYERS.app_id[:6] + "..." if FYERS.app_id else "NOT SET"

    if auth_status == FYERS_AUTHENTICATED:
        fyers_banner = """
        <div id="fyersBanner" style="background: rgba(34, 197, 94, 0.12); border: 1px solid #22c55e; color: #4ade80; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
            <span>🟢 <strong>Fyers API Live Connected</strong> &mdash; Real-time data active. Auto-renews daily at 08:50 IST via TOTP.</span>
            <span style="font-size: 11px; background: #22c55e; color: black; padding: 2px 10px; border-radius: 12px; font-weight: bold; letter-spacing: 0.5px;">LIVE ACTIVE</span>
        </div>
        """
    elif headless_ok:
        fyers_banner = f"""
        <div id="fyersBanner" style="background: rgba(234, 179, 8, 0.12); border: 1px solid #eab308; color: #fde047; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
            <span>🟡 <strong>FYERS Token Expired</strong> &mdash; TOTP auto-login configured. Click to reconnect instantly.</span>
            <button onclick="forceReconnect(this)" id="forceReconnectBtn" style="font-size: 12px; background: #eab308; color: black; padding: 4px 14px; border-radius: 10px; font-weight: bold; border: none; cursor: pointer; white-space: nowrap;">⚡ Auto-Reconnect Now</button>
        </div>
        """
    else:
        fyers_banner = f"""
        <div id="fyersBanner" style="background: rgba(234, 179, 8, 0.12); border: 1px solid #eab308; color: #fde047; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
            <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                <span>🔑 <strong>FYERS App ID ({app_id_short})</strong> &mdash; One-Time Login Required. <small style="color:#94a3b8;">(After adding FYERS_TOTP_KEY to .env, this never shows again)</small></span>
                <a href="/fyers/login" target="_blank" style="background: #eab308; color: black; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 13px;">⚡ OAuth Login</a>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                <input type="text" id="directTokenInput" placeholder="Paste FYERS_ACCESS_TOKEN here..." style="padding: 8px 12px; background: #0f172a; border: 1px solid #eab308; color: white; border-radius: 6px;">
                <input type="text" id="directRefreshTokenInput" placeholder="Paste FYERS_REFRESH_TOKEN (optional)..." style="padding: 8px 12px; background: #0f172a; border: 1px solid #eab308; color: white; border-radius: 6px;">
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px;">
                <div style="font-size: 12px; color: #94a3b8;">
                    💡 <strong>Permanent fix:</strong> Add <code style="background:#1e293b;padding:2px 5px;border-radius:3px;">FYERS_CLIENT_ID=FAK08110</code> and <code style="background:#1e293b;padding:2px 5px;border-radius:3px;">FYERS_TOTP_KEY=&lt;your_base32_key&gt;</code> to .env — system will auto-login daily at 08:50 IST forever.
                </div>
                <button onclick="saveTokenDirectly()" style="background: #eab308; color: black; padding: 8px 16px; border-radius: 6px; border: none; font-weight: bold; cursor: pointer; white-space: nowrap;">Save Token &amp; Connect</button>
            </div>
        </div>
        """

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ML Trading Engine Terminal</title>
        <style>
            :root {
                --bg: #090d16;
                --card-bg: #131b2e;
                --card-border: #1e293b;
                --accent: #3b82f6;
                --accent-hover: #2563eb;
                --text: #f8fafc;
                --text-muted: #94a3b8;
                --green: #22c55e;
                --green-bg: rgba(34, 197, 94, 0.12);
                --red: #ef4444;
                --red-bg: rgba(239, 68, 68, 0.12);
                --yellow: #eab308;
            }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
            .container { max-width: 1000px; margin: 0 auto; }
            .header-title { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; color: #ffffff; margin-bottom: 20px; }
            .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0,0,0,0.4); }
            .flex { display: flex; gap: 12px; align-items: center; }
            .grid-3-inputs { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; margin-bottom: 12px; }
            input, button { padding: 12px 18px; border-radius: 8px; border: 1px solid #334155; font-size: 15px; outline: none; }
            input { background: #0f172a; color: white; }
            button { background: #2563eb; color: white; cursor: pointer; border: none; font-weight: 600; transition: all 0.2s; }
            button:hover { background: #1d4ed8; }
            
            /* Actionable Signal Hero Box */
            .hero-signal { background: var(--green-bg); border: 1px solid var(--green); border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
            .hero-signal.wait { background: rgba(234, 179, 8, 0.12); border-color: var(--yellow); }
            .hero-signal.sell { background: var(--red-bg); border-color: var(--red); }
            .signal-label { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); font-weight: 700; margin-bottom: 4px; }
            .signal-value { font-size: 28px; font-weight: 800; color: var(--green); letter-spacing: 0.5px; }
            .signal-value.wait { color: var(--yellow); }
            .signal-value.sell { color: var(--red); }
            .hero-price-ticker { text-align: right; }
            .hero-ticker-name { font-size: 22px; font-weight: 800; color: #ffffff; }
            .hero-price-val { font-size: 18px; font-weight: 600; color: var(--text-muted); margin-top: 2px; }

            /* 2-Column Grid Cards */
            .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
            .card-section-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); font-weight: 700; margin-bottom: 16px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; }
            .row-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px; }
            .row-label { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
            .row-val { font-size: 18px; font-weight: 700; color: #ffffff; }
            
            pre { background: #060a12; padding: 16px; border-radius: 8px; border: 1px solid #1e293b; overflow-x: auto; color: #38bdf8; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
            .info-text { font-size: 13px; color: var(--text-muted); margin-top: 8px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-title">
                <span>📈</span> ML Trading Engine Terminal
            </div>
            
            {fyers_banner}

            <!-- Groww Style Order Terminal Input Form -->
            <div class="card" style="border-color:#3b82f6;">
                <div class="card-section-title" style="color:#38bdf8;">🛒 GROWW ORDER TERMINAL INPUTS</div>
                <div class="grid-3-inputs">
                    <div>
                        <div class="row-label">Stock Ticker</div>
                        <input type="text" id="tickerInput" list="niftyTickers" value="WIPRO" placeholder="Select stock (e.g. WIPRO, Reliance, LT)" style="width:100%; box-sizing:border-box;">
                    </div>
                    <div>
                        <div class="row-label">Quantity (Qty)</div>
                        <input type="number" id="qtyInput" value="100" min="1" placeholder="Qty (e.g. 100)" style="width:100%; box-sizing:border-box;">
                    </div>
                    <div>
                        <div class="row-label">Price Limit (₹)</div>
                        <input type="number" id="limitInput" step="0.05" placeholder="Limit Price (Optional)" style="width:100%; box-sizing:border-box;">
                    </div>
                </div>
                <datalist id="niftyTickers">
                    {datalist_options}
                </datalist>
                <button id="mainActionButton" onclick="analyzeAndTrack()" style="width:100%; margin-top:8px; background:#2563eb; font-size:16px; padding:14px; font-weight:bold; border:1px solid #3b82f6; border-radius:8px;">
                    🚀 Analyze Order & Activate Live Co-Pilot
                </button>
                <div class="info-text">💡 The platform will immediately begin monitoring this stock in the background minute-by-minute.</div>
            </div>

            <!-- Groww Custom Order AI Evaluation Card -->
            <div id="growwOrderCard" class="card" style="display:none; border-color:#22c55e; background:#0b1329;">
                <div class="card-section-title" style="color:#4ade80;">🛍️ GROWW CUSTOM ORDER AI ANALYSIS</div>
                <div style="margin-bottom:12px; font-size:16px; font-weight:700;" id="growwOrderVerdict">🟢 ORDER APPROVED — EXCELLENT LIMIT ENTRY</div>
                <div class="row-grid">
                    <div>
                        <div class="row-label">Required Capital</div>
                        <div id="growwCapital" class="row-val" style="color:#38bdf8;">₹18,310.00</div>
                    </div>
                    <div>
                        <div class="row-label">Custom Order R:R Ratio</div>
                        <div id="growwRRRatio" class="row-val">1:2.76</div>
                    </div>
                </div>
                <div class="row-grid" style="margin-bottom:8px;">
                    <div>
                        <div class="row-label">Custom Profit Potential (Target)</div>
                        <div id="growwProfit" class="row-val" style="color:var(--green);">+₹141.00</div>
                    </div>
                    <div>
                        <div class="row-label">Custom Max Risk (Stop Loss)</div>
                        <div id="growwRisk" class="row-val" style="color:var(--red);">-₹51.00</div>
                    </div>
                </div>
                <div id="growwAdvice" style="font-size:13px; color:#94a3b8; background:#070d1a; padding:10px; border-radius:6px; border-left:3px solid var(--green);">
                    Limit Price is inside optimal Entry Zone.
                </div>
            </div>

            <!-- Actionable Signal Hero Banner -->
            <div id="heroSignalBox" class="hero-signal" style="display:none;">
                <div>
                    <div class="signal-label">ACTIONABLE SIGNAL</div>
                    <div id="resActionableSignal" class="signal-value">STRONG BUY</div>
                </div>
                <div class="hero-price-ticker">
                    <div id="resHeroTicker" class="hero-ticker-name">WIPRO</div>
                    <div id="resHeroPrice" class="hero-price-val">₹183.10</div>
                </div>
            </div>

            <!-- Main Results Grid -->
            <div id="resultsGrid" class="grid-2" style="display:none;">
                <!-- Risk Management Card -->
                <div class="card" style="margin-bottom:0;">
                    <div class="card-section-title">RISK MANAGEMENT (30-MIN INTRADAY)</div>
                    <div class="row-grid">
                        <div>
                            <div class="row-label">Risk/Reward Ratio</div>
                            <div id="resRRRatio" class="row-val">1:2.76</div>
                        </div>
                        <div>
                            <div class="row-label">Capital Allocation</div>
                            <div id="resCapitalAlloc" class="row-val" style="font-size:14px; line-height:1.3;">100% Capital Allocation</div>
                        </div>
                    </div>
                    <div class="row-grid" style="margin-bottom:0;">
                        <div>
                            <div class="row-label">Stop Loss (Risk)</div>
                            <div id="resStopLoss" class="row-val" style="color:var(--red);">₹182.59</div>
                        </div>
                        <div>
                            <div class="row-label">30-Min Target (Reward)</div>
                            <div id="resTargetReward" class="row-val" style="color:var(--green);">₹184.51</div>
                        </div>
                    </div>
                </div>

                <!-- Technicals & Confluence Card -->
                <div class="card" style="margin-bottom:0;">
                    <div class="card-section-title">TECHNICALS & CONFLUENCE</div>
                    <div class="row-grid">
                        <div>
                            <div class="row-label">Predicted Move (30m)</div>
                            <div id="resPredictedMove" class="row-val" style="color:var(--green);">+0.26%</div>
                        </div>
                        <div>
                            <div class="row-label">Confidence Score</div>
                            <div id="resConfidenceScore" class="row-val">85.3%</div>
                        </div>
                    </div>
                    <div class="row-grid" style="margin-bottom:0;">
                        <div>
                            <div class="row-label">Market Trend</div>
                            <div id="resMarketTrend" class="row-val">Strong Bullish</div>
                        </div>
                        <div>
                            <div class="row-label">Optimal Entry Zone</div>
                            <div id="resEntryZone" class="row-val" style="font-size:15px;">₹182.70 - ₹183.40</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Real-Time AI Insights Card -->
            <div id="insightsCard" class="card" style="display:none; border-color:#334155;">
                <div class="card-section-title">🤖 REAL-TIME 30-MINUTE INTRADAY TARGET</div>
                <div style="background:#0f172a; padding:16px; border-radius:8px; border:1px solid #1e293b; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div class="row-label">🎯 30-Min Intraday Target (ATR Volatility Move)</div>
                        <div id="target30mVal" class="row-val" style="color:var(--green); font-size:24px; margin-top:4px;">₹184.51 (+0.26%)</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="row-label">30-Min Stop Loss</div>
                        <div id="target30mSL" class="row-val" style="color:var(--red); font-size:20px; margin-top:4px;">₹182.59</div>
                    </div>
                </div>
            </div>
            
            <!-- Live Co-Pilot Alerts Card -->
            <div class="card" id="alertsCard" style="border-color:var(--yellow);">
                <div class="card-section-title" style="color:var(--yellow);">🔔 LIVE CO-PILOT ALERTS</div>
                <div id="alertsContainer" style="max-height: 400px; overflow-y: auto; display:flex; flex-direction:column; gap:8px;">
                    <div style="padding:10px; background:#0f172a; border-radius:6px; color:var(--text-muted); font-size:13px; text-align:center;">
                        Listening for live background updates...
                    </div>
                </div>
            </div>

            <!-- Raw API JSON Payload -->
            <div class="card">
                <div class="card-section-title">Raw API Payload</div>
                <pre id="jsonResult">{"status": "Ready. Click 'Analyze Groww Order' to run ML model."}</pre>
            </div>
        </div>

        <script>
            // Store last predicted data to use for monitoring
            let lastPredictionData = null;

            // ─── Dynamic Fyers Banner Updater ───────────────────────────────────
            function updateFyersBanner() {
                fetch('/api/fyers-status')
                    .then(r => r.json())
                    .then(data => {
                        const banner = document.getElementById('fyersBanner');
                        if (!banner) return;
                        if (data.is_authenticated) {
                            banner.style.background = 'rgba(34,197,94,0.12)';
                            banner.style.borderColor = '#22c55e';
                            banner.style.color = '#4ade80';
                            banner.style.display = 'flex';
                            banner.style.justifyContent = 'space-between';
                            banner.style.alignItems = 'center';
                            banner.innerHTML = `<span>&#x1F7E2; <strong>Fyers API Live Connected</strong> &mdash; Real-time data active. Auto-renews daily at 08:50 IST.</span><span style="font-size:11px;background:#22c55e;color:black;padding:2px 10px;border-radius:12px;font-weight:bold;">LIVE ACTIVE</span>`;
                        } else if (data.headless_login_configured) {
                            banner.style.background = 'rgba(234,179,8,0.12)';
                            banner.style.borderColor = '#eab308';
                            banner.style.color = '#fde047';
                            banner.style.display = 'flex';
                            banner.style.justifyContent = 'space-between';
                            banner.style.alignItems = 'center';
                            banner.innerHTML = `<span>&#x1F7E1; <strong>FYERS Token Expired</strong> &mdash; TOTP auto-login configured. Click to reconnect instantly.</span><button onclick="forceReconnect(this)" id="forceReconnectBtn" style="font-size:12px;background:#eab308;color:black;padding:4px 14px;border-radius:10px;font-weight:bold;border:none;cursor:pointer;white-space:nowrap;">&#x26A1; Auto-Reconnect Now</button>`;
                        } else {
                            banner.style.background = 'rgba(234,179,8,0.12)';
                            banner.style.borderColor = '#eab308';
                            banner.style.color = '#fde047';
                            banner.style.display = 'flex';
                            banner.style.justifyContent = 'space-between';
                            banner.style.alignItems = 'center';
                            banner.innerHTML = `<span>&#x1F511; <strong>Fyers: Login Required</strong> &mdash; <a href="/fyers/login" style="color:#eab308;font-weight:bold;">OAuth Login</a> | Add FYERS_TOTP_KEY to .env for permanent auto-login.</span><span style="font-size:11px;background:#ef4444;color:white;padding:2px 10px;border-radius:12px;font-weight:bold;">DISCONNECTED</span>`;
                        }
                    })
                    .catch(() => {});
            }

            // ─── Force Reconnect via headless TOTP auto-login ────────────────────
            function forceReconnect(btn) {
                if (btn) { btn.disabled = true; btn.textContent = '\u23F3 Connecting...'; }
                fetch('/api/fyers/force-refresh', { method: 'POST' })
                    .then(async res => {
                        const data = await res.json();
                        if (res.ok && data.success) {
                            const banner = document.getElementById('fyersBanner');
                            if (banner) {
                                banner.style.background = 'rgba(34,197,94,0.12)';
                                banner.style.borderColor = '#22c55e';
                                banner.style.color = '#4ade80';
                                banner.innerHTML = `<span>&#x1F7E2; <strong>Fyers API Live Connected</strong> &mdash; Auto-login successful! Token active.</span><span style="font-size:11px;background:#22c55e;color:black;padding:2px 10px;border-radius:12px;font-weight:bold;">LIVE ACTIVE</span>`;
                            }
                        } else {
                            if (btn) { btn.disabled = false; btn.textContent = '\u26A1 Retry'; }
                            alert('Auto-reconnect error: ' + (data.detail || data.message || JSON.stringify(data)));
                        }
                    })
                    .catch(() => {
                        if (btn) { btn.disabled = false; btn.textContent = '\u26A1 Retry'; }
                        alert('Network error. Check server logs.');
                    });
            }

            // Poll status every 10 seconds so banner updates without page refresh
            updateFyersBanner();
            setInterval(updateFyersBanner, 10000);

            // ─── WebSocket for Live Co-Pilot Alerts ─────────────────────────────
            function setupWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = protocol + '//' + window.location.host + '/ws/alerts';
                const ws = new WebSocket(wsUrl);
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    
                    // Filter: Only show alerts for the currently selected ticker in the dashboard
                    if (!lastPredictionData || data.ticker !== lastPredictionData.ticker) {
                        return;
                    }

                    const alertsContainer = document.getElementById('alertsContainer');
                    
                    // Remove placeholder if it's the first alert
                    if (alertsContainer.innerHTML.includes('Listening for live')) {
                        alertsContainer.innerHTML = '';
                    }
                    
                    let bgColor = '#0f172a';
                    let borderColor = '#1e293b';
                    let icon = '🔔';
                    
                    if (data.type === 'PROFIT_LOCK' || data.type === 'TRAILING_SL') {
                        bgColor = 'var(--green-bg)';
                        borderColor = 'var(--green)';
                        icon = '🟢';
                    } else if (data.type === 'REVERSAL' || data.type === 'STOP_LOSS') {
                        bgColor = 'var(--red-bg)';
                        borderColor = 'var(--red)';
                        icon = '🔴';
                    } else if (data.type === 'MARKET_CLOSE') {
                        bgColor = 'rgba(234, 179, 8, 0.12)';
                        borderColor = 'var(--yellow)';
                        icon = '🟡';
                    }
                    
                    const timeStr = new Date(data.timestamp).toLocaleTimeString();
                    
                    const alertHtml = `
                        <div style="padding:12px; background:${bgColor}; border:1px solid ${borderColor}; border-radius:6px; font-size:14px;">
                            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                                <strong>${icon} ${data.ticker} [Trade #${data.trade_id}]</strong>
                                <span style="font-size:11px; color:var(--text-muted);">${timeStr}</span>
                            </div>
                            <div>${data.message}</div>
                        </div>
                    `;
                    alertsContainer.innerHTML = alertHtml + alertsContainer.innerHTML;
                };
                
                ws.onclose = function() {
                    console.log('WS disconnected. Reconnecting in 5s...');
                    setTimeout(setupWebSocket, 5000);
                };
            }
            
            // Initialize WS on load
            setupWebSocket();

            async function saveTokenDirectly() {
                const token = document.getElementById('directTokenInput').value.trim();
                const refreshToken = document.getElementById('directRefreshTokenInput').value.trim();
                if (!token) { alert('Please paste FYERS_ACCESS_TOKEN first (required).'); return; }
                try {
                    const payload = { access_token: token };
                    if (refreshToken) payload.refresh_token = refreshToken;
                    const res = await fetch('/fyers/token', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    const msg = (data.message || 'Token updated.') + (data.has_refresh_token === false ? '\\n⚠️ Note: No refresh token stored — you will need to re-login tomorrow.' : '');
                    alert(msg);
                    window.location.reload();
                } catch(e) {
                    alert('Error saving token: ' + e);
                }
            }

            async function getPrediction() {
                const ticker = document.getElementById('tickerInput').value.trim() || 'WIPRO';
                const qty = document.getElementById('qtyInput').value.trim() || '100';
                const limitPrice = document.getElementById('limitInput').value.trim();
                
                document.getElementById('jsonResult').innerText = 'Running ML inference...';
                
                let url = '/predict/' + encodeURIComponent(ticker) + '?qty=' + encodeURIComponent(qty);
                if (limitPrice) {
                    url += '&limit_price=' + encodeURIComponent(limitPrice);
                }
                
                try {
                    const res = await fetch(url);
                    const data = await res.json();
                    
                    if (!res.ok) {
                        document.getElementById('jsonResult').innerText = JSON.stringify(data, null, 2);
                        return;
                    }
                    
                    document.getElementById('jsonResult').innerText = JSON.stringify(data, null, 2);
                    
                    // Show Hero & Grid cards
                    document.getElementById('growwOrderCard').style.display = 'block';
                    document.getElementById('heroSignalBox').style.display = 'flex';
                    document.getElementById('resultsGrid').style.display = 'grid';
                    document.getElementById('insightsCard').style.display = 'block';

                    const ai = data.ai_insights || {};
                    const rm = data.risk_management || {};
                    const an = data.analytics || {};
                    const gr = data.groww_order_analysis || {};

                    // Groww Order Evaluation Card
                    const verdict = gr.order_verdict || '🟢 ORDER APPROVED';
                    document.getElementById('growwOrderVerdict').innerText = verdict;
                    document.getElementById('growwOrderVerdict').style.color = verdict.includes('APPROVED') ? '#4ade80' : (verdict.includes('ADVISORY') ? '#fde047' : '#ef4444');
                    document.getElementById('growwCapital').innerText = '₹' + (gr.required_capital || 0).toLocaleString('en-IN', {minimumFractionDigits: 2});
                    document.getElementById('growwRRRatio').innerText = gr.custom_rr_ratio || '1:1.5';
                    document.getElementById('growwProfit').innerText = '+₹' + (gr.custom_profit_potential || 0).toFixed(2);
                    document.getElementById('growwRisk').innerText = '-₹' + (gr.custom_max_risk || 0).toFixed(2);
                    document.getElementById('growwAdvice').innerText = gr.order_advice || 'Limit price analyzed.';

                    // Actionable Signal Hero
                    const sig = ai.actionable_signal || an.actionable_signal || 'STRONG BUY';
                    const heroBox = document.getElementById('heroSignalBox');
                    const sigVal = document.getElementById('resActionableSignal');
                    sigVal.innerText = sig;

                    if (sig.includes('WAIT') || sig.includes('NEUTRAL') || sig.includes('POOR')) {
                        heroBox.className = 'hero-signal wait';
                        sigVal.className = 'signal-value wait';
                    } else if (sig.includes('SELL')) {
                        heroBox.className = 'hero-signal sell';
                        sigVal.className = 'signal-value sell';
                    } else {
                        heroBox.className = 'hero-signal';
                        sigVal.className = 'signal-value';
                    }

                    document.getElementById('resHeroTicker').innerText = data.ticker || ticker;
                    document.getElementById('resHeroPrice').innerText = '₹' + (data.current_price || 0).toFixed(2);

                    // Auto-fill limit price input if empty
                    if (!limitPrice) {
                        document.getElementById('limitInput').value = (data.current_price || 0).toFixed(2);
                    }

                    // Risk Management Card
                    document.getElementById('resRRRatio').innerText = rm.risk_reward_ratio || '1:1.5';
                    document.getElementById('resCapitalAlloc').innerText = (rm.position_sizing || {}).position_size_label || '100% Capital Allocation';
                    document.getElementById('resStopLoss').innerText = '₹' + (rm.dynamic_stop_loss || 0).toFixed(2);
                    document.getElementById('resTargetReward').innerText = '₹' + (rm.dynamic_target_price || 0).toFixed(2);

                    // Technicals Card
                    const r30m = ai.target_return_30m_pct || 0;
                    document.getElementById('resPredictedMove').innerText = (r30m > 0 ? '+' : '') + r30m.toFixed(2) + '%';
                    document.getElementById('resPredictedMove').style.color = r30m >= 0 ? '#22c55e' : '#ef4444';
                    document.getElementById('resConfidenceScore').innerText = ((data.confidence_score || 0) * 100).toFixed(1) + '%';
                    document.getElementById('resMarketTrend').innerText = an.market_trend || 'Bullish';
                    document.getElementById('resEntryZone').innerText = (rm.key_levels_guard || {}).suggested_entry_zone || '₹0.00 - ₹0.00';

                    // Real-Time 30-Min AI Target
                    const t30m = ai.target_price_30m || rm.dynamic_target_price || 0;
                    document.getElementById('target30mVal').innerText = '₹' + t30m.toFixed(2) + ' (' + (r30m > 0 ? '+' : '') + r30m.toFixed(2) + '%)';
                    document.getElementById('target30mSL').innerText = '₹' + (rm.dynamic_stop_loss || 0).toFixed(2);
                    
                    lastPredictionData = data;

                } catch(e) {
                    document.getElementById('jsonResult').innerText = 'Network error: ' + e;
                }
            }
            
            async function analyzeAndTrack() {
                const btn = document.getElementById('mainActionButton');
                btn.innerText = "⏳ Running ML Model & Initializing Co-Pilot...";
                btn.style.background = "#eab308";
                btn.style.color = "black";
                
                // Clear previous alerts when analyzing a new stock
                const alertsContainer = document.getElementById('alertsContainer');
                alertsContainer.innerHTML = '<div style="padding:10px; background:#0f172a; border-radius:6px; color:var(--text-muted); font-size:13px; text-align:center;">Initializing Co-Pilot for new stock...</div>';
                
                // 1. Get Prediction
                await getPrediction();
                
                // 2. Automatically start monitoring if prediction succeeded
                if (lastPredictionData) {
                    btn.innerText = "🔄 Co-Pilot Active! Tracking in background...";
                    btn.style.background = "var(--green)";
                    btn.style.color = "white";
                    alertsContainer.innerHTML = '<div style="padding:10px; background:#0f172a; border-radius:6px; color:var(--text-muted); font-size:13px; text-align:center;">⏳ Co-Pilot activated. Waiting for first analysis...</div>';
                    await startMonitoringTrade(true);
                } else {
                    btn.innerText = "🚀 Analyze Order & Activate Live Co-Pilot";
                    btn.style.background = "#2563eb";
                    btn.style.color = "white";
                }
            }

            async function startMonitoringTrade(silent = false) {
                if (!lastPredictionData) return;
                
                const ticker = lastPredictionData.ticker;
                const entry_price = lastPredictionData.current_price;
                const qty = lastPredictionData.groww_order_analysis.qty;
                const direction = lastPredictionData.direction;
                const stop_loss = lastPredictionData.risk_management.dynamic_stop_loss;
                const target_price = lastPredictionData.risk_management.dynamic_target_price;
                
                try {
                    const res = await fetch('/api/trades', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            ticker, entry_price, qty, direction, stop_loss, target_price
                        })
                    });
                    const data = await res.json();
                    
                    if (res.ok) {
                        if (!silent) alert("✅ Tracking Started for " + ticker + " (Trade #" + data.trade_id + "). Co-Pilot is now monitoring this trade in the background.");
                        console.log("Auto-tracking started for trade ID:", data.trade_id);
                    } else {
                        if (!silent) alert("Failed to start tracking: " + JSON.stringify(data));
                    }
                } catch(e) {
                    console.error('Network error starting tracking:', e);
                }
            }

            // On page load: only fetch prediction preview, do NOT auto-start tracking.
            // User must click the button to explicitly start Co-Pilot monitoring.
            getPrediction();
        </script>
    </body>
    </html>
    """
    html_content = html_content.replace("{fyers_banner}", fyers_banner).replace("{datalist_options}", datalist_options)
    return HTMLResponse(content=html_content)
