from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from job_alert.config import Settings
from job_alert.runner import run


class RunnerTests(unittest.TestCase):
    def test_baseline_suppresses_existing_alerts_but_new_jobs_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample_path = root / "jobs.json"
            first_job = {
                "id": "existing", "title": "Backend Engineer", "company": "Example",
                "location": "Hyderabad, India", "url": "https://example.test/existing",
                "description": "Python APIs. 3+ years experience.",
            }
            sample_path.write_text(json.dumps([first_job]), encoding="utf-8")
            settings = Settings(
                raw={"telegram": {"enabled": True}, "matching": {
                    "title_keywords": ["backend engineer"], "skills": ["python"],
                    "locations": ["india"], "minimum_score": 4,
                }},
                config_path=root / "config.toml",
                database_path=root / "jobs.db",
                log_level="INFO",
                dry_run=False,
                telegram_token="test-token",
                telegram_chat_id="test-chat",
                sources=[{"name": "Amazon Jobs", "type": "sample", "path": str(sample_path)}],
            )
            with patch("job_alert.runner.TelegramNotifier") as notifier:
                baseline = run(settings, only_source="Amazon Jobs", baseline=True)
                self.assertEqual(baseline.baselined, 1)
                self.assertEqual(baseline.alerted, 0)
                notifier.assert_not_called()

                new_job = dict(first_job, id="new", url="https://example.test/new")
                sample_path.write_text(json.dumps([first_job, new_job]), encoding="utf-8")
                next_run = run(settings)
                self.assertEqual(next_run.new, 1)
                self.assertEqual(next_run.alerted, 1)
                notifier.return_value.send.assert_called_once()

    def test_second_run_deduplicates_jobs(self):
        sample_path = Path(__file__).resolve().parents[1] / "examples" / "sample_jobs.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(
                raw={
                    "telegram": {"enabled": False},
                    "matching": {
                        "title_keywords": ["software engineer ii"],
                        "include_keywords": ["backend"],
                        "exclude_keywords": ["intern"],
                        "skills": ["python"],
                        "locations": ["bangalore"],
                        "min_years": 1,
                        "max_years": 5,
                        "minimum_score": 4,
                        "require_title_keyword": True,
                    },
                },
                config_path=root / "config.toml",
                database_path=root / "jobs.db",
                log_level="INFO",
                dry_run=False,
                telegram_token=None,
                telegram_chat_id=None,
                sources=[{"name": "sample", "type": "sample", "path": str(sample_path)}],
            )
            first = run(settings)
            second = run(settings)
            self.assertEqual((first.fetched, first.new, first.matched), (2, 2, 1))
            self.assertEqual((second.fetched, second.new, second.matched), (2, 0, 0))


if __name__ == "__main__":
    unittest.main()
