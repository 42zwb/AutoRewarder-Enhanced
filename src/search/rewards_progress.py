"""Read and validate the server-side Microsoft Rewards search counter.

The browser search page only proves that a navigation happened.  Rewards may
decline to credit that navigation, so search completion must be based on the
authenticated Rewards user-info response instead of Selenium actions.
"""

from dataclasses import dataclass
import json
import time

from selenium.webdriver.common.by import By

REWARDS_USERINFO_URL = "https://rewards.bing.com/api/getuserinfo?type=1"


def _integer(value):
    """Return a non-negative integer or ``None`` for malformed values."""
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


@dataclass(frozen=True)
class RewardsSearchProgress:
    """Authoritative search progress returned for the signed-in account."""

    balance: int | None
    points: int | None
    maximum: int | None
    points_per_search: int | None

    @property
    def available(self):
        return self.points is not None and self.maximum is not None

    @property
    def complete(self):
        return self.available and self.maximum > 0 and self.points >= self.maximum


@dataclass(frozen=True)
class SearchCreditResult:
    """Comparison between two authoritative Rewards counter snapshots."""

    status: str
    submitted: int
    credited: int
    points_delta: int | None
    reason: str = ""

    @property
    def successful(self):
        return self.status in ("completed", "already_done")


def evaluate_search_credit(before, after, submitted):
    """Classify browser submissions using server-side Rewards progress."""
    submitted = max(0, _integer(submitted) or 0)
    if isinstance(before, RewardsSearchProgress) and before.complete:
        return SearchCreditResult("already_done", 0, 0, 0)
    if submitted <= 0:
        return SearchCreditResult("failed", 0, 0, None, "no Bing result loaded")
    if not isinstance(before, RewardsSearchProgress) or not before.available:
        return SearchCreditResult(
            "unavailable", submitted, 0, None, "starting Rewards counter unavailable"
        )
    if not isinstance(after, RewardsSearchProgress) or not after.available:
        return SearchCreditResult(
            "unavailable", submitted, 0, None, "final Rewards counter unavailable"
        )

    delta = after.points - before.points
    if delta < 0:
        return SearchCreditResult(
            "unavailable", submitted, 0, None, "Rewards counter moved backwards"
        )
    if delta == 0:
        return SearchCreditResult(
            "uncredited",
            submitted,
            0,
            0,
            "browser submissions did not increase Rewards search progress",
        )

    points_per_search = after.points_per_search or before.points_per_search
    credited = delta // points_per_search if points_per_search else 0
    if after.complete or credited >= submitted:
        return SearchCreditResult("completed", submitted, credited, delta)
    return SearchCreditResult(
        "partial",
        submitted,
        credited,
        delta,
        "only part of the submitted searches received Rewards credit",
    )


def parse_rewards_search_progress(payload):
    """Parse the small subset of ``getuserinfo`` used for verification."""
    if not isinstance(payload, dict):
        return RewardsSearchProgress(None, None, None, None)

    dashboard = payload.get("dashboard")
    user = dashboard.get("userStatus") if isinstance(dashboard, dict) else None
    if not isinstance(user, dict):
        return RewardsSearchProgress(None, None, None, None)

    level = user.get("levelInfo")
    level = level if isinstance(level, dict) else {}
    counters = user.get("counters")
    counters = counters if isinstance(counters, dict) else {}
    pc_search = counters.get("pcSearch")
    if isinstance(pc_search, list):
        pc_search = next((item for item in pc_search if isinstance(item, dict)), {})
    elif not isinstance(pc_search, dict):
        pc_search = {}

    attributes = pc_search.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}

    points = _integer(pc_search.get("pointProgress"))
    if points is None:
        points = _integer(attributes.get("progress"))
    if points is None:
        points = _integer(level.get("bingSearchDailyPoints"))

    maximum = _integer(pc_search.get("pointProgressMax"))
    points_per_search = _integer(level.get("pointsPerSearch"))
    balance = _integer(user.get("availablePoints"))
    return RewardsSearchProgress(balance, points, maximum, points_per_search)


def fetch_rewards_search_progress(driver, attempts=3, delay=1.5):
    """Navigate to the authenticated user-info endpoint and parse its counter.

    This is intentionally read-only.  Returning ``None`` on any malformed or
    unavailable response makes callers fail closed rather than claiming that
    browser actions earned points.
    """
    try:
        driver.set_page_load_timeout(30)
    except Exception:
        pass

    try:
        # Avoid a cached pre-search JSON document when this endpoint is read
        # again after the browser submissions.
        separator = "&" if "?" in REWARDS_USERINFO_URL else "?"
        driver.get(f"{REWARDS_USERINFO_URL}{separator}_={time.time_ns()}")
    except Exception:
        return None

    for attempt in range(max(1, int(attempts or 1))):
        try:
            body = driver.find_element(By.TAG_NAME, "body").text
            parsed = parse_rewards_search_progress(json.loads(body))
            if parsed.available and parsed.balance is not None:
                return parsed
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError):
            pass
        except Exception:
            return None
        if attempt + 1 < max(1, int(attempts or 1)):
            time.sleep(max(0.0, float(delay or 0)))
    return None
