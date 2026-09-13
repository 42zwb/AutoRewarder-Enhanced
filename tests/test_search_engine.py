import unittest

from src.search.engine import is_bing_search_result_url


class SearchResultUrlTests(unittest.TestCase):
    def test_accepts_https_bing_search_with_query(self):
        self.assertTrue(
            is_bing_search_result_url("https://www.bing.com/search?q=example&form=QBLH")
        )
        self.assertTrue(
            is_bing_search_result_url("https://cn.bing.com/search?q=%E6%B5%8B%E8%AF%95")
        )

    def test_rejects_homepage_missing_query_and_lookalike_hosts(self):
        self.assertFalse(is_bing_search_result_url("https://www.bing.com/"))
        self.assertFalse(is_bing_search_result_url("https://www.bing.com/search"))
        self.assertFalse(is_bing_search_result_url("http://www.bing.com/search?q=test"))
        self.assertFalse(
            is_bing_search_result_url("https://evilbing.com/search?q=test")
        )


if __name__ == "__main__":
    unittest.main()
