import os
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pricing.catalog import seed_demo_catalog, TierSoldOutError, TierNotFoundError
from pricing.engine import price_booking, PricingConfig

app = FastAPI(title="Multiplex Ticket Pricing Engine")
catalog = seed_demo_catalog()

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/shows")
def list_shows():
    return [
        {
            "show_id": s.show_id,
            "title": s.title,
            "tiers": [
                {
                    "name": t.name,
                    "price": t.price_rupees,
                    "seats_available": t.seats_available,
                    "total_seats": t.total_seats,
                }
                for t in s.tiers.values()
            ],
        }
        for s in catalog.list_shows()
    ]


class BookingRequest(BaseModel):
    tickets: Dict[str, int]           # {"Silver": 2, "Gold": 1}
    is_member: bool = False
    apply_festival_discount: bool = True
    commit: bool = False              # True = actually decrement seat inventory


@app.post("/shows/{show_id}/quote")
def quote_booking(show_id: str, req: BookingRequest):
    """Price a booking WITHOUT touching inventory. Use this to show the
    customer their bill before they confirm."""
    try:
        show = catalog.get_show(show_id)
    except KeyError:
        raise HTTPException(404, f"Unknown show_id '{show_id}'")

    try:
        bill = price_booking(
            show, req.tickets,
            is_member=req.is_member,
            apply_festival_discount=req.apply_festival_discount,
        )
    except TierNotFoundError as e:
        raise HTTPException(400, str(e))
    except TierSoldOutError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    return bill.as_dict()


@app.post("/shows/{show_id}/book")
def book(show_id: str, req: BookingRequest):
    """Price AND commit the booking (decrements seat inventory). Re-checks
    availability at commit time in case of a race between quote and book."""
    try:
        show = catalog.get_show(show_id)
    except KeyError:
        raise HTTPException(404, f"Unknown show_id '{show_id}'")

    try:
        bill = price_booking(
            show, req.tickets,
            is_member=req.is_member,
            apply_festival_discount=req.apply_festival_discount,
        )
        for tier_name, qty in req.tickets.items():
            if qty > 0:
                show.reserve(tier_name, qty)
    except TierNotFoundError as e:
        raise HTTPException(400, str(e))
    except TierSoldOutError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    return bill.as_dict()


@app.get("/")
def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "docs": "/docs"}
