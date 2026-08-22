"""HTTP client for the Microsoft Rewards mobile activity endpoint."""

import random
import re
import time
import uuid
from dataclasses import dataclass

import requests

BASE_URL = "https://prod.rewardsplatform.microsoft.com"
PROFILE_PATH = "/dapi/me"
ACTIVITIES_PATH = "/dapi/me/activities"
APP_ID = "SAIOS/33.4.440603001"
PARTNER_ID = "startapp"
USER_AGENT = (
    "Mozilla/5.0 (iPad; CPU iPad OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 "
    "Mobile/15E148 Safari/605.1.15 BingSapphire/33.4.440603001"
)


class RewardsClientError(RuntimeError):
    """Base class for mobile activity transport/schema failures."""


class RewardsAuthError(RewardsClientError):
    """The access token is absent or rejected."""


class RewardsUnavailableError(RewardsClientError):
    """The activity is not exposed for this account/region."""


@dataclass
class ActivityResponse:
    status_code: int
    data: dict

    @property
    def balance(self):
        return extract_balance(self.data)

    @property
    def completed(self):
        return response_says_done(self.data)


def _walk(value):
    """Yield nested dicts/lists without assuming a response schema."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def extract_balance(payload):
    """Extract a plausible Rewards balance from known and nested response keys."""
    preferred = ("balance", "currentPoints", "availablePoints", "pointsBalance")
    for obj in _walk(payload):
        for key in preferred:
            value = obj.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                return int(value)
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def response_says_done(payload):
    """Recognize explicit completion/already-claimed markers only."""
    done_keys = ("completed", "isCompleted", "alreadyCompleted", "claimed", "isClaimed")
    for obj in _walk(payload):
        for key in done_keys:
            if obj.get(key) is True:
                return True
        for key in ("status", "state", "message", "result"):
            value = obj.get(key)
            if isinstance(value, str) and re.search(r"already|complete|claimed|done", value, re.I):
                return True
    return False


def activity_says_done(payload, activity_type):
    """Recognize completion markers attached to one specific activity type."""
    wanted = str(int(activity_type))
    for obj in _walk(payload):
        kind = obj.get("type", obj.get("activityType"))
        if str(kind) != wanted:
            continue
        if response_says_done(obj):
            return True
    return False


def extract_locale(payload):
    """Return (country/geoLocale, language) when the profile exposes them."""
    country = None
    language = None
    for obj in _walk(payload):
        if not country:
            for key in ("geoLocale", "country", "countryCode", "market"):
                value = obj.get(key)
                if isinstance(value, str) and 2 <= len(value) <= 12:
                    country = value
                    break
        if not language:
            for key in ("langCode", "language", "locale"):
                value = obj.get(key)
                if isinstance(value, str) and 2 <= len(value) <= 16:
                    language = value
                    break
        if country and language:
            break
    return country, language


def extract_read_offer_id(payload):
    """Find a region-specific read-to-earn offer id in the profile payload."""
    candidates = []
    for obj in _walk(payload):
        for key, value in obj.items():
            if not isinstance(value, str):
                continue
            if key.lower() in ("offerid", "offer_id", "id") or "offer" in key.lower():
                if re.search(r"read(?:article|toearn)|read.?article", value, re.I):
                    candidates.append(value)
            elif re.search(r"read(?:article|toearn)|read.?article", value, re.I):
                candidates.append(value)
    # Prefer the offer that advertises the usual 30-point target, while still
    # accepting a regional variant if Microsoft changes the suffix.
    candidates = list(dict.fromkeys(candidates))
    candidates.sort(key=lambda value: ("30points" not in value.lower(), len(value)))
    return candidates[0] if candidates else None


class RewardsActivityClient:
    """Small, schema-defensive client for profile and activity submissions."""

    def __init__(
        self,
        access_token,
        token_refresh=None,
        logger=None,
        session=None,
        country=None,
        language=None,
        timeout=(10, 30),
        max_retries=3,
    ):
        if not access_token:
            raise RewardsAuthError("Mobile access token is missing")
        self.access_token = str(access_token)
        self.token_refresh = token_refresh
        self.logger = logger
        self.session = session or requests.Session()
        self.country = country
        self.language = language
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Rewards-AppId": APP_ID,
            "X-Rewards-PartnerId": PARTNER_ID,
            "X-Rewards-IsMobile": "true",
            "X-Rewards-ismobile": "true",
        }
        if self.country:
            headers["X-Rewards-Country"] = str(self.country)
        if self.language:
            headers["X-Rewards-Language"] = str(self.language)
        return headers

    def _request(self, method, path, params=None, payload=None):
        url = BASE_URL + path
        refreshed = False
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt + 1 >= self.max_retries:
                    raise RewardsClientError(f"Rewards API network error: {exc}") from exc
                delay = min(30.0, 2**attempt + random.uniform(0.1, 0.8))
                self._log(f"Mobile activity network retry {attempt + 1}/{self.max_retries} after {delay:.1f}s.")
                time.sleep(delay)
                continue

            if response.status_code in (401, 403):
                if not refreshed and self.token_refresh is not None:
                    refreshed = True
                    try:
                        self.access_token = self.token_refresh()
                    except Exception as exc:
                        raise RewardsAuthError("Mobile OAuth refresh was rejected") from exc
                    continue
                raise RewardsAuthError(f"Mobile activity authorization rejected (HTTP {response.status_code})")

            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 >= self.max_retries:
                    raise RewardsClientError(f"Mobile activity endpoint returned HTTP {response.status_code}")
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = 2**attempt + random.uniform(0.1, 0.8)
                delay = min(30.0, max(0.5, delay))
                self._log(f"Mobile activity HTTP {response.status_code}; retry {attempt + 1}/{self.max_retries} after {delay:.1f}s.")
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                raise RewardsClientError(f"Mobile activity endpoint returned HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise RewardsClientError("Mobile activity endpoint returned invalid JSON") from exc
            if not isinstance(data, dict):
                raise RewardsClientError("Mobile activity response schema is not an object")
            return ActivityResponse(response.status_code, data)
        raise RewardsClientError("Mobile activity request exhausted retries")

    def get_profile(self):
        return self._request("GET", PROFILE_PATH, params={"channel": "SAIOS", "options": "613"})

    def submit_activity(self, activity_type, country, offer_id=None):
        attributes = {}
        if offer_id:
            attributes["offerid"] = str(offer_id)
        body = {
            "risk_context": {},
            "type": int(activity_type),
            "channel": "SAIOS",
            "attributes": attributes,
            "id": uuid.uuid4().hex,
            "amount": 1,
            "country": str(country),
        }
        # Deliberately do not log body or headers: a request id is enough for
        # diagnostics and avoids leaking account-specific activity data.
        self._log(f"Submitting mobile activity type={int(activity_type)} request_id={body['id']}")
        return self._request("POST", ACTIVITIES_PATH, payload=body)
