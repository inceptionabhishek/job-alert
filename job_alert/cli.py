from __future__ import annotations

import argparse
import logging
import sys

from .adapters import create_adapter
from .config import load_config
from .http import HttpClient
from .runner import run
from .storage import JobStore


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="job-alert", description="Personal job alert system")
    root.add_argument("--config", default="config.toml", help="TOML config path (default: config.toml)")
    commands = root.add_subparsers(dest="command", required=True)
    once = commands.add_parser("run-once", help="Fetch, match, persist, and alert")
    once.add_argument("--dry-run", action="store_true", help="Do not persist or send Telegram alerts")
    test = commands.add_parser("test-source", help="Fetch one source without persisting")
    test.add_argument("source", nargs="?", help="Source name; omit to test every enabled source")
    test.add_argument("--limit", type=int, default=5)
    baseline = commands.add_parser("baseline-source", help="Save one source's current jobs without sending alerts")
    baseline.add_argument("source", help="Enabled source name")
    commands.add_parser("init-db", help="Create the SQLite database schema")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "init-db":
        JobStore(settings.database_path).initialize()
        print(f"Initialized database: {settings.database_path}")
        return 0
    if args.command == "test-source":
        selected = [source for source in settings.sources if not args.source or source.get("name") == args.source]
        if not selected:
            print(f"No enabled source named {args.source!r}", file=sys.stderr)
            return 2
        client = HttpClient(settings.http)
        failures = 0
        for source in selected:
            configured = dict(source)
            configured["_config_dir"] = str(settings.config_path.parent)
            try:
                jobs = create_adapter(configured, client).fetch()
                print(f"{source.get('name', source.get('type'))}: {len(jobs)} jobs")
                for job in jobs[: args.limit]:
                    print(f"  - {job.title} | {job.location or 'unknown location'} | {job.url}")
            except Exception as exc:
                failures += 1
                logging.exception("Source failed: %s", source.get("name", source.get("type")))
        return 1 if failures else 0
    if args.command == "baseline-source" and not any(source.get("name") == args.source for source in settings.sources):
        print(f"No enabled source named {args.source!r}", file=sys.stderr)
        return 2
    summary = (run(settings, only_source=args.source, baseline=True)
               if args.command == "baseline-source" else run(settings, dry_run=args.dry_run))
    print(
        f"Run complete: fetched={summary.fetched} new={summary.new} "
        f"matched={summary.matched} alerted={summary.alerted} "
        f"baselined={summary.baselined} errors={summary.errors}"
    )
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
