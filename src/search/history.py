"""History storage and retrieval for per-account searches."""

import os
import json
from datetime import datetime

from ..security import atomic_write_json, safe_log_text

_MAX_HISTORY_RECORDS = 5000
_MAX_HISTORY_BYTES = 8 * 1024 * 1024


class HistoryManager:
    """
    Manages the history of search queries for a single account.
    Each instance is bound to a specific history.json file path.
    """

    def __init__(self, history_file, logger=None):
        """
        Args:
            history_file (str): Absolute path to this account's history.json.
            logger (callable, optional): Logging function.
        """

        self.history_file = history_file
        self._logger = logger

    def _log(self, message):
        if self._logger:
            self._logger(message)

    def get_history(self):
        """
        Retrieve the search history from the JSON file.
        Returns an empty list if the file is missing or unreadable.
        """

        try:
            size = (
                os.path.getsize(self.history_file)
                if os.path.exists(self.history_file)
                else 0
            )
        except OSError:
            size = 0
        if size == 0:
            return []
        if size > _MAX_HISTORY_BYTES:
            self._log("[ERROR] History file is too large. Starting with a fresh one.")
            return []

        try:
            with open(self.history_file, "r", encoding="utf-8") as file:
                history = json.load(file)

                if not isinstance(history, list):
                    raise ValueError("History data must be a list")

                clean = []
                for item in history[-_MAX_HISTORY_RECORDS:]:
                    if not isinstance(item, dict):
                        continue
                    clean.append(
                        {
                            "date": safe_log_text(item.get("date"), 32),
                            "time": safe_log_text(item.get("time"), 32),
                            "query": safe_log_text(item.get("query"), 256),
                            "status": safe_log_text(item.get("status"), 160),
                        }
                    )
                return clean
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
            self._log(
                "[ERROR] History file was unreadable or damaged. Starting with a fresh one."
            )

            backup_path = self.history_file + ".backup"

            try:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.replace(self.history_file, backup_path)
            except OSError:
                pass
            try:
                atomic_write_json(self.history_file, [])
            except OSError:
                pass

            return []

    def save_history(self, history_list):
        """
        Save the search history to a JSON file atomically via a temp file.

        Args:
            history_list (list): The list of search records to save.
        """

        if not isinstance(history_list, list):
            history_list = []
        atomic_write_json(self.history_file, history_list[-_MAX_HISTORY_RECORDS:])

    def add_to_history(self, query_text, status):
        """
        Append a search record with the current date, time, query, and status.

        Args:
            query_text (str): The search query text.
            status (str): The status of the search.
        """

        now = datetime.now()
        current_date = now.strftime("%m-%d-%Y")
        current_time = now.strftime("%H:%M:%S")

        new_record = {
            "date": current_date,
            "time": current_time,
            "query": safe_log_text(query_text, 256),
            "status": safe_log_text(status, 160),
        }

        history_list = self.get_history()
        history_list.append(new_record)
        self.save_history(history_list)
