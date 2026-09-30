# Personal Job Alert — v1

A small, dependency-free Python service that checks configured career feeds, remembers jobs in SQLite, applies transparent rules, and sends only new matches to Telegram. It uses no LLM or paid API.

## What it supports

- Greenhouse public job-board API
- Lever public postings API
- Amazon Jobs public India search response (the site does not publish a stable API contract)
- Generic HTML pages that expose standard `schema.org/JobPosting` JSON-LD
- Local JSON sample data for offline testing
- Configurable title, keyword, skill, location, exclusion, and 1–5 YOE rules
- SQLite deduplication, request retries/timeouts, logging, and per-source failure isolation
- CLI commands: `run-once`, `test-source`, `baseline-source`, and `init-db`

Prefer Greenhouse, Lever, another documented public feed, or a company's own job alerts. The generic adapter reads structured metadata only; it does not bypass logins, CAPTCHAs, robots controls, or anti-bot systems. Review each site's terms and robots policy before adding it.

## Quick start

Python 3.9+ is required. No third-party packages are needed.

```bash
cp config.example.toml config.toml
cp .env.example .env
python -m job_alert --config config.toml init-db
python -m job_alert --config config.toml test-source
python -m job_alert --config config.toml run-once --dry-run
```

The included source is a local sample. Its dry run should fetch two jobs and match one. Remove or disable it when adding real sources. A normal (non-dry) run writes `data/jobs.db`; later runs will not alert for the same source/job ID again.

Optionally install the command in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
job-alert --config config.toml run-once --dry-run
```

## Telegram setup

1. Message `@BotFather` in Telegram, run `/newbot`, and save the token.
2. Start a chat with the new bot and send it a message.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates`; find your message's `chat.id`.
4. Put both values in `.env` locally. Never commit that file:

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace_me
TELEGRAM_CHAT_ID=123456789
```

If Telegram is enabled but secrets are absent, jobs are still stored and matches are logged; their alerts remain pending and will be retried after secrets are configured. Use `--dry-run` while tuning rules; it neither creates/changes the database nor sends alerts.

## Configuration and sources

Copy `config.example.toml` to `config.toml` and edit the `[matching]` lists. `exclude_title_keywords` rejects role titles such as Intern or Manager; `exclude_keywords` rejects text anywhere in the title or description. This distinction matters because Amazon SDE descriptions commonly require "non-internship experience". Matching then checks target titles, known locations, and explicit experience ranges before scoring title/keyword/skill/location evidence. `minimum_score` controls strictness. Unknown experience is allowed because many job descriptions omit it.

Greenhouse URLs often resemble `https://boards.greenhouse.io/acme`; `acme` is the board token:

```toml
[[sources]]
name = "Acme"
type = "greenhouse"
board_token = "acme"
company = "Acme"
enabled = true
```

Lever URLs often resemble `https://jobs.lever.co/acme`; `acme` is the site name:

```toml
[[sources]]
name = "Acme"
type = "lever"
site = "acme"
company = "Acme"
enabled = true
```

For a public page containing `JobPosting` JSON-LD:

```toml
[[sources]]
name = "Acme careers"
type = "generic_html"
url = "https://acme.example/careers"
company = "Acme"
enabled = true
```

For Amazon Jobs in India, use its public search response. The adapter filters `country_code = IND`, follows result pages, extracts the full JD, and deduplicates results across queries. Search terms and page limits are configurable:

```toml
[[sources]]
name = "Amazon Jobs"
type = "amazon"
search_queries = ["software development engineer ii", "backend engineer"]
page_size = 50
max_pages = 10
enabled = true
```

Check the source before saving anything:

```bash
python3 -m job_alert --config config.toml test-source "Amazon Jobs"
```

To save today's Amazon jobs without sending Telegram alerts, run this **once** before the next normal run:

```bash
python3 -m job_alert --config config.toml baseline-source "Amazon Jobs"
```

The baseline is stored in the configured SQLite database. Future `run-once` calls alert only on newly discovered matching Amazon jobs. If you run on another computer or GitHub Actions, that environment needs its own persistent database and baseline. Amazon's search response is public but undocumented, so an upstream format change may require updating this adapter.

Test without touching SQLite:

```bash
python -m job_alert --config config.toml test-source "Acme"
```

## Adding a new adapter

Create a `SourceAdapter` subclass in `job_alert/adapters/` whose `fetch()` returns `list[Job]`, then register its type in `job_alert/adapters/__init__.py`. Keep source-specific parsing there; matching, storage, and notifications should remain unchanged. Add a mapping test with a fake HTTP response.

## Run twice daily for free with GitHub Actions

1. Push the repository to a private GitHub repository.
2. Commit a real `config.toml` (it contains no secrets).
3. In **Settings → Secrets and variables → Actions**, add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. Open **Actions → Job alerts → Run workflow** on the default branch to initialize and test it. Ensure Actions is enabled and repository policies permit this workflow's `contents: write` permission.

For 09:00 and 20:00 IST, use `30 3 * * *` and `30 14 * * *` in GitHub's UTC cron schedule. GitHub scheduled runs can be delayed during busy periods.

The included `.github/workflows/job-alerts.yml` runs twice daily and supports manual **Run workflow**. Edit its two cron entries to change the times. Only the default branch's scheduled workflow runs. This version does **not** listen for Telegram commands: sending “give me new update” will not trigger it. Use manual **Run workflow** for an extra check without hosting a listener.

Job history is stored on a separate `job-alert-state` branch (not an expiring Actions cache). Runs are serialized to prevent conflicting updates. The first successful run baselines all enabled sources, sends a Telegram initialization confirmation, and does not flood you with existing jobs. Later runs send new matching jobs and a completion summary even when there are no new matches. Partial source failures are reported, and history is saved even if fetching or notification fails. Do not delete the state branch; losing it resets the baseline. The local database is left unchanged and is not uploaded. In a public repository the state branch and its public job data are also public; keep the repository private if desired.

No extra hosting, paid APIs, artifacts, or cache storage are required. Standard Linux Actions runners are free for public repositories; GitHub Free includes 2,000 monthly Actions minutes for private repositories, shared with your other workflows. A 15-minute cap per run limits normal twice-daily use to at most 930 runner minutes in a 31-day month (plus manual runs). For a strict zero-cost setup, keep paid overages disabled/set an enforced spending budget and monitor total account usage in GitHub Billing. GitHub can pause execution when the free allowance is exhausted. Never commit `.env`; use the two repository secrets above.

## Local scheduling alternative

On an always-on machine, cron is more deterministic. For 09:00 and 20:00 in the machine's local timezone:

```cron
0 9,20 * * * cd /absolute/path/to/project && /usr/bin/python3 -m job_alert --config config.toml run-once
```

## Tests

```bash
python -m unittest discover -s tests -v
```

The current tests cover rule matching and exclusions, experience parsing, adapter mappings, and SQLite deduplication.
