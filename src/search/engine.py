"""Search automation helpers for Bing queries."""

import json
import random
import time
from urllib.parse import parse_qs, urlparse
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..utils import human_typing
from ..emulator import HumanBehavior
from ..security import safe_log_text

_MAX_QUERY_LENGTH = 256
_MAX_QUERY_COUNT = 130


def is_bing_search_result_url(value):
    """Return True only for an HTTPS Bing results URL with a query value."""
    try:
        parsed = urlparse(str(value or ""))
    except (TypeError, ValueError):
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not (
        hostname == "bing.com" or hostname.endswith(".bing.com")
    ):
        return False
    if parsed.path.rstrip("/").lower() != "/search":
        return False
    return bool(parse_qs(parsed.query).get("q"))


class SearchEngine:
    """
    A class to handle search operations with human-like behavior.
    """

    def __init__(self, logger=None, history=None):
        """
        Initialize the SearchEngine with an optional logger and history manager.

        Args:
            logger (callable, optional): A logging function to log messages. Defaults to None.
            history (HistoryManager, optional): An instance of HistoryManager to manage search history. Defaults to None.
        """

        self._logger = logger
        self._history = history

    def _log(self, message):
        """
        Log a message using the provided logger, if available.

        Args:
            message (str): The message to log.
        """

        if self._logger:
            self._logger(message)

    def _add_to_history(self, query_text, status):
        """
        Add a search query and its status to the history manager.

        Args:
            query_text (str): The search query.
            status (str): The status of the search.
        """

        if self._history:
            self._history.add_to_history(query_text, status)

    def load_queries_from_json(self, filepath, num_needed):
        """
        Load search queries from a JSON file and return a random sample.

        Args:
            filepath (str): The path to the JSON file containing search queries.
            num_needed (int): The number of random queries to return.

        Returns:
            list: A list of randomly selected search queries.
            If the file is not found, an error is logged and an empty list is returned.
        """

        try:
            num_needed = max(0, min(_MAX_QUERY_COUNT, int(num_needed)))
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
                raw_queries = data.get("queries", []) if isinstance(data, dict) else []
                all_queries = []
                for raw in raw_queries if isinstance(raw_queries, list) else []:
                    if not isinstance(raw, str):
                        continue
                    query = "".join(
                        char
                        for char in raw.strip()
                        if ord(char) >= 32 and ord(char) != 127
                    )[:_MAX_QUERY_LENGTH]
                    if query:
                        all_queries.append(query)

                if len(all_queries) < num_needed:
                    self._log(
                        f"[WARNING] In the JSON file, there are only {len(all_queries)} queries available, but {num_needed} are needed."
                    )
                    return all_queries

                return random.sample(all_queries, num_needed)

        except FileNotFoundError:
            self._log("[ERROR] Search query file was not found.")
            self._add_to_history("N/A", "[ERROR] Search query file not found")
            return []
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
            TypeError,
            ValueError,
        ):
            self._log("[ERROR] Search query file is unreadable or malformed.")
            self._add_to_history("N/A", "[ERROR] Search query file malformed")
            return []

    def get_coffee_break_count(self):
        """
        Determine how many searches to perform before taking a coffee break, with a bias towards shorter breaks.

        Returns:
            int: The number of searches to perform before taking a break.
        """

        # 80% of the time, take a break after 4-9 searches
        if random.random() < 0.8:
            return random.randint(4, 9)
        # 20% of the time, take a break after 10-15 searches
        else:
            return random.randint(10, 15)

    def perform_searches(self, driver, queries, mobile=False, stop_event=None):
        """
        Perform searches on Bing using Selenium WebDriver with human-like behavior.

        Args:
            driver (WebDriver): An instance of Selenium WebDriver to control the browser.
            queries (list): A list of search queries to perform.
            mobile (bool): When True, HumanBehavior emits touch gestures instead
                of mouse events — pair with a mobile-emulated driver.
            stop_event (threading.Event, optional): If provided and set, the
                loop bails out at the next checkpoint and any in-progress
                coffee break is interrupted immediately.

        Returns:
            int: number of queries confirmed to reach a Bing results URL. This
                is a browser-submission count, not proof that Rewards credited
                the searches; the caller must verify server-side progress.
        """

        human = HumanBehavior(driver, show_cursor=True, mobile=mobile)

        next_coffee_break = self.get_coffee_break_count()
        searches_since_break = 0
        successful = 0

        self._log(f"Loaded {len(queries)} queries. Starting searches...")
        self._log(f"Next coffee break after {next_coffee_break} searches.")

        for i, raw_query in enumerate(queries):
            query = safe_log_text(raw_query, limit=_MAX_QUERY_LENGTH).strip()
            if not query:
                continue
            if stop_event is not None and stop_event.is_set():
                self._log("Stop requested — halting search loop.")
                return successful

            try:
                # Open Bing homepage
                driver.get("https://www.bing.com")
                time.sleep(random.uniform(4, 8))  # Random delay to mimic human behavior

                searches_since_break += 1

                # Longer break every few searches to mimic human behavior
                if searches_since_break >= next_coffee_break:

                    if next_coffee_break > 9:
                        pause_duration = random.uniform(45, 90)
                        self._log("Taking a big coffee break...")
                    else:
                        pause_duration = random.uniform(15, 30)
                        self._log("Taking a quick coffee break...")

                    self._log(
                        f"Sleeping for {pause_duration:.2f} seconds to mimic a coffee break."
                    )
                    # Interruptible sleep: Event.wait returns True early if Stop is pressed.
                    if stop_event is not None:
                        if stop_event.wait(pause_duration):
                            self._log("Stop requested during coffee break — halting.")
                            return successful
                    else:
                        time.sleep(pause_duration)

                    next_coffee_break = self.get_coffee_break_count()
                    searches_since_break = 0
                    self._log(f"Next coffee break after {next_coffee_break} searches.")

                # Find the search box, clear it
                search_box = driver.find_element(By.NAME, "q")
                search_box.clear()

                # Log the search query in log area
                self._log(f"Search #{i + 1}: {query}")

                # Type the query with human-like delays
                human_typing(search_box, query)
                search_box.send_keys(Keys.RETURN)  # Press Enter to search

                # A keypress is not enough to call the browser action
                # successful. Confirm that Bing actually reached a results URL.
                WebDriverWait(driver, 20).until(
                    lambda current: is_bing_search_result_url(current.current_url)
                )
                time.sleep(random.uniform(2, 4))

                # Scroll the page to mimic human behavior
                try:
                    human.scroll_page()
                except WebDriverException as e:
                    short_error = str(e).split("\n")[0][:28]
                    self._log(
                        f"[WARNING] WebDriver error when scrolling: {short_error}. Continuing."
                    )

                # Pause after scrolling
                time.sleep(random.uniform(2, 4))

                # Add to history.json
                self._add_to_history(
                    query, "Browser submitted; Rewards credit not yet verified"
                )
                successful += 1

            except NoSuchElementException:
                if stop_event is not None and stop_event.is_set():
                    return successful
                self._log(f"[ERROR] Search box not found on attempt #{i+1}")
                self._add_to_history(query, "[ERROR] Search box not found")

            except WebDriverException as e:
                if stop_event is not None and stop_event.is_set():
                    return successful
                short_error = str(e).split("\n")[0][:28]
                self._log(f"[ERROR] WebDriver error on attempt #{i+1}: {short_error}")
                self._add_to_history(query, f"[ERROR] WebDriver Error: {short_error}")

            except Exception as e:
                if stop_event is not None and stop_event.is_set():
                    return successful
                self._log(f"[ERROR] Unknown error on attempt #{i+1}: {e}")
                self._add_to_history(query, f"[ERROR] Unknown Error: {str(e)[:50]}")

        return successful
