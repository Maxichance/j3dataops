"""Point d'entrée FastAPI : GET /health et POST /run (pipeline complet)."""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.ingest import fetch_city_weather, parse_open_meteo_payload
from src.load import append_quarantine, load_partition_idempotent, save_raw_to_gcs
from src.transform import split_valid_and_quarantine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Weather Quality Micro-Pipeline")


def today_ymd() -> str:
    """Date du jour UTC au format YYYYMMDD (partition par défaut)."""
    return datetime.now(UTC).strftime("%Y%m%d")


class TriggerPayload(BaseModel):
    """Paramètres de POST /run (Scheduler, Pub/Sub ou curl)."""

    station_id: str = Field(default="FR-0075", pattern=r"^FR-[0-9]{4}$")
    latitude: float = 48.8566
    longitude: float = 2.3522
    partition_ymd: str = Field(default_factory=today_ymd, pattern=r"^[0-9]{8}$")


@app.get("/health")
def health() -> dict:
    """Sonde de santé pour Cloud Run et les tests."""
    return {"status": "ok"}


@app.post("/run")
def run_pipeline(req: TriggerPayload) -> dict:
    """Exécute une passe complète du pipeline qualité météo."""
    run_id = str(uuid.uuid4())

    # 1. Ingestion de la journée demandée + archivage brut
    try:
        raw_payload = fetch_city_weather(
            req.latitude, req.longitude, partition_ymd=req.partition_ymd
        )
    except httpx.HTTPError as exc:
        # 503 = panne transitoire : Pub/Sub / Scheduler relanceront
        logger.error("Source météo indisponible (run_id=%s)", run_id)
        raise HTTPException(status_code=503, detail="Source météo indisponible") from exc
    gcs_uri = save_raw_to_gcs(raw_payload, run_id=run_id, partition_ymd=req.partition_ymd)

    # 2. Contrat Pydantic + séparation Quarantaine (code Jour 2)
    records = parse_open_meteo_payload(raw_payload, station_id=req.station_id)
    valid_rows, bad_rows = split_valid_and_quarantine(records)

    # 3. Chargement idempotent (Trusted) + rejets (Quarantaine)
    loaded = load_partition_idempotent(valid_rows, partition_ymd=req.partition_ymd)
    quarantined = append_quarantine(bad_rows, run_id=run_id)

    logger.info(
        "Run terminé run_id=%s partition=%s loaded=%s quarantined=%s",
        run_id,
        req.partition_ymd,
        loaded,
        quarantined,
    )
    return {
        "run_id": run_id,
        "station_id": req.station_id,
        "partition_ymd": req.partition_ymd,
        "raw_uri": gcs_uri,
        "loaded": loaded,
        "quarantined": quarantined,
    }
