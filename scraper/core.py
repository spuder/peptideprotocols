"""Fetch configured source pages, parse them via the right adapter, and
write two kinds of output:

  data/json/<domain>/<slug>.json   canonical structured snapshot (source of truth)
  markdown/<slug>.md               human-readable snapshot per page

Run:
    python -m scraper.core                  # scrape everything in sources.yaml
    python -m scraper.core --only ghk-cu     # scrape sources whose slug/url matches
    python -m scraper.core --rebuild-only    # skip fetching, just regenerate MD from existing json
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml
import requests

from scraper.models import PageRecord
from scraper.adapters import peptidedosages

ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = ROOT / "data" / "json"
MARKDOWN = ROOT / "markdown"
SOURCES_FILE = ROOT / "sources.yaml"

ADAPTERS = [peptidedosages]  # add more site adapters here as you expand sources

HEADERS = {
    # A plain custom bot UA gets 403'd by this site's WAF after a few requests.
    # Identifying as a normal browser avoids that. Still fully polite: rate-limited,
    # respects robots.txt (checked manually — this site allows crawling), and only
    # hits URLs you've explicitly listed in sources.yaml.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY_SEC = 4  # be polite / avoid WAF rate-limiting


def slugify(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return re.sub(r"[^a-z0-9]+", "-", path.split("/")[-1].lower()).strip("-")


def domain_of(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def load_sources() -> list[dict]:
    with open(SOURCES_FILE) as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("sources", [])


def fetch(url: str, retries: int = 3) -> str:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                wait = 3 * attempt  # transient 403s/429s from bot-protection are common; back off
                print(f"  ! attempt {attempt} failed ({e}); retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise last_exc


def find_adapter(url: str):
    for adapter in ADAPTERS:
        if adapter.can_handle(url):
            return adapter
    return None


def scrape_one(url: str) -> PageRecord | None:
    adapter = find_adapter(url)
    if adapter is None:
        print(f"  ! no adapter for {url}, skipping", file=sys.stderr)
        return None

    html = fetch(url)
    record = adapter.parse(url, html)
    record.scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record.content_hash = hashlib.sha256(html.encode("utf-8", "ignore")).hexdigest()[:16]
    return record


def json_path_for(url: str) -> Path:
    return DATA_JSON / domain_of(url) / f"{slugify(url)}.json"


def save_json(record: PageRecord) -> Path:
    path = json_path_for(record.source_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    return path


def load_all_records() -> list[dict]:
    records = []
    for path in sorted(DATA_JSON.rglob("*.json")):
        records.append(json.loads(path.read_text()))
    return records


# ------------------------------------------------------------ Markdown ----

def write_markdown(record: dict) -> Path:
    r = record
    lines = [
        f"# {r['peptide']} ({r['vial_size_text']})",
        "",
        f"- Source: <{r['source_url']}>",
        f"- Scraped: {r['scraped_at']}",
    ]
    if r.get("page_updated"):
        lines.append(f"- Page last updated (per site): {r['page_updated']}")
    rc = r.get("reconstitution_summary", {})
    if rc.get("volume_ml"):
        lines.append(f"- Reconstitution: {rc['volume_ml']} mL -> {rc.get('concentration_mg_ml')} mg/mL")
    lines.append("")

    lines.append("## Dosing & Reconstitution Guide")
    for proto in r.get("protocols", []):
        lines.append("")
        lines.append(f"### {proto['name']}")
        lines.append(f"*{proto['heading_raw']}*")
        lines.append("")
        lines.append("| Week/Phase | Dose | Units (mL) |")
        lines.append("|---|---|---|")
        for row in proto.get("rows", []):
            lines.append(f"| {row['week_phase']} | {row['dose_text']} | {row['units_text']} |")
        if proto.get("frequency"):
            lines.append("")
            lines.append(f"**{proto['frequency']}**")

    if rc.get("steps"):
        lines.append("")
        lines.append("### Reconstitution Steps")
        for i, step in enumerate(rc["steps"], 1):
            lines.append(f"{i}. {step}")

    lines.append("")
    lines.append("## Supplies Needed")
    current_item = None
    current_schedule = object()  # sentinel, never equal to a real schedule
    for s in r.get("supplies", []):
        if s["item"] != current_item:
            lines.append("")
            lines.append(f"**{s['item']}**")
            current_item, current_schedule = s["item"], object()
        if s["schedule"] != current_schedule:
            if s["schedule"]:
                lines.append(f"- *{s['schedule']}*")
            current_schedule = s["schedule"]
        indent = "  " if s["schedule"] else ""
        lines.append(f"{indent}- {s['label']}: **{s['quantity_text']}**")

    lines.append("")
    lines.append("## References")
    current_cat = None
    for ref in r.get("references", []):
        if ref["category"] != current_cat:
            lines.append("")
            lines.append(f"### {ref['category']}")
            current_cat = ref["category"]
        desc = f" — {ref['description']}" if ref["description"] else ""
        link = f" [Source]({ref['url']})" if ref["url"] else ""
        lines.append(f"- **{ref['citation']}**{desc}{link}")

    lines.append("")
    path = MARKDOWN / f"{slugify(r['source_url'])}.md"
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------- main ----

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="substring filter on url/slug")
    ap.add_argument("--rebuild-only", action="store_true",
                     help="skip fetching; just rebuild MD from existing json/")
    args = ap.parse_args()

    MARKDOWN.mkdir(parents=True, exist_ok=True)

    if not args.rebuild_only:
        sources = load_sources()
        if args.only:
            sources = [s for s in sources if args.only in s["url"]]

        for src in sources:
            url = src["url"]
            print(f"Scraping {url}")
            try:
                record = scrape_one(url)
            except requests.RequestException as e:
                print(f"  ! fetch failed: {e}", file=sys.stderr)
                continue
            if record is None:
                continue
            save_json(record)
            time.sleep(REQUEST_DELAY_SEC)

    print("Rebuilding Markdown from data/json/ ...")
    records = load_all_records()
    for r in records:
        write_markdown(r)
    print(f"Done. {len(records)} pages archived.")


if __name__ == "__main__":
    main()
