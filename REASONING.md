# Reasoning

## Problem interpretation

The prompt deliberately gives no spec beyond: seat tiers at different
prices, sold-out tiers must not be bookable, two stacking offers (flat
festival discount + capped % member discount), a per-ticket convenience
fee, GST, exact-to-the-paisa totals, and a line-by-line breakup — built
generically ("any cinema counter, not one show"), not hardcoded to one
showtime.

So I treated this as: (1) a data model for tiers/shows, (2) a pure pricing
function that turns a booking request into an itemised bill, (3) a thin API
so it's actually usable at a counter, (4) tests that prove the money math
is exact, not just "looks about right".

## The core hard part: money that's exact to the paisa

Floats cannot represent rupee amounts exactly (`0.1 + 0.2 != 0.3`). I
represent every amount internally as **integer paisa** and only convert to
a display string at the boundary (`pricing/money.py`). Discounts and
percentages are computed on integers and rounded with `ROUND_HALF_UP`
(Python's built-in `round()` uses banker's rounding, which is wrong for
money and would occasionally round a bill the "wrong" way).

## Allocating a shared discount across multiple line items, exactly

When a booking mixes tiers (e.g. 2 Silver + 1 Gold) and a flat discount
applies to the whole order, splitting that discount proportionally across
lines by naive rounding can leave the line items **not summing** to the
order-level discount (off by a paisa or two). I used the **largest-remainder
method** (`allocate()` in `money.py`): compute each line's exact
proportional share, floor it, then hand out the leftover paisa one at a
time to the lines with the largest fractional remainder. This guarantees
the parts always sum exactly to the whole — the same technique used for
seat/vote apportionment problems.

## Order of operations for discounts and tax (the part that's genuinely
ambiguous, so I made an explicit choice and documented it)

1. **Gross** = sum(tier price × qty) per line.
2. **Festival discount** (flat, e.g. Rs.100) is capped at the subtotal (so a
   tiny order can't go negative), then allocated pro-rata across lines.
3. **Member discount** (%, capped at a rupee ceiling) is computed on the
   *post-festival* amount, then allocated pro-rata. I chose to stack member
   discount after festival discount, not on the original gross — this is
   the more conservative/common real-world convention (discounts compound
   sequentially) and it also guarantees the two discounts together can
   never exceed the subtotal.
4. **GST rate per line item** is determined by that tier's *base* (printed)
   price slab (≤Rs.100 → 12%, >Rs.100 → 18%, following the real GST slab
   for movie tickets in India), applied to the *net* (post-discount)
   taxable value. The slab is fixed by the tier's declared price, not the
   discounted price, because that's how ticket-price GST slabs actually
   work — a discount doesn't move a ticket into a lower tax bracket.
5. **Convenience fee** is a flat, undiscounted per-ticket service charge
   (it's not part of the ticket price, so festival/member discounts don't
   apply to it), and carries its own flat 18% GST.
6. **Grand total** = sum of every line's (net + GST) + fee + fee GST.

All of these numbers (discount %, caps, fee amount, GST rates) live in
`PricingConfig` / constants, not hardcoded into the algorithm, so the same
engine works for any cinema's pricing rules — that's the "build it for any
cinema counter, not one show" requirement.

## Sold-out tiers

`SeatTier.is_bookable()` is checked before quoting a price, and inventory is
only ever decremented in `Show.reserve()`, called by the `/book` endpoint
after a successful price computation — so quoting a price never
accidentally reserves a seat, and a race between "quote" and "book" is
caught by re-checking availability at commit time.

## Why FastAPI for the interface

The problem statement is about the *pricing engine*, not a UI, so I kept
the interface minimal: a `/quote` endpoint (price only, no side effects)
and a `/book` endpoint (price + commit). Swagger docs come for free, which
makes it trivial to demo without building a frontend. The engine itself
(`pricing/engine.py`) has zero dependency on FastAPI — it's a plain
function of plain dataclasses, which is why it's straightforward to unit
test in isolation.

## Testing strategy

Beyond "does the total look right", the tests specifically check the things
that are easy to get subtly wrong in a money problem: the GST slab
boundary, discount capping (both festival and member), sold-out/unknown
tier rejection, and — the one I consider most important — that the sum of
every line's numbers reconstructs the grand total exactly, with no paisa
left over anywhere.

## Admin portal, customer capture, and persistence

Added after the core engine was working: booking now requires a customer
name and phone number (validated server-side — non-empty name, ≥10 digit
phone), and every completed booking is persisted to a real SQLite
database (`pricing/db.py`), not an in-memory list, so it survives server
restarts within the same environment.

The admin portal (`/admin`) is a separate static page with its own login
(`/admin/login`), using a short-lived server-side session token
(`pricing/auth.py`) rather than trusting the browser — the frontend never
sees or checks credentials itself, it just gets a token back and sends it
on `X-Admin-Token` for `/admin/bookings` and `/admin/summary`. Every admin
data endpoint checks that token server-side before returning anything, so
booking data can't be read by guessing a URL.

The demo credentials are intentionally both "1234" per the requirement —
this is clearly demo-grade auth (plaintext comparison, in-memory sessions,
no password hashing) appropriate for an assessment project, not something
I'd ship in a real system. That trade-off is deliberate and documented
here rather than hidden.

The admin dashboard adds a few things beyond "list of bookings" because
they're what an actual box-office manager would want: total revenue and
seats-sold summary cards, a per-show breakdown, search by customer
name/phone, and a CSV export (built client-side from already-authenticated
data, so no token ever appears in a URL).

## What I'd add with more time

- Persistent storage (currently in-memory, resets on restart).
- Idempotency keys on `/book` so a retried request can't double-charge/oversell.
- Support for seat-level (not just tier-level) selection.
- Configurable discount stacking order via `PricingConfig`, rather than a
  fixed order in code.
