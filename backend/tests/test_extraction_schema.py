"""
Unit tests for the Pydantic extraction schema and schema mapping utilities.
"""

from datetime import date

import pytest

from app.schemas.extraction import (
    CommitRequest,
    ContainerSize,
    ContainerType,
    EIRExtraction,
    ExtractionResponse,
    OdooCommitResult,
    WeightEntry,
    WeightUnit,
)


class TestEIRExtraction:
    def test_fully_populated(self):
        e = EIRExtraction(
            container_number="MSCU1234567",
            seal_number="SL001",
            container_size=ContainerSize.s40,
            container_type=ContainerType.gp,
            condition="CLEAN",
            shipping_line="MSC",
            vessel_name="MSC ANNA",
            voyage_number="VO123",
            bill_of_lading="BL0001",
            booking_number="BK0001",
            port_of_loading="AEJEA",
            port_of_discharge="SAJED",
            gross_weight=WeightEntry(value=22000.0, unit=WeightUnit.kg),
            net_weight=WeightEntry(value=18000.0, unit=WeightUnit.kg),
            tare_weight=WeightEntry(value=4000.0, unit=WeightUnit.kg),
            receipt_date=date(2025, 3, 1),
            extraction_confidence=0.95,
            language_hints=["en", "ar"],
        )
        assert e.container_number == "MSCU1234567"
        assert e.gross_weight.value == 22000.0
        assert e.extraction_confidence == 0.95

    def test_all_nullable(self):
        """Minimum valid extraction is an empty shell."""
        e = EIRExtraction()
        assert e.container_number is None
        assert e.gross_weight is None

    def test_confidence_clamped_by_ge_le(self):
        with pytest.raises(Exception):
            EIRExtraction(extraction_confidence=1.5)

    def test_weight_entry_partial(self):
        w = WeightEntry(value=None, unit=WeightUnit.kg)
        assert w.value is None

    def test_extraction_response_roundtrip(self):
        extraction = EIRExtraction(container_number="TCKU3456789")
        resp = ExtractionResponse(
            request_id="abc-123",
            filename="test.pdf",
            extraction=extraction,
            warnings=["Missing vessel name"],
            provider_used="vertex_gemini",
        )
        data = resp.model_dump()
        assert data["extraction"]["container_number"] == "TCKU3456789"
        assert data["warnings"][0] == "Missing vessel name"


class TestCommitRequest:
    def test_defaults(self):
        req = CommitRequest(
            request_id="req-1",
            extraction=EIRExtraction(container_number="MSCU0000001"),
        )
        assert req.odoo_model == "stock.picking"
        assert req.dry_run is False

    def test_dry_run_flag(self):
        req = CommitRequest(
            request_id="req-2",
            extraction=EIRExtraction(),
            dry_run=True,
        )
        assert req.dry_run is True


class TestOdooCommitResult:
    def test_success_with_record(self):
        result = OdooCommitResult(
            success=True,
            record_id=42,
            odoo_model="stock.picking",
            dry_run=False,
        )
        assert result.record_id == 42
        assert result.warnings == []
        assert result.unresolved_refs == {}

    def test_dry_run_no_record(self):
        result = OdooCommitResult(
            success=True,
            record_id=None,
            odoo_model="stock.picking",
            dry_run=True,
            warnings=["No partner resolved"],
            unresolved_refs={"partner_id": "UNKNOWN CO"},
        )
        assert result.record_id is None
        assert len(result.unresolved_refs) == 1
