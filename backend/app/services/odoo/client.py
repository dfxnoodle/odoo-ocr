"""
Odoo XML-RPC client.

Maintains a single authenticated session per process and retries transient failures.
Supports Odoo 14+ (the xmlrpc.client stdlib module covers all Odoo XML-RPC versions).
"""

from __future__ import annotations

import xmlrpc.client
from functools import cached_property
from typing import Any

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.config import get_settings
from app.schemas.extraction import EIRExtraction, WeightEntry

logger = structlog.get_logger(__name__)


class OdooConnectionError(Exception):
    pass


class OdooAuthError(Exception):
    pass


class OdooClient:
    """Thread-safe (per-process) Odoo XML-RPC client with lazy auth."""

    def __init__(self) -> None:
        self._uid: int | None = None

    @cached_property
    def _common(self) -> xmlrpc.client.ServerProxy:
        settings = get_settings()
        return xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/common")

    @cached_property
    def _models(self) -> xmlrpc.client.ServerProxy:
        settings = get_settings()
        return xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/object")

    def _authenticate(self) -> int:
        settings = get_settings()
        if not all([settings.odoo_url, settings.odoo_db, settings.odoo_username, settings.odoo_password]):
            raise OdooAuthError("Odoo connection settings are not fully configured.")
        try:
            uid = self._common.authenticate(
                settings.odoo_db, settings.odoo_username, settings.odoo_password, {}
            )
        except Exception as exc:
            raise OdooConnectionError(f"Cannot reach Odoo at {settings.odoo_url}: {exc}") from exc

        if not uid:
            raise OdooAuthError(
                f"Odoo authentication failed for user '{settings.odoo_username}' "
                f"on database '{settings.odoo_db}'."
            )
        return uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            self._uid = self._authenticate()
        return self._uid

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((xmlrpc.client.Fault, ConnectionError)),
        reraise=True,
    )
    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        settings = get_settings()
        return self._models.execute_kw(
            settings.odoo_db, self.uid, settings.odoo_password,
            model, method, list(args), kwargs,
        )

    def search_read(self, model: str, domain: list, fields: list[str], limit: int = 1) -> list[dict]:
        return self.execute(model, "search_read", domain, fields=fields, limit=limit)

    def create(self, model: str, values: dict) -> int:
        return self.execute(model, "create", values)

    def resolve_many2one(self, model: str, field_value: str, name_field: str = "name") -> int | None:
        """Search for a record by name and return its ID, or None if not found."""
        results = self.search_read(model, [(name_field, "ilike", field_value)], ["id"], limit=1)
        return results[0]["id"] if results else None

    def check_duplicate(self, model: str, domain: list) -> int | None:
        results = self.search_read(model, domain, ["id"], limit=1)
        return results[0]["id"] if results else None


_client: OdooClient | None = None


def get_odoo_client() -> OdooClient:
    global _client
    if _client is None:
        _client = OdooClient()
    return _client


class EIRToOdooMapper:
    """
    Maps an EIRExtraction to Odoo field values for a target model.

    Extend the `_field_map` or override `map` for custom Odoo configurations.
    The default mapping targets `stock.picking` (receipts/transfers).
    Models and field names must match your Odoo instance's custom fields.
    """

    def map(
        self, extraction: EIRExtraction, model: str, client: OdooClient
    ) -> tuple[dict[str, Any], list[str], dict[str, str]]:
        """
        Returns (values_dict, warnings, unresolved_refs).

        values_dict: ready to pass to client.create()
        warnings: non-fatal issues found during mapping
        unresolved_refs: field_name -> raw_value for Many2one fields that couldn't be resolved
        """
        warnings: list[str] = []
        unresolved: dict[str, str] = {}
        values: dict[str, Any] = {}

        def set_field(odoo_field: str, value: Any) -> None:
            if value is not None:
                values[odoo_field] = value

        def resolve_m2o(odoo_field: str, odoo_model: str, raw_value: str | None) -> None:
            if raw_value is None:
                return
            rec_id = client.resolve_many2one(odoo_model, raw_value)
            if rec_id:
                values[odoo_field] = rec_id
            else:
                warnings.append(f"Could not resolve {odoo_field}='{raw_value}' in {odoo_model}")
                unresolved[odoo_field] = raw_value

        # Direct string/scalar fields (adjust field names to your Odoo custom fields)
        set_field("x_container_number", extraction.container_number)
        set_field("x_seal_number", extraction.seal_number)
        set_field("x_container_size", extraction.container_size.value if extraction.container_size else None)
        set_field("x_container_type", extraction.container_type.value if extraction.container_type else None)
        set_field("x_condition", extraction.condition)
        set_field("x_vessel_name", extraction.vessel_name)
        set_field("x_voyage_number", extraction.voyage_number)
        set_field("x_bill_of_lading", extraction.bill_of_lading)
        set_field("x_booking_number", extraction.booking_number)
        set_field("x_port_of_loading", extraction.port_of_loading)
        set_field("x_port_of_discharge", extraction.port_of_discharge)
        set_field("x_commodity", extraction.commodity)

        if extraction.receipt_date is not None:
            values["scheduled_date"] = str(extraction.receipt_date)

        # Weight fields
        def weight_val(entry: WeightEntry | None) -> float | None:
            return entry.value if entry and entry.value is not None else None

        set_field("x_gross_weight", weight_val(extraction.gross_weight))
        set_field("x_net_weight", weight_val(extraction.net_weight))
        set_field("x_tare_weight", weight_val(extraction.tare_weight))

        # Many2one resolution
        resolve_m2o("x_shipping_line_id", "res.partner", extraction.shipping_line)
        resolve_m2o("partner_id", "res.partner", extraction.consignee or extraction.shipper)

        if not values:
            warnings.append("No fields could be mapped – check that Odoo custom fields exist.")

        return values, warnings, unresolved
