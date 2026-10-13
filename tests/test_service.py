import unittest
from datetime import datetime

from models import ScrapeResult
from service import JobAlertService


class ServiceOrchestrationTests(unittest.TestCase):
    def make_service(self, searches, scrape_results):
        seen_jobs = {"old": "2026-01-01T00:00:00"}
        events = []

        def scrape(url):
            events.append(("scrape", url))
            return scrape_results[url]

        service = JobAlertService(
            searches=searches,
            seen_jobs=seen_jobs,
            scrape_jobs=scrape,
            notify=lambda job: events.append(("notify", job["id"])),
            cleanup_seen_jobs=lambda: events.append(("cleanup",)),
            save_seen_jobs=lambda: events.append(("save",)),
            now=lambda: datetime(2026, 10, 13, 12, 0, 0),
        )
        return service, seen_jobs, events

    def test_multiple_searches_deduplicate_and_preserve_notification_order(self):
        searches = [
            {"name": "first", "url": "https://example.test/first"},
            {"name": "second", "url": "https://example.test/second"},
        ]
        scrape_results = {
            searches[0]["url"]: ScrapeResult([
                {"id": "new-1"},
                {"id": "new-2"},
            ], "valid_listings"),
            searches[1]["url"]: ScrapeResult([
                {"id": "new-3"},
                {"id": "new-2"},
            ], "valid_listings"),
        }

        service, seen_jobs, events = self.make_service(searches, scrape_results)
        service.check_and_notify()

        self.assertEqual(
            [event for event in events if event[0] == "notify"],
            [("notify", "new-1"), ("notify", "new-2"), ("notify", "new-3")],
        )
        self.assertEqual(seen_jobs["new-1"], "2026-10-13T12:00:00")
        self.assertEqual(seen_jobs["new-2"], "2026-10-13T12:00:00")
        self.assertEqual(seen_jobs["new-3"], "2026-10-13T12:00:00")
        self.assertEqual(events.count(("cleanup",)), 2)
        self.assertEqual(events.count(("save",)), 2)

    def test_first_seen_job_stops_scan_for_that_search(self):
        searches = [{"name": "search", "url": "https://example.test/search"}]
        scrape_results = {
            searches[0]["url"]: ScrapeResult([
                {"id": "new"},
                {"id": "old"},
                {"id": "not-reached"},
            ], "valid_listings"),
        }

        service, seen_jobs, events = self.make_service(searches, scrape_results)
        service.check_and_notify()

        self.assertEqual([event for event in events if event[0] == "notify"], [("notify", "new")])
        self.assertEqual(set(seen_jobs), {"old", "new"})

    def test_failed_search_isolated_from_valid_search_persistence(self):
        searches = [
            {"name": "failed", "url": "https://example.test/failed"},
            {"name": "valid", "url": "https://example.test/valid"},
        ]
        scrape_results = {
            searches[0]["url"]: ScrapeResult([{"id": "should-not-process"}], "navigation_error"),
            searches[1]["url"]: ScrapeResult([{"id": "new"}], "valid_listings"),
        }

        service, seen_jobs, events = self.make_service(searches, scrape_results)
        service.check_and_notify()

        self.assertEqual(set(seen_jobs), {"old", "new"})
        self.assertEqual(events.count(("cleanup",)), 1)
        self.assertEqual(events.count(("save",)), 1)

    def test_next_search_uses_seen_jobs_replaced_by_cleanup(self):
        searches = [
            {"name": "first", "url": "https://example.test/first"},
            {"name": "second", "url": "https://example.test/second"},
        ]
        scrape_results = {
            searches[0]["url"]: ScrapeResult([{"id": "first"}], "valid_listings"),
            searches[1]["url"]: ScrapeResult([{"id": "expired"}], "valid_listings"),
        }
        state = {"expired": "2026-01-01T00:00:00"}
        replacement_state = {"first": "2026-10-13T12:00:00"}
        notified_ids = []
        saved_states = []

        def cleanup():
            nonlocal state
            state = replacement_state

        service = JobAlertService(
            searches=searches,
            seen_jobs=state,
            get_seen_jobs=lambda: state,
            scrape_jobs=lambda url: scrape_results[url],
            notify=lambda job: notified_ids.append(job["id"]),
            cleanup_seen_jobs=cleanup,
            save_seen_jobs=lambda: saved_states.append(service.seen_jobs),
            now=lambda: datetime(2026, 10, 13, 12, 0, 0),
        )

        service.check_and_notify()

        self.assertEqual(notified_ids, ["first", "expired"])
        self.assertIs(saved_states[0], replacement_state)
        self.assertIs(service.seen_jobs, replacement_state)


if __name__ == "__main__":
    unittest.main()