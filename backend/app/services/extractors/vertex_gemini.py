"""
Gemini extraction adapter using the google-genai SDK.

Authentication is resolved in priority order:
  1. GOOGLE_API_KEY env var  →  Google AI API (api.generativeai.google.com)
  2. GOOGLE_CLOUD_PROJECT    →  Vertex AI (service account / Workload Identity)

Set GOOGLE_API_KEY in your .env for the standard API-key path.
"""

from __future__ import annotations

import json
import re

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.schemas.extraction import (
    ContainerSize,
    ContainerType,
    EIRExtraction,
    WeightEntry,
    WeightUnit,
)
from app.services.extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)

_EXTRACTION_PROMPT = """
You are an expert logistics document parser specialising in Equipment Interchange Receipts (EIR),
gate passes, and container receipts. The document may be in English, Arabic, or a mixture of both.

Extract ALL of the following fields from the document and return ONLY a valid JSON object.
If a field cannot be found or determined, set its value to null.

Return this exact JSON structure (no extra text, no markdown fences):
{
  "container_number": "<ISO 6346 format, e.g. MSCU1234567>",
  "seal_number": "<string or null>",
  "container_size": "<one of: 20, 40, 45, 40HC, 45HC, OTHER, or null>",
  "container_type": "<one of: GP, HC, RF, OT, FR, TK, OTHER, or null>",
  "condition": "<e.g. CLEAN, DAMAGED, or null>",
  "shipping_line": "<string or null>",
  "vessel_name": "<string or null>",
  "voyage_number": "<string or null>",
  "bill_of_lading": "<string or null>",
  "booking_number": "<string or null>",
  "port_of_loading": "<string or null>",
  "port_of_discharge": "<string or null>",
  "place_of_receipt": "<string or null>",
  "gross_weight": {"value": <number or null>, "unit": "<KG, LBS, or MT or null>"},
  "net_weight": {"value": <number or null>, "unit": "<KG, LBS, or MT or null>"},
  "tare_weight": {"value": <number or null>, "unit": "<KG, LBS, or MT or null>"},
  "receipt_date": "<YYYY-MM-DD or null>",
  "discharge_date": "<YYYY-MM-DD or null>",
  "shipper": "<string or null>",
  "consignee": "<string or null>",
  "notify_party": "<string or null>",
  "commodity": "<string or null>",
  "package_count": <integer or null>,
  "package_type": "<string or null>",
  "extraction_confidence": <float 0.0–1.0 representing your confidence>,
  "language_hints": ["<language codes detected, e.g. en, ar>"]
}

Important rules:
- Normalize Arabic numerals to Western numerals.
- Container number must match pattern: 4 letters + 7 digits (e.g. MSCU1234567).
- Dates must be in ISO 8601 format YYYY-MM-DD.
- Weight values must be plain numbers (no units in the value field).
""".strip()


def _build_client():
    """
    Return a configured google-genai Client.

    Prefers API key auth. Falls back to Vertex AI (ADC / Workload Identity)
    if GOOGLE_API_KEY is not set but GOOGLE_CLOUD_PROJECT is.
    """
    try:
        from google import genai
    except ImportError as exc:
        raise ExtractionError(
            "vertex_gemini",
            "google-genai is not installed. Run: pip install google-genai",
            cause=exc,
        ) from exc

    settings = get_settings()

    if settings.google_api_key:
        return genai.Client(api_key=settings.google_api_key)

    if settings.google_cloud_project:
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location or "us-central1",
        )

    raise ExtractionError(
        "vertex_gemini",
        "No Gemini credentials found. Set GOOGLE_API_KEY (API key) "
        "or GOOGLE_CLOUD_PROJECT (Vertex AI / ADC) in your .env.",
    )


class VertexGeminiExtractor(BaseExtractor):
    """Sends the document as an inline image/PDF to Gemini and parses the JSON response."""

    provider_name = "vertex_gemini"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> EIRExtraction:
        from google.genai import types

        settings = get_settings()
        log = logger.bind(provider=self.provider_name, filename=filename, mime_type=mime_type)
        log.info("Starting Gemini extraction")

        if mime_type == "application/pdf":
            file_bytes, mime_type = _pdf_first_page_to_png(file_bytes)

        client = _build_client()

        image_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

        try:
            response = await client.aio.models.generate_content(
                model=settings.vertex_model,
                contents=[image_part, _EXTRACTION_PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=2048,
                ),
            )
        except Exception as exc:
            log.error("Gemini API call failed", error=str(exc))
            raise ExtractionError(self.provider_name, f"API call failed: {exc}", cause=exc) from exc

        raw_text = response.text.strip()
        log.debug("Raw Gemini response received", length=len(raw_text))

        parsed = _parse_json_response(raw_text, self.provider_name)
        extraction = _map_to_schema(parsed)
        extraction.provider_raw = {"raw_text": raw_text}
        log.info("Extraction complete", confidence=extraction.extraction_confidence)
        return extraction


def _pdf_first_page_to_png(pdf_bytes: bytes) -> tuple[bytes, str]:
    """Render the first page of a PDF to PNG for multimodal input."""
    try:
        import io
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)

        try:
            import fitz  # PyMuPDF – faster rasterisation if available
            doc = fitz.open(stream=buf.read(), filetype="pdf")
            pix = doc[0].get_pixmap(dpi=200)
            return pix.tobytes("png"), "image/png"
        except ImportError:
            return buf.read(), "application/pdf"
    except Exception as exc:
        logger.warning("PDF to PNG conversion failed, passing PDF directly", error=str(exc))
        return pdf_bytes, "application/pdf"


def _parse_json_response(raw_text: str, provider: str) -> dict:
    """Strip markdown fences and parse JSON from the model response."""
    text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(provider, f"Failed to parse JSON response: {exc}", cause=exc) from exc


def _nullable_str(val) -> str | None:
    if val is None or (isinstance(val, str) and val.strip().lower() in {"null", "none", ""}):
        return None
    return str(val).strip()


def _parse_weight(data: dict | None) -> WeightEntry | None:
    if not data:
        return None
    value = data.get("value")
    unit_raw = data.get("unit")
    unit = None
    if unit_raw:
        try:
            unit = WeightUnit(str(unit_raw).upper())
        except ValueError:
            unit = None
    if value is None and unit is None:
        return None
    return WeightEntry(value=float(value) if value is not None else None, unit=unit)


def _map_to_schema(data: dict) -> EIRExtraction:
    """Map raw parsed dict to a validated EIRExtraction."""

    def optional_enum(enum_cls, val):
        if val is None:
            return None
        try:
            return enum_cls(str(val).upper())
        except ValueError:
            return None

    from datetime import date as date_cls

    def parse_date(val) -> date_cls | None:
        if not val or str(val).strip().lower() in {"null", "none", ""}:
            return None
        try:
            return date_cls.fromisoformat(str(val))
        except ValueError:
            return None

    langs = data.get("language_hints")
    if not isinstance(langs, list):
        langs = [langs] if langs else None

    confidence_raw = data.get("extraction_confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else None
        if confidence is not None:
            confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = None

    return EIRExtraction(
        container_number=_nullable_str(data.get("container_number")),
        seal_number=_nullable_str(data.get("seal_number")),
        container_size=optional_enum(ContainerSize, data.get("container_size")),
        container_type=optional_enum(ContainerType, data.get("container_type")),
        condition=_nullable_str(data.get("condition")),
        shipping_line=_nullable_str(data.get("shipping_line")),
        vessel_name=_nullable_str(data.get("vessel_name")),
        voyage_number=_nullable_str(data.get("voyage_number")),
        bill_of_lading=_nullable_str(data.get("bill_of_lading")),
        booking_number=_nullable_str(data.get("booking_number")),
        port_of_loading=_nullable_str(data.get("port_of_loading")),
        port_of_discharge=_nullable_str(data.get("port_of_discharge")),
        place_of_receipt=_nullable_str(data.get("place_of_receipt")),
        gross_weight=_parse_weight(data.get("gross_weight")),
        net_weight=_parse_weight(data.get("net_weight")),
        tare_weight=_parse_weight(data.get("tare_weight")),
        receipt_date=parse_date(data.get("receipt_date")),
        discharge_date=parse_date(data.get("discharge_date")),
        shipper=_nullable_str(data.get("shipper")),
        consignee=_nullable_str(data.get("consignee")),
        notify_party=_nullable_str(data.get("notify_party")),
        commodity=_nullable_str(data.get("commodity")),
        package_count=data.get("package_count"),
        package_type=_nullable_str(data.get("package_type")),
        extraction_confidence=confidence,
        language_hints=langs,
    )
