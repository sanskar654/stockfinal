import logging
import asyncio
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


def _get_ws_price(ticker: str):
    """Tries to get a live WebSocket tick price for a ticker. Returns None if unavailable."""
    try:
        from services.fyers_market_data import get_market_data_manager
        market_mgr = get_market_data_manager()
        return market_mgr.get_live_price(f"NSE:{ticker}-EQ")
    except Exception:
        return None


async def run_continuous_monitoring():
    """
    Background loop that runs every 30 seconds (full ML re-prediction cycle).
    Checks all active trades, recalculates stop-loss/targets, and broadcasts alerts.
    """
    tracker = get_trade_tracker()
    
    # Check if market is closed (15:15 to 15:30 we close positions, after 15:30 we stop polling)
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
        await evaluate_single_trade(trade, tracker, use_full_ml=True)


async def run_fast_price_check():
    """
    Fast 5-second loop that uses WebSocket tick prices for instant Stop-Loss 
    and Target checks WITHOUT re-running the expensive ML model.
    Only triggers STOP_LOSS or REVERSAL alerts based on live price vs stored levels.
    """
    tracker = get_trade_tracker()
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Only run during market hours
    if now.hour < 9 or (now.hour == 9 and now.minute < 15) or now.hour >= 16:
        return
    if now.hour == 15 and now.minute >= 30:
        return

    active_trades = tracker.get_active_trades()
    if not active_trades:
        return

    for trade in active_trades:
        try:
            # Use fast WebSocket price — no ML model involved
            ws_price = _get_ws_price(trade["ticker"])
            if ws_price is None:
                continue  # WebSocket price not yet available for this ticker

            current_price = float(ws_price)
            entry_price = float(trade["entry_price"])
            direction = trade["direction"]
            current_stop_loss = trade["current_stop_loss"]
            target_price = trade["target_price"]
            pnl_per_share = current_price - entry_price if direction == "UP" else entry_price - current_price
            unrealized_pnl = round(pnl_per_share * int(trade["qty"]), 2)

            # Instant Stop-Loss check using exact live tick price
            sl_hit = False
            if direction == "UP" and current_price <= current_stop_loss:
                sl_hit = True
            elif direction == "DOWN" and current_price >= current_stop_loss:
                sl_hit = True

            if sl_hit:
                logger.info("⚡ [FAST] Stop loss hit for %s at %.2f (exact tick price).", trade["ticker"], current_price)
                tracker.update_status(trade["id"], "CLOSED_LOSS")
                await _broadcast_alert(
                    "STOP_LOSS",
                    trade["id"],
                    trade["ticker"],
                    f"Stop-Loss hit at ₹{current_price:.2f}. Position closed. (Live Tick)",
                    {"current_price": current_price, "unrealized_pnl": unrealized_pnl, "pnl_status": "LOSS"}
                )
                continue

            # Instant Target check using exact live tick price
            target_hit = False
            if direction == "UP" and current_price >= target_price:
                target_hit = True
            elif direction == "DOWN" and current_price <= target_price:
                target_hit = True

            if target_hit:
                logger.info("⚡ [FAST] Target reached for %s at %.2f (exact tick price).", trade["ticker"], current_price)
                await _broadcast_alert(
                    "PROFIT_LOCK",
                    trade["id"],
                    trade["ticker"],
                    f"🎯 Target ₹{target_price:.2f} reached! Current: ₹{current_price:.2f}. Consider trailing stop. (Live Tick)",
                    {"current_price": current_price, "unrealized_pnl": unrealized_pnl, "pnl_status": "PROFIT"}
                )

        except Exception as e:
            logger.error("Error in fast price check for trade %d (%s): %s", trade["id"], trade["ticker"], e)


async def evaluate_single_trade(trade: dict, tracker=None, use_full_ml: bool = True):
    """Evaluates a single trade and broadcasts alerts. Useful for immediate feedback.
    
    Args:
        trade: Trade dictionary with keys id, ticker, direction, current_stop_loss, target_price.
        tracker: TradeTracker instance (will create one if None).
        use_full_ml: If True, runs full ML prediction. If False, only does price checks.
    """
    if tracker is None:
        tracker = get_trade_tracker()
        
    try:
        # Re-run prediction pipeline for the specific ticker to get latest indicators
        # This will use WebSocket price automatically via live_pipeline.py
        pred_res = run_live_prediction(trade["ticker"])
        current_price = pred_res["current_price"]
        rm = pred_res["risk_management"]
        ai = pred_res["ai_insights"]
        analytics = pred_res["analytics"]
        predicted_direction = pred_res.get("direction", "NEUTRAL")
        entry_price = float(trade["entry_price"])
        qty = int(trade["qty"])
        position_direction = trade["direction"]
        pnl_per_share = current_price - entry_price if position_direction == "UP" else entry_price - current_price
        unrealized_pnl = round(pnl_per_share * qty, 2)
        pnl_pct = round((pnl_per_share / entry_price) * 100.0, 2) if entry_price else 0.0
        pnl_status = "PROFIT" if unrealized_pnl > 0 else "LOSS" if unrealized_pnl < 0 else "FLAT"
        model_conflicts_with_position = (
            (position_direction == "UP" and predicted_direction == "DOWN")
            or (position_direction == "DOWN" and predicted_direction == "UP")
        )
        if model_conflicts_with_position:
            recommendation = "SELL / EXIT NOW"
            user_guidance = "The model now expects the opposite direction. Exit this position to protect your money."
        elif pnl_status == "PROFIT":
            recommendation = "HOLD - KEEP THE STOCK"
            user_guidance = "The position is currently profitable. Keep the stock and let the target or trailing stop protect the gain. Do not buy more from this alert."
        elif pnl_status == "LOSS":
            recommendation = "HOLD WITH PROTECTION"
            user_guidance = "The price is below your entry. Do not add more shares. Keep the stop-loss active and exit if the stop-loss or reversal alert appears."
        else:
            recommendation = "HOLD - WAIT"
            user_guidance = "The position has just started and is near your entry price. Keep the stock; wait for the target, stop-loss, or reversal guidance."

        await _broadcast_alert(
            "ANALYSIS",
            trade["id"],
            trade["ticker"],
            f"{recommendation}. {user_guidance} "
            f"P&L: {pnl_status} ₹{unrealized_pnl:.2f} ({pnl_pct:+.2f}%). "
            f"Current price ₹{current_price:.2f}; model {ai.get('actionable_signal', predicted_direction)} "
            f"with {pred_res.get('confidence_score', 0) * 100:.1f}% confidence.",
            {
                "current_price": current_price,
                "direction": predicted_direction,
                "recommendation": recommendation,
                "user_guidance": user_guidance,
                "entry_price": entry_price,
                "qty": qty,
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
                "pnl_status": pnl_status,
                "confidence_score": pred_res.get("confidence_score"),
                "market_trend": ai.get("market_trend"),
                "target_price": rm.get("dynamic_target_price"),
                "stop_loss": rm.get("dynamic_stop_loss"),
            },
        )
        
        direction = trade["direction"] # "UP" or "DOWN"
        current_stop_loss = trade["current_stop_loss"]
        target_price = trade["target_price"]
        
        # Pillar 2 - Trend Reversal Detection
        # Compare the original trade direction with the NEW ML prediction direction
        pred_direction = predicted_direction
        market_trend = ai.get("market_trend", "")
        actionable_signal = ai.get("actionable_signal", "")
        
        is_reversal = False
        # If the ML model flipped its prediction direction, exit the trade immediately
        if direction == "UP" and pred_direction == "DOWN":
            is_reversal = True
        elif direction == "DOWN" and pred_direction == "UP":
            is_reversal = True
            
        if is_reversal:
            logger.info("Trend reversal detected for %s. Exiting trade.", trade["ticker"])
            tracker.update_status(trade["id"], "EXITED_REVERSAL")
            await _broadcast_alert(
                "REVERSAL", 
                trade["id"], 
                trade["ticker"], 
                "ALERT: Trend reversed. SELL immediately to protect capital.",
                {
                    "current_price": current_price,
                    "trend": market_trend,
                    "entry_price": entry_price,
                    "unrealized_pnl": unrealized_pnl,
                    "pnl_pct": pnl_pct,
                    "pnl_status": pnl_status,
                }
            )
            return
            
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
                {
                    "current_price": current_price,
                    "entry_price": entry_price,
                    "unrealized_pnl": unrealized_pnl,
                    "pnl_pct": pnl_pct,
                    "pnl_status": "LOSS",
                }
            )
            return

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
