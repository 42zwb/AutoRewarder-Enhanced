"""Per-account metadata persistence (setup, schedule, mobile task settings)."""

import json
import os

from ..config import account_dir, account_meta_path

DEFAULT_ACCOUNT_SCHEDULE = {
    # Master toggle for this account's scheduled headless run.
    "enabled": False,
    # False = single burst when the headless runner fires.
    # True  = drip-feed the total across runDuration at queriesPerHour.
    "advancedScheduling": False,
    "runDuration": 3,  # hours, 1..24
    "queriesPerHour": 10,  # 1..99
    "queries_pc": 30,  # 0..130
    "queries_mobile": 20,  # 0..99
    "last_triggered_date": None,
    # Wall-clock time at which the OS-level scheduled task fires for this
    # account (24h "HH:MM"). Each account gets its own scheduled task so
    # users can stagger runs (e.g. Alice 09:00, Bob 10:30).
    "run_time": "09:00",
}

DEFAULT_MOBILE_TASKS = {
    # The mobile API path is fail-closed until the user completes OAuth once.
    # Existing accounts therefore keep working and report auth_required rather
    # than silently submitting unauthenticated activity.
    "enabled": True,
    "check_in_enabled": True,
    "read_to_earn_enabled": True,
    "max_articles": 10,
    "read_delay_min": 8,
    "read_delay_max": 18,
    "target_points": 30,
    # Empty means discover the current region's offer from /dapi/me.
    "offer_id": "",
}

# Which Microsoft Rewards dashboard this account uses. Microsoft is rolling out
# a new React/Next.js dashboard that has a completely different DOM from the
# legacy `mee-rewards-*` one; the Daily Set automation must branch on it.
#   "auto"   -> detect at runtime which dashboard rendered (default)
#   "legacy" -> force the historical mee-rewards-* dashboard
#   "new"    -> force the new Next.js dashboard
DASHBOARD_VARIANTS = ("auto", "legacy", "new")
DEFAULT_DASHBOARD_VARIANT = "auto"


def default_account_schedule():
    """Return a fresh copy of the default per-account schedule."""
    return dict(DEFAULT_ACCOUNT_SCHEDULE)


def default_mobile_tasks():
    """Return a fresh copy of the per-account mobile task configuration."""
    return dict(DEFAULT_MOBILE_TASKS)


def _read_json(path, default):
    """Read a JSON file. On any parse/IO failure, back it up as .backup and return default."""
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
        backup_path = path + ".backup"
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass
        try:
            os.replace(path, backup_path)
        except OSError:
            pass
        return default


def _write_json(path, data):
    """
    Atomically write JSON via a temp file rename, with a retry loop that
    tolerates transient Windows locks (Defender, indexer, another instance
    briefly holding the file). A stale `.tmp` from a previous crashed write
    is removed before the write so its file attributes don't block us.

    Args:
        path: target file path to write
        data: JSON-serializable data to write

    Raises:
        OSError: If the file cannot be written.
    """
    import time as _time

    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass

    last_err = None
    for attempt in range(4):
        try:
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)
            os.replace(temp_path, path)
            return
        except PermissionError as e:
            last_err = e
            _time.sleep(0.15 * (attempt + 1))
        except OSError as e:
            last_err = e
            _time.sleep(0.1)
    raise last_err if last_err else OSError(f"Could not write {path}")


class AccountMetaManager:
    """
    Per-account metadata (currently just first_setup_done).
    Stored at accounts/<account_id>/meta.json.
    """

    def __init__(self, account_id):
        """
        Args:
            account_id: the ID of the account this manager handles (string)
        """
        self.account_id = account_id
        self.path = account_meta_path(account_id)

    def get_meta(self):
        """Return per-account meta merged with defaults."""
        defaults = {"first_setup_done": False}

        if not os.path.exists(account_dir(self.account_id)):
            try:
                os.makedirs(account_dir(self.account_id), exist_ok=True)
            except OSError:
                pass

        if not os.path.exists(self.path):
            try:
                self.save_meta(defaults)
            except OSError:
                pass
            return defaults

        meta = _read_json(self.path, None)
        if not isinstance(meta, dict):
            try:
                self.save_meta(defaults)
            except OSError:
                pass
            return defaults

        return {**defaults, **meta}

    def save_meta(self, meta):
        """Persist per-account meta to disk."""
        _write_json(self.path, meta)

    def is_first_setup_done(self):
        """Return True if first setup is marked complete."""
        return bool(self.get_meta().get("first_setup_done"))

    def mark_up_as_done(self):
        """Mark first setup as completed."""
        meta = self.get_meta()
        meta["first_setup_done"] = True
        self.save_meta(meta)

    def get_schedule(self):
        """Return this account's schedule, with defaults for missing keys."""
        meta = self.get_meta()
        sched = meta.get("schedule") if isinstance(meta, dict) else None
        merged = default_account_schedule()
        if isinstance(sched, dict):
            merged.update({k: sched.get(k, v) for k, v in merged.items()})
        return merged

    def get_mobile_tasks(self):
        """Return mobile task settings with safe defaults for old accounts."""
        meta = self.get_meta()
        configured = meta.get("mobile_tasks") if isinstance(meta, dict) else None
        merged = default_mobile_tasks()
        if isinstance(configured, dict):
            merged.update({key: configured.get(key, value) for key, value in merged.items()})
        try:
            merged["max_articles"] = max(1, min(10, int(merged["max_articles"])))
        except (TypeError, ValueError):
            merged["max_articles"] = 10
        try:
            merged["read_delay_min"] = max(0, min(3600, int(merged["read_delay_min"])))
        except (TypeError, ValueError):
            merged["read_delay_min"] = 8
        try:
            merged["read_delay_max"] = max(
                merged["read_delay_min"], min(3600, int(merged["read_delay_max"]))
            )
        except (TypeError, ValueError):
            merged["read_delay_max"] = max(merged["read_delay_min"], 18)
        try:
            merged["target_points"] = max(1, min(100, int(merged["target_points"])))
        except (TypeError, ValueError):
            merged["target_points"] = 30
        merged["enabled"] = bool(merged["enabled"])
        merged["check_in_enabled"] = bool(merged["check_in_enabled"])
        merged["read_to_earn_enabled"] = bool(merged["read_to_earn_enabled"])
        merged["offer_id"] = str(merged.get("offer_id") or "")[:160]
        return merged

    def set_mobile_tasks(self, payload):
        """Persist validated per-account mobile task settings."""
        if not isinstance(payload, dict):
            return False
        current = self.get_mobile_tasks()

        def pick(key):
            return payload[key] if key in payload else current[key]

        try:
            minimum = max(0, min(3600, int(pick("read_delay_min"))))
            maximum = max(minimum, min(3600, int(pick("read_delay_max"))))
            articles = max(1, min(10, int(pick("max_articles"))))
            target = max(1, min(100, int(pick("target_points"))))
        except (TypeError, ValueError):
            return False
        meta = self.get_meta()
        meta["mobile_tasks"] = {
            "enabled": bool(pick("enabled")),
            "check_in_enabled": bool(pick("check_in_enabled")),
            "read_to_earn_enabled": bool(pick("read_to_earn_enabled")),
            "max_articles": articles,
            "read_delay_min": minimum,
            "read_delay_max": maximum,
            "target_points": target,
            "offer_id": str(pick("offer_id") or "")[:160],
        }
        self.save_meta(meta)
        return True

    def set_schedule(self, sched):
        """
        Persist this account's schedule. `sched` should be a dict.

        Args:
            sched: dict with keys matching default_account_schedule.
                Missing keys will fall back to default values.
                Example: {"enabled": True, "queriesPerHour": 15}
        """
        meta = self.get_meta()
        meta["schedule"] = sched
        self.save_meta(meta)

    def get_dashboard_variant(self):
        """
        Return this account's Rewards dashboard variant.

        Returns one of DASHBOARD_VARIANTS, defaulting to DEFAULT_DASHBOARD_VARIANT
        when unset or invalid (backward compatible: pre-existing meta.json files
        simply resolve to "auto").
        """
        variant = self.get_meta().get("dashboard_variant")
        if variant in DASHBOARD_VARIANTS:
            return variant
        return DEFAULT_DASHBOARD_VARIANT

    def set_dashboard_variant(self, variant):
        """
        Persist this account's Rewards dashboard variant.

        Args:
            variant: one of DASHBOARD_VARIANTS ("auto", "legacy", "new").

        Returns:
            bool: True if persisted, False if the value was rejected.
        """
        if variant not in DASHBOARD_VARIANTS:
            return False
        meta = self.get_meta()
        meta["dashboard_variant"] = variant
        self.save_meta(meta)
        return True
