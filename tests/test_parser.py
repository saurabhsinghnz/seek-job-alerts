import unittest
from pathlib import Path

from models import ScrapeResult
from parser import classify_page, parse_jobs_from_html
from seek_job_alert import SeekJobScraper


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def read_fixture(self, name):
        return (FIXTURES_DIR / name).read_text()

    def test_fixture_classifications_match_existing_outputs(self):
        expected = {
            "successful-listings.html": "valid_listings",
            "empty-results.html": "empty_results",
            "consent.html": "consent",
            "bot-challenge.html": "bot_challenge",
        }

        for fixture_name, classification in expected.items():
            with self.subTest(fixture_name=fixture_name):
                jobs, diagnostic = parse_jobs_from_html(
                    self.read_fixture(fixture_name),
                    base_url="https://www.seek.com.au/jobs",
                )

                self.assertEqual(diagnostic["classification"], classification)
                self.assertEqual(bool(jobs), classification == "valid_listings")

    def test_url_and_title_only_signals_are_classified_in_static_html(self):
        cases = (
            ("https://www.seek.com.au/consent", "Jobs", "consent", "consent"),
            ("https://www.seek.com.au/jobs", "Cookie consent", "consent", "consent"),
            ("https://www.seek.com.au/challenge", "Jobs", "bot_challenge", "challenge"),
            ("https://www.seek.com.au/jobs", "Security check", "bot_challenge", "captcha"),
        )

        for url, title, classification, indicator in cases:
            with self.subTest(url=url, title=title):
                jobs, diagnostic = parse_jobs_from_html(
                    "<html><body> </body></html>",
                    base_url=url,
                    title=title,
                )

                self.assertEqual(jobs, [])
                self.assertEqual(diagnostic["classification"], classification)
                self.assertIn(indicator, diagnostic["body_indicators"])
                self.assertEqual(diagnostic["final_url"], url)
                self.assertEqual(diagnostic["title"], title)

    def test_error_title_keeps_static_http_error_indeterminate(self):
        jobs, diagnostic = parse_jobs_from_html(
            "<html><body>Request failed</body></html>",
            base_url="https://www.seek.com.au/error",
            response_status=500,
            title="Error",
        )

        self.assertEqual(jobs, [])
        self.assertEqual(diagnostic["classification"], "indeterminate")
        self.assertEqual(diagnostic["final_url"], "https://www.seek.com.au/error")
        self.assertEqual(diagnostic["title"], "Error")

    def test_malformed_cards_are_skipped_and_missing_fields_keep_defaults(self):
        html = """
        <article data-job-id="missing-title">
          <a href="/job/missing-title"><span>Not an automation title</span></a>
        </article>
        <article data-job-id="valid">
          <a href="/job/valid"><h3 data-automation="jobTitle">  Python
            Developer </h3></a>
        </article>
        <article data-job-id="missing-link">
          <h3 data-automation="jobTitle">No link</h3>
        </article>
        """

        jobs, diagnostic = parse_jobs_from_html(html)

        self.assertEqual(jobs, [{
            "id": "valid",
            "title": "Python Developer",
            "company": "N/A",
            "salary": "Not specified",
            "location": "Remote",
            "posted_date": "Recently",
            "link": "/job/valid",
        }])
        self.assertEqual(diagnostic["card_count"], 3)
        self.assertEqual(diagnostic["classification"], "valid_listings")

    def test_job_urls_resolve_absolute_root_relative_and_path_relative_links(self):
        html = """
        <article data-job-id="absolute"><a href="https://jobs.example/job/absolute">
          <h3 data-automation="jobTitle">Absolute</h3></a></article>
        <article data-job-id="root"><a href="/job/root">
          <h3 data-automation="jobTitle">Root</h3></a></article>
        <article data-job-id="relative"><a href="./job/relative">
          <h3 data-automation="jobTitle">Relative</h3></a></article>
        """

        jobs, _ = parse_jobs_from_html(
            html,
            base_url="https://www.seek.com.au/search/jobs",
        )

        self.assertEqual(
            [job["link"] for job in jobs],
            [
                "https://jobs.example/job/absolute",
                "https://www.seek.com.au/job/root",
                "https://www.seek.com.au/search/job/relative",
            ],
        )

    def test_classification_preserves_indicator_and_status_precedence(self):
        indicators = ["consent", "challenge", "empty_results"]

        self.assertEqual(
            classify_page(0, 0, indicators, response_status=403, source="static"),
            "bot_challenge",
        )
        self.assertEqual(
            classify_page(0, 0, ["consent"], response_status=403, source="static"),
            "consent",
        )
        self.assertEqual(
            classify_page(0, 0, ["consent"], response_status=403, source="browser"),
            "indeterminate",
        )
        self.assertEqual(
            classify_page(1, 0, ["challenge"], response_status=403, source="browser"),
            "valid_listings",
        )
        self.assertEqual(
            classify_page(0, 2, [], response_status=200, source="browser"),
            "selector_mismatch",
        )

    def test_result_model_retains_compatibility_fields(self):
        result = ScrapeResult(
            jobs=[{"id": "1"}],
            classification="valid_listings",
            diagnostic={"classification": "valid_listings"},
        )

        self.assertEqual(result.jobs, [{"id": "1"}])
        self.assertEqual(result.classification, "valid_listings")
        self.assertEqual(result.diagnostic["classification"], "valid_listings")
        self.assertEqual(ScrapeResult([], "empty_results").diagnostic, {})

    def test_page_parser_falls_back_to_browser_extraction_when_content_is_unavailable(self):
        class Locator:
            def count(self):
                return 1

        class Page:
            url = "https://www.seek.com.au/jobs"

            def title(self):
                return "Jobs"

            def locator(self, selector):
                return Locator()

            def evaluate(self, script):
                if "document.body" in script:
                    return "Python Developer"
                if "jobElements" in script:
                    return [{
                        "id": "123",
                        "title": "Python Developer",
                        "company": "Example Co",
                        "location": "Perth",
                        "salary": "$150k",
                        "date": "today",
                        "link": "https://www.seek.com.au/job/123",
                    }]
                raise AssertionError("Unexpected page evaluation")

            def wait_for_selector(self, selector, timeout):
                return None

            def content(self):
                raise RuntimeError("static content unavailable")

        scraper = object.__new__(SeekJobScraper)

        jobs = scraper._parse_jobs_from_page(Page())

        self.assertEqual(jobs[0]["id"], "123")
        self.assertEqual(jobs[0]["posted_date"], "today")


if __name__ == "__main__":
    unittest.main()