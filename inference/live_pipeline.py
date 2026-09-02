"""
Live Inference Pipeline.
Coordinates: Fyers live pull -> buffer update -> build_features.py -> Predictor -> Logged prediction.
Uses FyersDataSocket live tick price (millisecond accurate) when available, falls back to REST API.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import pandas as pd

from features.build_features import build_feature_matrix
from inference.fyers_client import FyersLiveClient
from inference.predictor import Predictor
from inference.ticker_utils import normalize_and_validate_ticker

logger = logging.getLogger(__name__)

_fyers_client = None
_predictor = None


def get_fyers_client() -> FyersLiveClient:
    global _fyers_client
    if _fyers_client is None:
        _fyers_client = FyersLiveClient()
    return _fyers_client


def get_predictor() -> Predictor:
    global _predictor
    if _predictor is None:
        _predictor = Predictor()
    return _predictor


def run_live_prediction(ticker: str, custom_qty: int = 100, custom_limit_price: Optional[float] = None) -> dict[str, Any]:
    """Full live pipeline for a single ticker.

    1. Validate & normalize ticker string against NIFTY 50 universe.
    2. Update rolling buffer via Fyers client (1-min candles for ML features).
    3. Build scale-invariant features using exact build_features.py.
    4. Inject WebSocket tick price as current_price for millisecond accuracy.
    5. Generate prediction via champion models and custom Groww order analysis.
    """
    client = get_fyers_client()
    predictor = get_predictor()

    # Normalize ticker (e.g., "Tata Steel" -> "TATASTEEL") and validate against NIFTY 50 universe
    clean_ticker = normalize_and_validate_ticker(ticker)

    # Step 1: Update buffer (1-min OHLCV candles for ML feature engineering)
    buffer_path = client.update_rolling_buffer(clean_ticker)
    candles_df = pd.read_parquet(buffer_path)

    if candles_df.empty:
        raise ValueError(f"No OHLCV candles found in buffer for {clean_ticker}")

    # Step 2: Get current price — prioritize WebSocket tick (exact), fall back to candle close
    ws_price = None
    try:
        from services.fyers_market_data import get_market_data_manager
        market_mgr = get_market_data_manager()
        fyers_symbol = f"NSE:{clean_ticker}-EQ"
        ws_price = market_mgr.get_live_price(fyers_symbol)
        if ws_price:
            logger.debug("Using WebSocket tick price for %s: %.2f", clean_ticker, ws_price)
    except Exception as e:
        logger.debug("WebSocket price unavailable for %s, using candle close: %s", clean_ticker, e)

    # Use WebSocket tick if available, else fall back to last candle close
    current_price = float(ws_price) if ws_price else float(candles_df.iloc[-1]["Close"])

    # Step 3: Scale-invariant feature engineering (identical to training)
    features_df = build_feature_matrix(candles_df, drop_na=True)

    if features_df.empty:
        raise ValueError(f"Insufficient history ({len(candles_df)} bars) to build warm-up features for {clean_ticker}")

    # Step 4: Run inference with real-time current_price
    pred_res = predictor.predict(features_df, current_price=current_price, custom_qty=custom_qty, custom_limit_price=custom_limit_price)

    result = {
        "ticker": clean_ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_price": current_price,
        "price_source": "websocket" if ws_price else "candle",
        **pred_res
    }

    logger.info("Live prediction for %s: return=%.2f%% | price=%.2f | dir=%s | conf=%.2f | src=%s",
                clean_ticker, result["predicted_return_pct"], result["predicted_price"],
                result["direction"], result["confidence_score"], result["price_source"])
    return result
