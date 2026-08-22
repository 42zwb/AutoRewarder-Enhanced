"""Policy/orchestration for the mobile check-in and Read to Earn activities."""

import json
import os
from datetime import date, datetime

from .client import (
    RewardsActivityClient,
    RewardsAuthError,
    RewardsClientError,
    RewardsUnavailableError,
    extract_locale,
)
from .models import MobileTaskSummary, RESULT_STATUSES
from .oauth import OAuthError, OAuthManager
from ..security import atomic_write_json
from .tasks import DailyCheckInTask, ReadToEarnTask

DEFAULT_MOBILE_TASKS = {
    "enabled": True,
    "check_in_enabled": True,
    "read_to_earn_enabled": True,
    "max_articles": 10,
    "read_delay_min": 8,
    "read_delay_max": 18,
    "target_points": 30,
    "offer_id": "",
}


def _atomic_write(path, data):
    atomic_write_json(path, data, indent=2)


class MobileTaskRunner:
    """Run at most one mobile task pass per top-level AutoRewarder run."""

    def __init__(
        self,
        account_id,
        status_path,
        token_path,
        driver_manager=None,
        config=None,
        logger=None,
        stop_event=None,
        client_factory=RewardsActivityClient,
        oauth_factory=OAuthManager,
    ):
        self.account_id = str(account_id)
        self.status_path = status_path
        self.token_path = token_path
        self.driver_manager = driver_manager
        self.logger = logger
        self.stop_event = stop_event
        self.client_factory = client_factory
        self.oauth_factory = oauth_factory
        self.oauth = None
        self.set_config(config)

    def _configure_tasks(self):
        self.check_in_task = DailyCheckInTask(
            self.config,
            save_status=self._save_status,
            logger=self.logger,
            stop_event=self.stop_event,
        )
        self.read_to_earn_task = ReadToEarnTask(
            self.config,
            save_status=self._save_status,
            logger=self.logger,
            stop_event=self.stop_event,
        )

    def set_config(self, config=None):
        """Update validated account settings and refresh task instances."""
        self.config = {**DEFAULT_MOBILE_TASKS, **(config or {})}
        self._configure_tasks()

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def _new_status(self):
        today = date.today().isoformat()
        return {
            "date": today,
            "check_in": {"status": "stopped", "points": 0},
            "read_to_earn": {
                "status": "stopped",
                "articles": 0,
                "points": 0,
                "target_points": self._target_points(),
                "target_articles": self._max_articles(),
            },
            "result": "stopped",
            "reason": "",
            "last_attempt_at": "",
        }

    def _load_status(self):
        if not os.path.exists(self.status_path):
            return self._new_status()
        try:
            with open(self.status_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError, json.JSONDecodeError):
            self._log(
                "[WARNING] mobile_status.json is unreadable; starting a fresh mobile status."
            )
            return self._new_status()
        if not isinstance(data, dict) or data.get("date") != date.today().isoformat():
            return self._new_status()
        fresh = self._new_status()
        fresh.update(data)
        if not isinstance(fresh.get("check_in"), dict):
            fresh["check_in"] = {"status": "stopped", "points": 0}
        if not isinstance(fresh.get("read_to_earn"), dict):
            fresh["read_to_earn"] = self._new_status()["read_to_earn"]
        # The UI should reflect the current account configuration immediately,
        # even when the persisted file was created with a different target.
        fresh["read_to_earn"]["target_points"] = self._target_points()
        fresh["read_to_earn"]["target_articles"] = self._max_articles()
        valid_statuses = set(RESULT_STATUSES)

        def _status(value, fallback="stopped"):
            return (
                value
                if isinstance(value, str) and value in valid_statuses
                else fallback
            )

        def _number(value, maximum):
            try:
                return max(0, min(maximum, int(value)))
            except (TypeError, ValueError, OverflowError):
                return 0

        fresh["check_in"]["status"] = _status(fresh["check_in"].get("status"))
        fresh["check_in"]["points"] = _number(fresh["check_in"].get("points"), 10000)
        fresh["read_to_earn"]["status"] = _status(fresh["read_to_earn"].get("status"))
        fresh["read_to_earn"]["articles"] = _number(
            fresh["read_to_earn"].get("articles"), self._max_articles()
        )
        fresh["read_to_earn"]["points"] = _number(
            fresh["read_to_earn"].get("points"), self._target_points()
        )
        fresh["result"] = _status(fresh.get("result"))
        fresh["reason"] = str(fresh.get("reason") or "")[:500]
        fresh["last_attempt_at"] = str(fresh.get("last_attempt_at") or "")[:64]
        # A persisted success marker is meaningful only when each enabled
        # subtask also has a success marker. This prevents a damaged/manual
        # status file from suppressing today's work.
        enabled_statuses = []
        if self.config.get("check_in_enabled", True):
            enabled_statuses.append(fresh["check_in"]["status"])
        if self.config.get("read_to_earn_enabled", True):
            enabled_statuses.append(fresh["read_to_earn"]["status"])
        if fresh["result"] in ("completed", "already_done") and not enabled_statuses:
            fresh["result"] = "unavailable"
        elif fresh["result"] in ("completed", "already_done") and not all(
            value in ("completed", "already_done") for value in enabled_statuses
        ):
            fresh["result"] = "partial"
        return fresh

    def _save_status(self, status):
        status["date"] = date.today().isoformat()
        status["last_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        _atomic_write(self.status_path, status)

    def get_status(self):
        """Return today's status for UI/diagnostics without contacting Microsoft."""
        return self._load_status()

    def _max_articles(self):
        try:
            return max(1, min(10, int(self.config.get("max_articles", 10))))
        except (TypeError, ValueError):
            return 10

    def _target_points(self):
        try:
            return max(1, min(100, int(self.config.get("target_points", 30))))
        except (TypeError, ValueError):
            return 30

    def _delays(self):
        try:
            low = max(0, min(3600, int(self.config.get("read_delay_min", 8))))
        except (TypeError, ValueError):
            low = 8
        try:
            high = max(low, min(3600, int(self.config.get("read_delay_max", 18))))
        except (TypeError, ValueError):
            high = max(low, 18)
        return low, high

    def _build_oauth(self):
        return self.oauth_factory(
            self.account_id,
            self.token_path,
            driver_manager=self.driver_manager,
            logger=self.logger,
        )

    def _set_result(self, status, check_status, read_status, reason, status_data):
        status_data["result"] = status if status in RESULT_STATUSES else "failed"
        status_data["reason"] = str(reason or "")[:500]
        status_data["check_in"]["status"] = check_status
        status_data["read_to_earn"]["status"] = read_status
        self._save_status(status_data)

    def _summary(self, status_data):
        return MobileTaskSummary.from_status(status_data)

    def _check_in(self, client, profile, status_data):
        return self.check_in_task.run(client, profile, status_data)

    def _read_to_earn(self, client, profile, status_data, current_balance):
        return self.read_to_earn_task.run(client, profile, status_data, current_balance)

    def run(self, account_id=None, force=False):
        """Run check-in then Read to Earn once; retry only incomplete state.

        ``account_id`` is accepted explicitly to keep the public orchestration
        contract unambiguous. The instance is already account-scoped, so a
        mismatched id fails closed instead of writing another account's state.
        For backward compatibility, ``run(True)`` is also interpreted as
        ``run(force=True)``.
        """
        if isinstance(account_id, bool) and force is False:
            force = account_id
            account_id = None
        if account_id is not None and str(account_id) != self.account_id:
            status_data = self._load_status()
            self._set_result(
                "failed",
                "failed",
                "failed",
                "mobile runner account mismatch",
                status_data,
            )
            return self._summary(status_data)
        status_data = self._load_status()
        status_data["read_to_earn"]["target_points"] = self._target_points()
        status_data["read_to_earn"]["target_articles"] = self._max_articles()
        if not self.config.get("enabled", True):
            self._set_result(
                "unavailable",
                "stopped",
                "stopped",
                "mobile tasks disabled by configuration",
                status_data,
            )
            return self._summary(status_data)
        if not self.config.get("check_in_enabled", True) and not self.config.get(
            "read_to_earn_enabled", True
        ):
            self._set_result(
                "unavailable",
                "stopped",
                "stopped",
                "all mobile tasks disabled by configuration",
                status_data,
            )
            return self._summary(status_data)
        if not force and status_data.get("result") in ("completed", "already_done"):
            return self._summary(status_data)
        if self.stop_event is not None and self.stop_event.is_set():
            self._set_result(
                "stopped", "stopped", "stopped", "stop requested", status_data
            )
            return self._summary(status_data)
        self.oauth = self._build_oauth()
        try:
            token = self.oauth.get_access_token()
        except OAuthError as exc:
            self._set_result(
                "auth_required", "auth_required", "auth_required", str(exc), status_data
            )
            return self._summary(status_data)
        try:
            client = self.client_factory(
                token,
                token_refresh=lambda: self.oauth.get_access_token(force_refresh=True),
                logger=self.logger,
            )
            profile_response = client.get_profile()
            profile = profile_response.data
            country, language = extract_locale(profile)
            if country:
                client.country = country
            if language:
                client.language = language
            check_result = self._check_in(client, profile, status_data)
            if check_result.status in ("unavailable", "failed"):
                self._set_result(
                    check_result.status,
                    check_result.status,
                    "stopped",
                    check_result.reason,
                    status_data,
                )
                return self._summary(status_data)
            balance = profile_response.balance
            if check_result.status == "completed" and balance is not None:
                # The profile snapshot predates the check-in request. Carry
                # its verified delta forward so the first Read to Earn delta
                # is not accidentally inflated by the check-in points.
                balance += check_result.points
            read_result = self._read_to_earn(client, profile, status_data, balance)
            check_status = status_data["check_in"].get("status", check_result.status)
            read_status = status_data["read_to_earn"].get("status", read_result.status)
            enabled_statuses = []
            if self.config.get("check_in_enabled", True):
                enabled_statuses.append(check_status)
            if self.config.get("read_to_earn_enabled", True):
                enabled_statuses.append(read_status)
            if not enabled_statuses:
                overall = "unavailable"
            elif self.stop_event is not None and self.stop_event.is_set():
                overall = "stopped"
            elif "auth_required" in enabled_statuses:
                overall = "auth_required"
            elif "failed" in enabled_statuses:
                overall = "failed"
            elif "unavailable" in enabled_statuses:
                overall = "unavailable"
            elif "partial" in enabled_statuses:
                overall = "partial"
            elif "stopped" in enabled_statuses:
                overall = "stopped"
            elif all(
                status in ("completed", "already_done") for status in enabled_statuses
            ):
                overall = (
                    "already_done"
                    if all(status == "already_done" for status in enabled_statuses)
                    else "completed"
                )
            else:
                overall = "partial"
            reason = "; ".join(
                part for part in (check_result.reason, read_result.reason) if part
            )
            self._set_result(overall, check_status, read_status, reason, status_data)
            return self._summary(status_data)
        except RewardsAuthError as exc:
            self._set_result(
                "auth_required", "auth_required", "auth_required", str(exc), status_data
            )
            return self._summary(status_data)
        except RewardsUnavailableError as exc:
            self._set_result(
                "unavailable", "unavailable", "unavailable", str(exc), status_data
            )
            return self._summary(status_data)
        except RewardsClientError as exc:
            self._set_result("failed", "failed", "failed", str(exc), status_data)
            return self._summary(status_data)
        except Exception as exc:
            self._set_result(
                "failed",
                "failed",
                "failed",
                f"unexpected mobile task error: {exc}",
                status_data,
            )
            return self._summary(status_data)
