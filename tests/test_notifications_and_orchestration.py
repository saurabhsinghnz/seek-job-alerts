import logging
import unittest
from unittest.mock import patch

from notifications import format_telegram_message
from seek_job_alert import ScrapeResult, SeekJobScraper


class FakeResponse:
    def __init__(self, status_code, text="response text", json_body=None, json_error=None):
        self.status_code = status_code
        self.text = text
        self._json_body = json_body
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        if self._json_body is None:
            raise ValueError("No JSON body")
        return self._json_body


class NotificationTests(unittest.TestCase):
    def make_scraper(self):
        scraper = object.__new__(SeekJobScraper)
        scraper.telegram_token = "token"
        scraper.chat_id = "chat-id"
        scraper.telegram_api_url = "https://api.telegram.org/bottoken/sendMessage"
        return scraper

    def make_job(self):
        return {
            "id": "123",
            "title": "Python Developer",
            "company": "Example Co",
            "salary": "$150k",
            "location": "Perth",
            "link": "https://example.test/job/123",
        }

    def test_module_formatter_preserves_current_markdown_message(self):
        expected = (
            "🔔 *New Job Alert!*\n\n"
            "📌 *Python Developer*\n"
            "🏢 Company: Example Co\n"
            "💰 Salary: $150k\n"
            "📍 Location: Perth\n\n"
            "🔗 [View Job](https://example.test/job/123)"
        )

        self.assertEqual(format_telegram_message(self.make_job()), expected)

    def test_successful_telegram_delivery_posts_expected_markdown_payload(self):
        scraper = self.make_scraper()
        job = self.make_job()

        with patch("seek_job_alert.requests.post", return_value=FakeResponse(200)) as post:
            scraper.send_telegram_notification(job)

        post.assert_called_once_with(
            scraper.telegram_api_url,
            json={
                "chat_id": "chat-id",
                "text": scraper._format_telegram_message(job),
                "parse_mode": "Markdown",
            },
            timeout=10,
        )

    def test_failed_telegram_response_is_logged_without_raising(self):
        scraper = self.make_scraper()

        with patch("seek_job_alert.requests.post", return_value=FakeResponse(500, "failed")), \
                self.assertLogs("seek_job_alert", level=logging.ERROR) as logs:
            scraper.send_telegram_notification(self.make_job())

        self.assertIn("Telegram API error (500)", "\n".join(logs.output))

    def test_telegram_json_api_failure_is_logged_without_raising(self):
        scraper = self.make_scraper()

        with patch(
            "seek_job_alert.requests.post",
            return_value=FakeResponse(
                200,
                "{\"ok\": false}",
                json_body={"ok": False, "description": "chat not found"},
            ),
        ), self.assertLogs("seek_job_alert", level=logging.ERROR) as logs:
            scraper.send_telegram_notification(self.make_job())

        self.assertIn("Telegram API error (200)", "\n".join(logs.output))
        self.assertIn("chat not found", "\n".join(logs.output))

    def test_telegram_request_exception_is_logged_without_raising(self):
        scraper = self.make_scraper()

        with patch("seek_job_alert.requests.post", side_effect=OSError("network down")), \
                self.assertLogs("seek_job_alert", level=logging.ERROR) as logs:
            scraper.send_telegram_notification(self.make_job())

        self.assertIn("Error sending Telegram notification", "\n".join(logs.output))


class OrchestrationTests(unittest.TestCase):
    def make_scraper(self):
        scraper = object.__new__(SeekJobScraper)
        scraper.chat_id = "chat-id"
        scraper.telegram_api_url = "https://api.telegram.org/bottoken/sendMessage"
        scraper.search_urls = [{"name": "IT", "url": "https://example.test/jobs"}]
        scraper.seen_jobs = {"old": "2026-01-01T00:00:00"}
        scraper._cleanup_old_jobs = lambda: None
        scraper._save_seen_jobs = lambda: None
        return scraper

    def test_first_already_seen_job_stops_scan_and_new_jobs_are_marked_before_delivery(self):
        scraper = self.make_scraper()
        jobs = [
            {"id": "new-1", "title": "First", "link": "https://example.test/job/new-1"},
            {"id": "old", "title": "Already seen", "link": "https://example.test/job/old"},
            {"id": "new-2", "title": "Not reached", "link": "https://example.test/job/new-2"},
        ]
        notification_seen_state = []

        scraper.scrape_jobs = lambda url: ScrapeResult(jobs, "valid_listings")

        def notify(job):
            notification_seen_state.append(job["id"] in scraper.seen_jobs)

        scraper.send_telegram_notification = notify
        scraper.check_and_notify()

        self.assertEqual(set(scraper.seen_jobs), {"old", "new-1"})
        self.assertEqual(notification_seen_state, [True])

    def test_notifications_follow_result_order_before_first_already_seen_job(self):
        scraper = self.make_scraper()
        jobs = [
            {"id": "new-1", "title": "First", "link": "https://example.test/job/new-1"},
            {"id": "new-2", "title": "Second", "link": "https://example.test/job/new-2"},
            {"id": "old", "title": "Already seen", "link": "https://example.test/job/old"},
        ]
        notified_ids = []

        scraper.scrape_jobs = lambda url: ScrapeResult(jobs, "valid_listings")
        scraper.send_telegram_notification = lambda job: notified_ids.append(job["id"])

        scraper.check_and_notify()

        self.assertEqual(notified_ids, [job["id"] for job in jobs[:2]])

    def test_notification_failure_does_not_remove_job_from_seen_state(self):
        scraper = self.make_scraper()
        job = {
            "id": "new-1",
            "title": "First",
            "company": "Example Co",
            "salary": "$150k",
            "location": "Perth",
            "link": "https://example.test/job/new-1",
        }
        scraper.scrape_jobs = lambda url: ScrapeResult([job], "valid_listings")

        with patch("seek_job_alert.requests.post", side_effect=OSError("network down")) as post:
            scraper.check_and_notify()

        post.assert_called_once()
        self.assertIn("new-1", scraper.seen_jobs)

    def test_failed_search_does_not_persist_but_successful_search_does(self):
        scraper = self.make_scraper()
        scraper.search_urls = [
            {"name": "failed", "url": "https://example.test/failed"},
            {"name": "successful", "url": "https://example.test/successful"},
        ]
        events = []
        scraper._cleanup_old_jobs = lambda: events.append("cleanup")
        scraper._save_seen_jobs = lambda: events.append("save")
        scraper.send_telegram_notification = lambda job: events.append("notify")

        def scrape(url):
            if url.endswith("failed"):
                return ScrapeResult([], "navigation_error")
            return ScrapeResult([
                {"id": "new", "title": "New", "link": "https://example.test/job/new"}
            ], "valid_listings")

        scraper.scrape_jobs = scrape
        scraper.check_and_notify()

        self.assertEqual(events, ["notify", "cleanup", "save"])
        self.assertIn("new", scraper.seen_jobs)


if __name__ == "__main__":
    unittest.main()