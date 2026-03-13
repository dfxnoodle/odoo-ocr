from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtractionProvider(str, Enum):
    vertex = "vertex"
    azure = "azure"
    paddle = "paddle"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_title: str = "EIR OCR Platform"
    app_version: str = "0.1.0"
    debug: bool = False
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:4173"])
    log_level: str = "INFO"

    # Extraction
    extraction_provider: ExtractionProvider = ExtractionProvider.vertex
    extraction_max_file_size_mb: int = 20

    # Gemini / Google AI API
    # Standard Google SDK env var names – picked up automatically by google-genai
    google_api_key: str = ""                     # API key auth (Google AI API)
    google_cloud_project: str = ""               # Vertex AI project (optional)
    google_cloud_location: str = "global"        # Region or "global" for API key path
    vertex_model: str = "gemini-2.0-flash"       # Model name passed to generate_content

    # Azure Document Intelligence
    azure_docintel_endpoint: str = ""
    azure_docintel_key: str = ""
    azure_docintel_model_id: str = "prebuilt-document"

    # Odoo
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""
    odoo_timeout: int = 30
    odoo_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
