"""Tests de l'ingestion Open-Meteo (Jour 3) : client HTTP simulé, zéro réseau."""

import httpx

from src import ingest


def test_ymd_to_iso_date():
    assert ingest.ymd_to_iso_date("20261125") == "2026-11-25"


def test_fetch_demande_exactement_la_journee_de_partition(monkeypatch):
    """start_date = end_date = partition : sinon BigQuery refuse le chargement $YYYYMMDD."""
    vus = {}

    def handler(request: httpx.Request) -> httpx.Response:
        vus.update(dict(request.url.params))
        return httpx.Response(200, json={"hourly": {}})

    vrai_client = httpx.Client
    monkeypatch.setattr(
        ingest.httpx,
        "Client",
        lambda **kw: vrai_client(transport=httpx.MockTransport(handler), **kw),
    )

    assert ingest.fetch_city_weather(48.85, 2.35, partition_ymd="20261125") == {"hourly": {}}
    assert vus["start_date"] == "2026-11-25"
    assert vus["end_date"] == "2026-11-25"
    assert vus["timezone"] == "UTC"
    assert "forecast_days" not in vus


def test_parse_ajoute_le_suffixe_utc():
    payload = {
        "hourly": {
            "time": ["2026-11-25T00:00"],
            "temperature_2m": [7.1],
            "relative_humidity_2m": [88],
        }
    }
    rows = ingest.parse_open_meteo_payload(payload, station_id="FR-0075")
    assert rows == [
        {
            "station_id": "FR-0075",
            "observed_at": "2026-11-25T00:00Z",
            "temperature_c": 7.1,
            "humidity_pct": 88,
        }
    ]
