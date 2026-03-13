"""
Unit tests for EIRToOdooMapper with a mocked OdooClient.
"""

from unittest.mock import MagicMock

import pytest

from app.schemas.extraction import (
    ContainerSize,
    ContainerType,
    EIRExtraction,
    WeightEntry,
    WeightUnit,
)
from app.services.odoo.client import EIRToOdooMapper


def make_client(partner_id: int | None = 7, m2o_default: int | None = None):
    """Return a mock OdooClient with configurable lookup results."""
    client = MagicMock()
    client.resolve_many2one.return_value = m2o_default
    client.check_duplicate.return_value = None
    return client


class TestEIRToOdooMapper:
    def setup_method(self):
        self.mapper = EIRToOdooMapper()

    def _extraction(self, **kwargs) -> EIRExtraction:
        defaults = dict(
            container_number="MSCU1234567",
            container_size=ContainerSize.s40,
            container_type=ContainerType.gp,
            condition="CLEAN",
            shipping_line="MSC",
            vessel_name="MSC ANNA",
            voyage_number="V001",
            gross_weight=WeightEntry(value=22000.0, unit=WeightUnit.kg),
            consignee="LOCAL CO LTD",
        )
        defaults.update(kwargs)
        return EIRExtraction(**defaults)

    def test_direct_fields_mapped(self):
        client = make_client()
        values, warnings, unresolved = self.mapper.map(self._extraction(), "stock.picking", client)
        assert values["x_container_number"] == "MSCU1234567"
        assert values["x_vessel_name"] == "MSC ANNA"
        assert values["x_gross_weight"] == 22000.0
        assert values["x_container_size"] == "40"

    def test_m2o_resolved_partner(self):
        client = make_client()
        client.resolve_many2one.return_value = 42
        values, warnings, unresolved = self.mapper.map(
            self._extraction(consignee="LOCAL CO LTD"), "stock.picking", client
        )
        assert values["partner_id"] == 42
        assert not unresolved

    def test_m2o_unresolved_emits_warning(self):
        client = make_client(m2o_default=None)
        values, warnings, unresolved = self.mapper.map(
            self._extraction(shipping_line="UNKNOWN LINE"), "stock.picking", client
        )
        assert "x_shipping_line_id" in unresolved
        assert any("x_shipping_line_id" in w for w in warnings)

    def test_null_fields_not_in_values(self):
        client = make_client()
        e = EIRExtraction(container_number="MSCU9999999")
        values, _, _ = self.mapper.map(e, "stock.picking", client)
        assert "x_vessel_name" not in values
        assert "x_gross_weight" not in values

    def test_receipt_date_sets_scheduled_date(self):
        from datetime import date
        client = make_client()
        e = self._extraction(receipt_date=date(2025, 6, 15))
        values, _, _ = self.mapper.map(e, "stock.picking", client)
        assert values["scheduled_date"] == "2025-06-15"
