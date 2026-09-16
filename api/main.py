import json
import os
from typing import Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pricing.catalog import seed_demo_catalog, TierSoldOutError, TierNotFoundError
from pricing.engine import price_booking, PricingConfig
from pricing import db, auth

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


class BookRequest(BookingRequest):
    customer_name: str
    phone: str


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
def book(show_id: str, req: BookRequest):
    """Price AND commit the booking (decrements seat inventory, persists a
    booking record). Re-checks availability at commit time in case of a
    race between quote and book."""
    name = req.customer_name.strip()
    phone = req.phone.strip()
    if not name:
        raise HTTPException(400, "customer_name is required")
    if not phone or not phone.replace("+", "").replace(" ", "").isdigit() or len(phone.replace("+", "").replace(" ", "")) < 10:
        raise HTTPException(400, "A valid phone number (at least 10 digits) is required")

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

    db.insert_booking(
        show_id=show.show_id,
        show_title=show.title,
        customer_name=name,
        phone=phone,
        tickets_json=json.dumps({k: v for k, v in req.tickets.items() if v > 0}),
        is_member=req.is_member,
        festival_applied=req.apply_festival_discount,
        subtotal_paisa=bill.subtotal_paisa,
        festival_discount_paisa=bill.festival_discount_paisa,
        member_discount_paisa=bill.member_discount_paisa,
        convenience_fee_paisa=bill.convenience_fee_paisa,
        convenience_fee_gst_paisa=bill.convenience_fee_gst_paisa,
        grand_total_paisa=bill.grand_total_paisa,
    )

    return bill.as_dict()


# ---------------------------------------------------------------------------
# Admin portal
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/admin/login")
def admin_login(req: LoginRequest):
    token = auth.login(req.username, req.password)
    if not token:
        raise HTTPException(401, "Invalid username or password")
    return {"token": token}


@app.post("/admin/logout")
def admin_logout(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token:
        auth.logout(x_admin_token)
    return {"status": "ok"}


def _require_admin(x_admin_token: Optional[str] = Header(None)):
    if not auth.is_valid(x_admin_token):
        raise HTTPException(401, "Not authenticated. Please log in again.")


@app.get("/admin/bookings")
def admin_bookings(x_admin_token: Optional[str] = Header(None)):
    _require_admin(x_admin_token)
    rows = db.list_bookings()
    from pricing.money import paisa_to_rupees_str

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "show_id": r["show_id"],
            "show_title": r["show_title"],
            "customer_name": r["customer_name"],
            "phone": r["phone"],
            "tickets": json.loads(r["tickets_json"]),
            "is_member": bool(r["is_member"]),
            "festival_applied": bool(r["festival_applied"]),
            "subtotal": paisa_to_rupees_str(r["subtotal_paisa"]),
            "festival_discount": paisa_to_rupees_str(r["festival_discount_paisa"]),
            "member_discount": paisa_to_rupees_str(r["member_discount_paisa"]),
            "convenience_fee": paisa_to_rupees_str(r["convenience_fee_paisa"]),
            "convenience_fee_gst": paisa_to_rupees_str(r["convenience_fee_gst_paisa"]),
            "grand_total": paisa_to_rupees_str(r["grand_total_paisa"]),
            "created_at": r["created_at"],
        })
    return out


@app.get("/admin/summary")
def admin_summary(x_admin_token: Optional[str] = Header(None)):
    _require_admin(x_admin_token)
    from pricing.money import paisa_to_rupees_str

    rows = db.list_bookings()
    total_revenue_paisa = sum(r["grand_total_paisa"] for r in rows)
    total_seats = sum(sum(json.loads(r["tickets_json"]).values()) for r in rows)
    per_show = {}
    for r in rows:
        entry = per_show.setdefault(r["show_id"], {
            "show_title": r["show_title"], "bookings": 0, "seats": 0, "revenue_paisa": 0,
        })
        entry["bookings"] += 1
        entry["seats"] += sum(json.loads(r["tickets_json"]).values())
        entry["revenue_paisa"] += r["grand_total_paisa"]

    return {
        "total_bookings": len(rows),
        "total_seats_sold": total_seats,
        "total_revenue": paisa_to_rupees_str(total_revenue_paisa),
        "per_show": [
            {
                "show_id": k,
                "show_title": v["show_title"],
                "bookings": v["bookings"],
                "seats": v["seats"],
                "revenue": paisa_to_rupees_str(v["revenue_paisa"]),
            }
            for k, v in per_show.items()
        ],
    }


@app.get("/")
def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "docs": "/docs"}


@app.get("/admin")
def admin_page():
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.isfile(admin_path):
        return FileResponse(admin_path)
    raise HTTPException(404, "admin.html not found")
