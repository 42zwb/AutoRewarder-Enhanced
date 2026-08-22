import os
import tempfile
import unittest

from src.stats.manager import StatsManager


class StatsMobileTests(unittest.TestCase):
    def test_mobile_fields_are_recorded_without_fixed_read_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = StatsManager(os.path.join(tmp, "stats.json"))
            data = stats.record_session(
                check_ins=1,
                read_articles=10,
                read_points=30,
                mobile_task_runs=1,
            )
            self.assertEqual(data["lifetime"]["check_ins"], 1)
            self.assertEqual(data["lifetime"]["read_articles"], 10)
            self.assertEqual(data["lifetime"]["read_points"], 30)
            self.assertEqual(data["lifetime"]["mobile_task_runs"], 1)
            self.assertEqual(data["last_session"]["points_estimate"], 30)
            today = sorted(data["daily"])[-1]
            self.assertEqual(data["daily"][today]["read_points"], 30)


if __name__ == "__main__":
    unittest.main()
