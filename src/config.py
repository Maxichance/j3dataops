"""Configuration 12-Factor : tout vient des variables d'environnement."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    """Paramètres injectés via variables d'environnement ou fichier .env."""

    # "local" permet de tester le service sans compte GCP
    gcp_project_id: str = "local"
    bq_dataset_trusted: str = "weather_trusted__UAT"
    bq_dataset_quarantine: str = "weather_quarantine__UAT"
    gcs_raw_bucket: str = ""
    source_api_url: str = "https://api.open-meteo.com/v1/forecast"
    http_timeout_sec: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = PipelineSettings()
