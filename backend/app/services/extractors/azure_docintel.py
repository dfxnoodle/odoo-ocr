"""
Azure Document Intelligence extraction adapter (stub).

To activate, install: azure-ai-formrecognizer>=3.3.0
and set AZURE_DOCINTEL_ENDPOINT + AZURE_DOCINTEL_KEY in your .env.
"""

from __future__ import annotations

import structlog

from app.schemas.extraction import EIRExtraction
from app.services.extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)


class AzureDocIntelExtractor(BaseExtractor):
    provider_name = "azure_docintel"

    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> EIRExtraction:
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.azure_docintel_endpoint or not settings.azure_docintel_key:
            raise ExtractionError(
                self.provider_name,
                "AZURE_DOCINTEL_ENDPOINT and AZURE_DOCINTEL_KEY must be configured.",
            )

        try:
            from azure.ai.formrecognizer.aio import DocumentAnalysisClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise ExtractionError(
                self.provider_name,
                "azure-ai-formrecognizer is not installed. Run: pip install azure-ai-formrecognizer",
                cause=exc,
            ) from exc

        log = logger.bind(provider=self.provider_name, filename=filename)
        log.info("Starting Azure Document Intelligence extraction")

        client = DocumentAnalysisClient(
            endpoint=settings.azure_docintel_endpoint,
            credential=AzureKeyCredential(settings.azure_docintel_key),
        )

        async with client:
            poller = await client.begin_analyze_document(
                settings.azure_docintel_model_id, document=file_bytes
            )
            result = await poller.result()

        extraction = _map_azure_result(result)
        log.info("Azure extraction complete")
        return extraction


def _map_azure_result(result) -> EIRExtraction:
    """
    Map Azure Document Intelligence AnalyzeResult to EIRExtraction.
    Field names must be aligned with your trained custom model or the prebuilt response.
    Extend this mapping as you label more training documents.
    """
    fields = {}
    if result.documents:
        fields = result.documents[0].fields or {}

    def get_str(key: str) -> str | None:
        f = fields.get(key)
        return f.content if f else None

    def get_float(key: str) -> float | None:
        f = fields.get(key)
        try:
            return float(f.content) if f else None
        except (TypeError, ValueError):
            return None

    from app.schemas.extraction import WeightEntry, WeightUnit

    return EIRExtraction(
        container_number=get_str("ContainerNumber"),
        seal_number=get_str("SealNumber"),
        shipping_line=get_str("ShippingLine"),
        vessel_name=get_str("VesselName"),
        voyage_number=get_str("VoyageNumber"),
        bill_of_lading=get_str("BillOfLading"),
        booking_number=get_str("BookingNumber"),
        port_of_loading=get_str("PortOfLoading"),
        port_of_discharge=get_str("PortOfDischarge"),
        gross_weight=WeightEntry(value=get_float("GrossWeight"), unit=WeightUnit.kg),
        extraction_confidence=0.85,
        provider_raw={"document_count": len(result.documents) if result.documents else 0},
    )
