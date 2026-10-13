import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from seek_job_alert import ScrapeResult, SeekJobScraper


FIXTURES_DIR = Path(__file__).parent / "tests" / "fixtures"


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, *, url, title, status, body, card_count, link_count, jobs=None):
        self.url = url
        self._title = title
        self._goto_response = type("Response", (), {"status": status})() if status is not None else None
        self._body = body
        self._card_count = card_count
        self._link_count = link_count
        self._jobs = jobs or []

    def goto(self, *args, **kwargs):
        return self._goto_response

    def title(self):
        return self._title

    def locator(self, selector):
        if selector == "[data-job-id]":
            return FakeLocator(self._card_count)
        if selector == 'a[href*="/job/"]':
            return FakeLocator(self._link_count)
        raise AssertionError(f"Unexpected selector: {selector}")

    def evaluate(self, script):
        if "document.body" in script:
            return self._body
        if "jobElements" in script:
            return self._jobs
        raise AssertionError("Unexpected page evaluation")

    def wait_for_selector(self, selector, timeout):
        if self._card_count == 0:
            raise TimeoutError("selector timed out")


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.scraper = object.__new__(SeekJobScraper)

    def test_valid_listings_are_classified_and_parsed_as_before(self):
        jobs_data = [{
            "id": "123",
            "title": "Senior Developer",
            "company": "Example Co",
            "location": "Perth",
            "salary": "$150k",
            "date": "today",
            "link": "https://www.seek.com.au/job/123",
        }]
        page = FakePage(
            url="https://www.seek.com.au/jobs",
            title="Jobs in Australia",
            status=200,
            body="Senior Developer Example Co",
            card_count=1,
            link_count=1,
            jobs=jobs_data,
        )

        jobs = self.scraper._parse_jobs_from_page(page)

        self.assertEqual(jobs[0]["id"], "123")
        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "valid_listings")
        self.assertEqual(self.scraper.last_page_diagnostic["card_count"], 1)
        self.assertEqual(self.scraper.last_page_diagnostic["job_link_count"], 1)

    def test_empty_static_html_falls_back_to_rendered_cards(self):
        class StaticEmptyPage(FakePage):
            def content(self):
                return "<html><body>Static shell</body></html>"

        rendered_job = {
            "id": "123",
            "title": "Python Developer",
            "company": "Example Co",
            "location": "Perth",
            "salary": "$150k",
            "date": "today",
            "link": "https://www.seek.com.au/job/123",
        }
        page = StaticEmptyPage(
            url="https://www.seek.com.au/jobs",
            title="Search results",
            status=200,
            body="Python Developer Example Co",
            card_count=1,
            link_count=1,
            jobs=[rendered_job],
        )

        jobs = self.scraper._parse_jobs_from_page(page)

        self.assertEqual([job["id"] for job in jobs], ["123"])
        self.assertEqual(
            self.scraper.last_page_diagnostic["classification"],
            "valid_listings",
        )

    def test_genuine_empty_results_are_classified(self):
        page = FakePage(
            url="https://www.seek.com.au/jobs?query=rare",
            title="Search results",
            status=200,
            body="No jobs found matching your search",
            card_count=0,
            link_count=0,
        )

        self.assertEqual(self.scraper._parse_jobs_from_page(page), [])
        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "empty_results")
        self.assertIsNone(self.scraper.last_page_diagnostic["response_status"])
        self.assertFalse(hasattr(page, "response"))

    def test_empty_results_with_privacy_footer_are_not_classified_as_consent(self):
        page = FakePage(
            url="https://www.seek.com.au/jobs?query=rare",
            title="Search results",
            status=200,
            body=(
                "No jobs found matching your search. "
                "Please review our privacy policy and cookie settings."
            ),
            card_count=0,
            link_count=0,
        )

        self.scraper._parse_jobs_from_page(page)

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "empty_results")

    def test_ordinary_http_errors_are_indeterminate(self):
        for status in (404, 410, 500):
            with self.subTest(status=status):
                page = FakePage(
                    url="https://www.seek.com.au/jobs",
                    title="Error",
                    status=status,
                    body="The requested page could not be loaded.",
                    card_count=0,
                    link_count=0,
                )

                response = page.goto()
                self.scraper._parse_jobs_from_page(
                    page,
                    response_status=response.status,
                )

                self.assertEqual(
                    self.scraper.last_page_diagnostic["classification"],
                    "indeterminate",
                )

    def test_http_error_with_empty_result_wording_is_indeterminate(self):
        page = FakePage(
            url="https://www.seek.com.au/jobs",
            title="Not found",
            status=404,
            body="No results found for this page.",
            card_count=0,
            link_count=0,
        )

        response = page.goto()
        self.scraper._parse_jobs_from_page(page, response_status=response.status)

        self.assertEqual(
            self.scraper.last_page_diagnostic["classification"],
            "indeterminate",
        )

    def test_http_error_html_with_empty_result_wording_is_indeterminate(self):
        jobs = self.scraper._parse_jobs_from_html(
            "<html><body>No results found for this page.</body></html>",
            base_url="https://www.seek.com.au/jobs",
            response_status=404,
            title="Not found",
        )

        self.assertEqual(jobs, [])
        self.assertEqual(
            self.scraper.last_page_diagnostic["classification"],
            "indeterminate",
        )

    def test_page_html_uses_goto_response_status_for_static_diagnostic(self):
        class StaticErrorPage(FakePage):
            def content(self):
                return "<html><body>No results found for this page.</body></html>"

        page = StaticErrorPage(
            url="https://www.seek.com.au/jobs",
            title="Not found",
            status=404,
            body="No results found for this page.",
            card_count=0,
            link_count=0,
        )

        response = page.goto()
        self.scraper._parse_jobs_from_page(page, response_status=response.status)
        diagnostic = self.scraper.last_page_diagnostic or {}

        self.assertEqual(diagnostic.get("classification"), "indeterminate")
        self.assertEqual(diagnostic.get("response_status"), 404)

    def test_consent_page_is_not_an_empty_result(self):
        page = FakePage(
            url="https://www.seek.com.au/consent",
            title="Privacy consent",
            status=200,
            body="Before you continue, we need your consent to use cookies",
            card_count=0,
            link_count=0,
        )

        self.scraper._parse_jobs_from_page(page)

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "consent")

    def test_bot_challenge_page_is_not_an_empty_result(self):
        page = FakePage(
            url="https://www.seek.com.au/challenge",
            title="Security check",
            status=403,
            body="Please verify you are human captcha challenge",
            card_count=0,
            link_count=0,
        )

        self.scraper._parse_jobs_from_page(page)

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "bot_challenge")
        self.assertIn("captcha", self.scraper.last_page_diagnostic["body_indicators"])

    def test_rate_limit_browser_check_is_a_bot_challenge(self):
        page = FakePage(
            url="https://www.seek.com.au/jobs",
            title="Just a moment...",
            status=429,
            body="Checking your browser before accessing seek.com.au",
            card_count=0,
            link_count=0,
        )

        self.scraper._parse_jobs_from_page(page)

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "bot_challenge")
        self.assertIn("challenge", self.scraper.last_page_diagnostic["body_indicators"])

    def test_navigation_error_is_classified(self):
        self.scraper._record_page_diagnostic(
            page=None,
            navigation_error=TimeoutError("navigation timed out"),
        )

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "navigation_error")
        self.assertEqual(self.scraper.last_page_diagnostic["response_status"], None)

    def test_selector_mismatch_has_job_links_but_no_cards(self):
        page = FakePage(
            url="https://www.seek.com.au/jobs",
            title="Search results",
            status=200,
            body="Developer jobs",
            card_count=0,
            link_count=3,
        )

        self.scraper._parse_jobs_from_page(page)

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "selector_mismatch")

    def test_unknown_zero_card_page_is_indeterminate(self):
        page = FakePage(
            url="https://www.seek.com.au/error",
            title="Something went wrong",
            status=200,
            body="We are unable to complete this request right now",
            card_count=0,
            link_count=0,
        )

        self.scraper._parse_jobs_from_page(page)

        self.assertEqual(self.scraper.last_page_diagnostic["classification"], "indeterminate")

    def test_indeterminate_state_is_not_logged_as_ordinary_empty_search(self):
        self.scraper.search_urls = [{"name": "IT Remote", "url": "https://example.test"}]
        self.scraper.seen_jobs = {}
        self.scraper._cleanup_old_jobs = lambda: None
        self.scraper._save_seen_jobs = lambda: None
        self.scraper.scrape_jobs = lambda url: ScrapeResult(
            jobs=[],
            classification="bot_challenge",
            diagnostic=self.scraper.last_page_diagnostic,
        )
        self.scraper.last_page_diagnostic = {
            "classification": "bot_challenge",
            "final_url": "https://example.test/challenge",
            "title": "Security check",
            "response_status": 403,
            "card_count": 0,
            "job_link_count": 0,
            "body_indicators": ["captcha"],
        }

        with self.assertLogs("seek_job_alert", level=logging.WARNING) as captured:
            self.scraper.check_and_notify()

        output = "\n".join(captured.output)
        self.assertIn("bot_challenge", output)
        self.assertNotIn("No new jobs found", output)

    def test_scrape_result_exposes_classification_and_jobs(self):
        result = ScrapeResult(
            jobs=[{"id": "123"}],
            classification="valid_listings",
            diagnostic={"classification": "valid_listings"},
        )

        self.assertEqual(result.jobs, [{"id": "123"}])
        self.assertEqual(result.classification, "valid_listings")
        self.assertEqual(result.diagnostic["classification"], "valid_listings")

    def test_scrape_jobs_exposes_navigation_error_result(self):
        class FailingPage:
            def goto(self, *args, **kwargs):
                raise TimeoutError("navigation timed out")

        class BrowserContext:
            def new_page(self):
                return FailingPage()

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                return BrowserContext()

            def close(self):
                pass

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        class PlaywrightManager:
            def __enter__(self):
                return Playwright()

            def __exit__(self, *args):
                pass

        with patch("seek_job_alert.sync_playwright", return_value=PlaywrightManager()):
            result = self.scraper.scrape_jobs("https://example.test/failed")

        self.assertEqual(result.jobs, [])
        self.assertEqual(result.classification, "navigation_error")
        self.assertEqual(result.diagnostic["classification"], "navigation_error")

    def test_scrape_jobs_retries_transient_navigation_failure_with_a_bound(self):
        class RetryingPage:
            def __init__(self):
                self.goto_calls = 0
                self.url = "https://example.test/jobs"

            def goto(self, *args, **kwargs):
                self.goto_calls += 1
                if self.goto_calls == 1:
                    raise TimeoutError("temporary navigation timeout")
                return type("Response", (), {"status": 200})()

            def wait_for_selector(self, selector, timeout):
                return None

            def title(self):
                return "Jobs"

            def locator(self, selector):
                return FakeLocator(0)

            def evaluate(self, script):
                return "No jobs found"

            def content(self):
                return "<html><body>No jobs found</body></html>"

        page = RetryingPage()

        class BrowserContext:
            def new_page(self):
                return page

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                return BrowserContext()

            def close(self):
                pass

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        class PlaywrightManager:
            def __enter__(self):
                return Playwright()

            def __exit__(self, *args):
                pass

        with patch("seek_job_alert.sync_playwright", return_value=PlaywrightManager()):
            result = self.scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(page.goto_calls, 2)
        self.assertEqual(result.classification, "empty_results")

    def test_scrape_jobs_replaces_stale_diagnostic_when_final_navigation_fails(self):
        class MalformedThenFailingPage:
            def __init__(self):
                self.goto_calls = 0
                self.url = "https://example.test/jobs"

            def goto(self, *args, **kwargs):
                self.goto_calls += 1
                if self.goto_calls == 1:
                    return type("Response", (), {"status": 200})()
                raise TimeoutError("final navigation timed out")

            def wait_for_selector(self, selector, timeout):
                raise TimeoutError("no job cards")

            def title(self):
                return "Malformed response"

            def locator(self, selector):
                return FakeLocator(0)

            def evaluate(self, script):
                return "Unexpected response"

            def content(self):
                return "<html><body><div data-job-id='missing-fields'></div></body></html>"

        page = MalformedThenFailingPage()

        class BrowserContext:
            def new_page(self):
                return page

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                return BrowserContext()

            def close(self):
                pass

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        class PlaywrightManager:
            def __enter__(self):
                return Playwright()

            def __exit__(self, *args):
                pass

        with patch("seek_job_alert.sync_playwright", return_value=PlaywrightManager()):
            result = self.scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(page.goto_calls, 2)
        self.assertEqual(result.classification, "navigation_error")
        self.assertEqual(result.diagnostic["classification"], "navigation_error")
        self.assertIn("final navigation timed out", result.diagnostic["body_indicators"])

    def test_scrape_jobs_uses_targeted_readiness_check_without_fixed_sleep(self):
        class ReadyPage(FakePage):
            def __init__(self):
                super().__init__(
                    url="https://example.test/jobs",
                    title="Jobs",
                    status=200,
                    body="No jobs found",
                    card_count=0,
                    link_count=0,
                )
                self.waited_for = []

            def goto(self, *args, **kwargs):
                return super().goto(*args, **kwargs)

            def wait_for_load_state(self, state, timeout):
                self.waited_for.append(("load_state", state, timeout))

            def wait_for_selector(self, selector, timeout):
                self.waited_for.append(("selector", selector, timeout))
                raise TimeoutError("no listings")

            def content(self):
                return "<html><body>No jobs found</body></html>"

        page = ReadyPage()

        class BrowserContext:
            def new_page(self):
                return page

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                return BrowserContext()

            def close(self):
                pass

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        class PlaywrightManager:
            def __enter__(self):
                return Playwright()

            def __exit__(self, *args):
                pass

        with patch("seek_job_alert.sync_playwright", return_value=PlaywrightManager()), \
                patch("seek_job_alert.time.sleep") as sleep:
            result = self.scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(result.classification, "empty_results")
        self.assertTrue(any(call[0] == "selector" for call in page.waited_for))
        self.assertTrue(any(call[0] == "load_state" for call in page.waited_for))
        sleep.assert_not_called()

    def test_blocked_page_artifacts_are_opt_in(self):
        class BlockedPage(FakePage):
            def __init__(self):
                super().__init__(
                    url="https://example.test/challenge",
                    title="Security check",
                    status=403,
                    body="Please verify you are human captcha challenge",
                    card_count=0,
                    link_count=0,
                )

            def goto(self, *args, **kwargs):
                return super().goto(*args, **kwargs)

            def content(self):
                return "<html><body>captcha challenge</body></html>"

            def screenshot(self, path, full_page):
                Path(path).write_bytes(b"image")

        page = BlockedPage()

        class BrowserContext:
            def new_page(self):
                return page

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                return BrowserContext()

            def close(self):
                pass

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        class PlaywrightManager:
            def __enter__(self):
                return Playwright()

            def __exit__(self, *args):
                pass

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"SEEK_DIAGNOSTIC_DIR": directory}), \
                patch("seek_job_alert.sync_playwright", return_value=PlaywrightManager()):
            result = self.scraper.scrape_jobs("https://example.test/jobs")
            artifacts = list(Path(directory).iterdir())

        self.assertEqual(result.classification, "bot_challenge")
        self.assertTrue(artifacts)

    def test_failed_search_does_not_mutate_state_or_block_later_success(self):
        self.scraper.search_urls = [
            {"name": "Failed", "url": "https://example.test/failed"},
            {"name": "Working", "url": "https://example.test/working"},
        ]
        self.scraper.seen_jobs = {}
        notifications = []
        cleanup_calls = []
        save_calls = []
        self.scraper._cleanup_old_jobs = lambda: cleanup_calls.append(True)
        self.scraper._save_seen_jobs = lambda: save_calls.append(True)
        self.scraper.send_telegram_notification = notifications.append

        def scrape(url):
            if url.endswith("failed"):
                return ScrapeResult(
                    jobs=[],
                    classification="navigation_error",
                    diagnostic={"classification": "navigation_error"},
                )
            return ScrapeResult(
                jobs=[{"id": "123", "title": "Working job"}],
                classification="valid_listings",
                diagnostic={"classification": "valid_listings"},
            )

        self.scraper.scrape_jobs = scrape

        self.scraper.check_and_notify()

        self.assertEqual(set(self.scraper.seen_jobs), {"123"})
        self.assertEqual([job["id"] for job in notifications], ["123"])
        self.assertEqual(len(cleanup_calls), 1)
        self.assertEqual(len(save_calls), 1)

    def test_success_then_failed_search_persists_before_failure_without_extra_save(self):
        self.scraper.search_urls = [
            {"name": "Working", "url": "https://example.test/working"},
            {"name": "Failed", "url": "https://example.test/failed"},
        ]
        self.scraper.seen_jobs = {}
        events = []
        notifications = []
        self.scraper._cleanup_old_jobs = lambda: events.append("cleanup")
        self.scraper._save_seen_jobs = lambda: events.append("save")
        self.scraper.send_telegram_notification = notifications.append

        def scrape(url):
            events.append(url.rsplit("/", 1)[-1])
            if url.endswith("failed"):
                return ScrapeResult(
                    jobs=[],
                    classification="navigation_error",
                    diagnostic={"classification": "navigation_error"},
                )
            return ScrapeResult(
                jobs=[{"id": "123", "title": "Working job"}],
                classification="valid_listings",
                diagnostic={"classification": "valid_listings"},
            )

        self.scraper.scrape_jobs = scrape

        self.scraper.check_and_notify()

        self.assertEqual(set(self.scraper.seen_jobs), {"123"})
        self.assertEqual([job["id"] for job in notifications], ["123"])
        self.assertEqual(events, ["working", "cleanup", "save", "failed"])

    def test_failed_search_then_empty_search_only_persists_for_empty_result(self):
        self.scraper.search_urls = [
            {"name": "Failed", "url": "https://example.test/failed"},
            {"name": "Empty", "url": "https://example.test/empty"},
        ]
        self.scraper.seen_jobs = {"old": "2000-01-01T00:00:00"}
        events = []
        self.scraper._cleanup_old_jobs = lambda: events.append("cleanup")
        self.scraper._save_seen_jobs = lambda: events.append("save")

        def scrape(url):
            events.append(url.rsplit("/", 1)[-1])
            classification = "navigation_error" if url.endswith("failed") else "empty_results"
            return ScrapeResult(
                jobs=[],
                classification=classification,
                diagnostic={"classification": classification},
            )

        self.scraper.scrape_jobs = scrape

        self.scraper.check_and_notify()

        self.assertEqual(self.scraper.seen_jobs, {"old": "2000-01-01T00:00:00"})
        self.assertEqual(events, ["failed", "empty", "cleanup", "save"])

    def test_failed_search_does_not_mutate_seen_jobs_or_call_persistence(self):
        self.scraper.search_urls = [{"name": "Failed", "url": "https://example.test/failed"}]
        self.scraper.seen_jobs = {"old": "2000-01-01T00:00:00"}
        cleanup_calls = []
        save_calls = []
        self.scraper._cleanup_old_jobs = lambda: cleanup_calls.append(True)
        self.scraper._save_seen_jobs = lambda: save_calls.append(True)
        self.scraper.scrape_jobs = lambda url: ScrapeResult(
            jobs=[{"id": "must-not-be-recorded"}],
            classification="bot_challenge",
            diagnostic={"classification": "bot_challenge"},
        )

        self.scraper.check_and_notify()

        self.assertEqual(self.scraper.seen_jobs, {"old": "2000-01-01T00:00:00"})
        self.assertEqual(cleanup_calls, [])
        self.assertEqual(save_calls, [])

    def test_failed_only_search_does_not_cleanup_or_save_seen_jobs(self):
        self.scraper.search_urls = [{"name": "Failed", "url": "https://example.test/failed"}]
        self.scraper.seen_jobs = {"old": "2000-01-01T00:00:00"}
        cleanup_calls = []
        save_calls = []
        self.scraper._cleanup_old_jobs = lambda: cleanup_calls.append(True)
        self.scraper._save_seen_jobs = lambda: save_calls.append(True)
        self.scraper.scrape_jobs = lambda url: ScrapeResult(
            jobs=[],
            classification="bot_challenge",
            diagnostic={"classification": "bot_challenge"},
        )

        self.scraper.check_and_notify()

        self.assertEqual(self.scraper.seen_jobs, {"old": "2000-01-01T00:00:00"})
        self.assertEqual(cleanup_calls, [])
        self.assertEqual(save_calls, [])


class OfflineParserTests(unittest.TestCase):
    def setUp(self):
        self.scraper = object.__new__(SeekJobScraper)

    def read_fixture(self, name):
        return (FIXTURES_DIR / name).read_text()

    def test_success_fixture_extracts_complete_jobs(self):
        html = self.read_fixture("successful-listings.html")

        jobs = self.scraper._parse_jobs_from_html(
            html,
            base_url="https://www.seek.com.au/jobs",
            title="IT jobs in Australia",
        )

        self.assertEqual(
            jobs,
            [
                {
                    "id": "1001",
                    "title": "Senior Python Developer",
                    "company": "Harbour Systems",
                    "salary": "$140,000 - $160,000 per year",
                    "location": "Perth WA",
                    "posted_date": "Listed two days ago",
                    "link": "https://www.seek.com.au/job/1001",
                },
                {
                    "id": "1002",
                    "title": "Frontend Engineer",
                    "company": "Southern Digital",
                    "salary": "Competitive salary",
                    "location": "Remote",
                    "posted_date": "Listed today",
                    "link": "https://www.seek.com.au/job/1002",
                },
            ],
        )
        self.assertEqual(
            self.scraper.last_page_diagnostic["title"],
            "IT jobs in Australia",
        )
        self.assertEqual(self.scraper.last_page_diagnostic["job_link_count"], 3)

    def test_malformed_card_is_skipped_without_affecting_valid_cards(self):
        html = self.read_fixture("successful-listings.html")

        jobs = self.scraper._parse_jobs_from_html(html)

        self.assertEqual([job["id"] for job in jobs], ["1001", "1002"])

    def test_empty_consent_and_challenge_fixtures_are_classified_without_jobs(self):
        expected_classifications = {
            "empty-results.html": "empty_results",
            "consent.html": "consent",
            "bot-challenge.html": "bot_challenge",
        }

        for fixture_name, expected_classification in expected_classifications.items():
            with self.subTest(fixture_name=fixture_name):
                jobs = self.scraper._parse_jobs_from_html(
                    self.read_fixture(fixture_name),
                )

                self.assertEqual(jobs, [])
                self.assertEqual(
                    self.scraper.last_page_diagnostic["classification"],
                    expected_classification,
                )


if __name__ == "__main__":
    unittest.main()
