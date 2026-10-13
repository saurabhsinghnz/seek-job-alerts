import json
import logging
from datetime import datetime, timedelta
from pathlib import Path


logger = logging.getLogger("seek_job_alert")


class SeenJobState:
    """Loads, persists, and cleans up seen-job timestamps."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> dict:
        if self.path.exists():
            try:
                with self.path.open('r') as state_file:
                    data = json.load(state_file)

                    if 'seen_jobs' in data and isinstance(data['seen_jobs'], dict):
                        return data['seen_jobs']

                    if 'seen_job_ids' in data and isinstance(data['seen_job_ids'], list):
                        logger.info("Migrating seen_jobs from list to dict format with timestamps")
                        return {
                            job_id: datetime.now().isoformat()
                            for job_id in data['seen_job_ids']
                        }
            except Exception as error:
                logger.error(f"Error loading seen jobs: {error}")

        return {}

    def save(self, seen_jobs: dict):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('w') as state_file:
                json.dump({'seen_jobs': seen_jobs}, state_file, indent=2)
        except Exception as error:
            logger.error(f"Error saving seen jobs: {error}")

    def cleanup(self, seen_jobs: dict, retention_days: int = 90) -> dict:
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        cleaned = {}
        for job_id, timestamp in seen_jobs.items():
            try:
                if datetime.fromisoformat(timestamp) > cutoff_date:
                    cleaned[job_id] = timestamp
            except (TypeError, ValueError) as error:
                logger.warning(f"Skipping cleanup for job {job_id} with invalid timestamp: {error}")
                cleaned[job_id] = timestamp
        return cleaned