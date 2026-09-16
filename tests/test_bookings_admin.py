import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Isolate the DB per test run so tests don't pollute each other or the
    # real dev database.
    from pricing import db as db_module
    db_module.configure(str(tmp_path / "test_bookings.db"))

    from api.main import app
    return TestClient(app)


def test_book_requires_name_and_phone(client):
    res = client.post(
        "/shows/fri-night-avengers/book",
        json={"tickets": {"Gold": 1}, "customer_name": "", "phone": "9876543210"},
    )
    assert res.status_code == 400

    res2 = client.post(
        "/shows/fri-night-avengers/book",
        json={"tickets": {"Gold": 1}, "customer_name": "Asha Rao", "phone": "123"},
    )
    assert res2.status_code == 400


def test_book_persists_and_admin_can_see_it(client):
    res = client.post(
        "/shows/fri-night-avengers/book",
        json={
            "tickets": {"Gold": 2},
            "is_member": True,
            "apply_festival_discount": True,
            "customer_name": "Asha Rao",
            "phone": "9876543210",
        },
    )
    assert res.status_code == 200

    # cannot view admin data without logging in
    unauth = client.get("/admin/bookings")
    assert unauth.status_code == 401

    login = client.post("/admin/login", json={"username": "1234", "password": "1234"})
    assert login.status_code == 200
    token = login.json()["token"]

    bookings = client.get("/admin/bookings", headers={"X-Admin-Token": token})
    assert bookings.status_code == 200
    data = bookings.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Asha Rao"
    assert data[0]["phone"] == "9876543210"
    assert data[0]["tickets"] == {"Gold": 2}

    summary = client.get("/admin/summary", headers={"X-Admin-Token": token})
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_bookings"] == 1
    assert s["total_seats_sold"] == 2


def test_admin_login_rejects_bad_credentials(client):
    res = client.post("/admin/login", json={"username": "wrong", "password": "wrong"})
    assert res.status_code == 401


def test_admin_token_invalid_after_logout(client):
    login = client.post("/admin/login", json={"username": "1234", "password": "1234"})
    token = login.json()["token"]
    ok = client.get("/admin/bookings", headers={"X-Admin-Token": token})
    assert ok.status_code == 200

    client.post("/admin/logout", headers={"X-Admin-Token": token})
    after = client.get("/admin/bookings", headers={"X-Admin-Token": token})
    assert after.status_code == 401
