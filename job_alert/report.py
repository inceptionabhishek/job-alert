"""Offline, dependency-free exports of saved jobs with current rule explanations."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from .matching import match_job, extract_years
from .models import Job


def csv_value(value):
    text = "" if value is None else str(value)
    # Prevent spreadsheet formula injection from untrusted source descriptions.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def report_rows(database: Path, matching: dict) -> list[dict]:
    if not database.is_file():
        raise ValueError(f"Database not found: {database}")
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        saved = connection.execute("SELECT * FROM jobs ORDER BY first_seen_at DESC, company, title").fetchall()
    rows = []
    for record in saved:
        row = dict(record)
        job = Job(**{key: row[key] or "" for key in (
            "source", "external_id", "title", "company", "location", "url", "description", "posted_date"
        )})
        result = match_job(job, matching)
        years = extract_years(job.description)
        rows.append({
            "title": job.title, "company": job.company, "location": job.location,
            "source": job.source, "job_id": job.external_id, "url": job.url,
            "description": job.description, "posted_date": job.posted_date,
            "first_seen_at": row["first_seen_at"], "last_seen_at": row["last_seen_at"],
            "current_match": "yes" if result.matched else "no",
            "saved_match": "yes" if row["matched"] else "no", "score": result.score,
            "reasons": "; ".join(result.reasons),
            "experience": f"{years[0]}-{years[1]} years" if years and years[1] is not None else f"{years[0]}+ years" if years else "unknown",
            "status": "alerted" if row["alerted_at"] else "baseline" if row.get("baselined_at") else "not alerted",
            "alerted_at": row["alerted_at"] or "", "baselined_at": row.get("baselined_at") or "",
        })
    return rows


FIELDS = ["title", "company", "location", "source", "job_id", "url", "current_match", "saved_match",
          "score", "reasons", "experience", "status", "posted_date", "first_seen_at", "last_seen_at",
          "alerted_at", "baselined_at", "description"]


def render_html(rows: list[dict]) -> str:
    cards = []
    for row in rows:
        e = lambda key: escape(str(row[key]), quote=True)
        link = (f'<a href="{e("url")}" target="_blank" rel="noopener noreferrer">View / apply</a>'
                if urlsplit(row["url"]).scheme.lower() in ("http", "https") else "No safe application URL")
        cards.append(f'''<article data-match="{e('current_match')}" data-source="{e('source')}" data-location="{e('location')}" data-status="{e('status')}">
<h2>{e('title')}</h2><p>{e('company')} · {e('location')} · {e('source')}</p>
<p>Current match: {e('current_match')} · Saved match: {e('saved_match')} · Score: {e('score')} · {e('status')}</p>
<p class="reason">{e('reasons')}</p><p>Experience: {e('experience')} · Posted: {e('posted_date') or 'unknown'}</p>
<p>First seen (UTC): {e('first_seen_at')} · Last seen (UTC): {e('last_seen_at')}</p>{link}
<details><summary>Full job description</summary><pre>{e('description')}</pre></details></article>''')
    count = sum(row["current_match"] == "yes" for row in rows)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saved job report</title><style>
body{font:16px system-ui,sans-serif;max-width:1050px;margin:auto;padding:24px;background:#f3f5f9;color:#1c2635}
h1{margin-bottom:8px}article{background:white;border:1px solid #ccd3dd;border-radius:12px;padding:20px;margin:16px 0}
h2{font-size:20px;margin-top:0}input,select{font:inherit;padding:10px;max-width:100%;margin:5px}label{display:inline-block}
.filters{position:sticky;top:0;background:#f3f5f9;padding:8px;border-bottom:1px solid #ccd3dd}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.5}p{overflow-wrap:anywhere}a{color:#174fbc}
[hidden]{display:none!important}.reason{color:#45546a}</style>
<h1>Your saved jobs</h1>''' + f'''<p>{len(rows)} saved jobs · {count} match current rules · Generated {timestamp} (UTC)</p>''' + '''
<p>Historical snapshot, not proof a listing is still open. Current rules are re-evaluated without changing the database or sending alerts. Unknown experience needs manual review.</p>
<p><a href="jobs.csv" download>Download CSV</a> · <button id="reset">Reset filters</button></p>
<div class="filters"><label>Search <input id="search" type="search" placeholder="Title, company, skill, JD…"></label>
<label>Match <select id="match"><option value="yes">Matching jobs</option><option value="">All jobs</option><option value="no">Rejected jobs</option></select></label>
<label>Source <select id="source"><option value="">All sources</option></select></label>
<label>Location <select id="location"><option value="">All locations</option></select></label>
<label>Status <select id="status"><option value="">All statuses</option><option>baseline</option><option>alerted</option><option>not alerted</option></select></label>
<p id="count" role="status"></p></div><main>''' + "\n".join(cards) + '''</main>
<script>
const cards=[...document.querySelectorAll('article')], keys=['match','source','location','status'];
for(const key of ['source','location']){const select=document.getElementById(key);
 [...new Set(cards.map(c=>c.dataset[key]))].sort().forEach(value=>{const o=document.createElement('option');o.value=value;o.textContent=value||'Unknown';select.appendChild(o)})}
const texts=cards.map(c=>c.textContent.toLowerCase());
function filter(){const q=document.getElementById('search').value.trim().toLowerCase();let count=0;
cards.forEach((c,i)=>{c.hidden=!(texts[i].includes(q)&&keys.every(k=>!document.getElementById(k).value||c.dataset[k]===document.getElementById(k).value));if(!c.hidden)count++});
document.getElementById('count').textContent=count+' jobs shown';}
document.querySelectorAll('input,select').forEach(e=>e.addEventListener('input',filter));
document.getElementById('reset').addEventListener('click',()=>{document.getElementById('search').value='';keys.forEach(k=>document.getElementById(k).value=k==='match'?'yes':'');filter()});filter();
</script></html>'''


def export_report(database: Path, output: Path, matching: dict) -> int:
    rows = report_rows(database, matching)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "jobs.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: csv_value(row[key]) for key in FIELDS} for row in rows)
    (output / "jobs.html").write_text(render_html(rows), encoding="utf-8")
    return len(rows)
