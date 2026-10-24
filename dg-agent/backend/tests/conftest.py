"""Test fixtures.

IMPORTANT: Entries created here are TEST FIXTURES that exercise engine logic (matching,
status composition, edition control). They are labelled as such, live in a source with
verification_status='test_fixture', and are NOT validated regulatory outcomes.
DG_TEST_MODE lets these fixtures exercise the 'verified' code paths; it is never set in
deployments.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DG_TEST_MODE"] = "1"
os.environ["DEMO_USERS_PASSWORD"] = "test-password-123"
os.environ["SEED_DEMO_DATA"] = "1"
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["FRONTEND_DIST"] = f"{_tmp}/no-frontend"

import datetime as dt  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DGEntry, RegulatorySource, RuleTable  # noqa: E402

FIXTURE_SOURCE = "TEST-FIXTURE-IMDG"

# Synthetic fixture rows (logic tests only — NOT regulatory data).
FIXTURE_ENTRIES = [
    dict(un_number="UN9001", proper_shipping_name="FIXTURE LIQUID ALPHA", hazard_class="3",
         subsidiary_hazards=["6.1"], packing_groups=["II"], special_provisions=[], marine_pollutant="-"),
    dict(un_number="UN9002", proper_shipping_name="FIXTURE GAS BETA", hazard_class="2.2",
         subsidiary_hazards=[], packing_groups=[], special_provisions=[], marine_pollutant="-"),
    dict(un_number="UN9003", proper_shipping_name="FIXTURE SUBSTANCE, N.O.S.", hazard_class="8",
         subsidiary_hazards=[], packing_groups=["I", "II", "III"], special_provisions=["999"], marine_pollutant="P"),
    dict(un_number="UN9004", proper_shipping_name="FIXTURE SULPHUR COMPOUND", hazard_class="4.1",
         subsidiary_hazards=[], packing_groups=["III"], special_provisions=[], marine_pollutant="-"),
]


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        with SessionLocal() as db:
            src = RegulatorySource(code=FIXTURE_SOURCE, rule_set="IMDG", publisher="TEST FIXTURE",
                                   title="Synthetic fixture dataset", edition="test", verification_status="test_fixture",
                                   status="current", content_loaded=True)
            iata = RegulatorySource(code="TEST-FIXTURE-IATA", rule_set="IATA", publisher="TEST FIXTURE",
                                    title="Synthetic IATA fixture", edition="test", verification_status="test_fixture",
                                    status="current", content_loaded=True)
            old = RegulatorySource(code="TEST-FIXTURE-OLD", rule_set="IMDG", publisher="TEST FIXTURE",
                                   title="Superseded fixture edition", edition="old", verification_status="test_fixture",
                                   status="current", effective_date=dt.date(2000, 1, 1),
                                   expiry_date=dt.date(2001, 1, 1), content_loaded=True)
            db.add_all([src, iata, old])
            db.flush()
            for e in FIXTURE_ENTRIES:
                db.add(DGEntry(source_id=src.id, verification_status="verified", section_ref="fixture", **e))
            # Same UN number in IATA fixture with a different packing group to test mode separation.
            db.add(DGEntry(source_id=iata.id, verification_status="verified", section_ref="fixture",
                           un_number="UN9001", proper_shipping_name="FIXTURE LIQUID ALPHA", hazard_class="3",
                           subsidiary_hazards=["6.1"], packing_groups=["III"], special_provisions=[]))
            db.add(DGEntry(source_id=old.id, verification_status="verified", un_number="UN9005",
                           proper_shipping_name="FIXTURE OLD ENTRY", hazard_class="9", subsidiary_hazards=[],
                           packing_groups=["III"], special_provisions=[]))
            demo_table = db.query(RuleTable).filter_by(code="IMDG-SEG-DEMO").one()
            db.add(RuleTable(code="IMDG-SEG-FIXTURE", source_id=src.id, name="fixture table",
                             data=demo_table.data, complete=True, verification_status="verified"))
            db.commit()
        yield c


def login(client, who: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{who}@demo.local", "password": "test-password-123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def op(client):
    return login(client, "operator")


@pytest.fixture(scope="session")
def approver(client):
    return login(client, "approver")
