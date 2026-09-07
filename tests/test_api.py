import pytest
from fastapi.testclient import TestClient
from factlens.api import app
from factlens import db

client = TestClient(app)

def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "llm_mode" in data

def test_api_cases():
    res = client.get("/api/cases")
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) >= 4
    categories = {c["case_category"] for c in cases}
    assert "corroboration" in categories
    assert "contextual_difference" in categories
    assert "genuine_contradiction" in categories
    assert "extraction_failure" in categories

def test_api_seed_starter_cases():
    res = client.post("/api/seed_starter_cases")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["seeded_cases"] >= 4

def test_api_facts_and_comparisons():
    # After seeding, facts and comparisons should be queryable
    res_facts = client.get("/api/facts")
    assert res_facts.status_code == 200
    facts = res_facts.json()
    assert len(facts) > 0

    res_cmp = client.get("/api/comparisons")
    assert res_cmp.status_code == 200
    cmps = res_cmp.json()
    assert len(cmps) > 0

    res_fail = client.get("/api/failures")
    assert res_fail.status_code == 200
    fails = res_fail.json()
    assert len(fails) > 0

def test_api_upload_invalid_file():
    fake_pdf = b"Not a valid PDF header"
    res = client.post(
        "/api/upload",
        files=[("files", ("fake.pdf", fake_pdf, "application/pdf"))]
    )
    assert res.status_code == 400
    assert "magic header" in res.json()["detail"]
