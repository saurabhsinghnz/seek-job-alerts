import json
import logging
from pathlib import Path


logger = logging.getLogger("seek_job_alert")


class SearchConfig:
    """Loads and normalizes Seek search configuration."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> list:
        if self.path.exists():
            try:
                with self.path.open('r') as config_file:
                    config = json.load(config_file)
                    searches = config.get('searches', [])
                    if searches:
                        for search in searches:
                            url = search.get('url', '')
                            if url and 'sortmode=' not in url:
                                search['url'] = url.rstrip('&') + '&sortmode=ListedDate'

                        logger.info(f"Loaded {len(searches)} search configuration(s)")
                        return searches
            except Exception as error:
                logger.error(f"Error loading search config: {error}")

        logger.warning(f"No search configurations found in {self.path}")
        return []