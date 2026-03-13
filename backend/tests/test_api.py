"""
Integration-style tests for the FastAPI endpoints using TestClient.
No real API calls are made – all external services are mocked.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.extraction import EIRExtraction, ExtractionResponse


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "extraction_provider" in data


class TestExtract:
    def _mock_extraction(self) -> EIRExtraction:
        return EIRExtraction(
            container_number="MSCU1234567",
            shipping_line="MSC",
            extraction_confidence=0.90,
        )

    def test_missing_file_returns_422(self, client):
        resp = client.post("/api/v1/extract")
        assert resp.status_code == 422

    def test_unsupported_mime_returns_415(self, client):
        resp = client.post(
            "/api/v1/extract",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 415

    def test_successful_extraction(self, client):
        mock_extraction = self._mock_extraction()

        mock_extractor = MagicMock()
        mock_extractor.provider_name = "vertex_gemini"
        mock_extractor.extract = AsyncMock(return_value=mock_extraction)

        with patch("app.api.v1.extract.get_extractor", return_value=mock_extractor):
            png_bytes = _minimal_png()
            resp = client.post(
                "/api/v1/extract",
                files={"file": ("test.png", png_bytes, "image/png")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["extraction"]["container_number"] == "MSCU1234567"
        assert data["provider_used"] == "vertex_gemini"
        assert "request_id" in data

    def test_extraction_provider_error_returns_502(self, client):
        from app.services.extractors.base import ExtractionError

        mock_extractor = MagicMock()
        mock_extractor.provider_name = "vertex_gemini"
        mock_extractor.extract = AsyncMock(
            side_effect=ExtractionError("vertex_gemini", "API quota exceeded")
        )

        with patch("app.api.v1.extract.get_extractor", return_value=mock_extractor):
            resp = client.post(
                "/api/v1/extract",
                files={"file": ("test.png", _minimal_png(), "image/png")},
            )

        assert resp.status_code == 502


class TestOdooCommit:
    def _commit_payload(self, dry_run=False):
        return {
            "request_id": "test-req-001",
            "extraction": {"container_number": "MSCU1234567"},
            "odoo_model": "stock.picking",
            "dry_run": dry_run,
        }

    def test_dry_run_does_not_call_odoo(self, client):
        mock_client = MagicMock()

        with patch("app.api.v1.odoo.get_odoo_client", return_value=mock_client):
            resp = client.post("/api/v1/odoo/commit", json=self._commit_payload(dry_run=True))

        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["record_id"] is None
        mock_client.create.assert_not_called()

    def test_commit_creates_record(self, client):
        mock_client = MagicMock()
        mock_client.check_duplicate.return_value = None
        mock_client.create.return_value = 99
        mock_client.resolve_many2one.return_value = None

        with patch("app.api.v1.odoo.get_odoo_client", return_value=mock_client):
            resp = client.post("/api/v1/odoo/commit", json=self._commit_payload(dry_run=False))

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["record_id"] == 99

    def test_auth_error_returns_401(self, client):
        from app.services.odoo.client import OdooAuthError

        with patch("app.api.v1.odoo.get_odoo_client", side_effect=OdooAuthError("Bad creds")):
            resp = client.post("/api/v1/odoo/commit", json=self._commit_payload())

        assert resp.status_code == 401

    def test_connection_error_returns_503(self, client):
        from app.services.odoo.client import OdooConnectionError

        with patch(
            "app.api.v1.odoo.get_odoo_client",
            side_effect=OdooConnectionError("Timeout"),
        ):
            resp = client.post("/api/v1/odoo/commit", json=self._commit_payload())

        assert resp.status_code == 503


def _minimal_png() -> bytes:
    """Return a 1×1 transparent PNG (smallest valid PNG)."""
    return bytes([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
        0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
        0x89, 0x00, 0x00, 0x00, 0x0a, 0x49, 0x44, 0x41,
        0x54, 0x78, 0x9c, 0x62, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
        0x42, 0x60, 0x82,
    ])
