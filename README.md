# Multiplex Ticket Pricing Engine

A paisa-exact pricing engine for a cinema counter: seat tiers, sold-out
handling, a flat festival discount, a capped member discount, a per-ticket
convenience fee, and GST — with a full line-by-line bill breakup.

## Project layout

```
pricing/
  money.py     # paisa-exact arithmetic + largest-remainder allocation
  catalog.py   # SeatTier / Show / Catalog (inventory)
  engine.py    # the pricing engine itself (price_booking)
api/
  main.py      # FastAPI wrapper exposing the engine over HTTP
tests/
  test_money.py
  test_engine.py
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

Start the API:

```bash
uvicorn api.main:app --reload
```

Open `http://localhost:8000/docs` for interactive Swagger docs.

### Example: list shows

```bash
curl http://localhost:8000/shows
```

### Example: quote a booking (no inventory change)

```bash
curl -X POST http://localhost:8000/shows/fri-night-avengers/quote \
  -H "Content-Type: application/json" \
  -d '{"tickets": {"Silver": 2, "Gold": 1}, "is_member": true, "apply_festival_discount": true}'
```

### Example: book (commits inventory)

```bash
curl -X POST http://localhost:8000/shows/fri-night-avengers/book \
  -H "Content-Type: application/json" \
  -d '{"tickets": {"Gold": 2}, "is_member": false}'
```

### Example: sold-out tier (Recliner is seeded as sold out)

```bash
curl -X POST http://localhost:8000/shows/fri-night-avengers/quote \
  -H "Content-Type: application/json" \
  -d '{"tickets": {"Recliner": 1}}'
# -> 409 Conflict
```

## Running tests

```bash
pytest tests/ -v
```

18 tests cover: plain totals, GST slab boundaries, festival-discount
capping, member-discount capping, sold-out/unknown-tier rejection, custom
pricing configs, and — most importantly — that every line item always sums
exactly to the grand total (no paisa drift).

## Admin portal

Visit `http://localhost:8000/admin`. Login: username `1234`, password
`1234` (demo credentials — see REASONING.md for why these are intentionally
simple). Shows total revenue, seats sold, a per-show breakdown, a
searchable table of every booking (with customer name/phone), and a CSV
export button.

Bookings are stored in a local SQLite file at `data/bookings.db`, created
automatically on first run. It's gitignored by default since it's live
transactional data, not source code — see the note at the top of
`pricing/db.py` if you want to understand why "a database in GitHub" isn't
quite the right framing for a live store.

## Debugging notes

- All money is handled as **integer paisa** internally (see `pricing/money.py`).
  If a bug ever shows a bill off by a paisa, the first place to look is
  whether some code path introduced a float/Decimal comparison instead of
  going through `allocate()` / `round_half_up()`.
- `price_booking()` never mutates inventory — it's a pure function of
  `(Show, requested tickets, flags, config)`. Inventory is only touched by
  `Show.reserve()`, called separately by the `/book` endpoint. This makes
  the engine trivial to unit-test and safe to call repeatedly for quotes.
- Business rules (discount %, caps, fee, GST rates/slabs) live in
  `PricingConfig` and the GST-slab constants in `catalog.py` — not
  hardcoded inside the algorithm — so this is reusable for any cinema
  counter's numbers, not just this one demo.

## Extending

- Swap `Catalog`'s in-memory dict for a DB-backed repository — `engine.py`
  doesn't need to change, it only depends on the `Show`/`SeatTier` interface.
- Add more discount types by adding another pro-rata `allocate()` step
  between festival and member discount, following the same pattern.
