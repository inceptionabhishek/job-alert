"""Scheduled entry point; state is a separate Git branch, never an expiring cache."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import shutil
import sqlite3

from .config import load_config, Settings
from .http import HttpClient
from .notifier import TelegramNotifier
from .runner import run


def scheduled_run(settings: Settings, state: Path) -> int:
    if not settings.telegram_enabled or not settings.telegram_token or not settings.telegram_chat_id:
        raise ValueError("Enable Telegram and configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets")
    if settings.dry_run or not settings.sources:
        raise ValueError("Scheduled runs require enabled sources and app.dry_run=false")
    state.mkdir(parents=True, exist_ok=True)
    saved_db = state / "jobs.db"
    marker = state / "initialized"
    notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id, HttpClient(settings.http))
    if marker.exists() and not saved_db.exists():
        raise ValueError("Persistent job history is missing; refusing to resend historical jobs")
    if saved_db.exists():
        with sqlite3.connect(str(saved_db)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Persistent SQLite history is corrupt")
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved_db, settings.database_path)
    try:
        if not marker.exists():
            errors = 0
            for source in settings.sources:
                if not source.get("name"):
                    raise ValueError("Each scheduled source needs a name")
                errors += run(settings, only_source=source["name"], baseline=True).errors
            if not errors:
                marker.write_text("Baseline complete\n", encoding="utf-8")
            notifier.send_text(
                "Job alerts initialized: current jobs saved without alerts. Future runs will send only new matches."
                if not errors else "Job alert initialization had source errors; it will retry on the next run."
            )
            return 1 if errors else 0
        summary = run(settings)
        notifier.send_text(
            f"Job check complete: {summary.fetched} jobs checked, "
            f"{summary.alerted} new matching job alerts sent, {summary.errors} errors."
        )
        return 1 if summary.errors else 0
    finally:
        if settings.database_path.exists():
            # SQLite backup also handles any journal/WAL changes safely.
            with sqlite3.connect(str(settings.database_path)) as source:
                with sqlite3.connect(str(saved_db)) as target:
                    source.backup(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return scheduled_run(load_config(args.config), Path(args.state_dir).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
