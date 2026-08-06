"""Shared data shapes for scraped peptide protocol pages.

Kept as plain dataclasses (not pydantic) so this has zero extra
dependencies beyond requests/bs4/pyyaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class DoseRow:
    week_phase: str
    dose_text: str          # "1.0 mg (1000 mcg)" as displayed
    dose_mg: Optional[float]
    units_text: str         # "6 units (0.06 mL)" as displayed
    units: Optional[float]
    ml: Optional[float]


@dataclass
class ProtocolTable:
    name: str                # e.g. "Standard / Conservative Approach"
    heading_raw: str         # full h2 text, incl. concentration/frequency hint
    frequency: str           # free text frequency sentence
    rows: list[DoseRow] = field(default_factory=list)


@dataclass
class Reconstitution:
    diluent: str              # "sterile" / "bacteriostatic" as stated
    volume_ml: Optional[float]
    concentration_mg_ml: Optional[float]
    steps: list[str] = field(default_factory=list)


@dataclass
class SupplyLine:
    item: str                 # "Peptide Vials (GHK-Cu, 50 mg each)"
    schedule: Optional[str]   # "5 days/week (1.0-2.0 mg/day)" or None
    label: str                 # "8 weeks (~50 mg total)" or "Per week"
    quantity_text: str         # "1 vial" as displayed
    quantity: Optional[float]
    unit: Optional[str]        # "vial", "syringes", "mL", "swabs"


@dataclass
class Reference:
    ref_id: str                # "ref-1"
    citation: str               # "Mulder GD, et al. Wound Repair and Regeneration."
    description: str
    url: Optional[str]
    category: str               # "Research References" / "Additional Technical..."


@dataclass
class PageRecord:
    source_url: str
    domain: str
    scraped_at: str             # ISO8601 UTC
    peptide: str
    vial_size_text: str         # "50 mg Vial"
    vial_size_mg: Optional[float]
    page_updated: Optional[str]  # site's own "Updated <date>" if present
    reconstitution_summary: dict
    protocols: list[ProtocolTable] = field(default_factory=list)
    supplies: list[SupplyLine] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    content_hash: str = ""       # to detect no-op re-scrapes

    def to_dict(self) -> dict:
        return asdict(self)
