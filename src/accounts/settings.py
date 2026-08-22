"""App-wide global settings persistence."""

import json
import os

from ..config import APP_DIR, GLOBAL_SETTINGS_PATH, LLM_API_KEY_PATH
from ..mobiletasks.secure_store import ApiKeyStore, SecretStoreError
from ..security import atomic_write_json

SCHEMA_VERSION = 3


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

    last_err = None
    for attempt in range(4):
        try:
            atomic_write_json(path, data)
            return
        except OSError as e:
            last_err = e
            _time.sleep(0.15 * (attempt + 1))
    raise last_err if last_err else OSError(f"Could not write {path}")


class GlobalSettingsManager:
    """
    Manages app-wide (account-agnostic) settings.
    Keys: hide_browser, current_account_id, schema_version.
    """

    def __init__(self):
        self.path = GLOBAL_SETTINGS_PATH
        self._api_key_store = ApiKeyStore(LLM_API_KEY_PATH)

    def _migrate_legacy_api_key(self, settings):
        """Move the pre-v4 plaintext key out of settings.json when possible."""
        if not isinstance(settings, dict):
            return settings
        legacy = settings.get("llm_api_key")
        if not isinstance(legacy, str) or not legacy.strip():
            settings.pop("llm_api_key", None)
            return settings
        try:
            self._api_key_store.save(legacy.strip())
            settings = dict(settings)
            settings.pop("llm_api_key", None)
            _write_json(self.path, settings)
        except (SecretStoreError, OSError):
            # Keep the key available in memory for this call, but never return
            # it through the generic get_settings() API.
            pass
        return settings

    def _load_api_key(self):
        try:
            value = self._api_key_store.load()
        except SecretStoreError:
            value = ""
        if value:
            return value
        # A failed migration should not make an existing configuration
        # unusable. This is a one-time compatibility fallback.
        raw = _read_json(self.path, {})
        legacy = raw.get("llm_api_key") if isinstance(raw, dict) else ""
        return str(legacy or "").strip()

    def get_settings(self):
        """Return settings merged with defaults."""
        defaults = {
            "hide_browser": False,
            "current_account_id": None,
            "schema_version": SCHEMA_VERSION,
            # OS-level autostart master switch. When True, the app syncs
            # per-account daily scheduled tasks (Windows Task Scheduler /
            # systemd user timers); each account's schedule.run_time
            # decides when its own task fires.
            "autoStartUp": False,
            # When True, clicking the window X hides the app to the system
            # tray instead of quitting. Default True preserves the behavior
            # introduced in v3.3; users who prefer the standard X = quit
            # can flip it off in Settings. Read once at app startup.
            "close_to_tray": True,
            # Default query counts.
            "queries_pc": 30,
            "queries_mobile": 20,
            # LLM-generated search terms (bring-your-own-key). The API key is
            # stored separately using DPAPI (or a mode-600 development file).
            "use_llm_queries": False,
            "llm_provider": "openai",  # openai | anthropic | gemini
            "llm_model": "",  # blank = provider default
            # Language of generated queries. "auto" resolves from
            # detected_locale (navigator.language) or OS detection.
            "search_locale": "auto",
            "detected_locale": "",  # filled by the GUI from navigator.language
        }

        if APP_DIR and not os.path.exists(APP_DIR):
            try:
                os.makedirs(APP_DIR)
            except OSError:
                pass

        if not os.path.exists(self.path):
            # First-launch init. If we can't write (locked/denied), still
            # return defaults so reads don't blow up — the next successful
            # write (via save_settings from a user action) will create it.
            try:
                self.save_settings(defaults)
            except OSError:
                pass
            return defaults

        settings = _read_json(self.path, None)
        if not isinstance(settings, dict):
            # Recovery path: recreate defaults. If the write fails (e.g.
            # transient Windows lock), don't crash the read — caller still
            # gets a valid default dict.
            try:
                self.save_settings(defaults)
            except OSError:
                pass
            return defaults

        settings = self._migrate_legacy_api_key(settings)
        # Fill missing defaults without returning secrets through this generic
        # settings endpoint.
        merged = {**defaults, **settings}
        merged.pop("llm_api_key", None)
        return merged

    def save_settings(self, settings):
        """Persist settings to disk."""
        if not isinstance(settings, dict):
            raise ValueError("Settings must be a dictionary")
        clean = dict(settings)
        # Enforce the secret-storage invariant at the generic persistence
        # boundary too, so legacy callers cannot put a key back in JSON.
        if "llm_api_key" in clean:
            legacy = clean.pop("llm_api_key")
            if legacy is not None:
                self._api_key_store.save(str(legacy).strip())
        clean.pop("llm_api_key", None)
        _write_json(self.path, clean)

    def set_hide_browser(self, is_hide):
        """Update the hide_browser flag in settings."""
        settings = self.get_settings()
        settings["hide_browser"] = bool(is_hide)
        self.save_settings(settings)

    def set_close_to_tray(self, value):
        """Update the close_to_tray flag in settings."""
        settings = self.get_settings()
        settings["close_to_tray"] = bool(value)
        self.save_settings(settings)

    def get_current_account_id(self):
        """Return the current account id from settings."""
        return self.get_settings().get("current_account_id")

    def set_current_account_id(self, account_id):
        """Persist the current account id in settings."""
        if account_id is not None:
            import re

            if not isinstance(account_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,64}", account_id
            ):
                raise ValueError("Invalid account id")
        settings = self.get_settings()
        settings["current_account_id"] = account_id
        self.save_settings(settings)

    def get_queries_pc(self):
        """Return the saved PC queries count from settings."""
        try:
            return max(0, min(130, int(self.get_settings().get("queries_pc", 30))))
        except (TypeError, ValueError, OverflowError):
            return 30

    def set_queries_pc(self, count):
        """Persist the PC queries count in settings."""
        settings = self.get_settings()
        settings["queries_pc"] = max(0, min(130, int(count)))
        self.save_settings(settings)

    def get_queries_mobile(self):
        """Return the saved mobile queries count from settings."""
        try:
            return max(0, min(99, int(self.get_settings().get("queries_mobile", 20))))
        except (TypeError, ValueError, OverflowError):
            return 20

    def set_queries_mobile(self, count):
        """Persist the mobile queries count in settings."""
        settings = self.get_settings()
        settings["queries_mobile"] = max(0, min(99, int(count)))
        self.save_settings(settings)

    # ------------------------------------------------------------------
    # LLM-generated search terms + locale
    # ------------------------------------------------------------------

    def get_llm_config(self):
        """Return the LLM query-generation config from settings."""
        from ..search.llm import SUPPORTED_PROVIDERS

        s = self.get_settings()
        provider = str(s.get("llm_provider", "openai") or "openai").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            provider = "openai"
        return {
            "use_llm_queries": bool(s.get("use_llm_queries", False)),
            "llm_provider": provider,
            "llm_model": str(s.get("llm_model", "") or "")[:100],
            "llm_api_key": self._load_api_key(),
            "search_locale": str(s.get("search_locale", "auto") or "auto")[:32],
            "detected_locale": str(s.get("detected_locale", "") or "")[:32],
        }

    def set_llm_config(
        self, use_llm_queries, provider, model, api_key, search_locale="auto"
    ):
        """Persist the LLM query-generation config.

        Unknown providers fall back to "openai"; an empty locale becomes
        "auto". The API key is stored by ``ApiKeyStore`` rather than in the
        general settings JSON.
        """
        from ..search.llm import SUPPORTED_PROVIDERS

        provider = str(provider or "openai").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            provider = "openai"

        locale = str(search_locale or "").strip() or "auto"
        locale = (
            "".join(char for char in locale if ord(char) >= 32 and ord(char) != 127)[
                :32
            ]
            or "auto"
        )
        model = "".join(
            char
            for char in str(model or "").strip()
            if ord(char) >= 32 and ord(char) != 127
        )[:100]
        key = str(api_key or "").strip()

        settings = self.get_settings()
        settings["use_llm_queries"] = bool(use_llm_queries)
        settings["llm_provider"] = provider
        self._api_key_store.save(key)
        settings["llm_model"] = model
        settings["search_locale"] = locale
        self.save_settings(settings)

    def set_detected_locale(self, locale):
        """Persist the locale reported by the GUI (navigator.language)."""
        settings = self.get_settings()
        value = "".join(
            char
            for char in str(locale or "").strip()
            if ord(char) >= 32 and ord(char) != 127
        )[:32]
        settings["detected_locale"] = value
        self.save_settings(settings)

    def get_effective_locale(self):
        """Return the locale that query generation will actually use."""
        from ..search.locale import resolve_search_locale

        return resolve_search_locale(self.get_settings())
