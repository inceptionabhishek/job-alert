from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from job_alert.config import Settings
from job_alert.digest import build_parts, send_digest, utf16_length
from job_alert.models import Job
from job_alert.ranking import rank_job
from job_alert.report import report_rows
from job_alert.runner import run
from job_alert.storage import JobStore
from job_alert.scheduled import scheduled_run


RANKING = {"preferred_title_keywords": ["backend"], "skills": ["python", "aws", "java", "go", "kubernetes"],
           "topics": ["api", "microservices", "distributed systems", "systems"]}
MATCHING = {"title_keywords": ["software engineer", "backend engineer"], "minimum_score": 3,
            "max_years_exclusive": 3, "allow_unknown_experience": False}


def job(identifier, **changes):
    fields = dict(source="Sample", external_id=str(identifier), title="Backend Engineer", company="Example",
                  location="London", url=f"https://example.test/{identifier}",
                  description="Python AWS Java Go Kubernetes. API microservices distributed systems. 2+ years.")
    fields.update(changes)
    return Job(**fields)


def settings(root):
    return Settings(raw={"matching": MATCHING, "ranking": RANKING, "digest": {"enabled": True}},
                    config_path=root / "config.toml", database_path=root / "jobs.db", log_level="INFO",
                    dry_run=False, telegram_token="fake", telegram_chat_id="fake", sources=[{"name": "Sample", "type": "sample"}])


class RankingTests(unittest.TestCase):
    def test_points_and_caps(self):
        rank = rank_job(job(1), RANKING)
        self.assertEqual(rank.score, 10)
        self.assertEqual(len(rank.reasons), 8)
        self.assertIn("title: backend (+3)", rank.reasons)

    def test_keywords_are_not_substrings(self):
        rank = rank_job(job(1, title="Software Engineer", description="Ongoing JavaScript"), RANKING)
        self.assertEqual(rank.score, 0)

    def test_empty_preferences_have_zero_points(self):
        self.assertEqual(rank_job(job(1), {}).score, 0)


class DigestTests(unittest.TestCase):
    def setUp(self):
        pacing = patch("job_alert.digest.time.sleep")
        pacing.start()
        self.addCleanup(pacing.stop)

    def make_store(self, root):
        store = JobStore(root / "jobs.db")
        store.initialize()
        return store

    def test_migration_does_not_requeue_baselines_or_delivered(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            store.record(job(1), True, baseline=True)
            store.record(job(2), True)
            store.mark_alerted(job(2))
            store.record(job(3), True)
            store.record(job(4), False)
            store.initialize()
            self.assertEqual(store.enqueue_pending(), 1)
            self.assertEqual(store.enqueue_pending(), 0)
            self.assertEqual([row["external_id"] for row in store.queued_jobs()], ["3"])

    def test_morning_collects_and_evening_delivers_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            with patch("job_alert.runner.create_adapter") as adapter, patch("job_alert.runner.TelegramNotifier") as individual:
                adapter.return_value.fetch.return_value = [job(1)]
                first = run(s)
                second = run(s)
            self.assertEqual((first.queued, first.alerted, second.queued), (1, 0, 0))
            individual.assert_not_called()
            store = JobStore(s.database_path)
            notifier = Mock()
            self.assertEqual(send_digest(s, store, notifier), 1)
            self.assertFalse(store.needs_alert(job(1)))
            self.assertEqual(send_digest(s, store, notifier), 0)
            self.assertIn("No new matching jobs", notifier.send_text.call_args.args[0])

    def test_rank_cannot_override_failed_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            store = self.make_store(root)
            store.record(job(1, description="Python AWS Go. 5+ years."), True)
            store.enqueue_pending()
            notifier = Mock()
            self.assertEqual(send_digest(s, store, notifier), 0)
            self.assertEqual(store.queued_jobs(), [])
            self.assertIn("No new matching jobs", notifier.send_text.call_args.args[0])

    def test_split_accounts_for_unicode_without_dropping_jobs(self):
        ranked = [(job(i, title="😀" * 400, company="😀" * 200, location="😀" * 200), rank_job(job(i), RANKING)) for i in range(40)]
        parts = build_parts(ranked, "2026-10-01", ["Example"])
        self.assertGreater(len(parts), 1)
        self.assertEqual(sum(len(keys) for _, keys in parts), 40)
        self.assertTrue(all(utf16_length(text) <= 4096 for text, _ in parts))
        self.assertIn("Results may be incomplete", parts[0][0])

    def test_partial_failure_resumes_only_unfinished_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            store = self.make_store(root)
            for i in range(40):
                store.record(job(i), True)
            store.enqueue_pending()
            notifier = Mock()
            notifier.send_text.side_effect = [None, RuntimeError("Telegram unavailable")]
            with self.assertRaises(RuntimeError):
                send_digest(s, store, notifier)
            delivered_text = notifier.send_text.call_args_list[0].args[0]
            retry = Mock()
            # Simulate a fresh process reopening persistent SQLite.
            reopened = JobStore(s.database_path)
            pending_before = reopened.pending_parts()
            delivered = send_digest(s, reopened, retry)
            self.assertEqual(retry.send_text.call_count, len(pending_before))
            self.assertNotIn(delivered_text, [call.args[0] for call in retry.send_text.call_args_list])
            self.assertGreater(delivered, 0)
            self.assertEqual(reopened.pending_parts(), [])
            with sqlite3.connect(s.database_path) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE alerted_at IS NOT NULL").fetchone()[0], 40)

    def test_zero_preference_job_is_included_after_high_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            store = self.make_store(root)
            store.record(job(1, title="Software Engineer", description="2+ years."), True)
            store.record(job(2), True)
            store.enqueue_pending()
            notifier = Mock()
            self.assertEqual(send_digest(s, store, notifier), 2)
            text = notifier.send_text.call_args.args[0]
            self.assertLess(text.index("Backend Engineer"), text.index("Software Engineer"))
            self.assertIn("0/10", text)

    def test_source_failure_in_empty_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.make_store(root)
            store.record_check(["CRED"])
            notifier = Mock()
            send_digest(settings(root), store, notifier)
            self.assertIn("CRED", notifier.send_text.call_args.args[0])
            self.assertIn("incomplete", notifier.send_text.call_args.args[0])

    def test_report_shows_rank_and_delivery_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.make_store(root)
            store.record(job(1), True)
            store.record(job(2, title="Software Engineer", description="2+ years."), True)
            store.enqueue_pending()
            rows = report_rows(root / "jobs.db", MATCHING, RANKING)
            self.assertEqual((rows[0]["rank"], rows[0]["preference_score"], rows[0]["status"]), (1, 10, "queued"))
            send_digest(settings(root), store, Mock())
            self.assertEqual(report_rows(root / "jobs.db", MATCHING, RANKING)[0]["status"], "delivered")

    def test_failed_digest_still_backs_up_retry_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            state = root / "state"
            state.mkdir()
            (state / "initialized").touch()
            JobStore(state / "jobs.db").initialize()
            with patch("job_alert.runner.create_adapter") as adapter, patch("job_alert.scheduled.TelegramNotifier") as notifier:
                adapter.return_value.fetch.return_value = [job(1)]
                notifier.return_value.send_text.side_effect = RuntimeError("Timeout")
                with self.assertRaises(RuntimeError):
                    scheduled_run(s, state, deliver_digest=True)
            saved = JobStore(state / "jobs.db")
            self.assertEqual(len(saved.pending_parts()), 1)
            self.assertTrue(saved.needs_alert(job(1)))

    def test_disabled_source_pending_job_is_not_delivered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            store = self.make_store(root)
            store.record(job(1, source="Disabled"), True)
            store.enqueue_pending()
            notifier = Mock()
            self.assertEqual(send_digest(s, store, notifier), 0)
            self.assertNotIn("Backend Engineer", notifier.send_text.call_args.args[0])

    def test_scheduled_manual_default_is_silent_then_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            s = settings(root)
            state = root / "state"
            state.mkdir()
            (state / "initialized").touch()
            JobStore(state / "jobs.db").initialize()
            with patch("job_alert.runner.create_adapter") as adapter, patch("job_alert.scheduled.TelegramNotifier") as notifier:
                adapter.return_value.fetch.return_value = [job(1)]
                self.assertEqual(scheduled_run(s, state), 0)
                notifier.return_value.send_text.assert_not_called()
                self.assertEqual(scheduled_run(s, state, deliver_digest=True), 0)
                self.assertEqual(notifier.return_value.send_text.call_count, 1)
                notifier.return_value.send_text.assert_called_with(unittest.mock.ANY)
