"""Adapter for peptidedosages.com dosage-protocol pages.

The same WordPress template is reused across every /single-peptide-dosages/
and /peptide-blend-dosages/ page on the site, so this one adapter covers
all of them (~100+ pages) as long as they keep this markup:

  div#dosing-schedule > section > h2 + table + <p>Frequency...</p>
  section#supplies-needed > ul > li (nested ul of quantities)
  section#references > h3 (category) + ul.reference-list > li#ref-N

If the site redesigns this template, only this file needs updating —
core.py and the output formats are unaffected.
"""
from __future__ import annotations

import re
from bs4 import BeautifulSoup

from scraper.models import (
    DoseRow, ProtocolTable, Reconstitution, SupplyLine, Reference, PageRecord,
)

DOMAIN = "peptidedosages.com"

# Supply line items to skip entirely — edit this list to change what gets archived.
EXCLUDED_SUPPLY_KEYWORDS = ["syringe", "swab"]

_NUM = r"[-+]?\d*\.?\d+"


def _to_float(text: str) -> float | None:
    if not text:
        return None
    m = re.search(_NUM, text.replace(",", ""))
    return float(m.group()) if m else None


def can_handle(url: str) -> bool:
    return DOMAIN in url


def _parse_title(soup: BeautifulSoup) -> tuple[str, str, float | None]:
    h1 = soup.select_one("h1.page-title") or soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else ""
    # "GHK-Cu (50 mg Vial) Dosage Protocol" -> peptide="GHK-Cu", vial="50 mg Vial"
    m = re.match(r"^(.*?)\s*\((.*?Vial)\)", title)
    if m:
        peptide, vial_text = m.group(1).strip(), m.group(2).strip()
    else:
        peptide, vial_text = title, ""
    vial_mg = _to_float(vial_text)
    return peptide, vial_text, vial_mg


def _parse_dose_row(tr) -> DoseRow:
    cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
    week_phase, dose_text, units_text = (cells + ["", "", ""])[:3]
    dose_mg = _to_float(dose_text)
    units_m = re.search(r"([-+]?\d*\.?\d+)\s*units?", units_text, re.I)
    ml_m = re.search(r"\(([-+]?\d*\.?\d+)\s*mL\)", units_text, re.I)
    return DoseRow(
        week_phase=week_phase,
        dose_text=dose_text,
        dose_mg=dose_mg,
        units_text=units_text,
        units=float(units_m.group(1)) if units_m else None,
        ml=float(ml_m.group(1)) if ml_m else None,
    )


def _parse_protocols(soup: BeautifulSoup) -> tuple[list[ProtocolTable], Reconstitution]:
    wrapper = soup.select_one("#dosing-schedule") or soup.select_one(".dosing-recon-wrapper")
    protocols: list[ProtocolTable] = []
    steps: list[str] = []
    volume_ml = concentration = None

    if wrapper:
        for section in wrapper.select("section"):
            h2 = section.find("h2")
            if not h2:
                continue
            heading_raw = h2.get_text(" ", strip=True)
            name = re.sub(r"\s*\(.*?\)\s*$", "", heading_raw).strip()

            table = section.find("table")
            rows = [_parse_dose_row(tr) for tr in table.select("tbody tr")] if table else []

            freq_p = None
            for p in section.find_all("p"):
                if p.get_text(strip=True).lower().startswith("frequency"):
                    freq_p = p.get_text(" ", strip=True)
                    break

            protocols.append(ProtocolTable(
                name=name, heading_raw=heading_raw,
                frequency=freq_p or "", rows=rows,
            ))

            # concentration/volume are consistent across protocols on a page;
            # pull from the first heading that has them, e.g. "3 mL = 16.67 mg/mL"
            if volume_ml is None:
                vm = re.search(r"([\d.]+)\s*mL\s*=\s*([\d.]+)\s*mg/mL", heading_raw)
                if vm:
                    volume_ml, concentration = float(vm.group(1)), float(vm.group(2))

            steps_ol = section.find("ol")
            if steps_ol and not steps:
                steps = [li.get_text(" ", strip=True) for li in steps_ol.find_all("li")]

    recon = Reconstitution(
        diluent="sterile/bacteriostatic water",
        volume_ml=volume_ml,
        concentration_mg_ml=concentration,
        steps=steps,
    )
    return protocols, recon


def _parse_supplies(soup: BeautifulSoup) -> list[SupplyLine]:
    section = soup.select_one("#supplies-needed")
    if not section:
        return []
    out: list[SupplyLine] = []
    top_ul = section.find("ul")
    if not top_ul:
        return out

    for li in top_ul.find_all("li", recursive=False):
        strong = li.find("strong")
        item = strong.get_text(strip=True) if strong else li.get_text(" ", strip=True)[:80]

        if any(kw in item.lower() for kw in EXCLUDED_SUPPLY_KEYWORDS):
            continue

        nested_ul = li.find("ul")
        if not nested_ul:
            continue

        schedule = None
        for sub_li in nested_ul.find_all("li", recursive=False):
            em = sub_li.find("em")
            if em and not sub_li.find("strong"):
                # a sub-header line like "5 days/week (1.0-2.0 mg/day):"
                schedule = em.get_text(strip=True).rstrip(":")
                continue

            strongs = sub_li.find_all("strong")
            qty_text = strongs[0].get_text(strip=True) if strongs else ""
            # label = whatever text precedes the first <strong> (e.g. "8 weeks:")
            label = ""
            for node in sub_li.children:
                if node is strongs[0] if strongs else False:
                    break
                label += node.get_text() if hasattr(node, "get_text") else str(node)
            label = label.strip(" :")
            # a second <strong> is an aside like "or 1 x 100-count box" — keep it
            if len(strongs) > 1:
                extra = " / ".join(s.get_text(strip=True) for s in strongs[1:])
                qty_text = f"{qty_text} (also: {extra})"
            qty_val = _to_float(strongs[0].get_text(strip=True)) if strongs else None
            unit_m = re.search(r"[\d.]+\s*([a-zA-Z]+)", strongs[0].get_text(strip=True)) if strongs else None
            unit = unit_m.group(1) if unit_m else None

            out.append(SupplyLine(
                item=item, schedule=schedule, label=label,
                quantity_text=qty_text, quantity=qty_val, unit=unit,
            ))
    return out


def _parse_references(soup: BeautifulSoup) -> list[Reference]:
    section = soup.select_one("#references")
    if not section:
        return []
    out: list[Reference] = []
    category = ""
    for el in section.find_all(["h3", "ul"], recursive=False):
        if el.name == "h3":
            category = el.get_text(strip=True)
            continue
        if el.name == "ul" and "reference-list" in (el.get("class") or []):
            for li in el.find_all("li", recursive=False):
                ref_id = li.get("id", "")
                ref_line = li.select_one(".ref-line")
                strong = ref_line.find("strong") if ref_line else None
                span = ref_line.find("span") if ref_line else None
                a = li.select_one(".ref-button-line a") or li.find("a")
                desc = span.get_text(strip=True) if span else ""
                desc = re.sub(r"^[\s—–\-]+", "", desc)  # strip leading em-dash some pages include
                out.append(Reference(
                    ref_id=ref_id,
                    citation=strong.get_text(strip=True) if strong else "",
                    description=desc,
                    url=a.get("href") if a else None,
                    category=category or "References",
                ))
    return out


def parse(url: str, html: str) -> PageRecord:
    soup = BeautifulSoup(html, "html.parser")

    peptide, vial_text, vial_mg = _parse_title(soup)
    protocols, recon = _parse_protocols(soup)
    supplies = _parse_supplies(soup)
    references = _parse_references(soup)

    updated = None
    updated_el = soup.find(string=re.compile(r"^Updated\s"))
    if updated_el:
        updated = updated_el.strip().replace("Updated", "").strip()

    return PageRecord(
        source_url=url,
        domain=DOMAIN,
        scraped_at="",  # filled in by core.py
        peptide=peptide,
        vial_size_text=vial_text,
        vial_size_mg=vial_mg,
        page_updated=updated,
        reconstitution_summary=recon.__dict__,
        protocols=protocols,
        supplies=supplies,
        references=references,
    )
