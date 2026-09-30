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

## Browse saved jobs (HTML + CSV)

After a workflow finishes, open **Actions → Job alerts → the latest run → Artifacts → job-report**. Download and unzip it, then open `jobs.html` in your browser. Keep `jobs.csv` next to it for the CSV download link. Reports are retained for 7 days and regenerated each run; the database history does not expire. These small artifacts use your GitHub storage allowance. This is an offline report, not a hosted or publicly published website. No external scripts or internet connection are needed to browse it.

Matching jobs are shown initially. Search covers the title, company, description and reasons; selectors filter matching/rejected jobs, source, location and alert status. Switch to **All jobs** to browse everything, including the initial baseline. Application links open the source website. Saved listings can have closed since their last check.

Generate a local report from your own database or a downloaded snapshot:

```bash
python -m job_alert --config config.toml export-report --output reports
python -m job_alert --config config.toml export-report --database /path/to/jobs.db --output reports
```

Reports re-evaluate every stored job against the **current** config and show the score and reasons. `saved_match` is the original persisted decision, while `current_match` reflects current rules. Exporting does not fetch sources, send notifications, change records or replay old alerts. CSV includes the full description, identifiers, first/last-seen timestamps, baseline and alert timestamps. CSV values that could act as spreadsheet formulas are prefixed with an apostrophe.

## CRED source

CRED is enabled through the existing Lever adapter (`site = "cred"`), using the public postings API linked to https://jobs.lever.co/cred. No API key or additional secret is required. On your already-initialized GitHub deployment, adding CRED does not reset the baseline or previous history: any currently available matching CRED jobs are sent once on the next run, then normal deduplication applies. Do not run `baseline-source CRED` if you want these existing matches. The September 30, 2026 feed test found eight published jobs and zero SDE2/backend matches; source availability does not guarantee matching openings. Full Lever qualification/responsibility sections are now included in the extracted JD.

## Tune matching

Start with rejected jobs and inspect their reasons. Edit `[matching]` in `config.toml`, export again, and compare current versus saved decisions. Commit/push the config so Actions uses it. History and previous alerts are preserved; report re-evaluation is for review, not an automatic backfill of old rejected jobs.

The September 2026 review of 164 saved jobs found false level-II matches for level-III titles, and missed Amazon `Engineer - II`/`Software Dev Engineer II` variants. Keywords now use word boundaries (so `go` no longer matches `ongoing`, or `java` matches `javascript`), and title separators are normalized. The live config adds the missing level-II title variants and restricts locations to India and listed Indian cities; unknown locations and foreign-only remote listings are excluded. Add other Indian city spellings as needed. Title exclusions continue to suppress staff/principal/manager/intern/full-stack roles.

Experience remains a lightweight heuristic, not a perfect reading of every qualification: detected ranges outside 1–5 years reject a job, while missing recognizable experience is allowed and explicitly marked **unknown (manual review)**. Skills/include keywords contribute to a score; they are not mandatory individually. Generic level-II roles may therefore pass without a backend-specific title. Review the full JD before applying. Reports are a useful audit aid, not a claim of perfect fit.

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
