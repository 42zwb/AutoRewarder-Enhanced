import unittest
from unittest.mock import patch

from src.mobiletasks.client import (
    RewardsActivityClient,
    RewardsAuthError,
    RewardsClientError,
    response_says_done,
)
from src.mobiletasks.oauth import is_valid_callback_url


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class MobileClientTests(unittest.TestCase):
    def test_401_refreshes_once_without_logging_token(self):
        session = FakeSession(
            [
                FakeResponse(401),
                FakeResponse(200, {"response": {"balance": 42}}),
            ]
        )
        refreshes = []

        def refresh():
            refreshes.append(True)
            return "rotated-access-token"

        client = RewardsActivityClient(
            "expired-access-token",
            token_refresh=refresh,
            session=session,
            max_retries=2,
        )
        with patch("src.mobiletasks.client.time.sleep"):
            result = client.get_profile()
        self.assertEqual(result.balance, 42)
        self.assertEqual(len(refreshes), 1)
        self.assertEqual(
            session.calls[-1][2]["headers"]["Authorization"],
            "Bearer rotated-access-token",
        )

    def test_429_retries_and_invalid_schema_fails_closed(self):
        session = FakeSession(
            [
                FakeResponse(429, headers={"Retry-After": "0"}),
                FakeResponse(200, {"response": {"balance": 43}}),
            ]
        )
        client = RewardsActivityClient("access", session=session, max_retries=2)
        with patch("src.mobiletasks.client.time.sleep"):
            self.assertEqual(client.get_profile().balance, 43)

        bad = FakeSession([FakeResponse(200, ["not-an-object"])])
        bad_client = RewardsActivityClient("access", session=bad, max_retries=1)
        with self.assertRaises(RewardsClientError):
            bad_client.get_profile()

    def test_repeated_auth_failure_is_auth_error(self):
        session = FakeSession([FakeResponse(401), FakeResponse(401)])
        client = RewardsActivityClient(
            "access",
            token_refresh=lambda: "still-invalid",
            session=session,
            max_retries=2,
        )
        with self.assertRaises(RewardsAuthError):
            client.get_profile()

    def test_completion_parser_does_not_treat_incomplete_as_done(self):
        self.assertFalse(response_says_done({"status": "incomplete"}))
        self.assertFalse(response_says_done({"message": "not completed"}))
        self.assertTrue(response_says_done({"status": "already_completed"}))

    def test_empty_token_refresh_fails_closed(self):
        session = FakeSession([FakeResponse(401)])
        client = RewardsActivityClient(
            "access", token_refresh=lambda: "", session=session, max_retries=1
        )
        with self.assertRaises(RewardsAuthError):
            client.get_profile()

    def test_oauth_callback_requires_expected_host_path_and_state(self):
        state = "expected-state"
        valid = (
            "https://login.live.com/oauth20_desktop.srf?"
            "code=abc&state=expected-state"
        )
        wrong_state = valid.replace("expected-state", "other-state")
        wrong_host = valid.replace("login.live.com", "evil.example")
        self.assertTrue(is_valid_callback_url(valid, state))
        self.assertFalse(is_valid_callback_url(wrong_state, state))
        self.assertFalse(is_valid_callback_url(wrong_host, state))


class ScheduledBatchTests(unittest.TestCase):
    def test_mobile_tasks_are_enabled_only_on_first_advanced_batch(self):
        from AutoRewarder_CLI import _run_scheduled

        class FakeAPI:
            def __init__(self):
                self.calls = []
                self._last_run_status = "idle"

            def main(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                self._last_run_status = "completed"
                return {"status": "completed"}

        api = FakeAPI()
        with patch("AutoRewarder_CLI.console_log"), patch(
            "AutoRewarder_CLI.time.sleep"
        ), patch("AutoRewarder_CLI.random.uniform", return_value=1.0):
            _run_scheduled(
                api,
                pc=3,
                mobile=0,
                duration_hours=0,
                queries_per_hour=6,
                include_mobile_tasks=True,
            )

        self.assertEqual(len(api.calls), 3)
        self.assertTrue(api.calls[0][1]["include_mobile_tasks"])
        self.assertFalse(api.calls[1][1]["include_mobile_tasks"])
        self.assertFalse(api.calls[2][1]["include_mobile_tasks"])

    def test_advanced_batches_stop_after_unverified_result(self):
        from AutoRewarder_CLI import _run_scheduled

        class PartialAPI:
            def __init__(self):
                self.calls = []
                self._last_run_status = "idle"

            def main(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                self._last_run_status = "partial"
                return {"status": "partial"}

        api = PartialAPI()
        with patch("AutoRewarder_CLI.console_log"), patch(
            "AutoRewarder_CLI.time.sleep"
        ), patch("AutoRewarder_CLI.random.uniform", return_value=1.0):
            _run_scheduled(
                api,
                pc=3,
                mobile=0,
                duration_hours=0,
                queries_per_hour=6,
                include_mobile_tasks=True,
            )

        self.assertEqual(len(api.calls), 1)


if __name__ == "__main__":
    unittest.main()
