import logging
import os
import re
from datetime import datetime
from pathlib import Path

from models import ScrapeResult
from parser import classify_page, collect_body_indicators, parse_jobs_from_html


logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
MAX_NAVIGATION_ATTEMPTS = 2
READINESS_TIMEOUT_MS = 5000
JOB_SELECTOR_TIMEOUT_MS = 10000


class BrowserScraper:
    """Own Playwright lifecycle, extraction, readiness, and page diagnostics."""

    def __init__(
        self,
        playwright_factory,
        *,
        max_navigation_attempts=MAX_NAVIGATION_ATTEMPTS,
        readiness_timeout_ms=READINESS_TIMEOUT_MS,
        job_selector_timeout_ms=JOB_SELECTOR_TIMEOUT_MS,
        user_agent=USER_AGENT,
    ):
        self.playwright_factory = playwright_factory
        self.max_navigation_attempts = max_navigation_attempts
        self.readiness_timeout_ms = readiness_timeout_ms
        self.job_selector_timeout_ms = job_selector_timeout_ms
        self.user_agent = user_agent
        self.last_page_diagnostic = None

    def _record_page_diagnostic(self, page, response_status=None, navigation_error=None):
        diagnostic = {
            "classification": "navigation_error" if navigation_error else "indeterminate",
            "final_url": None,
            "title": None,
            "response_status": response_status,
            "card_count": 0,
            "job_link_count": 0,
            "body_indicators": [],
        }

        if navigation_error:
            diagnostic["body_indicators"] = [str(navigation_error)]
            self.last_page_diagnostic = diagnostic
            logger.warning("Page diagnostic: navigation_error (%s)", navigation_error)
            return diagnostic

        try:
            diagnostic["final_url"] = page.url
            diagnostic["title"] = page.title()
            diagnostic["card_count"] = page.locator("[data-job-id]").count()
            diagnostic["job_link_count"] = page.locator('a[href*="/job/"]').count()
            body_text = page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            ) or ""
            diagnostic["body_indicators"] = collect_body_indicators(
                body_text,
                final_url=diagnostic["final_url"],
                title=diagnostic["title"],
            )
            url_lower = (diagnostic["final_url"] or "").lower()
            title_lower = (diagnostic["title"] or "").lower()
            challenge_evidence = (
                any(
                    indicator in diagnostic["body_indicators"]
                    for indicator in ("captcha", "challenge")
                )
                or "/challenge" in url_lower
                or "security check" in title_lower
            )
            diagnostic["classification"] = classify_page(
                diagnostic["card_count"],
                diagnostic["job_link_count"],
                diagnostic["body_indicators"],
                response_status=diagnostic["response_status"],
                source="browser",
                challenge_evidence=challenge_evidence,
            )
        except Exception as error:
            diagnostic["body_indicators"].append(str(error))

        self.last_page_diagnostic = diagnostic
        logger.info(
            "Page diagnostic: %s url=%s title=%r status=%s cards=%s job_links=%s indicators=%s",
            diagnostic["classification"],
            diagnostic["final_url"],
            diagnostic["title"],
            diagnostic["response_status"],
            diagnostic["card_count"],
            diagnostic["job_link_count"],
            diagnostic["body_indicators"],
        )
        return diagnostic

    def _parse_jobs_from_html(self, html, base_url="", response_status=None, title=None):
        jobs, diagnostic = parse_jobs_from_html(
            html,
            base_url=base_url,
            response_status=response_status,
            title=title,
        )
        self.last_page_diagnostic = diagnostic
        return jobs

    def _prefer_stronger_diagnostic(self, browser_diagnostic, static_diagnostic):
        priorities = {
            "indeterminate": 0,
            "empty_results": 1,
            "selector_mismatch": 1,
            "consent": 2,
            "bot_challenge": 3,
            "navigation_error": 4,
            "valid_listings": 5,
        }
        if priorities.get(browser_diagnostic.get("classification"), 0) > priorities.get(
            static_diagnostic.get("classification"), 0
        ):
            return browser_diagnostic
        return static_diagnostic

    def _parse_jobs_from_page(self, page, response_status=None):
        try:
            page.wait_for_selector(
                "[data-job-id]", timeout=self.job_selector_timeout_ms
            )
            logger.info("Found job listings on page")
        except Exception as error:
            logger.warning("Timeout waiting for job listings: %s", error)

        browser_diagnostic = self._record_page_diagnostic(
            page, response_status=response_status
        )

        if hasattr(page, "content"):
            try:
                static_jobs = self._parse_jobs_from_html(
                    page.content(),
                    base_url=page.url,
                    response_status=response_status,
                    title=page.title(),
                )
                static_diagnostic = self.last_page_diagnostic
                self.last_page_diagnostic = self._prefer_stronger_diagnostic(
                    browser_diagnostic, static_diagnostic
                )
                if static_jobs or not browser_diagnostic.get("card_count"):
                    return static_jobs
            except Exception as error:
                logger.warning(
                    "Static HTML extraction failed; using browser extraction: %s", error
                )

        try:
            job_locator = page.locator("[data-job-id]")
            job_count = job_locator.count()
            logger.info("Found %s job elements", job_count)
            jobs_data = page.evaluate(
                """
                () => {
                    const jobElements = document.querySelectorAll('[data-job-id]');
                    const jobs = [];
                    jobElements.forEach((el, idx) => {
                        if (idx >= 50) return;
                        try {
                            const jobId = el.getAttribute('data-job-id');
                            const titleElem = el.querySelector('[data-automation="jobTitle"]');
                            const companyElem = el.querySelector('[data-automation="jobCompany"]');
                            const locationElem = el.querySelector('[data-automation="jobLocation"]');
                            const salaryElem = el.querySelector('[data-automation="jobSalary"]');
                            const dateElem = el.querySelector('[data-automation="jobListedDate"]');
                            const linkElem = el.querySelector('a[href*="/job/"]');
                            jobs.push({
                                id: jobId,
                                title: titleElem ? titleElem.textContent.trim() : 'N/A',
                                company: companyElem ? companyElem.textContent.trim() : 'N/A',
                                location: locationElem ? locationElem.textContent.trim() : 'Remote',
                                salary: salaryElem ? salaryElem.textContent.trim() : 'Not specified',
                                date: dateElem ? dateElem.textContent.trim() : 'Recently',
                                link: linkElem ? linkElem.href : ''
                            });
                        } catch (e) {
                            console.error('Error parsing job:', e);
                        }
                    });
                    return jobs;
                }
                """
            )
            jobs = []
            for job_data in jobs_data:
                if job_data["title"] and job_data["title"] != "N/A" and job_data["id"]:
                    jobs.append({
                        "id": job_data["id"],
                        "title": job_data["title"],
                        "company": job_data["company"],
                        "salary": job_data["salary"],
                        "location": job_data["location"],
                        "posted_date": job_data["date"],
                        "link": job_data["link"],
                    })
            return jobs
        except Exception as error:
            logger.error("Error parsing jobs from page: %s", error)
            return []

    def _wait_for_page_readiness(self, page):
        if hasattr(page, "wait_for_load_state"):
            try:
                page.wait_for_load_state("networkidle", timeout=self.readiness_timeout_ms)
            except Exception as error:
                logger.info("Network idle readiness check did not complete: %s", error)
        try:
            page.wait_for_selector(
                "[data-job-id]", timeout=self.readiness_timeout_ms
            )
            return True
        except Exception as error:
            logger.info("Job-card readiness check did not find listings: %s", error)
            return False

    def _capture_page_artifacts(self, page, diagnostic):
        diagnostic_dir = os.getenv("SEEK_DIAGNOSTIC_DIR")
        if not diagnostic_dir or diagnostic.get("classification") not in {
            "bot_challenge", "consent", "indeterminate", "selector_mismatch",
        }:
            return
        try:
            output_dir = Path(diagnostic_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            html_path = output_dir / f"seek-page-{stamp}.html"
            html_path.write_text(page.content(), encoding="utf-8")
            diagnostic["html_artifact"] = str(html_path)
            if hasattr(page, "screenshot"):
                screenshot_path = output_dir / f"seek-page-{stamp}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                diagnostic["screenshot_artifact"] = str(screenshot_path)
        except Exception as error:
            logger.warning("Unable to save page diagnostics: %s", error)

    def _close_browser_resources(self, browser, context):
        if context is not None:
            try:
                context.close()
            except Exception as error:
                logger.warning("Unable to close browser context: %s", error)
        if browser is not None:
            try:
                browser.close()
            except Exception as error:
                logger.warning("Unable to close browser: %s", error)

    def _scrape_with_playwright(self, playwright, seek_url):
        browser = None
        context = None
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=self.user_agent)
            page = context.new_page()
        except Exception:
            self._close_browser_resources(browser, context)
            raise
        try:
            navigation_error = None
            last_diagnostic = None
            for attempt in range(1, self.max_navigation_attempts + 1):
                try:
                    logger.info(
                        "Loading page (attempt %s/%s)...",
                        attempt,
                        self.max_navigation_attempts,
                    )
                    response = page.goto(
                        seek_url,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    self._wait_for_page_readiness(page)
                    response_status = response.status if response else None
                    jobs = self._parse_jobs_from_page(
                        page, response_status=response_status
                    )
                    diagnostic = self.last_page_diagnostic or {
                        "classification": "indeterminate"
                    }
                    last_diagnostic = diagnostic
                    classification = diagnostic.get("classification", "indeterminate")
                    if classification not in {"indeterminate", "selector_mismatch"}:
                        self._capture_page_artifacts(page, diagnostic)
                        return ScrapeResult(jobs, classification, diagnostic)
                    navigation_error = RuntimeError(
                        f"page readiness unresolved ({classification})"
                    )
                except Exception as error:
                    navigation_error = error
                    last_diagnostic = None
                    logger.warning(
                        "Page attempt %s/%s failed: %s",
                        attempt,
                        self.max_navigation_attempts,
                        error,
                    )
            if last_diagnostic is not None:
                self._capture_page_artifacts(page, last_diagnostic)
                return ScrapeResult(
                    [], last_diagnostic.get("classification", "indeterminate"),
                    last_diagnostic,
                )
            diagnostic = self._record_page_diagnostic(
                page, navigation_error=navigation_error
            )
            return ScrapeResult([], "navigation_error", diagnostic)
        finally:
            self._close_browser_resources(browser, context)

    def scrape_jobs(self, seek_url):
        self.last_page_diagnostic = None
        result = None
        try:
            try:
                with self.playwright_factory() as playwright:
                    try:
                        result = self._scrape_with_playwright(playwright, seek_url)
                    except Exception as error:
                        self._record_page_diagnostic(None, navigation_error=error)
                        logger.error("Error during scraping: %s", error)
                        result = ScrapeResult(
                            [], "navigation_error", self.last_page_diagnostic or {
                                "classification": "navigation_error"
                            }
                        )
            except Exception as error:
                if result is not None:
                    logger.warning("Unable to close Playwright manager: %s", error)
                    return result
                raise
            return result
        except Exception as error:
            self._record_page_diagnostic(None, navigation_error=error)
            logger.error("Error during scraping: %s", error)
            return ScrapeResult(
                [], "navigation_error", self.last_page_diagnostic or {
                    "classification": "navigation_error"
                }
            )
