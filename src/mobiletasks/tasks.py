"""Independent task implementations for the Microsoft Rewards mobile flow."""

import random
import time

from .client import activity_says_done, extract_balance, extract_locale, extract_read_offer_id
from .models import MobileTaskResult


class _TaskBase:
    """Shared configuration, persistence, and cancellation helpers."""

    def __init__(self, config=None, save_status=None, logger=None, stop_event=None):
        self.config = config if isinstance(config, dict) else {}
        self.save_status = save_status
        self.logger = logger
        self.stop_event = stop_event

    def _save(self, status_data):
        if self.save_status is not None:
            self.save_status(status_data)

    def _log(self, message):
        if self.logger:
            self.logger(message)

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

    @staticmethod
    def _number(value):
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0


class DailyCheckInTask(_TaskBase):
    """Submit the current account's mobile daily check-in once."""

    activity_type = 103

    def run(self, client, profile, status_data):
        entry = status_data.setdefault("check_in", {"status": "stopped", "points": 0})
        if not self.config.get("check_in_enabled", True):
            entry["status"] = "stopped"
            self._save(status_data)
            return MobileTaskResult("check_in", "stopped", reason="disabled by configuration")

        current_status = entry.get("status")
        if current_status in ("completed", "already_done"):
            return MobileTaskResult(
                "check_in",
                current_status,
                points=self._number(entry.get("points")),
                reason="already recorded today",
            )

        country, _language = extract_locale(profile)
        if not country:
            return MobileTaskResult(
                "check_in", "unavailable", reason="current Rewards region was not returned"
            )

        before = extract_balance(profile)
        if activity_says_done(profile, self.activity_type):
            entry["status"] = "already_done"
            self._save(status_data)
            return MobileTaskResult(
                "check_in", "already_done", reason="profile reports completed"
            )

        response = client.submit_activity(self.activity_type, country)
        after = response.balance
        if before is not None and after is not None and after > before:
            gained = after - before
            entry.update({"status": "completed", "points": gained})
            self._save(status_data)
            return MobileTaskResult("check_in", "completed", points=gained)

        if response.completed:
            entry["status"] = "already_done"
            self._save(status_data)
            return MobileTaskResult(
                "check_in", "already_done", reason="API reports already completed"
            )

        entry["status"] = "partial"
        self._save(status_data)
        return MobileTaskResult(
            "check_in", "partial", reason="request returned no positive balance delta"
        )


class ReadToEarnTask(_TaskBase):
    """Submit unique Read to Earn activities until the verified target is met."""

    activity_type = 101

    def run(self, client, profile, status_data, current_balance):
        entry = status_data.setdefault(
            "read_to_earn",
            {"status": "stopped", "articles": 0, "points": 0},
        )
        if not self.config.get("read_to_earn_enabled", True):
            entry["status"] = "stopped"
            self._save(status_data)
            return MobileTaskResult(
                "read_to_earn", "stopped", reason="disabled by configuration"
            )

        target = self._target_points()
        limit = self._max_articles()
        entry["target_points"] = target
        entry["target_articles"] = limit
        existing_points = self._number(entry.get("points"))
        existing_articles = self._number(entry.get("articles"))

        if entry.get("status") in ("completed", "already_done"):
            return MobileTaskResult(
                "read_to_earn",
                entry["status"],
                existing_points,
                existing_articles,
                "already recorded today",
            )
        if existing_points >= target:
            entry["status"] = "already_done"
            self._save(status_data)
            return MobileTaskResult(
                "read_to_earn",
                "already_done",
                existing_points,
                existing_articles,
                "target already recorded",
            )

        country, language = extract_locale(profile)
        if not country:
            return MobileTaskResult(
                "read_to_earn",
                "unavailable",
                existing_points,
                existing_articles,
                "current Rewards region was not returned",
            )
        offer_id = self.config.get("offer_id") or extract_read_offer_id(profile)
        if not offer_id:
            return MobileTaskResult(
                "read_to_earn",
                "unavailable",
                existing_points,
                existing_articles,
                "read activity is not available for this region",
            )

        client.country = country
        if language:
            client.language = language
        balance = current_balance
        gained_total = existing_points
        articles = existing_articles
        low, high = self._delays()

        for index in range(existing_articles, limit):
            if self.stop_event is not None and self.stop_event.is_set():
                entry["status"] = "stopped"
                self._save(status_data)
                return MobileTaskResult(
                    "read_to_earn", "stopped", gained_total, articles, "stop requested"
                )

            response = client.submit_activity(
                self.activity_type, country, offer_id=offer_id
            )
            new_balance = response.balance
            delta = None
            if balance is not None and new_balance is not None:
                delta = new_balance - balance
            if delta is None or delta <= 0:
                entry["status"] = "partial"
                self._save(status_data)
                reason = "no positive balance delta; stopped to avoid duplicate submissions"
                if response.completed:
                    reason = "API reports completed but balance did not increase"
                return MobileTaskResult(
                    "read_to_earn", "partial", gained_total, articles, reason
                )

            gained_total += delta
            articles = index + 1
            balance = new_balance
            entry.update({"status": "partial", "articles": articles, "points": gained_total})
            self._save(status_data)
            if gained_total >= target:
                entry["status"] = "completed"
                self._save(status_data)
                return MobileTaskResult(
                    "read_to_earn", "completed", gained_total, articles
                )
            if index < limit - 1 and high > 0:
                time.sleep(random.uniform(low, high))

        entry["status"] = "partial"
        self._save(status_data)
        return MobileTaskResult(
            "read_to_earn",
            "partial",
            gained_total,
            articles,
            "article limit reached before target points",
        )
