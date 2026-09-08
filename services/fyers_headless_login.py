"""
Fyers v3 Headless Auto-Login Engine.

Implements the complete passwordless TOTP + PIN login flow for Fyers API v3.
This is the official workaround after Fyers disabled the refresh-token endpoint
due to SEBI regulations (error code -16).

Flow:
  1. POST /api/v3/send-login-otp   → get request_key
  2. POST /api/v3/verify-otp       → verify TOTP code (pyotp), get new request_key
  3. POST /api/v3/verify-pin       → verify PIN, get internal access_token
  4. POST /api/v3/token            → exchange for auth_code
  5. SessionModel.generate_token() → exchange auth_code for real access_token + refresh_token

Required .env variables:
  FYERS_APP_ID       = e.g. ZVNJ3Y1IZY-100
  FYERS_SECRET_KEY   = e.g. UCYE5YHWB0
  FYERS_CLIENT_ID    = e.g. FAK08110   (your Fyers user/client ID)
  FYERS_PIN          = e.g. 7803
  FYERS_TOTP_KEY     = base32 TOTP secret from Fyers authenticator setup
  FYERS_REDIRECT_URL = (optional) defaults to http://127.0.0.1:8000/fyers/callback
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import urllib.parse
from typing import Tuple

import requests

logger = logging.getLogger(__name__)

_VAGATOR_URL = "https://api-t2.fyers.in/vagator/v2"
_V3_URL = "https://api-t1.fyers.in/api/v3"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _totp_code(totp_key: str) -> str:
    """Generate current 6-digit TOTP from base32 key."""
    try:
        import pyotp
        return pyotp.TOTP(totp_key.strip()).now()
    except ImportError:
        raise RuntimeError(
            "pyotp is not installed. Run: pip install pyotp"
        )


# ---------------------------------------------------------------------------
# Core headless login steps
# ---------------------------------------------------------------------------

def _step1_send_otp(client_id: str, session: requests.Session) -> str:
    """
    Step 1: Request OTP delivery via send_login_otp_v2.
    Client ID is Base64 encoded.
    """
    b64_fy_id = base64.b64encode(client_id.encode("utf-8")).decode("utf-8")
    payload = {"fy_id": b64_fy_id, "app_id": "2"}
    resp = session.post(f"{_VAGATOR_URL}/send_login_otp_v2", json=payload, headers=_HEADERS, timeout=15).json()
    logger.debug("[HEADLESS] send_login_otp_v2 response: %s", resp)

    if resp.get("s") != "ok" or not resp.get("request_key"):
        raise RuntimeError(
            f"[HEADLESS] Step 1 (send-login-otp) failed: "
            f"code={resp.get('code')}, msg='{resp.get('message', resp)}'"
        )
    return resp["request_key"]


def _step2_verify_totp(request_key: str, totp_key: str, session: requests.Session) -> str:
    """Step 2: Verify TOTP code via verify_otp. Returns new request_key."""
    otp = _totp_code(totp_key)
    payload = {"request_key": request_key, "otp": otp}
    resp = session.post(f"{_VAGATOR_URL}/verify_otp", json=payload, headers=_HEADERS, timeout=15).json()
    logger.debug("[HEADLESS] verify_otp response: %s", resp)

    if resp.get("s") != "ok" or not resp.get("request_key"):
        raise RuntimeError(
            f"[HEADLESS] Step 2 (verify-otp) failed: "
            f"code={resp.get('code')}, msg='{resp.get('message', resp)}'"
        )
    return resp["request_key"]


def _step3_verify_pin(request_key: str, pin: str, session: requests.Session) -> str:
    """Step 3: Verify PIN via verify_pin_v2 with Base64 encoded PIN."""
    b64_pin = base64.b64encode(str(pin).strip().encode("utf-8")).decode("utf-8")
    payload = {
        "request_key": request_key,
        "identity_type": "pin",
        "identifier": b64_pin,
    }
    resp = session.post(f"{_VAGATOR_URL}/verify_pin_v2", json=payload, headers=_HEADERS, timeout=15).json()
    logger.debug("[HEADLESS] verify_pin_v2 response: %s", resp)

    if resp.get("s") != "ok":
        raise RuntimeError(
            f"[HEADLESS] Step 3 (verify-pin) failed: "
            f"code={resp.get('code')}, msg='{resp.get('message', resp)}'"
        )

    data = resp.get("data") or {}
    internal_token = (
        data.get("access_token")
        or resp.get("access_token")
        or ""
    )
    if not internal_token:
        raise RuntimeError(
            f"[HEADLESS] Step 3 (verify-pin) returned ok but no internal token. Response: {resp}"
        )
    return internal_token


def _step4_get_auth_code(
    internal_token: str,
    app_id: str,
    app_id_short: str,
    client_id: str,
    redirect_uri: str,
    session: requests.Session,
) -> str:
    """Step 4: Exchange internal session token for an auth_code via api/v3/token."""
    payload = {
        "fyers_id": client_id,
        "app_id": app_id_short,
        "redirect_uri": redirect_uri,
        "appType": "100",
        "code_challenge": "",
        "state": "state_ml_auto",
        "scope": "",
        "nonce": "",
        "response_type": "code",
        "create_token": "1",
    }
    headers = {
        **_HEADERS,
        "Authorization": f"Bearer {internal_token}",
    }
    resp_raw = session.post(
        f"{_V3_URL}/token",
        json=payload,
        headers=headers,
        timeout=15,
    )
    try:
        resp = resp_raw.json()
    except Exception:
        raise RuntimeError(
            f"[HEADLESS] Step 4 (get-auth-code) response not JSON: {resp_raw.text}"
        )

    logger.debug("[HEADLESS] token endpoint response: %s", resp)

    # Auth code can be returned in redirect 'Url' query param or directly
    auth_code = ""
    if "Url" in resp:
        parsed = urllib.parse.urlparse(resp["Url"])
        qs = urllib.parse.parse_qs(parsed.query)
        auth_code = qs.get("auth_code", [""])[0]
    
    if not auth_code:
        auth_code = resp.get("authorization_code") or resp.get("auth_code") or ""

    if not auth_code:
        raise RuntimeError(
            f"[HEADLESS] Step 4 failed to extract auth_code. Response: {resp}"
        )
    return auth_code


def _step5_exchange_auth_code(
    auth_code: str,
    app_id: str,
    secret_key: str,
    redirect_uri: str,
) -> Tuple[str, str, int]:
    """
    Step 5: Exchange auth_code for access_token + refresh_token via fyers_apiv3 SessionModel.
    Returns (access_token, refresh_token, expires_in).
    """
    from fyers_apiv3 import fyersModel

    session = fyersModel.SessionModel(
        client_id=app_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )
    session.set_token(auth_code)
    response = session.generate_token()

    if not isinstance(response, dict) or response.get("s") != "ok":
        msg = response.get("message", str(response)) if isinstance(response, dict) else str(response)
        raise RuntimeError(f"[HEADLESS] Step 5 (generate-token) failed: {msg}")

    access_token = response.get("access_token", "")
    refresh_token = response.get("refresh_token", "")
    expires_in = int(response.get("expires_in", 86400))

    if not access_token:
        raise RuntimeError(f"[HEADLESS] Step 5 returned ok but no access_token. Response: {response}")

    return access_token, refresh_token, expires_in


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def headless_login() -> bool:
    """
    Performs the complete Fyers v3 headless TOTP login flow and saves
    the resulting access token via FyersTokenManager.

    Returns True on success, False if configuration is missing or login fails.

    Required .env keys: FYERS_APP_ID, FYERS_SECRET_KEY, FYERS_CLIENT_ID,
                        FYERS_PIN, FYERS_TOTP_KEY
    Optional .env keys: FYERS_REDIRECT_URL (defaults to localhost callback)
    """
    from config.settings import FYERS
    FYERS.reload()

    app_id = FYERS.app_id          # e.g. "ZVNJ3Y1IZY-100"
    secret_key = FYERS.secret_key
    pin = FYERS.pin
    totp_key = FYERS.totp_key
    redirect_uri = FYERS.redirect_url

    # Client ID is separate from App ID (e.g. "FAK08110")
    client_id = os.getenv("FYERS_CLIENT_ID", "").strip()
    if not client_id:
        # Try to infer from FYERS_APP_ID if it looks like a user ID
        client_id = os.getenv("FYERS_USER_ID", "").strip()

    # ── Preflight checks ──────────────────────────────────────────────────
    missing = []
    if not app_id:
        missing.append("FYERS_APP_ID")
    if not secret_key:
        missing.append("FYERS_SECRET_KEY")
    if not client_id:
        missing.append("FYERS_CLIENT_ID")
    if not pin:
        missing.append("FYERS_PIN")
    if not totp_key:
        missing.append("FYERS_TOTP_KEY")

    if missing:
        logger.warning(
            "[HEADLESS] Cannot perform headless login — missing .env keys: %s. "
            "Add these to .env to enable fully automatic daily authentication.",
            ", ".join(missing),
        )
        return False

    # App ID short form (strip the appType suffix like '-100')
    app_id_short = app_id.split("-")[0] if "-" in app_id else app_id

    logger.info("[HEADLESS] Starting Fyers v3 TOTP headless auto-login for client: %s", client_id)

    with requests.Session() as http:
        try:
            # Step 1 — Request OTP handshake
            logger.info("[HEADLESS] Step 1/5: Sending login OTP...")
            request_key = _step1_send_otp(client_id, http)

            # Step 2 — Verify TOTP
            logger.info("[HEADLESS] Step 2/5: Verifying TOTP code...")
            request_key = _step2_verify_totp(request_key, totp_key, http)

            # Step 3 — Verify PIN
            logger.info("[HEADLESS] Step 3/5: Verifying PIN...")
            internal_token = _step3_verify_pin(request_key, pin, http)

            # Step 4 — Get auth code
            logger.info("[HEADLESS] Step 4/5: Fetching auth code...")
            auth_code = _step4_get_auth_code(
                internal_token, app_id, app_id_short, client_id, redirect_uri, http
            )

            # Step 5 — Exchange for real access token
            logger.info("[HEADLESS] Step 5/5: Exchanging auth code for access token...")
            access_token, refresh_token, expires_in = _step5_exchange_auth_code(
                auth_code, app_id, secret_key, redirect_uri
            )

        except Exception as exc:
            logger.error("[HEADLESS] Auto-login failed: %s", exc)
            return False

    # ── Persist tokens ───────────────────────────────────────────────────
    try:
        from services.fyers_auth import get_token_manager
        token_mgr = get_token_manager()
        token_mgr.save_tokens(access_token, refresh_token=refresh_token, expires_in=expires_in)
        logger.info(
            "[HEADLESS] ✅ Auto-login SUCCESS! New access token saved. "
            "Expires in %d seconds (%.1f hours).",
            expires_in, expires_in / 3600,
        )
        return True
    except Exception as exc:
        logger.error("[HEADLESS] Failed to save tokens after successful login: %s", exc)
        return False


def is_headless_login_configured() -> bool:
    """Returns True if all required .env keys for headless login are present."""
    from config.settings import FYERS
    FYERS.reload()
    client_id = os.getenv("FYERS_CLIENT_ID", "").strip() or os.getenv("FYERS_USER_ID", "").strip()
    return bool(
        FYERS.app_id
        and FYERS.secret_key
        and FYERS.pin
        and FYERS.totp_key
        and client_id
    )
