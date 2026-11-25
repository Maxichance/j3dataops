"""Ingestion HTTP résiliente depuis l'API Open-Meteo (timeouts + retries)."""

import logging
import time
from datetime import datetime

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def ymd_to_iso_date(partition_ymd: str) -> str:
    """Convertit '20261125' en '2026-11-25' (format attendu par Open-Meteo)."""
    return datetime.strptime(partition_ymd, "%Y%m%d").date().isoformat()


def fetch_city_weather(
    lat: float, lon: float, partition_ymd: str | None = None, max_retries: int = 3
) -> dict:
    """Appelle Open-Meteo avec timeout explicite et backoff exponentiel (2s, 4s...).

    Avec `partition_ymd`, on demande EXACTEMENT cette journée : BigQuery refuse de
    charger dans la partition $YYYYMMDD des lignes datées d'un autre jour.
    """
    params: dict = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m",
        "timezone": "UTC",
    }
    if partition_ymd:
        jour = ymd_to_iso_date(partition_ymd)
        params["start_date"] = jour
        params["end_date"] = jour
    else:
        params["forecast_days"] = 1

    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=settings.http_timeout_sec) as client:
                response = client.get(settings.source_api_url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError):
            if attempt == max_retries:
                logger.error("Échec d'ingestion API après %s tentatives", attempt)
                raise
            attente = 2**attempt
            logger.warning("Erreur HTTP transitoire, nouvelle tentative dans %ss", attente)
            time.sleep(attente)

    return {}  # pragma: no cover


def parse_open_meteo_payload(payload: dict, station_id: str) -> list[dict]:
    """Convertit la réponse horaire d'Open-Meteo en liste d'observations brutes."""
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    humidities = hourly.get("relative_humidity_2m", [])

    records: list[dict] = []
    for obs_time, temp, hum in zip(times, temps, humidities, strict=False):
        # Open-Meteo renvoie des dates UTC sans 'Z' : on le rend explicite
        iso_utc = obs_time if obs_time.endswith("Z") else f"{obs_time}Z"
        records.append(
            {
                "station_id": station_id,
                "observed_at": iso_utc,
                "temperature_c": temp,
                "humidity_pct": hum,
            }
        )
    return records
