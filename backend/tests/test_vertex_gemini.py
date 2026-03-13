"""
Unit tests for the Vertex Gemini adapter's JSON parsing and schema mapping.
These tests do NOT call the real Vertex API.
"""

import pytest

from app.services.extractors.vertex_gemini import (
    _map_to_schema,
    _nullable_str,
    _parse_json_response,
    _parse_weight,
)
from app.schemas.extraction import WeightUnit
from app.services.extractors.base import ExtractionError


class TestParseJsonResponse:
    def test_plain_json(self):
        raw = '{"container_number": "MSCU1234567"}'
        result = _parse_json_response(raw, "vertex")
        assert result["container_number"] == "MSCU1234567"

    def test_json_with_markdown_fence(self):
        raw = '```json\n{"container_number": "TCKU7654321"}\n```'
        result = _parse_json_response(raw, "vertex")
        assert result["container_number"] == "TCKU7654321"

    def test_json_with_bare_fence(self):
        raw = '```\n{"shipping_line": "MSC"}\n```'
        result = _parse_json_response(raw, "vertex")
        assert result["shipping_line"] == "MSC"

    def test_invalid_json_raises(self):
        with pytest.raises(ExtractionError) as exc_info:
            _parse_json_response("not json at all", "vertex")
        assert "vertex" in str(exc_info.value)


class TestNullableStr:
    def test_normal_string(self):
        assert _nullable_str("  hello  ") == "hello"

    def test_null_string(self):
        assert _nullable_str("null") is None
        assert _nullable_str("NULL") is None
        assert _nullable_str("none") is None
        assert _nullable_str("") is None

    def test_none_input(self):
        assert _nullable_str(None) is None


class TestParseWeight:
    def test_valid_weight(self):
        w = _parse_weight({"value": 22000, "unit": "KG"})
        assert w is not None
        assert w.value == 22000.0
        assert w.unit == WeightUnit.kg

    def test_none_input(self):
        assert _parse_weight(None) is None

    def test_empty_dict(self):
        assert _parse_weight({}) is None

    def test_unknown_unit_falls_back(self):
        w = _parse_weight({"value": 100, "unit": "TONS"})
        assert w is not None
        assert w.unit is None

    def test_lbs_unit(self):
        w = _parse_weight({"value": 50000, "unit": "LBS"})
        assert w.unit == WeightUnit.lbs


class TestMapToSchema:
    def test_full_payload(self):
        data = {
            "container_number": "MSCU1234567",
            "seal_number": "SL001",
            "container_size": "40",
            "container_type": "GP",
            "condition": "CLEAN",
            "shipping_line": "MSC",
            "vessel_name": "MSC ANNA",
            "voyage_number": "V001",
            "bill_of_lading": "BL001",
            "booking_number": "BK001",
            "port_of_loading": "AEJEA",
            "port_of_discharge": "SAJED",
            "gross_weight": {"value": 22000, "unit": "KG"},
            "net_weight": {"value": 18000, "unit": "KG"},
            "tare_weight": {"value": 4000, "unit": "KG"},
            "receipt_date": "2025-03-01",
            "discharge_date": None,
            "shipper": "ACME CORP",
            "consignee": "LOCAL CO",
            "commodity": "General Cargo",
            "package_count": 100,
            "package_type": "CARTONS",
            "extraction_confidence": 0.92,
            "language_hints": ["en", "ar"],
        }
        e = _map_to_schema(data)
        assert e.container_number == "MSCU1234567"
        assert e.container_size.value == "40"
        assert e.gross_weight.value == 22000.0
        assert e.gross_weight.unit == WeightUnit.kg
        assert e.receipt_date.isoformat() == "2025-03-01"
        assert e.extraction_confidence == 0.92
        assert "ar" in e.language_hints

    def test_nulls_are_none(self):
        e = _map_to_schema({"container_number": "null", "vessel_name": None})
        assert e.container_number is None
        assert e.vessel_name is None

    def test_confidence_clamped_to_range(self):
        e = _map_to_schema({"extraction_confidence": 1.5})
        assert e.extraction_confidence == 1.0
        e2 = _map_to_schema({"extraction_confidence": -0.5})
        assert e2.extraction_confidence == 0.0

    def test_invalid_date_becomes_none(self):
        e = _map_to_schema({"receipt_date": "not-a-date"})
        assert e.receipt_date is None
