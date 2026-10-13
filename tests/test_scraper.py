import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper import BrowserScraper


class Locator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class Page:
    def __init__(self, *, cards=0, links=0, body="No jobs found", html=None):
        self.url = "https://example.test/jobs"
        self._cards = cards
        self._links = links
        self._body = body
        self._html = html or f"<html><body>{body}</body></html>"
        self.goto_calls = 0
        self.waited_for = []

    def goto(self, *args, **kwargs):
        self.goto_calls += 1
        return type("Response", (), {"status": 200})()

    def title(self):
        return "Search results"

    def locator(self, selector):
        return Locator(self._cards if selector == "[data-job-id]" else self._links)

    def evaluate(self, script):
        if "document.body" in script:
            return self._body
        if "jobElements" in script:
            return [{
                "id": "123",
                "title": "Python Developer",
                "company": "Example Co",
                "location": "Perth",
                "salary": "$150k",
                "date": "today",
                "link": "https://example.test/job/123",
            }]
        raise AssertionError("Unexpected page evaluation")

    def wait_for_load_state(self, state, timeout):
        self.waited_for.append(("load_state", state, timeout))

    def wait_for_selector(self, selector, timeout):
        self.waited_for.append(("selector", selector, timeout))
        if not self._cards:
            raise TimeoutError("no cards")

    def content(self):
        return self._html

    def screenshot(self, path, full_page):
        Path(path).write_bytes(b"image")


class BrowserScraperTests(unittest.TestCase):
    def make_factory(self, page):
        class Context:
            def new_page(self):
                return page

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                return Context()

            def close(self):
                pass

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        class Manager:
            def __enter__(self):
                return Playwright()

            def __exit__(self, *args):
                pass

        return lambda: Manager()

    def test_navigation_retries_are_bounded(self):
        page = Page()

        def fail_navigation(*args, **kwargs):
            page.goto_calls += 1
            raise TimeoutError("navigation timed out")

        page.goto = fail_navigation
        scraper = BrowserScraper(playwright_factory=self.make_factory(page), max_navigation_attempts=2)

        result = scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(page.goto_calls, 2)
        self.assertEqual(result.classification, "navigation_error")
        self.assertIn("navigation timed out", result.diagnostic["body_indicators"])

    def test_context_creation_failure_closes_browser(self):
        events = []

        class Browser:
            def new_context(self, **kwargs):
                raise RuntimeError("context creation failed")

            def close(self):
                events.append("browser.close")

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        scraper = BrowserScraper(playwright_factory=self._make_manager(Playwright))

        result = scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(result.classification, "navigation_error")
        self.assertEqual(events, ["browser.close"])

    def test_page_creation_failure_closes_context_and_browser(self):
        events = []

        class Context:
            def new_page(self):
                raise RuntimeError("page creation failed")

            def close(self):
                events.append("context.close")

        class Browser:
            def new_context(self, **kwargs):
                return Context()

            def close(self):
                events.append("browser.close")

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        scraper = BrowserScraper(playwright_factory=self._make_manager(Playwright))

        result = scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(result.classification, "navigation_error")
        self.assertEqual(events, ["context.close", "browser.close"])

    def test_cleanup_attempts_browser_after_context_close_failure(self):
        page = Page(cards=1)
        events = []

        class Context:
            def new_page(self):
                return page

            def close(self):
                events.append("context.close")
                raise RuntimeError("context close failed")

        class Browser:
            def new_context(self, **kwargs):
                return Context()

            def close(self):
                events.append("browser.close")
                raise RuntimeError("browser close failed")

        class Playwright:
            class Chromium:
                def launch(self, **kwargs):
                    return Browser()

            chromium = Chromium()

        scraper = BrowserScraper(playwright_factory=self._make_manager(Playwright))

        result = scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(result.classification, "valid_listings")
        self.assertEqual(events, ["context.close", "browser.close"])

    def test_manager_cleanup_failure_does_not_replace_valid_result(self):
        page = Page(cards=1)

        class Manager(self.make_factory(page)().__class__):
            def __exit__(self, *args):
                raise RuntimeError("manager close failed")

        scraper = BrowserScraper(playwright_factory=lambda: Manager())

        with self.assertLogs("scraper", level="WARNING") as logs:
            result = scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(result.classification, "valid_listings")
        self.assertEqual(result.jobs[0]["id"], "123")
        self.assertIn("Unable to close Playwright manager", logs.output[0])

    def _make_manager(self, playwright):
        class Manager:
            def __enter__(self):
                return playwright

            def __exit__(self, *args):
                pass

        return lambda: Manager()

    def test_readiness_uses_network_idle_and_selector_checks(self):
        page = Page()
        scraper = BrowserScraper(playwright_factory=self.make_factory(page))

        scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(page.waited_for[0][0], "load_state")
        self.assertEqual(page.waited_for[1][0], "selector")

    def test_empty_static_extraction_falls_back_to_browser_cards(self):
        page = Page(cards=1, links=1, html="<html><body>shell</body></html>")
        scraper = BrowserScraper(playwright_factory=self.make_factory(page))

        result = scraper.scrape_jobs("https://example.test/jobs")

        self.assertEqual(result.classification, "valid_listings")
        self.assertEqual(result.jobs[0]["id"], "123")

    def test_blocked_diagnostics_capture_opt_in_artifacts(self):
        page = Page(body="captcha challenge", html="<html><body>captcha</body></html>")
        page.url = "https://example.test/challenge"
        scraper = BrowserScraper(playwright_factory=self.make_factory(page))

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SEEK_DIAGNOSTIC_DIR": directory}
        ):
            result = scraper.scrape_jobs("https://example.test/jobs")
            artifacts = list(Path(directory).iterdir())

        self.assertEqual(result.classification, "bot_challenge")
        self.assertTrue(artifacts)
        self.assertIn("html_artifact", result.diagnostic)


if __name__ == "__main__":
    unittest.main()