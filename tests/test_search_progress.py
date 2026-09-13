import unittest
from unittest.mock import patch

from src.api import AutoRewarderAPI
from src.search.rewards_progress import (
    RewardsSearchProgress,
    evaluate_search_credit,
    parse_rewards_search_progress,
)


class RewardsSearchProgressTests(unittest.TestCase):
    def test_parses_authoritative_pc_search_counter(self):
        payload = {
            "dashboard": {
                "userStatus": {
                    "availablePoints": 11318,
                    "levelInfo": {
                        "bingSearchDailyPoints": 15,
                        "pointsPerSearch": 3,
                    },
                    "counters": {
                        "pcSearch": [
                            {
                                "pointProgress": 18,
                                "pointProgressMax": 60,
                                "attributes": {"progress": 18},
                            }
                        ]
                    },
                }
            }
        }

        progress = parse_rewards_search_progress(payload)
        self.assertEqual(
            progress,
            RewardsSearchProgress(
                balance=11318,
                points=18,
                maximum=60,
                points_per_search=3,
            ),
        )
        self.assertTrue(progress.available)
        self.assertFalse(progress.complete)

    def test_counter_falls_back_to_level_info(self):
        progress = parse_rewards_search_progress(
            {
                "dashboard": {
                    "userStatus": {
                        "availablePoints": "90",
                        "levelInfo": {
                            "bingSearchDailyPoints": "60",
                            "pointsPerSearch": "3",
                        },
                        "counters": {"pcSearch": []},
                    }
                }
            }
        )
        self.assertEqual(progress.points, 60)
        self.assertIsNone(progress.maximum)
        self.assertFalse(progress.available)

    def test_malformed_payload_fails_closed(self):
        progress = parse_rewards_search_progress({"dashboard": []})
        self.assertIsNone(progress.balance)
        self.assertIsNone(progress.points)
        self.assertFalse(progress.available)

    def test_no_counter_increase_is_uncredited(self):
        before = RewardsSearchProgress(100, 18, 60, 3)
        after = RewardsSearchProgress(100, 18, 60, 3)
        result = evaluate_search_credit(before, after, submitted=1)
        self.assertEqual(result.status, "uncredited")
        self.assertEqual(result.credited, 0)
        self.assertFalse(result.successful)

    def test_counter_delta_is_converted_to_verified_searches(self):
        before = RewardsSearchProgress(100, 18, 60, 3)
        after = RewardsSearchProgress(106, 24, 60, 3)
        result = evaluate_search_credit(before, after, submitted=2)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.credited, 2)
        self.assertEqual(result.points_delta, 6)

    def test_completed_counter_skips_browser_submissions(self):
        before = RewardsSearchProgress(142, 60, 60, 3)
        result = evaluate_search_credit(before, None, submitted=0)
        self.assertEqual(result.status, "already_done")
        self.assertTrue(result.successful)

    def test_progress_polling_waits_for_a_counter_change(self):
        unchanged = RewardsSearchProgress(100, 18, 60, 3)
        changed = RewardsSearchProgress(103, 21, 60, 3)
        api = object.__new__(AutoRewarderAPI)
        with patch(
            "src.api.fetch_rewards_search_progress",
            side_effect=[unchanged, changed],
        ) as fetch, patch("src.api.time.sleep") as sleep:
            result = api._wait_for_search_progress_change(object(), 18, attempts=4)
        self.assertEqual(result, changed)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
