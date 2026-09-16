from pricing.price_import import import_price_list, parse_price_to_rupees
from decimal import Decimal
import pytest


def test_parse_price_formats():
    assert parse_price_to_rupees("150") == Decimal("150")
    assert parse_price_to_rupees("150.00") == Decimal("150.00")
    assert parse_price_to_rupees("\u20b9150") == Decimal("150")
    assert parse_price_to_rupees("Rs. 250") == Decimal("250")
    assert parse_price_to_rupees("Rs250/-") == Decimal("250")
    assert parse_price_to_rupees("1,200.00") == Decimal("1200.00")
    assert parse_price_to_rupees(150) == Decimal("150")
    assert parse_price_to_rupees(150.5) == Decimal("150.5")


def test_parse_price_rejects_blank_and_garbage():
    with pytest.raises(ValueError):
        parse_price_to_rupees("")
    with pytest.raises(ValueError):
        parse_price_to_rupees(None)
    with pytest.raises(ValueError):
        parse_price_to_rupees("abc")
    with pytest.raises(ValueError):
        parse_price_to_rupees("Rs.")  # nothing left after stripping the currency marker


MESSY_LIST = [
    {"name": "Silver", "price": "150"},               # row 1: clean, imported
    {"name": "silver", "price": "150.00"},             # row 2: dup, same price -> merged
    {"name": "SILVER", "price": "\u20b9150"},          # row 3: dup, same price -> merged
    {"name": "Gold", "price": "Rs. 250"},              # row 4: clean, imported
    {"name": "GOLD", "price": "260"},                  # row 5: dup, CONFLICTING price -> rejected
    {"name": "Recliner", "price": "-500"},             # row 6: negative -> rejected
    {"name": "   ", "price": "300"},                   # row 7: blank name -> rejected
    {"name": "VIP", "price": ""},                      # row 8: blank price -> rejected
    {"name": "Balcony", "price": "abc"},               # row 9: unparseable -> rejected
    {"name": "Premium", "price": "1,200.00"},          # row 10: clean, imported
    {"name": "Couple Seats", "price": "999/-"},        # row 11: clean, imported
]


def test_messy_list_end_to_end():
    report = import_price_list(MESSY_LIST)

    imported_names = {t.name: t.price_rupees for t in report.imported}
    assert imported_names == {
        "Silver": "150.00",
        "Gold": "250.00",
        "Premium": "1200.00",
        "Couple Seats": "999.00",
    }

    # Silver's two duplicate rows (2 and 3) were merged, not rejected
    assert len(report.deduplicated) == 1
    dup = report.deduplicated[0]
    assert dup.canonical_name == "Silver"
    assert dup.kept_row == 1
    assert dup.merged_rows == [2, 3]

    # 5 rows should be rejected: GOLD conflict, Recliner, blank name, VIP, Balcony
    assert len(report.rejected) == 5
    reasons_by_row = {r.row: r.reason for r in report.rejected}
    assert "conflicting price" in reasons_by_row[5]
    assert "negative" in reasons_by_row[6]
    assert "missing seat-class name" in reasons_by_row[7]
    assert "blank" in reasons_by_row[8]
    assert "could not be parsed" in reasons_by_row[9]


def test_report_as_dict_summary():
    report = import_price_list(MESSY_LIST)
    d = report.as_dict()
    assert d["summary"]["rows_in"] == 11
    assert d["summary"]["clean_tiers_out"] == 4
    assert d["summary"]["rows_merged_as_duplicates"] == 2
    assert d["summary"]["rows_rejected"] == 5


def test_empty_list():
    report = import_price_list([])
    assert report.imported == []
    assert report.deduplicated == []
    assert report.rejected == []


def test_case_insensitive_dedup_keeps_first_seen_casing_as_title_case():
    report = import_price_list([
        {"name": "gOLD", "price": "100"},
        {"name": "Gold", "price": "100"},
    ])
    assert len(report.imported) == 1
    assert report.imported[0].name == "Gold"  # .title() normalises casing
