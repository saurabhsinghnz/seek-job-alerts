#!/usr/bin/env python3
"""
Seek.com.au Job Alert Bot
Monitors Seek for TypeScript IT jobs and sends Telegram notifications
"""

import logging
import os
import re
import time

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from playwright.sync_api import sync_playwright

from models import ScrapeResult
from notifications import format_telegram_message, send_telegram_notification
from scraper import BrowserScraper
from config import SearchConfig
from service import JobAlertService
from state import SeenJobState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_alert.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_runtime_config() -> dict:
    """Load and validate runtime settings from environment variables."""
    telegram_token = os.getenv('SEEK_TELEGRAM_TOKEN')
    chat_id = os.getenv('SEEK_CHAT_ID')

    if not telegram_token or not chat_id:
        logger.error("Error: SEEK_TELEGRAM_TOKEN and SEEK_CHAT_ID environment variables are required")
        raise ValueError("Missing required environment variables")

    return {
        "telegram_token": telegram_token,
        "chat_id": chat_id,
        "check_interval": int(os.getenv('SEEK_CHECK_INTERVAL', '10')),
    }


# Configuration
SEARCH_CONFIG_FILE = "search_config.json"
SEEN_JOBS_FILE = "seen_jobs.json"
JOB_RETENTION_DAYS = 90  # Remove job IDs older than this many days

class SeekJobScraper:
    """Handles scraping jobs from Seek.com.au using Playwright"""
    
    def __init__(self, telegram_token: str, chat_id: str):
        self.telegram_token = telegram_token
        self.chat_id = chat_id
        self.telegram_api_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        self.seen_jobs = self._load_seen_jobs()
        self.search_urls = self._load_search_urls()
        self.last_page_diagnostic = None
    
    def _load_search_urls(self) -> list:
        """Load search URLs from configuration file and ensure sort parameter is present"""
        return SearchConfig(SEARCH_CONFIG_FILE).load()
    
    def _load_seen_jobs(self) -> dict:
        """Load previously seen job IDs with timestamps from JSON file.
        Handles migration from old list format to new dict format."""
        return SeenJobState(SEEN_JOBS_FILE).load()
    
    def _save_seen_jobs(self):
        """Save seen job IDs with timestamps to JSON file"""
        SeenJobState(SEEN_JOBS_FILE).save(self.seen_jobs)
    
    def _cleanup_old_jobs(self, retention_days: int = JOB_RETENTION_DAYS):
        """Remove job IDs older than retention_days to keep the list manageable"""
        jobs_before = len(self.seen_jobs)
        self.seen_jobs = SeenJobState(SEEN_JOBS_FILE).cleanup(
            self.seen_jobs,
            retention_days=retention_days,
        )
        jobs_after = len(self.seen_jobs)
        if jobs_before > jobs_after:
            removed = jobs_before - jobs_after
            logger.info(f"🗑️  Cleaned up {removed} old job(s) ({retention_days}+ days). "
                        f"Retained {jobs_after} job(s).")
    
    def _extract_job_id(self, job_link: str) -> str:
        """Extract job ID from job link"""
        try:
            # Link format: /job/XXXXXXXXXX
            match = re.search(r'/job/(\d+)', job_link)
            if match:
                return match.group(1)
            return str(hash(job_link))
        except Exception:
            return str(hash(job_link))

    def _browser_scraper(self):
        scraper = BrowserScraper(playwright_factory=sync_playwright)
        scraper.last_page_diagnostic = getattr(self, 'last_page_diagnostic', None)
        return scraper

    def _delegate_browser_method(self, method_name, *args, **kwargs):
        scraper = self._browser_scraper()
        result = getattr(scraper, method_name)(*args, **kwargs)
        self.last_page_diagnostic = scraper.last_page_diagnostic
        return result

    def _record_page_diagnostic(self, page, response_status=None, navigation_error=None):
        return self._delegate_browser_method(
            '_record_page_diagnostic',
            page,
            response_status=response_status,
            navigation_error=navigation_error,
        )

    def _parse_jobs_from_html(self, html: str, base_url: str = '', response_status=None, title=None) -> list:
        return self._delegate_browser_method(
            '_parse_jobs_from_html',
            html,
            base_url=base_url,
            response_status=response_status,
            title=title,
        )

    def _prefer_stronger_diagnostic(self, browser_diagnostic, static_diagnostic):
        return self._delegate_browser_method(
            '_prefer_stronger_diagnostic', browser_diagnostic, static_diagnostic
        )

    def _parse_jobs_from_page(self, page, response_status=None) -> list:
        return self._delegate_browser_method(
            '_parse_jobs_from_page', page, response_status=response_status
        )

    def _wait_for_page_readiness(self, page):
        return self._delegate_browser_method('_wait_for_page_readiness', page)

    def _capture_page_artifacts(self, page, diagnostic):
        return self._delegate_browser_method(
            '_capture_page_artifacts', page, diagnostic
        )

    def scrape_jobs(self, seek_url: str) -> ScrapeResult:
        scraper = self._browser_scraper()
        result = scraper.scrape_jobs(seek_url)
        self.last_page_diagnostic = scraper.last_page_diagnostic
        return result
    
    def _format_telegram_message(self, job: dict) -> str:
        """Format job details for Telegram message"""
        return format_telegram_message(job)
    
    def send_telegram_notification(self, job: dict):
        """Send job notification via Telegram using HTTP API"""
        send_telegram_notification(
            job,
            chat_id=self.chat_id,
            telegram_api_url=self.telegram_api_url,
            request_post=requests.post,
        )
    
    def check_and_notify(self):
        """Main job checking and notification routine"""
        JobAlertService(
            searches=self.search_urls,
            seen_jobs=self.seen_jobs,
            get_seen_jobs=lambda: self.seen_jobs,
            scrape_jobs=self.scrape_jobs,
            notify=self.send_telegram_notification,
            cleanup_seen_jobs=self._cleanup_old_jobs,
            save_seen_jobs=self._save_seen_jobs,
        ).check_and_notify()
    
    def start_scheduler(self, check_interval_minutes: int = 10):
        """Start background scheduler for periodic job checks"""
        scheduler = BackgroundScheduler()
        
        # Schedule job checks every N minutes
        scheduler.add_job(
            self.check_and_notify,
            'interval',
            minutes=check_interval_minutes,
            id='job_check',
            name='Check for new Seek jobs'
        )
        
        scheduler.start()
        logger.info(f"Scheduler started. Checking for jobs every {check_interval_minutes} minutes")
        
        return scheduler


def main():
    """Main entry point"""
    runtime_config = load_runtime_config()
    
    # Initialize scraper and start scheduler
    scraper = SeekJobScraper(
        runtime_config["telegram_token"],
        runtime_config["chat_id"],
    )
    scheduler = scraper.start_scheduler(
        check_interval_minutes=runtime_config["check_interval"]
    )
    
    try:
        # Run the first check immediately, then wait for scheduled checks
        logger.info("Running initial job check...")
        scraper.check_and_notify()
        
        # Keep the scheduler running
        logger.info("Scheduler is running. Press Ctrl+C to exit.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down scheduler...")
    finally:
        scheduler.shutdown()
        logger.info("Job alert bot stopped")


if __name__ == '__main__':
    main()
