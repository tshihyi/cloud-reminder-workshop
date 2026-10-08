"""CI 用的單元測試：python3 -m unittest discover -s tests -v"""

import datetime
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import monitor_and_notify as monitor  # noqa: E402

NOW = datetime.datetime(2026, 12, 10, 14, 0, tzinfo=monitor.TAIPEI)

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item><title>YOASOBI 大巨蛋演唱會門票開賣</title><link>https://example.com/1</link>
    <pubDate>Wed, 09 Dec 2026 02:00:00 GMT</pubDate></item>
  <item><title>YOASOBI 新歌上架</title><link>https://example.com/2</link>
    <pubDate>Wed, 09 Dec 2026 03:00:00 GMT</pubDate></item>
  <item><title>YOASOBI 演唱會舊聞</title><link>https://example.com/3</link>
    <pubDate>Mon, 01 Jun 2026 03:00:00 GMT</pubDate></item>
</channel></rss>"""

YOASOBI = {
    "artist": "YOASOBI",
    "venue": "臺北大巨蛋",
    "shows": ["2027-01-09 18:00", "2027-01-10 18:00"],
    "platform": "遠大售票",
    "sale_at": "2026-09-17 12:00",
}


class SimulatedFailureTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SIMULATE_CI_FAILURE", "").lower() == "true", "只有選「CI 測試失敗」情境才跑")
    def test_simulated_failure(self):
        self.fail("模擬：有人把程式改壞了，CI 擋下來，後面都不會部署")


class NewsTest(unittest.TestCase):
    def test_parse_feed(self):
        items = monitor.parse_feed(SAMPLE_FEED)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["link"], "https://example.com/1")

    def test_filter_keeps_recent_concert_news_only(self):
        news = monitor.filter_news(monitor.parse_feed(SAMPLE_FEED), NOW)
        self.assertEqual([item["link"] for item in news], ["https://example.com/1"])

    def test_feed_url_contains_artist(self):
        self.assertIn("YOASOBI", monitor.build_feed_url("YOASOBI"))


class ReminderTest(unittest.TestCase):
    def test_show_tomorrow(self):
        reminders = monitor.build_reminders(YOASOBI, datetime.date(2027, 1, 8))
        self.assertIn("明天", reminders[-1])

    def test_sale_tomorrow(self):
        reminders = monitor.build_reminders(YOASOBI, datetime.date(2026, 9, 16))
        self.assertIn("開賣", reminders[0])

    def test_days_left(self):
        reminders = monitor.build_reminders(YOASOBI, datetime.date(2026, 12, 10))
        self.assertIn("還有 30 天", reminders[-1])

    def test_show_ended(self):
        self.assertIn("結束", monitor.build_reminders(YOASOBI, datetime.date(2027, 2, 1))[-1])

    def test_unknown_artist(self):
        self.assertIn("沒有登記", monitor.build_reminders(None, datetime.date(2026, 12, 10))[0])

    def test_find_concert_ignores_case(self):
        self.assertIs(monitor.find_concert("yoasobi", [YOASOBI]), YOASOBI)

    def test_anonymous_name(self):
        self.assertTrue(monitor.build_message("", "YOASOBI", ["x"], []).startswith("🎤 匿名"))

    def test_bad_today_format(self):
        with self.assertRaises(RuntimeError):
            monitor.resolve_today("2027/1/8")


class ConcertDataTest(unittest.TestCase):
    """concerts/ 的資料也要過 CI：缺值可以，錯值要擋。"""

    def test_all_concert_files(self):
        for path in sorted(monitor.CONCERTS_DIR.glob("*.json")):
            with self.subTest(file=path.name):
                concert = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(concert.get("artist"))
                self.assertTrue(concert.get("venue"))
                self.assertTrue(concert.get("shows"))
                for show in concert["shows"]:
                    self.assertRegex(show, r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$")
                    datetime.datetime.fromisoformat(show)
                if concert.get("sale_at"):
                    datetime.datetime.strptime(concert["sale_at"], "%Y-%m-%d %H:%M")


if __name__ == "__main__":
    unittest.main()
