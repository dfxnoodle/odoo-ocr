"""
Pydantic schemas for EIR document extraction.

All fields are Optional because confidence and completeness vary across document types.
The human validation step in the UI is the authoritative correction gate.
"""

from __future__ import annotations

from datetime import datetime
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


class WeightEntry(BaseModel):
    value: float | None = None
    unit: WeightUnit | None = None


class EIRExtraction(BaseModel):
    """
    Fields extracted from an EIR, scoped to exactly what the Odoo Gate-IN
    record requires.
    """

    # ── Container ─────────────────────────────────────────────────────────────
    container_number: str | None = Field(default=None, description="CONTAINER NO. — ISO 6346, e.g. MSCU1234567")
    seal_number: str | None = Field(default=None, description="SEAL NO.")
    container_size: ContainerSize | None = Field(default=None, description="SIZE / TYPE — size portion: 20, 40, 45…")

    # ── Transport ─────────────────────────────────────────────────────────────
    vehicle_number: str | None = Field(default=None, description="VEHICLE NO. — truck plate")
    haulier: str | None = Field(default=None, description="HAULIER — maps to Supplier in Odoo Gate-IN")

    # ── Gate timestamp ────────────────────────────────────────────────────────
    receipt_date: datetime | None = Field(
        default=None,
        description="DATE OF ISSUE — full datetime including time component, e.g. 2026-03-12T03:21:00",
    )

    # ── Weight ────────────────────────────────────────────────────────────────
    gross_weight: WeightEntry | None = Field(default=None, description="WEIGHT — value and unit (KG or MT)")

    # ── Extraction metadata ───────────────────────────────────────────────────
    extraction_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Overall confidence score from the extraction provider",
    )
    provider_raw: dict[str, Any] | None = Field(
        default=None, description="Raw provider response for audit purposes",
    )
    language_hints: list[str] | None = Field(
        default=None, description="Detected languages in document, e.g. ['en', 'ar']",
    )


class ExtractionRequest(BaseModel):
    provider: str | None = Field(default=None, description="Override extraction provider for this request")


class ExtractionResponse(BaseModel):
    request_id: str
    filename: str
    extraction: EIRExtraction
    warnings: list[str] = Field(default_factory=list)
    provider_used: str
    page_number: int = Field(default=1, description="1-based page index within the original document")
    total_pages: int = Field(default=1, description="Total pages extracted from the document")


class ExtractionBatchResponse(BaseModel):
    """Returned by the extract endpoint; always contains one item per document page."""
    request_id: str
    filename: str
    provider_used: str
    total_pages: int
    extractions: list[ExtractionResponse] = Field(default_factory=list)


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
