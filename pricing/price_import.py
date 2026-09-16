"""
Import a messy seat-class price list and clean it into a correct,
de-duplicated one -- reporting exactly what was imported, merged as a
duplicate, and rejected (and why).

This is intentionally decoupled from Catalog/Show: it's a standalone
cleaning utility. A real system would run this once (e.g. on a CSV/
spreadsheet upload from the box-office manager), show the human the
report below, and only then feed `imported` into `seed_demo_catalog`-style
code to build actual SeatTier objects.

Messiness this handles, per the brief:
  - duplicate seat-class names in different cases ("Silver" / "silver" /
    "SILVER") -- merged into one canonical entry if their prices agree.
  - inconsistent price formats ("150", "150.00", "Rs. 150", "\u20b9150",
    "1,200.00", "999/-") -- all normalised to a plain rupee amount.
  - blank values (missing/empty name or price) -- rejected.
  - negative prices -- rejected.

The one genuinely ambiguous case -- the SAME name appearing twice with
DIFFERENT prices -- can't be silently resolved (which one is right?), so
we keep the first-seen price and reject the later, conflicting one with
an explanation, rather than guessing.
"""
import re
from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from .money import rupees_to_paisa

# Strip common currency markers: "Rs.", "Rs", "INR", "\u20b9" (case-insensitive).
_CURRENCY_TOKENS = re.compile(r"(?i)(rs\.?|inr|\u20b9)")
# Strip a trailing "/-" (a common Indian convention for whole-rupee amounts).
_TRAILING_SLASH = re.compile(r"/-\s*$")


def parse_price_to_rupees(raw: Any) -> Decimal:
    """
    Parse a messy price value (str/int/float/None) into a Decimal rupee
    amount. Raises ValueError with a human-readable reason if it can't be
    parsed as a number at all.

    Does NOT reject negative values here -- that's a business rule the
    caller checks separately, not a parsing failure.
    """
    if raw is None:
        raise ValueError("price is missing")
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw))

    s = str(raw).strip()
    if s == "":
        raise ValueError("price is blank")

    s = _CURRENCY_TOKENS.sub("", s)
    s = _TRAILING_SLASH.sub("", s)
    s = s.replace(",", "")  # thousands separator -- never a decimal point here
    s = s.strip()

    if s == "":
        raise ValueError(f"'{raw}' has no digits after stripping currency symbols")

    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"'{raw}' could not be parsed as a number")


@dataclass
class ImportedTier:
    name: str
    price_rupees: str      # display string, e.g. "150.00"
    price_paisa: int
    source_row: int        # 1-indexed position in the raw input


@dataclass
class DuplicateMerge:
    canonical_name: str
    kept_row: int
    merged_rows: List[int] = field(default_factory=list)
    price_rupees: str = ""


@dataclass
class RejectedEntry:
    row: int
    raw_name: Any
    raw_price: Any
    reason: str


@dataclass
class ImportReport:
    imported: List[ImportedTier]
    deduplicated: List[DuplicateMerge]
    rejected: List[RejectedEntry]
    total_rows: int = 0

    def as_dict(self) -> Dict[str, Any]:
        merged_row_count = sum(len(d.merged_rows) for d in self.deduplicated)
        return {
            "imported": [asdict(i) for i in self.imported],
            "deduplicated": [asdict(d) for d in self.deduplicated],
            "rejected": [asdict(r) for r in self.rejected],
            "summary": {
                "rows_in": self.total_rows,
                "clean_tiers_out": len(self.imported),
                "rows_merged_as_duplicates": merged_row_count,
                "rows_rejected": len(self.rejected),
            },
        }


def import_price_list(raw_entries: List[Dict[str, Any]]) -> ImportReport:
    """
    raw_entries: a list of dicts like {"name": ..., "price": ...}, straight
    from an untrusted source (pasted spreadsheet, CSV upload, etc).

    Returns an ImportReport with three buckets -- see module docstring.
    """
    imported: List[ImportedTier] = []
    deduplicated: List[DuplicateMerge] = []
    rejected: List[RejectedEntry] = []

    seen: Dict[str, int] = {}  # canonical lowercase name -> index into `imported`

    for row_idx, entry in enumerate(raw_entries, start=1):
        raw_name = entry.get("name") if isinstance(entry, dict) else None
        raw_price = entry.get("price") if isinstance(entry, dict) else None

        name = str(raw_name).strip() if raw_name is not None else ""
        if not name:
            rejected.append(RejectedEntry(row_idx, raw_name, raw_price, "missing seat-class name"))
            continue

        try:
            price_rupees = parse_price_to_rupees(raw_price)
        except ValueError as e:
            rejected.append(RejectedEntry(row_idx, raw_name, raw_price, str(e)))
            continue

        if price_rupees < 0:
            rejected.append(RejectedEntry(row_idx, raw_name, raw_price, "negative price is not allowed"))
            continue

        canonical_key = name.lower()
        price_paisa = rupees_to_paisa(price_rupees)

        if canonical_key in seen:
            existing = imported[seen[canonical_key]]
            if existing.price_paisa == price_paisa:
                merge = next((d for d in deduplicated if d.canonical_name == existing.name), None)
                if merge is None:
                    merge = DuplicateMerge(
                        canonical_name=existing.name,
                        kept_row=existing.source_row,
                        merged_rows=[],
                        price_rupees=existing.price_rupees,
                    )
                    deduplicated.append(merge)
                merge.merged_rows.append(row_idx)
            else:
                rejected.append(RejectedEntry(
                    row_idx, raw_name, raw_price,
                    f"duplicate of '{existing.name}' (row {existing.source_row}) with a "
                    f"conflicting price -- kept \u20b9{existing.price_rupees}, "
                    f"rejected this \u20b9{price_rupees:.2f}",
                ))
            continue

        canonical_name = name.title()
        tier = ImportedTier(
            name=canonical_name,
            price_rupees=f"{price_rupees:.2f}",
            price_paisa=price_paisa,
            source_row=row_idx,
        )
        imported.append(tier)
        seen[canonical_key] = len(imported) - 1

    return ImportReport(
        imported=imported,
        deduplicated=deduplicated,
        rejected=rejected,
        total_rows=len(raw_entries),
    )
