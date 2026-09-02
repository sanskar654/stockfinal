"""
Official FYERS API v3 Token Authentication Manager & State Machine.
Handles token persistence, automatic refresh-token renewal, and safe auth state reporting.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any

from config.settings import FYERS, BASE_DIR

logger = logging.getLogger(__name__)


def _decode_jwt_exp(token: str) -> float:
    """Decodes the 'exp' (expiry) claim from a JWT token without verifying the signature.
    Returns the expiry timestamp as a float, or 0.0 if decoding fails.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0.0
        # Base64url decode the payload (add padding as needed)
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        return float(payload.get("exp", 0.0))
    except Exception:
        return 0.0

# Authentication States
FYERS_AUTHENTICATED = "FYERS_AUTHENTICATED"
FYERS_TOKEN_EXPIRED = "FYERS_TOKEN_EXPIRED"
FYERS_REAUTH_REQUIRED = "FYERS_REAUTH_REQUIRED"
FYERS_AUTH_ERROR = "FYERS_AUTH_ERROR"


def _update_env_file(updates: Dict[str, str]):
    """Helper to safely update key=value pairs in ml_service/.env without corrupting existing lines."""
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        matched_key = None
        for key in updates:
            if stripped.startswith(f"{key}="):
                matched_key = key
                break

        if matched_key:
            updated_keys.add(matched_key)
            val = updates[matched_key].strip()
            if val:
                new_lines.append(f"{matched_key}={val}\n")
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys and val.strip():
            new_lines.append(f"{key}={val.strip()}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)


class FyersTokenManager:
    """Manages the server-side lifecycle of FYERS access and refresh tokens."""

    def __init__(self):
        self.token_store_path = FYERS.token_store_path
        self.token_store_path.parent.mkdir(parents=True, exist_ok=True)

        self.access_token: str = ""
        self.refresh_token: str = ""
        self.expires_at: float = 0.0
        self.status: str = FYERS_REAUTH_REQUIRED
        self.last_error: str = ""

        self.reload_and_verify()

    def load_tokens(self) -> bool:
        """Loads stored tokens from server-side JSON store or environment variables."""
        FYERS.reload()
        # 1. Check local JSON store
        if self.token_store_path.exists():
            try:
                with open(self.token_store_path, "r") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token", "").strip()
                    self.refresh_token = data.get("refresh_token", "").strip()
                    self.expires_at = float(data.get("expires_at", 0.0))
            except Exception as e:
                logger.warning("Error reading server-side token store: %s", e)

        # 2. Fallback to .env if JSON store empty
        if not self.access_token and FYERS.access_token:
            self.access_token = FYERS.access_token
        if not self.refresh_token and FYERS.refresh_token:
            self.refresh_token = FYERS.refresh_token

        return bool(self.access_token or self.refresh_token)

    def save_tokens(self, access_token: str, refresh_token: str = "", expires_in: int = 86400):
        """Persists access token and refresh token server-side and updates environment file."""
        self.access_token = access_token.strip()
        if refresh_token.strip():
            self.refresh_token = refresh_token.strip()

        self.expires_at = time.time() + float(expires_in)

        # Save to server-side JSON file (excluded from git/frontend)
        token_data = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "updated_at": time.time()
        }
        with open(self.token_store_path, "w") as f:
            json.dump(token_data, f, indent=2)

        # Sync to .env for fallback
        env_updates = {"FYERS_ACCESS_TOKEN": self.access_token}
        if self.refresh_token:
            env_updates["FYERS_REFRESH_TOKEN"] = self.refresh_token
        _update_env_file(env_updates)
        FYERS.reload()

        self.status = FYERS_AUTHENTICATED
        logger.info("[INFO] FYERS authentication loaded & tokens securely saved server-side.")

    def is_access_token_valid(self) -> bool:
        """Returns True if access token is present and not expired (with 5-minute safety buffer).
        When expires_at is 0.0 (token loaded from .env without a JSON store record),
        decodes the JWT payload directly to check the real 'exp' claim.
        """
        if not self.access_token:
            return False
        # If the JSON store has a recorded expiry, use it
        if self.expires_at > 0:
            if time.time() >= (self.expires_at - 300):
                logger.debug("[AUTH] Access token expired per stored expires_at.")
                return False
            return True
        # Fallback: decode the JWT exp claim directly (covers tokens loaded from .env)
        jwt_exp = _decode_jwt_exp(self.access_token)
        if jwt_exp > 0 and time.time() >= (jwt_exp - 300):
            logger.warning(
                "[AUTH] Access token loaded from .env is expired (JWT exp=%s, now=%s). "
                "Marking invalid so refresh-token flow can proceed.",
                jwt_exp, int(time.time())
            )
            return False
        return True

    def refresh_access_token(self) -> bool:
        """Attempts automatic access token renewal using the official Fyers v3 refresh-token endpoint.
        Uses a direct POST to https://api-t1.fyers.in/api/v3/validate-refresh-token with
        appIdHash (SHA-256 of client_id:secret_key) and the stored refresh token + PIN.
        SessionModel is NOT used here — it only supports authorization_code grant, not refresh_token.
        """
        if not FYERS.app_id or not FYERS.secret_key:
            self.status = FYERS_REAUTH_REQUIRED
            self.last_error = "Missing FYERS_APP_ID or FYERS_SECRET_KEY in environment."
            logger.warning("[WARNING] Cannot refresh FYERS token: missing App ID or Secret Key.")
            return False

        if not self.refresh_token:
            self.load_tokens()
            if not self.refresh_token:
                self.status = FYERS_REAUTH_REQUIRED
                self.last_error = "No refresh token available server-side."
                logger.info("[INFO] Refresh token not present server-side. Re-authentication required.")
                return False

        if not FYERS.pin:
            self.status = FYERS_REAUTH_REQUIRED
            self.last_error = "FYERS_PIN not configured in .env. Required for refresh-token flow."
            logger.warning("[WARNING] FYERS_PIN is not set — cannot auto-refresh access token. "
                           "Add FYERS_PIN=<your_4_digit_pin> to the .env file.")
            return False

        import hashlib
        import requests as _requests

        app_id_hash = hashlib.sha256(f"{FYERS.app_id}:{FYERS.secret_key}".encode()).hexdigest()
        url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
        payload = {
            "grant_type": "refresh_token",
            "appIdHash": app_id_hash,
            "refresh_token": self.refresh_token,
            "pin": FYERS.pin,
        }
        headers = {"Content-Type": "application/json"}

        retry_count = 3
        last_response = None
        last_exception = None

        for attempt in range(1, retry_count + 1):
            try:
                logger.info("[INFO] Refreshing FYERS access token via v3 endpoint (attempt %d/%d)...", attempt, retry_count)
                resp = _requests.post(url, json=payload, headers=headers, timeout=15)
                response = resp.json()
                last_response = response

                if isinstance(response, dict) and response.get("s") == "ok" and response.get("access_token"):
                    new_access_token = response["access_token"]
                    new_refresh_token = response.get("refresh_token", self.refresh_token)
                    expires_in = response.get("expires_in", 86400)
                    self.save_tokens(new_access_token, new_refresh_token, expires_in=expires_in)
                    logger.info("[INFO] FYERS access token refreshed successfully on attempt %d!", attempt)
                    return True

                error_msg = response.get("message", str(response)) if isinstance(response, dict) else str(response)
                error_code = response.get("code") if isinstance(response, dict) else None
                error_lower = error_msg.lower()

                explicit_invalid = (
                    error_code in [-14, 401, -501]
                    or "invalid refresh" in error_lower
                    or "refresh token expired" in error_lower
                    or "refresh token is invalid" in error_lower
                    or "token not found" in error_lower
                    or ("unauthorized" in error_lower and "refresh" in error_lower)
                )

                if explicit_invalid:
                    logger.error(
                        "[AUTH] FYERS refresh token explicitly rejected by server (code=%s, msg='%s'). "
                        "Clearing stored tokens — manual re-login required.",
                        error_code, error_msg
                    )
                    self._clear_all_tokens()
                    self.status = FYERS_REAUTH_REQUIRED
                    self.last_error = f"Re-authentication required: {error_msg}"
                    return False

                logger.warning(
                    "[AUTH] Refresh attempt %d returned non-ok (code=%s, msg='%s'). Retrying...",
                    attempt, error_code, error_msg
                )

            except Exception as e:
                last_exception = e
                logger.warning("[AUTH] Refresh attempt %d raised exception: %s. Retrying...", attempt, e)

            if attempt < retry_count:
                import time as _time
                _time.sleep(2 ** attempt)

        logger.error("[AUTH] All %d refresh attempts failed. Last response: %s. Last exception: %s",
                     retry_count, last_response, last_exception)

        self.status = FYERS_TOKEN_EXPIRED
        self.last_error = (
            f"Automatic token refresh failed after {retry_count} attempts. "
            f"Last error: {last_exception or last_response}"
        )
        return False


    def _clear_all_tokens(self):
        """Wipes tokens from in-memory state, server-side JSON store, and .env fallback."""
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = 0.0

        if self.token_store_path.exists():
            try:
                with open(self.token_store_path, "w") as f:
                    import json as _json
                    _json.dump({"access_token": "", "refresh_token": "", "expires_at": 0, "cleared_at": __import__("time").time()}, f, indent=2)
                logger.info("[AUTH] Server-side token store cleared.")
            except Exception as e:
                logger.warning("[AUTH] Could not clear token store file: %s", e)

        _update_env_file({"FYERS_ACCESS_TOKEN": "", "FYERS_REFRESH_TOKEN": ""})
        FYERS.reload()

    def exchange_code_for_tokens(self, auth_code: str) -> str:
        """Exchanges initial auth_code for access_token and refresh_token, saving them server-side."""
        if not FYERS.app_id or not FYERS.secret_key:
            raise ValueError("FYERS_APP_ID and FYERS_SECRET_KEY must be set in environment.")

        from fyers_apiv3 import fyersModel

        session = fyersModel.SessionModel(
            client_id=FYERS.app_id,
            secret_key=FYERS.secret_key,
            redirect_uri=FYERS.redirect_url,
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_token()

        if isinstance(response, dict) and response.get("s") == "ok" and response.get("access_token"):
            access_token = response["access_token"]
            refresh_token = response.get("refresh_token", "")
            expires_in = response.get("expires_in", 86400)
            self.save_tokens(access_token, refresh_token, expires_in=expires_in)
            return access_token
        else:
            msg = response.get("message", str(response)) if isinstance(response, dict) else str(response)
            self.status = FYERS_AUTH_ERROR
            self.last_error = msg
            raise RuntimeError(f"FYERS token generation failed: {msg}")

    def reload_and_verify(self) -> str:
        """Startup check: loads stored tokens, validates access token, or automatically refreshes token."""
        self.load_tokens()

        if not FYERS.app_id:
            self.status = FYERS_REAUTH_REQUIRED
            self.last_error = "FYERS_APP_ID not configured."
            return self.status

        if self.is_access_token_valid():
            self.status = FYERS_AUTHENTICATED
            logger.info("[INFO] FYERS access token is valid and active.")
            return self.status

        # Access token missing or expired -> attempt refresh if refresh token present
        if self.refresh_token:
            if self.refresh_access_token():
                return self.status

        self.status = FYERS_REAUTH_REQUIRED
        self.last_error = "Re-authentication required. Access token expired and no valid refresh token."
        logger.info("[INFO] FYERS authentication status: %s", self.status)
        return self.status

    def get_auth_status(self) -> Dict[str, Any]:
        """Returns safe user-friendly authentication status dict for backend API responses without leaking secrets/tokens."""
        return {
            "status": self.status,
            "is_authenticated": (self.status == FYERS_AUTHENTICATED),
            "app_id_configured": bool(FYERS.app_id),
            "has_access_token": bool(self.access_token),
            "has_refresh_token": bool(self.refresh_token),
            "last_error": self.last_error if self.status != FYERS_AUTHENTICATED else ""
        }


# Global Singleton Manager Instance
_token_manager_instance: FyersTokenManager | None = None

def get_token_manager() -> FyersTokenManager:
    global _token_manager_instance
    if _token_manager_instance is None:
        _token_manager_instance = FyersTokenManager()
    return _token_manager_instance
