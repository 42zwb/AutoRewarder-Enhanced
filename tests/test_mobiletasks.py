import json
import os
import tempfile
import threading
import unittest

from src.mobiletasks.client import ActivityResponse
from src.mobiletasks.oauth import OAuthError
from src.mobiletasks.runner import MobileTaskRunner


class FakeOAuth:
    def __init__(self, *args, **kwargs):
        self.calls = 0

    def get_access_token(self, force_refresh=False):
        self.calls += 1
        return "test-access-token"


class MissingOAuth:
    def __init__(self, *args, **kwargs):
        pass

    def get_access_token(self, force_refresh=False):
        raise OAuthError("Mobile OAuth authorization is required")


class CreditingClient:
    instances: list["CreditingClient"] = []

    def __init__(self, token, token_refresh=None, logger=None, **kwargs):
        self.balance = 100
        self.submit_calls = []
        CreditingClient.instances.append(self)

    def get_profile(self):
        return ActivityResponse(
            200,
            {
                "geoLocale": "US",
                "langCode": "en-US",
                "response": {
                    "balance": self.balance,
                    "offers": [{"offerId": "ENUS_readarticle3_30points"}],
                },
            },
        )

    def submit_activity(self, activity_type, country, offer_id=None):
        self.submit_calls.append((activity_type, country, offer_id))
        self.balance += 15 if activity_type == 103 else 3
        return ActivityResponse(200, {"response": {"balance": self.balance}})


class NoReadCreditClient(CreditingClient):
    def submit_activity(self, activity_type, country, offer_id=None):
        self.submit_calls.append((activity_type, country, offer_id))
        if activity_type == 103:
            self.balance += 15
        return ActivityResponse(200, {"response": {"balance": self.balance}})


class MobileTaskRunnerTests(unittest.TestCase):
    def _runner(self, client_factory, oauth_factory=FakeOAuth, **config):
        tmp = tempfile.TemporaryDirectory()
        status_path = os.path.join(tmp.name, "mobile_status.json")
        token_path = os.path.join(tmp.name, "mobile_token.bin")
        runner = MobileTaskRunner(
            "account-1",
            status_path,
            token_path,
            config={
                "enabled": True,
                "check_in_enabled": True,
                "read_to_earn_enabled": True,
                "max_articles": 10,
                "target_points": 30,
                "read_delay_min": 0,
                "read_delay_max": 0,
                **config,
            },
            client_factory=client_factory,
            oauth_factory=oauth_factory,
        )
        runner._test_tmp = tmp
        self.addCleanup(tmp.cleanup)
        return runner

    def test_missing_oauth_is_auth_required_and_does_not_submit(self):
        runner = self._runner(CreditingClient, oauth_factory=MissingOAuth)
        summary = runner.run()
        self.assertEqual(summary.status, "auth_required")
        self.assertEqual(summary.check_in_status, "auth_required")
        with open(runner.status_path, "r", encoding="utf-8") as handle:
            status = json.load(handle)
        self.assertNotEqual(status["result"], "completed")

    def test_read_to_earn_reaches_ten_articles_and_thirty_points(self):
        CreditingClient.instances = []
        runner = self._runner(CreditingClient)
        summary = runner.run()
        self.assertEqual(summary.status, "completed")
        self.assertEqual(summary.check_in_status, "completed")
        self.assertEqual(summary.read_status, "completed")
        self.assertEqual(summary.read_articles, 10)
        self.assertEqual(summary.read_points, 30)
        calls = CreditingClient.instances[0].submit_calls
        self.assertEqual([call[0] for call in calls], [103] + [101] * 10)
        self.assertTrue(
            all(call[2] == "ENUS_readarticle3_30points" for call in calls[1:])
        )

    def test_no_read_credit_stops_immediately_as_partial(self):
        runner = self._runner(NoReadCreditClient)
        summary = runner.run()
        self.assertEqual(summary.status, "partial")
        self.assertEqual(summary.read_status, "partial")
        self.assertEqual(summary.read_articles, 0)
        self.assertIn("no positive balance delta", summary.reason)

    def test_second_run_does_not_duplicate_completed_activities(self):
        CreditingClient.instances = []
        runner = self._runner(CreditingClient)
        first = runner.run()
        self.assertEqual(first.status, "completed")
        first_calls = len(CreditingClient.instances[0].submit_calls)
        second = runner.run()
        self.assertEqual(second.status, "completed")
        self.assertEqual(len(CreditingClient.instances), 1)
        self.assertEqual(first_calls, 11)

    def test_account_mismatch_fails_closed(self):
        runner = self._runner(CreditingClient)
        summary = runner.run("different-account")
        self.assertEqual(summary.status, "failed")
        self.assertIn("account mismatch", summary.reason)

    def test_stop_request_is_not_reported_as_completed(self):
        runner = self._runner(CreditingClient)
        runner.stop_event = threading.Event()
        runner.stop_event.set()
        runner.set_config(runner.config)
        summary = runner.run()
        self.assertEqual(summary.status, "stopped")
        self.assertFalse(summary.successful)

    def test_both_subtasks_disabled_are_unavailable_without_oauth(self):
        runner = self._runner(
            CreditingClient, check_in_enabled=False, read_to_earn_enabled=False
        )
        runner.oauth_factory = MissingOAuth
        summary = runner.run()
        self.assertEqual(summary.status, "unavailable")
        self.assertIn("all mobile tasks disabled", summary.reason)


if __name__ == "__main__":
    unittest.main()
