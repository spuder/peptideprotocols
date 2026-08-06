# Peptide Protocol Archive

Scrapes key metrics (not full pages) from peptide dosage-protocol pages and
stores them as JSON (canonical), CSV (tidy/analyzable), and Markdown
(human-readable, Obsidian-friendly). Built to be re-run on a schedule so you
get a **version history via git commits** — every re-scrape that changes
something shows up as a diff.

## What gets captured

Per page:
- **Dosing & Reconstitution Guide** — every protocol table found (standard,
  alternative/aggressive, whatever the page calls them), with week/phase,
  dose (mg + parsed numeric), and syringe units (+ mL), plus the
  reconstitution volume/concentration and prep steps.
- **Supplies Needed** — vials, syringes, bac water, swabs — broken out by
  schedule (e.g. 5x/week vs 3x/week) and duration (8/12/16 weeks).
- **References** — citation, short description, and source URL.

## Quick start

```bash
pip install -r requirements.txt
python -m scraper.core                # scrape everything in sources.yaml
python -m scraper.core --only bpc-157 # scrape only sources matching this substring
python -m scraper.core --rebuild-only # skip fetching; just rebuild CSV/MD from data/json/
```

Outputs:
- `data/json/<domain>/<slug>.json` — canonical structured snapshot (source of truth)
- `data/csv/{protocols,supplies,references,reconstitution}.csv` — rebuilt
  from **all** json files every run, so these always reflect everything archived
- `markdown/<slug>.md` — one file per page, safe to symlink/copy into an Obsidian vault

## Adding a source

Just add a URL to `sources.yaml`:

```yaml
sources:
  - url: https://peptidedosages.com/single-peptide-dosages/retatrutide-5-mg-vial-dosage-protocol/
```

The `peptidedosages` adapter (`scraper/adapters/peptidedosages.py`) handles
**every** page on that site using the same template — it's not hardcoded to
GHK-Cu, so adding more of that site's ~100 pages is just adding URLs.

## Adding a different site

Different sites will have different HTML. Add a new adapter:

1. Copy `scraper/adapters/peptidedosages.py` as a starting point.
2. Write `can_handle(url)` (usually just a domain check) and
   `parse(url, html) -> PageRecord`.
3. Register it in the `ADAPTERS` list near the top of `scraper/core.py`.

Everything downstream (JSON/CSV/Markdown writers) works off the shared
`PageRecord` shape in `scraper/models.py`, so new sites don't need changes
anywhere else.

## Scheduling

Two workflow files are included — use whichever matches where this repo lives:

- **`.forgejo/workflows/scrape.yml`** — for your Forgejo instance (matches
  your existing CI setup). Runs weekly, commits changes automatically.
- **`.github/workflows/scrape.yml`** — same thing for GitHub Actions.

Both just run `python -m scraper.core` and commit if anything changed. If
you'd rather run it from your homelab instead of CI, it's a plain Python
script — an n8n Cron node calling `python -m scraper.core` in a container
(or an Execute Command node over Tailscale) works identically; there's
nothing CI-specific in the scraper itself.

Either way you get free versioning: `git log -p data/csv/protocols.csv`
shows you exactly when and how a site changed a dosing table.

## Feeding this into a webpage later

`data/csv/*.csv` and `data/json/**/*.json` are the stable interface — an
Astro site (or anything else) can read them at build time without touching
the scraper. The JSON is one file per page if you want per-peptide detail
pages; the CSVs are pre-flattened if you want a searchable/sortable table
across everything archived.

## Politeness / etiquette notes

- `robots.txt` on peptidedosages.com has no `Disallow` rules.
- The scraper identifies with a browser-like User-Agent (a generic bot UA
  gets 403'd by this site's WAF) and waits `REQUEST_DELAY_SEC` (4s) between
  requests — tune both in `scraper/core.py` if needed.
- Failed fetches retry with backoff (transient 403/429s happen) but a page
  that fails 3x is just skipped for that run, not fatal to the rest.
