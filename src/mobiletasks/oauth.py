"""Interactive Microsoft OAuth and headless refresh-token handling."""

import time
import urllib.parse
import uuid

import requests

from .secure_store import ProtectedTokenStore, SecretStoreError

OAUTH_CLIENT_ID = "0000000040170455"
OAUTH_AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
OAUTH_REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
OAUTH_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
OAUTH_SCOPE = "service::prod.rewardsplatform.microsoft.com::MBI_SSL"


class OAuthError(RuntimeError):
    """Raised when OAuth cannot produce a usable access token."""


class OAuthManager:
    """Manage one account's protected refresh token."""

    def __init__(self, account_id, token_path, driver_manager=None, logger=None, session=None):
        self.account_id = str(account_id)
        self.store = ProtectedTokenStore(token_path)
        self.driver_manager = driver_manager
        self.logger = logger
        self.session = session or requests.Session()
        self._access_token = None
        self._access_token_expires_at = 0

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def has_refresh_token(self):
        try:
            return bool(self.store.load(self.account_id))
        except SecretStoreError:
            return False

    def _exchange_refresh_token(self, refresh_token):
        try:
            response = self.session.post(
                OAUTH_TOKEN_URL,
                data={
                    "client_id": OAUTH_CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "scope": OAUTH_SCOPE,
                },
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            raise OAuthError(f"OAuth token refresh network error: {exc}") from exc
        if response.status_code in (400, 401, 403):
            raise OAuthError("OAuth refresh token expired or was rejected")
        if response.status_code >= 400:
            raise OAuthError(f"OAuth token endpoint returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OAuthError("OAuth token endpoint returned invalid JSON") from exc
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not access_token:
            raise OAuthError("OAuth token response did not contain an access token")
        new_refresh = payload.get("refresh_token") or refresh_token
        try:
            self.store.save(new_refresh, self.account_id)
        except SecretStoreError as exc:
            raise OAuthError("Could not save the protected OAuth refresh token") from exc
        self._access_token = str(access_token)
        try:
            expires = max(60, int(payload.get("expires_in", 3600)))
        except (TypeError, ValueError):
            expires = 3600
        self._access_token_expires_at = time.time() + expires - 60
        return self._access_token

    def get_access_token(self, force_refresh=False):
        if self._access_token and not force_refresh and time.time() < self._access_token_expires_at:
            return self._access_token
        try:
            refresh_token = self.store.load(self.account_id)
        except SecretStoreError as exc:
            raise OAuthError(str(exc)) from exc
        if not refresh_token:
            raise OAuthError("Mobile OAuth authorization is required")
        return self._exchange_refresh_token(refresh_token)

    def connect(self, timeout=180):
        """Open the account's Edge profile and complete a one-time code flow.

        The browser remains visible so the user can approve/sign in. Passwords
        are never read by this program. The callback is inspected only for the
        short-lived authorization code, which is exchanged immediately.
        """
        if self.driver_manager is None:
            raise OAuthError("An Edge profile is required for interactive authorization")
        params = {
            "client_id": OAUTH_CLIENT_ID,
            "scope": OAUTH_SCOPE,
            "response_type": "code",
            "redirect_uri": OAUTH_REDIRECT_URI,
            "state": uuid.uuid4().hex,
        }
        url = f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
        driver = None
        try:
            driver = self.driver_manager.setup_driver(headless=False, mobile=False)
            driver.get(url)
            deadline = time.time() + max(30, int(timeout))
            code = None
            while time.time() < deadline:
                current = driver.current_url or ""
                parsed = urllib.parse.urlparse(current)
                query = urllib.parse.parse_qs(parsed.query)
                if query.get("error"):
                    detail = query.get("error_description", query.get("error"))[0]
                    raise OAuthError(f"OAuth authorization failed: {detail[:160]}")
                if query.get("code"):
                    code = query["code"][0]
                    break
                time.sleep(1)
            if not code:
                raise OAuthError("Timed out waiting for Microsoft OAuth authorization")
            try:
                response = self.session.post(
                    OAUTH_TOKEN_URL,
                    data={
                        "client_id": OAUTH_CLIENT_ID,
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": OAUTH_REDIRECT_URI,
                        "scope": OAUTH_SCOPE,
                    },
                    timeout=(10, 30),
                )
            except requests.RequestException as exc:
                raise OAuthError(f"OAuth authorization exchange network error: {exc}") from exc
            if response.status_code >= 400:
                raise OAuthError(f"OAuth authorization exchange returned HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise OAuthError("OAuth authorization exchange returned invalid JSON") from exc
            refresh_token = payload.get("refresh_token") if isinstance(payload, dict) else None
            if not refresh_token:
                raise OAuthError("OAuth response did not contain a refresh token")
            self.store.save(refresh_token, self.account_id)
            self._access_token = None
            token = self._exchange_refresh_token(refresh_token)
            self._log("Mobile OAuth authorization completed; refresh token saved with Windows DPAPI.")
            return bool(token)
        except SecretStoreError as exc:
            raise OAuthError(str(exc)) from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
