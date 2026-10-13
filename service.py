import logging
from datetime import datetime


logger = logging.getLogger("seek_job_alert")


class JobAlertService:
    """Orchestrates searches, notifications, and seen-job persistence."""

    def __init__(
        self,
        *,
        searches,
        seen_jobs,
        scrape_jobs,
        notify,
        cleanup_seen_jobs,
        save_seen_jobs,
        now=datetime.now,
        get_seen_jobs=None,
    ):
        self.searches = searches
        self.seen_jobs = seen_jobs
        self.get_seen_jobs = get_seen_jobs or (lambda: self.seen_jobs)
        self.scrape_jobs = scrape_jobs
        self.notify = notify
        self.cleanup_seen_jobs = cleanup_seen_jobs
        self.save_seen_jobs = save_seen_jobs
        self.now = now

    def check_and_notify(self):
        logger.info(f"\n{'='*60}")
        logger.info(f"Job check started at {self.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        if not self.searches:
            logger.error("No search URLs configured. Please add searches to search_config.json")
            return

        total_new_jobs = 0

        for search in self.searches:
            search_name = search.get('name', 'Unknown')
            search_url = search.get('url', '')

            if not search_url:
                logger.warning(f"Skipping search '{search_name}' - no URL provided")
                continue

            logger.info(f"\n--- Checking search: {search_name} ---")

            result = self.scrape_jobs(search_url)
            if result.classification not in {'valid_listings', 'empty_results'}:
                logger.warning(
                    "No jobs processed for '%s'; page classification is %s",
                    search_name,
                    result.classification,
                )
                continue

            jobs = result.jobs
            new_jobs = []
            already_scanned_count = 0
            seen_jobs = self.get_seen_jobs()
            self.seen_jobs = seen_jobs

            for job in jobs:
                if job['id'] not in seen_jobs:
                    new_jobs.append(job)
                    seen_jobs[job['id']] = self.now().isoformat()
                else:
                    already_scanned_count = len(jobs) - len(new_jobs) - 1
                    logger.info(
                        f"Encountered already-scanned job. Stopping scan "
                        f"(skipped {already_scanned_count} older jobs)"
                    )
                    break

            if new_jobs:
                logger.info(f"Found {len(new_jobs)} new job(s) in '{search_name}'")
                total_new_jobs += len(new_jobs)
                for job in new_jobs:
                    self.notify(job)
            elif result.classification == 'empty_results':
                logger.info(f"No new jobs found in '{search_name}'")
            else:
                logger.warning(
                    "No jobs processed for '%s'; page classification is %s",
                    search_name,
                    result.classification,
                )

            self.cleanup_seen_jobs()
            self.seen_jobs = self.get_seen_jobs()
            self.save_seen_jobs()

        logger.info(f"\n{'='*60}")
        logger.info(
            f"Job check completed. {total_new_jobs} new job(s) total. "
            f"Total seen jobs: {len(self.seen_jobs)}"
        )
        logger.info(f"{'='*60}")