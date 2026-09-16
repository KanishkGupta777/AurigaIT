# Multiplex Ticket Pricing Engine

A paisa-exact pricing engine for a cinema counter: seat tiers, sold-out
handling, a flat festival discount, a capped member discount, a per-ticket
convenience fee, and GST — with a full line-by-line bill breakup.

## Quick links

> ⚠️ The live links below only work while your GitHub Codespace is running
> and the server is started (see **Running**). Replace the URL with your
> own Codespace's forwarded address — it's shown in the **Ports** tab and
> looks like `https://<random-name>-8000.app.github.dev`.

| | |
|---|---|
| **Customer / booking counter** | `https://solid-meme-g47x45jpjpg7cvp9-8000.app.github.dev/` |
| **Admin portal** | `https://solid-meme-g47x45jpjpg7cvp9-8000.app.github.dev/admin` |
| **Admin login** | username `1234` · password `1234` (demo credentials — intentionally simple; see REASONING.md) |
| **API docs (Swagger)** | `https://<your-codespace-url>-8000.app.github.dev/docs` |

## Project layout

```
pricing/
  money.py         # paisa-exact arithmetic + largest-remainder allocation
  catalog.py       # SeatTier / Show / Catalog (inventory)
  engine.py        # the pricing engine itself (price_booking)
  price_import.py  # cleans a messy seat-class price list (the "twist")
  db.py            # SQLite persistence for bookings
  auth.py          # minimal admin session auth
api/
  main.py          # FastAPI wrapper exposing everything over HTTP
static/
  index.html       # customer-facing booking counter UI
  admin.html       # admin dashboard UI
tests/
  test_money.py
  test_engine.py
  test_bookings_admin.py
  test_price_import.py
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --reload
```

In GitHub Codespaces, `--host 0.0.0.0` is required so the forwarded port
is reachable — `127.0.0.1` (uvicorn's default) only listens inside the
container. Open the forwarded port from the **Ports** tab, or use the
link Codespaces pops up automatically.

Locally, open `http://localhost:8000`.

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
  -d '{"tickets": {"Gold": 2}, "is_member": false, "customer_name": "Asha Rao", "phone": "9876543210"}'
```

### Example: sold-out tier (Recliner is seeded as sold out)

```bash
curl -X POST http://localhost:8000/shows/fri-night-avengers/quote \
  -H "Content-Type: application/json" \
  -d '{"tickets": {"Recliner": 1}}'
# -> 409 Conflict
```

## Cleaning a messy price list (the "twist")

Real seat-class price lists (spreadsheet exports, CSV pastes) are rarely
clean: duplicate names in different cases, prices in mixed formats, blank
cells, stray negative values. `POST /catalog/import-price-list` takes a
raw list of `{"name": ..., "price": ...}` entries and returns a report of
what was imported (clean, ready to use), de-duplicated (merged because
the duplicate agreed on price), and rejected (with a specific reason for
each). It does not touch the live catalog — it's a standalone cleaning
utility a human would review before approving the result.

```bash
curl -X POST http://localhost:8000/catalog/import-price-list \
  -H "Content-Type: application/json" \
  -d '{
    "entries": [
      {"name": "Silver", "price": "150"},
      {"name": "silver", "price": "₹150"},
      {"name": "Gold", "price": "260"},
      {"name": "Gold", "price": "250"},
      {"name": "", "price": "300"},
      {"name": "VIP", "price": ""},
      {"name": "Recliner", "price": "-500"}
    ]
  }'
```

See `pricing/price_import.py` and `REASONING.md` for the exact cleaning
rules (accepted price formats, and how a genuine name/price conflict
between two duplicate rows is resolved).

## Running tests

```bash
pytest tests/ -v
```

28 tests cover: plain totals, GST slab boundaries, festival-discount
capping, member-discount capping, sold-out/unknown-tier rejection, custom
pricing configs, the admin/booking API, the messy price-list importer, and
— most importantly — that every line item always sums exactly to the
grand total (no paisa drift).

## Admin portal

Visit `/admin`. Login: username `1234`, password `1234` (demo credentials
— see REASONING.md for why these are intentionally simple). Shows total
revenue, seats sold, a per-show breakdown, a searchable table of every
booking (with customer name/phone), and a CSV export button.

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
- If the app won't start with `ModuleNotFoundError: No module named 'api'`
  (or `'pricing'`), it means the folder structure got flattened somewhere
  along the way — `main.py` must live inside an `api/` folder, and
  `engine.py`/`catalog.py`/etc. must live inside a `pricing/` folder, both
  at the repo root, for Python's package imports to resolve.
- If your Codespace's forwarded URL shows a blank page after an update,
  hard-refresh (`Ctrl+Shift+R`) — the browser sometimes caches the old
  `static/index.html`.

## Extending

- Swap `Catalog`'s in-memory dict for a DB-backed repository — `engine.py`
  doesn't need to change, it only depends on the `Show`/`SeatTier` interface.
- Add more discount types by adding another pro-rata `allocate()` step
  between festival and member discount, following the same pattern.
- Wire `pricing/price_import.py`'s cleaned output directly into `Catalog`
  construction, once a human has reviewed the import report.
