from dataclasses import dataclass, field
from typing import Dict
from .money import rupees_to_paisa


# GST slab for cinema tickets in India: tickets priced <=Rs.100 attract 12%,
# tickets priced >Rs.100 attract 18%. The slab is decided by the tier's base
# (undiscounted) price -- that's the "declared" ticket price -- not by the
# discounted amount actually charged. This is documented in REASONING.md.
GST_LOW_SLAB_RATE = 0.12
GST_HIGH_SLAB_RATE = 0.18
GST_SLAB_THRESHOLD_RUPEES = 100


@dataclass
class SeatTier:
    name: str
    price_rupees: float
    total_seats: int
    seats_available: int = None  # defaults to total_seats

    def __post_init__(self):
        if self.seats_available is None:
            self.seats_available = self.total_seats

    @property
    def price_paisa(self) -> int:
        return rupees_to_paisa(self.price_rupees)

    def gst_rate(self) -> float:
        return (
            GST_LOW_SLAB_RATE
            if self.price_rupees <= GST_SLAB_THRESHOLD_RUPEES
            else GST_HIGH_SLAB_RATE
        )

    def is_bookable(self, qty: int) -> bool:
        return self.seats_available >= qty


class TierSoldOutError(Exception):
    pass


class TierNotFoundError(Exception):
    pass


@dataclass
class Show:
    show_id: str
    title: str
    tiers: Dict[str, SeatTier] = field(default_factory=dict)

    def add_tier(self, tier: SeatTier):
        self.tiers[tier.name] = tier

    def get_tier(self, name: str) -> SeatTier:
        tier = self.tiers.get(name)
        if tier is None:
            raise TierNotFoundError(f"Unknown seat tier '{name}' for show '{self.show_id}'")
        return tier

    def reserve(self, name: str, qty: int):
        """Decrement inventory. Call only after a successful price quote,
        inside the same request, so we never oversell."""
        tier = self.get_tier(name)
        if not tier.is_bookable(qty):
            raise TierSoldOutError(
                f"'{tier.name}' has only {tier.seats_available} seat(s) left, requested {qty}"
            )
        tier.seats_available -= qty


class Catalog:
    """In-memory store of shows. Swap for a DB-backed repo in production;
    the pricing engine itself doesn't care where SeatTier data comes from."""

    def __init__(self):
        self._shows: Dict[str, Show] = {}

    def add_show(self, show: Show):
        self._shows[show.show_id] = show

    def get_show(self, show_id: str) -> Show:
        show = self._shows.get(show_id)
        if show is None:
            raise KeyError(f"Unknown show_id '{show_id}'")
        return show

    def list_shows(self):
        return list(self._shows.values())


def seed_demo_catalog() -> Catalog:
    """A couple of demo shows so the API has something to book against."""
    cat = Catalog()

    friday_night = Show(show_id="fri-night-avengers", title="Avengers: Friday 9:30 PM")
    friday_night.add_tier(SeatTier(name="Silver", price_rupees=150, total_seats=50))
    friday_night.add_tier(SeatTier(name="Gold", price_rupees=250, total_seats=40))
    friday_night.add_tier(SeatTier(name="Recliner", price_rupees=500, total_seats=10, seats_available=0))  # sold out
    cat.add_show(friday_night)

    matinee = Show(show_id="sat-matinee-kids-movie", title="Kids Movie: Saturday 11 AM")
    matinee.add_tier(SeatTier(name="Silver", price_rupees=90, total_seats=60))
    matinee.add_tier(SeatTier(name="Gold", price_rupees=140, total_seats=30))
    cat.add_show(matinee)

    return cat
