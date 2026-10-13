import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from config import SearchConfig
from seek_job_alert import SeekJobScraper
from state import SeenJobState


class ConfigurationAndStateTests(unittest.TestCase):
    def make_scraper(self):
        scraper = object.__new__(SeekJobScraper)
        scraper.telegram_token = "token"
        scraper.chat_id = "chat"
        scraper.telegram_api_url = "https://api.telegram.org/bottoken/sendMessage"
        return scraper

    def test_search_urls_add_listed_date_sort_without_replacing_existing_sort(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "search_config.json"
            config_path.write_text(json.dumps({
                "searches": [
                    {"name": "plain", "url": "https://example.test/jobs?query=python"},
                    {"name": "sorted", "url": "https://example.test/jobs?sortmode=Relevance"},
                    {"name": "trimmed", "url": "https://example.test/jobs?query=go&&"},
                ]
            }))

            with patch("seek_job_alert.SEARCH_CONFIG_FILE", str(config_path)):
                searches = self.make_scraper()._load_search_urls()

        self.assertEqual(
            [search["url"] for search in searches],
            [
                "https://example.test/jobs?query=python&sortmode=ListedDate",
                "https://example.test/jobs?sortmode=Relevance",
                "https://example.test/jobs?query=go&sortmode=ListedDate",
            ],
        )

    def test_search_config_returns_empty_for_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            searches = SearchConfig(Path(directory) / "missing.json").load()

        self.assertEqual(searches, [])

    def test_search_config_returns_empty_for_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "search_config.json"
            config_path.write_text("not json")

            searches = SearchConfig(config_path).load()

        self.assertEqual(searches, [])

    def test_search_config_normalizes_urls_without_mutating_other_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "search_config.json"
            config_path.write_text(json.dumps({
                "searches": [
                    {"name": "plain", "url": "https://example.test/jobs?query=python"},
                    {"name": "sorted", "url": "https://example.test/jobs?sortmode=Relevance"},
                    {"name": "trimmed", "url": "https://example.test/jobs?query=go&&"},
                    {"name": "empty", "url": ""},
                ]
            }))

            searches = SearchConfig(config_path).load()

        self.assertEqual(searches[0]["name"], "plain")
        self.assertEqual(searches[0]["url"], "https://example.test/jobs?query=python&sortmode=ListedDate")
        self.assertEqual(searches[1]["url"], "https://example.test/jobs?sortmode=Relevance")
        self.assertEqual(searches[2]["url"], "https://example.test/jobs?query=go&sortmode=ListedDate")
        self.assertEqual(searches[3]["url"], "")

    def test_old_seen_job_list_is_migrated_with_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "seen_jobs.json"
            state_path.write_text(json.dumps({"seen_job_ids": ["123", "456"]}))

            with patch("seek_job_alert.SEEN_JOBS_FILE", str(state_path)):
                seen_jobs = self.make_scraper()._load_seen_jobs()

        self.assertEqual(set(seen_jobs), {"123", "456"})
        for timestamp in seen_jobs.values():
            self.assertIsInstance(datetime.fromisoformat(timestamp), datetime)

    def test_seen_job_state_returns_empty_for_missing_or_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SeenJobState(Path(directory) / "missing.json")
            self.assertEqual(state.load(), {})

            state.path.write_text("not json")
            self.assertEqual(state.load(), {})

    def test_seen_job_state_loads_current_format_without_changing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "seen_jobs.json"
            expected = {"123": "not-a-timestamp"}
            state_path.write_text(json.dumps({"seen_jobs": expected}))

            self.assertEqual(SeenJobState(state_path).load(), expected)

    def test_seen_job_state_cleanup_removes_old_jobs_and_ignores_bad_timestamps(self):
        state = SeenJobState("seen_jobs.json")
        seen_jobs = {
            "old": (datetime.now() - timedelta(days=91)).isoformat(),
            "recent": (datetime.now() - timedelta(days=89)).isoformat(),
            "malformed": "not-a-timestamp",
        }

        cleaned = state.cleanup(seen_jobs, retention_days=90)

        self.assertEqual(cleaned.keys(), {"recent", "malformed"})

    def test_cleanup_removes_only_jobs_older_than_retention_window(self):
        scraper = self.make_scraper()
        scraper.seen_jobs = {
            "old": (datetime.now() - timedelta(days=91)).isoformat(),
            "recent": (datetime.now() - timedelta(days=89)).isoformat(),
        }

        scraper._cleanup_old_jobs(retention_days=90)

        self.assertEqual(scraper.seen_jobs.keys(), {"recent"})

    def test_save_seen_jobs_writes_current_dict_format(self):
        scraper = self.make_scraper()
        scraper.seen_jobs = {"123": "2026-01-01T00:00:00"}

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "seen_jobs.json"
            with patch("seek_job_alert.SEEN_JOBS_FILE", str(state_path)):
                scraper._save_seen_jobs()

            self.assertEqual(
                json.loads(state_path.read_text()),
                {"seen_jobs": {"123": "2026-01-01T00:00:00"}},
            )

    def test_seen_job_state_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "nested" / "seen_jobs.json"
            expected = {"123": "2026-01-01T00:00:00"}

            state = SeenJobState(state_path)
            state.save(expected)

            self.assertEqual(state.load(), expected)


if __name__ == "__main__":
    unittest.main()