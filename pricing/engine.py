"""
The pricing engine. Given a show's seat tiers and a booking request, produces
a full paisa-exact, line-by-line bill breakdown.

Order of operations (documented in REASONING.md):
  1. Gross = sum(tier price * qty) per line item.
  2. Flat festival discount (capped at the subtotal so it never goes
     negative), allocated pro-rata across line items.
  3. Percentage member discount (capped at a max rupee amount), computed on
     the post-festival amount, allocated pro-rata across line items.
  4. GST on each line's net (post-discount) ticket value, at the rate
     determined by that tier's *base* price slab.
  5. Convenience fee: flat, per ticket, NOT discounted (it's a service fee,
     not part of the ticket price) -- plus its own GST at a flat rate.
  6. Grand total = sum of every line total + fee + fee GST.

Every discount/tax split uses `allocate()` (largest-remainder method) so the
line items always sum EXACTLY to their respective totals -- no paisa drift.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from .money import rupees_to_paisa, round_half_up, allocate, paisa_to_rupees_str
from .catalog import Show, TierSoldOutError, TierNotFoundError


@dataclass
class PricingConfig:
    festival_discount_rupees: float = 100.0       # flat, per booking
    member_discount_pct: float = 0.10             # 10%
    member_discount_cap_rupees: float = 150.0      # capped
    convenience_fee_per_ticket_rupees: float = 20.0
    convenience_fee_gst_rate: float = 0.18


@dataclass
class LineItem:
    tier: str
    qty: int
    unit_price_paisa: int
    gross_paisa: int
    festival_discount_paisa: int
    member_discount_paisa: int
    net_paisa: int
    gst_rate: float
    gst_paisa: int
    line_total_paisa: int

    def as_dict(self):
        return {
            "tier": self.tier,
            "qty": self.qty,
            "unit_price": paisa_to_rupees_str(self.unit_price_paisa),
            "gross": paisa_to_rupees_str(self.gross_paisa),
            "festival_discount": paisa_to_rupees_str(self.festival_discount_paisa),
            "member_discount": paisa_to_rupees_str(self.member_discount_paisa),
            "net_taxable": paisa_to_rupees_str(self.net_paisa),
            "gst_rate": f"{self.gst_rate * 100:.0f}%",
            "gst": paisa_to_rupees_str(self.gst_paisa),
            "line_total": paisa_to_rupees_str(self.line_total_paisa),
        }


@dataclass
class Bill:
    lines: List[LineItem]
    subtotal_paisa: int
    festival_discount_paisa: int
    member_discount_paisa: int
    convenience_fee_paisa: int
    convenience_fee_gst_paisa: int
    grand_total_paisa: int

    def as_dict(self):
        return {
            "lines": [l.as_dict() for l in self.lines],
            "subtotal": paisa_to_rupees_str(self.subtotal_paisa),
            "festival_discount": paisa_to_rupees_str(self.festival_discount_paisa),
            "member_discount": paisa_to_rupees_str(self.member_discount_paisa),
            "convenience_fee": paisa_to_rupees_str(self.convenience_fee_paisa),
            "convenience_fee_gst": paisa_to_rupees_str(self.convenience_fee_gst_paisa),
            "grand_total": paisa_to_rupees_str(self.grand_total_paisa),
        }


def price_booking(
    show: Show,
    requested: Dict[str, int],
    is_member: bool = False,
    apply_festival_discount: bool = True,
    config: PricingConfig = None,
) -> Bill:
    """
    show: a Show with its SeatTiers (availability is only CHECKED here, not
          decremented -- call show.reserve(...) separately once you've
          decided to commit the booking).
    requested: {tier_name: qty}
    """
    config = config or PricingConfig()

    lines_raw = []
    for tier_name, qty in requested.items():
        if qty <= 0:
            continue
        tier = show.get_tier(tier_name)          # raises TierNotFoundError
        if not tier.is_bookable(qty):             # raises-equivalent check
            raise TierSoldOutError(
                f"'{tier.name}' has only {tier.seats_available} seat(s) left, requested {qty}"
            )
        gross = tier.price_paisa * qty
        lines_raw.append({"tier": tier, "qty": qty, "gross": gross})

    if not lines_raw:
        raise ValueError("No valid tickets requested")

    subtotal = sum(l["gross"] for l in lines_raw)

    # --- Step 2: flat festival discount, capped at subtotal ---
    festival_total = 0
    if apply_festival_discount:
        festival_total = min(rupees_to_paisa(config.festival_discount_rupees), subtotal)
    festival_shares = allocate(festival_total, [l["gross"] for l in lines_raw])
    after_festival = [l["gross"] - f for l, f in zip(lines_raw, festival_shares)]
    after_festival_total = sum(after_festival)

    # --- Step 3: percentage member discount, capped, on post-festival amount ---
    member_total = 0
    if is_member:
        raw_member = round_half_up(after_festival_total * config.member_discount_pct)
        cap = rupees_to_paisa(config.member_discount_cap_rupees)
        member_total = min(raw_member, cap, after_festival_total)
    member_shares = allocate(member_total, after_festival)

    # --- Step 4: GST per line, on the net (post-discount) value ---
    lines: List[LineItem] = []
    for l, festival_share, member_share in zip(lines_raw, festival_shares, member_shares):
        net = l["gross"] - festival_share - member_share
        rate = l["tier"].gst_rate()
        gst = round_half_up(net * rate)
        lines.append(LineItem(
            tier=l["tier"].name,
            qty=l["qty"],
            unit_price_paisa=l["tier"].price_paisa,
            gross_paisa=l["gross"],
            festival_discount_paisa=festival_share,
            member_discount_paisa=member_share,
            net_paisa=net,
            gst_rate=rate,
            gst_paisa=gst,
            line_total_paisa=net + gst,
        ))

    # --- Step 5: convenience fee (flat, undiscounted) + its own GST ---
    total_qty = sum(l.qty for l in lines)
    conv_fee_total = rupees_to_paisa(config.convenience_fee_per_ticket_rupees) * total_qty
    conv_fee_gst = round_half_up(conv_fee_total * config.convenience_fee_gst_rate)

    grand_total = sum(l.line_total_paisa for l in lines) + conv_fee_total + conv_fee_gst

    return Bill(
        lines=lines,
        subtotal_paisa=subtotal,
        festival_discount_paisa=festival_total,
        member_discount_paisa=member_total,
        convenience_fee_paisa=conv_fee_total,
        convenience_fee_gst_paisa=conv_fee_gst,
        grand_total_paisa=grand_total,
    )
