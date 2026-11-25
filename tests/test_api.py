"""Tests de l'API FastAPI (Jour 3) : zéro appel réseau ni GCP."""

import httpx
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_run_separe_valides_et_quarantaine(monkeypatch):
    """1 mesure saine + 1 aberrante (+999 °C) : 1 chargée, 1 en quarantaine."""
    fausse_reponse = {
        "hourly": {
            "time": ["2026-11-25T10:00", "2026-11-25T11:00"],
            "temperature_2m": [18.5, 999.0],
            "relative_humidity_2m": [60.0, 55.0],
        }
    }
    monkeypatch.setattr("src.main.fetch_city_weather", lambda lat, lon, **_: fausse_reponse)

    resp = client.post("/run", json={"station_id": "FR-0075", "partition_ymd": "20261125"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["loaded"] == 1
    assert body["quarantined"] == 1


def test_run_rejette_payload_invalide():
    resp = client.post("/run", json={"station_id": "PARIS", "partition_ymd": "2026-11-25"})
    assert resp.status_code == 422


def test_run_partition_par_defaut_transmise_a_l_ingestion(monkeypatch):
    """Sans partition_ymd : jour UTC courant, transmis à l'ingestion."""
    appels = {}

    def faux_fetch(lat, lon, partition_ymd=None):
        appels["partition_ymd"] = partition_ymd
        return {"hourly": {"time": [], "temperature_2m": [], "relative_humidity_2m": []}}

    monkeypatch.setattr("src.main.fetch_city_weather", faux_fetch)
    monkeypatch.setattr("src.main.today_ymd", lambda: "20261125")

    resp = client.post("/run", json={})

    assert resp.status_code == 200
    assert appels["partition_ymd"] == "20261125"


def test_run_503_si_source_indisponible(monkeypatch):
    def fetch_en_panne(lat, lon, **_):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("src.main.fetch_city_weather", fetch_en_panne)
    assert client.post("/run", json={}).status_code == 503
