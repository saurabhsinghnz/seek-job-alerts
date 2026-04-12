#!/usr/bin/env python3
"""
Seek.com.au Job Alert Bot
Monitors Seek for TypeScript IT jobs and sends Telegram notifications
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from playwright.sync_api import sync_playwright
import re

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

# Configuration
SEEK_URL = "https://www.seek.com.au/typescript-jobs-in-information-communication-technology/full-time/remote?salaryrange=150000-&salarytype=annual&sortmode=ListedDate"
SEEN_JOBS_FILE = "seen_jobs.json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

class SeekJobScraper:
    """Handles scraping jobs from Seek.com.au using Playwright"""
    
    def __init__(self, telegram_token: str, chat_id: str):
        self.telegram_token = telegram_token
        self.chat_id = chat_id
        self.telegram_api_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        self.seen_jobs = self._load_seen_jobs()
    
    def _load_seen_jobs(self) -> set:
        """Load previously seen job IDs from JSON file"""
        if Path(SEEN_JOBS_FILE).exists():
            try:
                with open(SEEN_JOBS_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data.get('seen_job_ids', []))
            except Exception as e:
                logger.error(f"Error loading seen jobs: {e}")
                return set()
        return set()
    
    def _save_seen_jobs(self):
        """Save seen job IDs to JSON file"""
        try:
            with open(SEEN_JOBS_FILE, 'w') as f:
                json.dump({'seen_job_ids': list(self.seen_jobs)}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving seen jobs: {e}")
    
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
    
    def _parse_jobs_from_page(self, page) -> list:
        """Parse job listings from the rendered page"""
        jobs = []
        
        try:
            # Wait for job listings to load
            page.wait_for_selector('[data-job-id]', timeout=10000)
            logger.info("Found job listings on page")
        except Exception as e:
            logger.warning(f"Timeout waiting for job listings: {e}")
        
        try:
            # Extract all job elements with data attributes
            job_locator = page.locator('[data-job-id]')
            job_count = job_locator.count()
            logger.info(f"Found {job_count} job elements")
            logger.info(f"Starting to parse {min(job_count, 50)} jobs...")
            
            # Extract all job data at once using JavaScript for efficiency
            jobs_data = page.evaluate("""
                () => {
                    const jobElements = document.querySelectorAll('[data-job-id]');
                    const jobs = [];
                    jobElements.forEach((el, idx) => {
                        if (idx >= 50) return;  // Limit to 50
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
            """)
            
            logger.info(f"Extracted {len(jobs_data)} jobs via JavaScript")
            
            # Convert to our job format
            for job_data in jobs_data:
                if job_data['title'] and job_data['title'] != 'N/A' and job_data['id']:
                    jobs.append({
                        'id': job_data['id'],
                        'title': job_data['title'],
                        'company': job_data['company'],
                        'salary': job_data['salary'],
                        'location': job_data['location'],
                        'posted_date': job_data['date'],
                        'link': job_data['link']
                    })
            
            logger.info(f"Successfully parsed {len(jobs)} jobs")
            
        except Exception as e:
            logger.error(f"Error parsing jobs from page: {e}")
            import traceback
            traceback.print_exc()
        
        return jobs
    
    def scrape_jobs(self) -> list:
        """Scrape jobs from Seek.com.au using Playwright"""
        try:
            logger.info("Launching browser and fetching jobs...")
            
            with sync_playwright() as p:
                # Launch browser in headless mode
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                
                try:
                    # Load the seek page
                    logger.info(f"Loading page...")
                    page.goto(SEEK_URL, wait_until='domcontentloaded', timeout=30000)
                    
                    # Wait a bit for content to load (but not indefinitely)
                    import time
                    time.sleep(3)
                    
                    # Parse jobs from the page
                    jobs = self._parse_jobs_from_page(page)
                    
                    return jobs
                    
                finally:
                    context.close()
                    browser.close()
                    
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _format_telegram_message(self, job: dict) -> str:
        """Format job details for Telegram message"""
        message = (
            f"🔔 *New TypeScript Job Alert!*\n\n"
            f"📌 *{job['title']}*\n"
            f"🏢 Company: {job['company']}\n"
            f"💰 Salary: {job['salary']}\n"
            f"📍 Location: {job['location']}\n"
            f"📅 Posted: {job['posted_date']}\n\n"
            f"🔗 [View Job]({job['link']})"
        )
        return message
    
    def send_telegram_notification(self, job: dict):
        """Send job notification via Telegram using HTTP API"""
        try:
            message = self._format_telegram_message(job)
            
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(self.telegram_api_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✓ Telegram notification sent for job: {job['title']}")
            else:
                logger.error(f"✗ Telegram API error ({response.status_code}): {response.text}")
                
        except Exception as e:
            logger.error(f"✗ Error sending Telegram notification: {e}")
    
    def check_and_notify(self):
        """Main job checking and notification routine"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Job check started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        jobs = self.scrape_jobs()
        new_jobs = []
        
        for job in jobs:
            if job['id'] not in self.seen_jobs:
                new_jobs.append(job)
                self.seen_jobs.add(job['id'])
        
        if new_jobs:
            logger.info(f"Found {len(new_jobs)} new job(s)")
            for job in new_jobs:
                self.send_telegram_notification(job)
        else:
            logger.info("No new jobs found")
        
        self._save_seen_jobs()
        logger.info(f"Job check completed. Total seen jobs: {len(self.seen_jobs)}")
    
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
    # Get configuration from environment variables
    telegram_token = os.getenv('SEEK_TELEGRAM_TOKEN')
    chat_id = os.getenv('SEEK_CHAT_ID')
    check_interval = int(os.getenv('SEEK_CHECK_INTERVAL', '10'))
    
    if not telegram_token or not chat_id:
        logger.error("Error: SEEK_TELEGRAM_TOKEN and SEEK_CHAT_ID environment variables are required")
        raise ValueError("Missing required environment variables")
    
    # Initialize scraper and start scheduler
    scraper = SeekJobScraper(telegram_token, chat_id)
    scheduler = scraper.start_scheduler(check_interval_minutes=check_interval)
    
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
        scheduler.shutdown()
        logger.info("Job alert bot stopped")


if __name__ == '__main__':
    main()
