"""Tests du chargement BigQuery (Jour 3) : client BigQuery simulé, zéro appel GCP."""

from google.cloud import bigquery

from src import load


class FauxJob:
    def result(self):
        return None


class FauxClient:
    """Enregistre les tables créées et les jobs de chargement lancés."""

    def __init__(self, *args, **kwargs):
        self.tables_creees = []
        self.chargements = []
        FauxClient.derniere_instance = self

    def create_table(self, table, exists_ok=False):
        assert exists_ok is True
        self.tables_creees.append(table)

    def load_table_from_json(self, rows, table_id, job_config):
        self.chargements.append((rows, table_id, job_config))
        return FauxJob()


def _mode_gcp(monkeypatch):
    monkeypatch.setattr(load.settings, "gcp_project_id", "proj")
    monkeypatch.setattr(load.bigquery, "Client", FauxClient)


def test_mode_local_ne_touche_pas_bigquery(monkeypatch):
    monkeypatch.setattr(load.settings, "gcp_project_id", "local")
    assert load.load_partition_idempotent([{"a": 1}], "20261125") == 1
    assert load.append_quarantine([{"raw": {}, "reason": "x"}], run_id="r") == 1


def test_trusted_write_truncate_sur_la_partition(monkeypatch):
    _mode_gcp(monkeypatch)
    n = load.load_partition_idempotent([{"station_id": "FR-0075"}], "20261125")
    c = FauxClient.derniere_instance

    assert n == 1
    # Tables créées explicitement, la Trusted partitionnée par jour sur observed_at
    trusted = c.tables_creees[0]
    assert trusted.table_id == "observations"
    assert trusted.time_partitioning.field == "observed_at"
    # Chargement de LA partition du jour, en écrasement (idempotence)
    _, table_id, cfg = c.chargements[0]
    assert table_id == "proj.weather_trusted__UAT.observations$20261125"
    assert cfg.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE


def test_quarantaine_write_append_avec_motif(monkeypatch):
    _mode_gcp(monkeypatch)
    n = load.append_quarantine([{"raw": {"t": 999}, "reason": "trop chaud"}], run_id="r1")
    rows, table_id, cfg = FauxClient.derniere_instance.chargements[0]

    assert n == 1
    assert table_id == "proj.weather_quarantine__UAT.weather_errors"
    assert cfg.write_disposition == bigquery.WriteDisposition.WRITE_APPEND
    assert rows[0]["run_id"] == "r1" and rows[0]["reason"] == "trop chaud"


def test_lot_vide_ne_charge_rien(monkeypatch):
    _mode_gcp(monkeypatch)
    assert load.load_partition_idempotent([], "20261125") == 0
    assert load.append_quarantine([], run_id="r") == 0
