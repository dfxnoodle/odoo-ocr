"""
Pydantic schemas for EIR document extraction.

All fields are Optional because confidence and completeness vary across document types.
The human validation step in the UI is the authoritative correction gate.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WeightUnit(str, Enum):
    kg = "KG"
    lbs = "LBS"
    mt = "MT"


class ContainerSize(str, Enum):
    s20 = "20"
    s40 = "40"
    s45 = "45"
    hc40 = "40HC"
    hc45 = "45HC"
    other = "OTHER"


class ContainerType(str, Enum):
    gp = "GP"
    hc = "HC"
    reefer = "RF"
    open_top = "OT"
    flat_rack = "FR"
    tank = "TK"
    other = "OTHER"


class FieldConfidence(BaseModel):
    value: str | float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_text: str | None = None


class WeightEntry(BaseModel):
    value: float | None = None
    unit: WeightUnit | None = None


class EIRExtraction(BaseModel):
    """Structured output from the OCR/LLM extraction pipeline."""

    # Container identification
    container_number: str | None = Field(default=None, description="ISO 6346 container number, e.g. MSCU1234567")
    seal_number: str | None = None
    container_size: ContainerSize | None = None
    container_type: ContainerType | None = None
    condition: str | None = Field(default=None, description="Container condition on receipt, e.g. CLEAN, DAMAGED")

    # Shipping references
    shipping_line: str | None = None
    vessel_name: str | None = None
    voyage_number: str | None = None
    bill_of_lading: str | None = None
    booking_number: str | None = None

    # Ports / routing
    port_of_loading: str | None = None
    port_of_discharge: str | None = None
    place_of_receipt: str | None = None

    # Weight
    gross_weight: WeightEntry | None = None
    net_weight: WeightEntry | None = None
    tare_weight: WeightEntry | None = None

    # Dates
    receipt_date: date | None = None
    discharge_date: date | None = None

    # Parties
    shipper: str | None = None
    consignee: str | None = None
    notify_party: str | None = None

    # Commodity / cargo
    commodity: str | None = None
    package_count: int | None = None
    package_type: str | None = None

    # Metadata from extraction
    extraction_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Overall confidence score from the extraction provider"
    )
    provider_raw: dict[str, Any] | None = Field(
        default=None, description="Raw provider response for audit purposes"
    )
    language_hints: list[str] | None = Field(
        default=None, description="Detected languages in document, e.g. ['en', 'ar']"
    )


class ExtractionRequest(BaseModel):
    provider: str | None = Field(default=None, description="Override extraction provider for this request")


class ExtractionResponse(BaseModel):
    request_id: str
    filename: str
    extraction: EIRExtraction
    warnings: list[str] = Field(default_factory=list)
    provider_used: str


class CommitRequest(BaseModel):
    request_id: str = Field(description="Tracks provenance back to the original extract call")
    extraction: EIRExtraction
    odoo_model: str = Field(default="stock.picking", description="Target Odoo model to push the record into")
    dry_run: bool = Field(default=False, description="Validate mapping without writing to Odoo")


class OdooCommitResult(BaseModel):
    success: bool
    record_id: int | None = None
    odoo_model: str
    dry_run: bool
    warnings: list[str] = Field(default_factory=list)
    unresolved_refs: dict[str, str] = Field(
        default_factory=dict,
        description="Field name -> unresolved value that needs manual Many2one lookup"
    )
