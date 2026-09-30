from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from job_alert.config import Settings
from job_alert.http import redact
from job_alert.scheduled import scheduled_run


class ScheduledTests(unittest.TestCase):
    def settings(self, root):
        return Settings(
            raw={"telegram": {"enabled": True}, "matching": {}},
            config_path=root / "config.toml", database_path=root / "data/jobs.db",
            log_level="INFO", dry_run=False, telegram_token="fake-token",
            telegram_chat_id="fake-chat", sources=[{
                "name": "Sample", "type": "sample",
                "path": str(Path(__file__).resolve().parents[1] / "examples/sample_jobs.json"),
            }],
        )

    def test_baseline_and_restore_do_not_resend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.settings(root)
            state = root / "state"
            with patch("job_alert.scheduled.TelegramNotifier") as status, patch("job_alert.runner.TelegramNotifier") as alerts:
                self.assertEqual(scheduled_run(settings, state), 0)
                self.assertTrue((state / "jobs.db").exists())
                self.assertTrue((state / "initialized").exists())
                settings.database_path = root / "fresh-runner/jobs.db"
                self.assertEqual(scheduled_run(settings, state), 0)
                alerts.return_value.send.assert_not_called()
                self.assertIn("0 new matching", status.return_value.send_text.call_args.args[0])

    def test_missing_secrets_do_not_create_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.settings(root)
            settings.telegram_token = None
            with self.assertRaises(ValueError):
                scheduled_run(settings, root / "state")
            self.assertFalse(settings.database_path.exists())

    def test_missing_initialized_database_is_not_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            state.mkdir()
            (state / "initialized").touch()
            with self.assertRaises(ValueError):
                scheduled_run(self.settings(root), state)

    def test_tokens_are_redacted(self):
        self.assertNotIn("secret-token", redact("https://api.telegram.org/botsecret-token/sendMessage"))
