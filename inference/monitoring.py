import logging
import time
from datetime import datetime, timezone
import pytz

from services.trade_tracker import get_trade_tracker
from inference.live_pipeline import run_live_prediction

logger = logging.getLogger(__name__)

# List of active WebSocket connections to push alerts to
_active_ws_connections = []

def register_ws_connection(websocket):
    _active_ws_connections.append(websocket)

def unregister_ws_connection(websocket):
    if websocket in _active_ws_connections:
        _active_ws_connections.remove(websocket)

async def _broadcast_alert(alert_type: str, trade_id: int, ticker: str, message: str, data: dict = None):
    """Broadcasts a real-time alert to all connected WebSocket clients."""
    if not _active_ws_connections:
        return
        
    payload = {
        "type": alert_type,
        "trade_id": trade_id,
        "ticker": ticker,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {}
    }
    
    dead_connections = []
    for ws in _active_ws_connections:
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.warning("Failed to send WS message: %s", e)
            dead_connections.append(ws)
            
    for ws in dead_connections:
        unregister_ws_connection(ws)

async def run_continuous_monitoring():
    """
    Background loop that runs every 1 minute.
    Checks all active trades, recalculates stop-loss/targets, and broadcasts alerts.
    """
    tracker = get_trade_tracker()
    
    # Check if market is closed (15:15 to 15:30 we close positions, after 15:30 we stop polling)
    # Simple time check for India timezone
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Intraday closing check
    if now.hour == 15 and now.minute >= 15:
        active_trades = tracker.get_active_trades()
        for trade in active_trades:
            tracker.update_status(trade["id"], "CLOSED_EOD")
            await _broadcast_alert(
                "MARKET_CLOSE", 
                trade["id"], 
                trade["ticker"], 
                "Market closing soon. Closed intraday open position.",
                {"current_price": None}
            )
        return

    # Outside market hours: 9:15 to 15:30
    if now.hour < 9 or (now.hour == 9 and now.minute < 15) or now.hour >= 16:
        logger.debug("Market is closed. Skipping monitoring cycle.")
        return

    active_trades = tracker.get_active_trades()
    if not active_trades:
        logger.debug("No active trades to monitor.")
        return

    logger.info("Monitoring %d active trades...", len(active_trades))

    for trade in active_trades:
        try:
            # Re-run prediction pipeline for the specific ticker to get latest indicators
            pred_res = run_live_prediction(trade["ticker"])
            current_price = pred_res["current_price"]
            rm = pred_res["risk_management"]
            ai = pred_res["ai_insights"]
            analytics = pred_res["analytics"]
            
            direction = trade["direction"] # "UP" or "DOWN"
            current_stop_loss = trade["current_stop_loss"]
            target_price = trade["target_price"]
            
            # Pillar 2 - Trend Reversal Detection
            market_trend = ai.get("market_trend", "")
            actionable_signal = ai.get("actionable_signal", "")
            
            is_reversal = False
            if direction == "UP" and ("Bearish" in market_trend or "SELL" in actionable_signal):
                is_reversal = True
            elif direction == "DOWN" and ("Bullish" in market_trend or "BUY" in actionable_signal):
                is_reversal = True
                
            if is_reversal:
                logger.info("Trend reversal detected for %s. Exiting trade.", trade["ticker"])
                tracker.update_status(trade["id"], "EXITED_REVERSAL")
                await _broadcast_alert(
                    "REVERSAL", 
                    trade["id"], 
                    trade["ticker"], 
                    "ALERT: Trend reversed. SELL immediately to protect capital.",
                    {"current_price": current_price, "trend": market_trend}
                )
                continue
                
            # Stop Loss Hit Check
            sl_hit = False
            if direction == "UP" and current_price <= current_stop_loss:
                sl_hit = True
            elif direction == "DOWN" and current_price >= current_stop_loss:
                sl_hit = True
                
            if sl_hit:
                logger.info("Stop loss hit for %s at %.2f.", trade["ticker"], current_price)
                tracker.update_status(trade["id"], "CLOSED_LOSS")
                await _broadcast_alert(
                    "STOP_LOSS", 
                    trade["id"], 
                    trade["ticker"], 
                    f"Stop-Loss hit at ₹{current_price}. Position closed.",
                    {"current_price": current_price}
                )
                continue

            # Pillar 1 - Trailing Stop-Loss
            new_suggested_sl = rm.get("dynamic_stop_loss")
            sl_updated = False
            
            if direction == "UP" and new_suggested_sl and new_suggested_sl > current_stop_loss:
                # Ensure we don't accidentally set SL higher than current price
                if new_suggested_sl < current_price:
                    tracker.update_stop_loss(trade["id"], new_suggested_sl)
                    current_stop_loss = new_suggested_sl
                    sl_updated = True
            elif direction == "DOWN" and new_suggested_sl and new_suggested_sl < current_stop_loss:
                if new_suggested_sl > current_price:
                    tracker.update_stop_loss(trade["id"], new_suggested_sl)
                    current_stop_loss = new_suggested_sl
                    sl_updated = True
                    
            # Target Hit Check
            target_hit = False
            if direction == "UP" and current_price >= target_price:
                target_hit = True
            elif direction == "DOWN" and current_price <= target_price:
                target_hit = True
                
            if target_hit:
                logger.info("Target reached for %s. Suggesting hold and trailing SL.", trade["ticker"])
                # We do not close the trade! We keep it active and trail the stop loss.
                msg = f"Target reached! Trend is still {market_trend}. HOLD for more profit."
                if sl_updated:
                    msg += f" Stop-Loss moved to ₹{current_stop_loss}."
                    
                await _broadcast_alert(
                    "PROFIT_LOCK", 
                    trade["id"], 
                    trade["ticker"], 
                    msg,
                    {"current_price": current_price, "new_stop_loss": current_stop_loss}
                )
            elif sl_updated:
                logger.info("Trailing stop loss updated for %s to %.2f", trade["ticker"], current_stop_loss)
                await _broadcast_alert(
                    "TRAILING_SL", 
                    trade["id"], 
                    trade["ticker"], 
                    f"Trailing Stop-Loss moved to ₹{current_stop_loss}.",
                    {"current_price": current_price, "new_stop_loss": current_stop_loss}
                )

        except Exception as e:
            logger.error("Error monitoring trade %d (%s): %s", trade["id"], trade["ticker"], e)
