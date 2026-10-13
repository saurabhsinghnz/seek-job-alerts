import unittest
from unittest.mock import Mock, patch

from seek_job_alert import SeekJobScraper, load_runtime_config, main


class RuntimeConfigurationTests(unittest.TestCase):
    def test_load_runtime_config_reads_required_values_and_interval(self):
        with patch.dict(
            "os.environ",
            {
                "SEEK_TELEGRAM_TOKEN": "token",
                "SEEK_CHAT_ID": "chat-id",
                "SEEK_CHECK_INTERVAL": "15",
            },
            clear=True,
        ):
            self.assertEqual(
                load_runtime_config(),
                {
                    "telegram_token": "token",
                    "chat_id": "chat-id",
                    "check_interval": 15,
                },
            )

    def test_load_runtime_config_defaults_interval_to_ten_minutes(self):
        with patch.dict(
            "os.environ",
            {
                "SEEK_TELEGRAM_TOKEN": "token",
                "SEEK_CHAT_ID": "chat-id",
            },
            clear=True,
        ):
            self.assertEqual(load_runtime_config()["check_interval"], 10)

    def test_load_runtime_config_rejects_missing_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing required environment variables"):
                load_runtime_config()

    def test_load_runtime_config_rejects_invalid_interval(self):
        with patch.dict(
            "os.environ",
            {
                "SEEK_TELEGRAM_TOKEN": "token",
                "SEEK_CHAT_ID": "chat-id",
                "SEEK_CHECK_INTERVAL": "not-an-integer",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                load_runtime_config()


class RuntimeLifecycleTests(unittest.TestCase):
    def test_scheduler_registers_interval_job_and_starts(self):
        scraper = object.__new__(SeekJobScraper)
        scheduler = Mock()

        with patch("seek_job_alert.BackgroundScheduler", return_value=scheduler):
            result = scraper.start_scheduler(check_interval_minutes=15)

        self.assertIs(result, scheduler)
        scheduler.add_job.assert_called_once_with(
            scraper.check_and_notify,
            "interval",
            minutes=15,
            id="job_check",
            name="Check for new Seek jobs",
        )
        scheduler.start.assert_called_once_with()

    def test_main_shuts_down_scheduler_after_keyboard_interrupt(self):
        scraper = Mock()
        scheduler = Mock()
        scraper.start_scheduler.return_value = scheduler
        scraper.check_and_notify.side_effect = KeyboardInterrupt

        with patch("seek_job_alert.load_runtime_config", return_value={
            "telegram_token": "token",
            "chat_id": "chat-id",
            "check_interval": 10,
        }), patch("seek_job_alert.SeekJobScraper", return_value=scraper), patch(
            "seek_job_alert.time.sleep"
        ) as sleep:
            main()

        scraper.start_scheduler.assert_called_once_with(check_interval_minutes=10)
        scraper.check_and_notify.assert_called_once_with()
        scheduler.shutdown.assert_called_once_with()
        sleep.assert_not_called()

    def test_main_shuts_down_scheduler_after_initial_check_exception(self):
        scraper = Mock()
        scheduler = Mock()
        scraper.start_scheduler.return_value = scheduler
        scraper.check_and_notify.side_effect = RuntimeError("initial check failed")

        with patch("seek_job_alert.load_runtime_config", return_value={
            "telegram_token": "token",
            "chat_id": "chat-id",
            "check_interval": 10,
        }), patch("seek_job_alert.SeekJobScraper", return_value=scraper):
            with self.assertRaisesRegex(RuntimeError, "initial check failed"):
                main()

        scheduler.shutdown.assert_called_once_with()

    def test_main_shuts_down_scheduler_after_loop_exception(self):
        scraper = Mock()
        scheduler = Mock()
        scraper.start_scheduler.return_value = scheduler

        with patch("seek_job_alert.load_runtime_config", return_value={
            "telegram_token": "token",
            "chat_id": "chat-id",
            "check_interval": 10,
        }), patch("seek_job_alert.SeekJobScraper", return_value=scraper), patch(
            "seek_job_alert.time.sleep",
            side_effect=RuntimeError("loop failed"),
        ) as sleep:
            with self.assertRaisesRegex(RuntimeError, "loop failed"):
                main()

        scraper.check_and_notify.assert_called_once_with()
        sleep.assert_called_once_with(1)
        scheduler.shutdown.assert_called_once_with()

    def test_main_runs_initial_check_and_scheduler_loop(self):
        scraper = Mock()
        scheduler = Mock()
        scraper.start_scheduler.return_value = scheduler

        with patch("seek_job_alert.load_runtime_config", return_value={
            "telegram_token": "token",
            "chat_id": "chat-id",
            "check_interval": 10,
        }), patch("seek_job_alert.SeekJobScraper", return_value=scraper), patch(
            "seek_job_alert.time.sleep",
            side_effect=[None, KeyboardInterrupt],
        ) as sleep:
            main()

        scraper.start_scheduler.assert_called_once_with(check_interval_minutes=10)
        scraper.check_and_notify.assert_called_once_with()
        self.assertEqual(sleep.call_args_list, [((1,), {}), ((1,), {})])
        scheduler.shutdown.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()