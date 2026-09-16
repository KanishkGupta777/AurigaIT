import pytest

from pricing.catalog import Show, SeatTier, TierSoldOutError, TierNotFoundError
from pricing.engine import price_booking, PricingConfig


def make_show():
    show = Show(show_id="test-show", title="Test Movie")
    show.add_tier(SeatTier(name="Silver", price_rupees=90, total_seats=10))   # <=100 -> 12% GST
    show.add_tier(SeatTier(name="Gold", price_rupees=250, total_seats=10))    # >100 -> 18% GST
    show.add_tier(SeatTier(name="Recliner", price_rupees=500, total_seats=2, seats_available=0))
    return show


def test_plain_booking_total_no_offers():
    show = make_show()
    bill = price_booking(show, {"Gold": 2}, is_member=False, apply_festival_discount=False)
    # 2 * 250 = 500 gross, no discounts, 18% GST = 90, + fee 2*20=40 + fee GST 18% of 40 = 7.2 -> 7
    assert bill.subtotal_paisa == 50000
    assert bill.festival_discount_paisa == 0
    assert bill.member_discount_paisa == 0
    assert bill.lines[0].gst_paisa == 9000  # 18% of 50000
    assert bill.convenience_fee_paisa == 4000
    assert bill.convenience_fee_gst_paisa == 720  # 18% of 4000
    assert bill.grand_total_paisa == 50000 + 9000 + 4000 + 720


def test_gst_slab_boundary():
    show = make_show()
    # Silver is priced at exactly 90 (<=100) -> 12% slab
    bill = price_booking(show, {"Silver": 1}, apply_festival_discount=False)
    assert bill.lines[0].gst_rate == 0.12
    # Gold is 250 (>100) -> 18% slab
    bill2 = price_booking(show, {"Gold": 1}, apply_festival_discount=False)
    assert bill2.lines[0].gst_rate == 0.18


def test_sold_out_tier_rejected():
    show = make_show()
    with pytest.raises(TierSoldOutError):
        price_booking(show, {"Recliner": 1})


def test_unknown_tier_rejected():
    show = make_show()
    with pytest.raises(TierNotFoundError):
        price_booking(show, {"Platinum": 1})


def test_over_capacity_request_rejected():
    show = make_show()
    with pytest.raises(TierSoldOutError):
        price_booking(show, {"Silver": 999})


def test_festival_discount_applied_and_capped_at_subtotal():
    show = make_show()
    # subtotal 90 (1 Silver ticket), festival discount configured at 100 ->
    # must cap at the subtotal so the bill never goes negative.
    bill = price_booking(show, {"Silver": 1}, apply_festival_discount=True)
    assert bill.festival_discount_paisa == 9000  # capped at subtotal (90 rupees)
    assert bill.lines[0].net_paisa == 0


def test_member_discount_capped():
    show = make_show()
    # 10 Gold tickets @250 = 2500 gross. Member gets 10% = 250, but cap is 150.
    bill = price_booking(show, {"Gold": 10}, is_member=True, apply_festival_discount=False)
    assert bill.member_discount_paisa == 15000  # capped at Rs.150, not 10% (Rs.250)


def test_line_items_sum_exactly_to_grand_total_no_paisa_drift():
    show = make_show()
    bill = price_booking(
        show, {"Silver": 3, "Gold": 7}, is_member=True, apply_festival_discount=True
    )
    line_sum = sum(l.line_total_paisa for l in bill.lines)
    computed_total = line_sum + bill.convenience_fee_paisa + bill.convenience_fee_gst_paisa
    assert computed_total == bill.grand_total_paisa

    # discount allocations across lines must also sum exactly to the totals
    assert sum(l.festival_discount_paisa for l in bill.lines) == bill.festival_discount_paisa
    assert sum(l.member_discount_paisa for l in bill.lines) == bill.member_discount_paisa


def test_convenience_fee_is_not_discounted():
    show = make_show()
    bill = price_booking(show, {"Gold": 5}, is_member=True, apply_festival_discount=True)
    assert bill.convenience_fee_paisa == rupees_to_paisa_helper(20) * 5


def rupees_to_paisa_helper(r):
    from pricing.money import rupees_to_paisa
    return rupees_to_paisa(r)


def test_custom_config_is_respected():
    show = make_show()
    config = PricingConfig(
        festival_discount_rupees=50,
        member_discount_pct=0.05,
        member_discount_cap_rupees=1000,
        convenience_fee_per_ticket_rupees=10,
        convenience_fee_gst_rate=0.18,
    )
    bill = price_booking(show, {"Gold": 1}, apply_festival_discount=True, config=config)
    assert bill.festival_discount_paisa == 5000  # Rs.50
    assert bill.convenience_fee_paisa == 1000    # Rs.10 * 1 ticket


def test_multi_tier_booking_breakup():
    show = make_show()
    bill = price_booking(show, {"Silver": 2, "Gold": 1}, apply_festival_discount=False)
    assert len(bill.lines) == 2
    silver_line = next(l for l in bill.lines if l.tier == "Silver")
    gold_line = next(l for l in bill.lines if l.tier == "Gold")
    assert silver_line.gross_paisa == 18000  # 2 * 90
    assert gold_line.gross_paisa == 25000    # 1 * 250
