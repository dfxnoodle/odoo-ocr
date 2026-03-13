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

_PDF_DPI = 300  # DPI for rasterising PDF pages; 300 gives good OCR quality
from app.services.extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)

_EXTRACTION_PROMPT = """
You are an expert document parser for Equipment Interchange Receipts (EIR) issued by container
terminals such as Khorfakkan Container Terminal. The document may contain English and/or Arabic text,
rotated labels, stamps, and handwritten annotations.

Extract ONLY the fields listed below — do not invent or add any other fields.
If a field is not present in the document, set it to null.
Return ONLY a valid JSON object with no extra text and no markdown fences.

=== FIELDS TO EXTRACT ===

  "container_number"    — label "CONTAINER NO."  — ISO 6346: 4 letters + 7 digits, e.g. MSCU1234567
  "container_size"      — label "SIZE / TYPE"     — size portion only: one of 20, 40, 45, 40HC, 45HC, OTHER
  "container_type"      — label "SIZE / TYPE"     — type portion only: one of GP, HC, RF, OT, FR, TK, OTHER
  "seal_number"         — label "SEAL NO."
  "eir_number"          — label "EIR NO."
  "in_out_direction"    — label "IN/OUT"          — value must be exactly "IN" or "OUT"
  "designation"         — label "DESIGNATION"     — container designation / classification code
  "shipping_line"       — label "SHIPPING LINE"
  "vessel_name"         — label "VESSEL/VOYAGE"   — vessel name portion (word-based name, e.g. "MSC MAYA")
  "voyage_number"       — label "VESSEL/VOYAGE"   — voyage number portion (alphanumeric code, e.g. "QC604B")
  "booking_number"      — label "RELEASE ORDER /BOOKING"
  "gross_weight"        — label "WEIGHT"          — numeric value and unit; if shown as "24420/VGM", value=24420, unit="KG"
  "receipt_date"        — label "DATE OF ISSUE"   — ISO 8601 YYYY-MM-DD
  "discharge_date"      — label "DATE OF DISCHARGE" — ISO 8601 YYYY-MM-DD
  "do_validity_date"    — label "D.O VALIDITY"    — ISO 8601 YYYY-MM-DD
  "do_number"           — label "D.O. NO."
  "bill_of_entry_number"— label "BILL OF ENTRY NO."
  "consignee"           — label "CONSIGNEE/SHIPPER" — full text of that field
  "agent"               — label "AGENT"
  "haulier"             — label "HAULIER"
  "vehicle_number"      — label "VEHICLE NO."
  "remarks"             — label "REMARKS"
  "user_name"           — label "USER NAME" or "SYSTEM GENERATED USER NAME"

=== OUTPUT FORMAT ===

{
  "container_number":     "<string or null>",
  "container_size":       "<20 | 40 | 45 | 40HC | 45HC | OTHER | null>",
  "container_type":       "<GP | HC | RF | OT | FR | TK | OTHER | null>",
  "seal_number":          "<string or null>",
  "eir_number":           "<string or null>",
  "in_out_direction":     "<IN | OUT | null>",
  "designation":          "<string or null>",
  "shipping_line":        "<string or null>",
  "vessel_name":          "<string or null>",
  "voyage_number":        "<string or null>",
  "booking_number":       "<string or null>",
  "gross_weight":         {"value": <number or null>, "unit": "<KG | LBS | MT | null>"},
  "receipt_date":         "<YYYY-MM-DD or null>",
  "discharge_date":       "<YYYY-MM-DD or null>",
  "do_validity_date":     "<YYYY-MM-DD or null>",
  "do_number":            "<string or null>",
  "bill_of_entry_number": "<string or null>",
  "consignee":            "<string or null>",
  "agent":                "<string or null>",
  "haulier":              "<string or null>",
  "vehicle_number":       "<string or null>",
  "remarks":              "<string or null>",
  "user_name":            "<string or null>",
  "extraction_confidence": <float 0.0–1.0>,
  "language_hints":       ["<en | ar | ...>"]
}

=== RULES ===
- Normalize Arabic-Indic numerals (٠١٢٣٤٥٦٧٨٩) to Western numerals.
- Container number: 4 letters + 7 digits including the check digit (e.g. MSCU1234567).
- All dates: convert DD-MM-YYYY or DD/MM/YYYY to ISO 8601 YYYY-MM-DD.
- VESSEL/VOYAGE combined field: if the value is a single alphanumeric code (e.g. "MALXQC604B"),
  put the full value in vessel_name and set voyage_number to null unless you can clearly separate them.
- SIZE / TYPE combined field: "20 GP" → size="20", type="GP".
- Read ALL text including rotated labels, header text, and stamps.
- Do NOT extract any field not listed above.
""".strip()


def _build_client():
    """
    Return a configured google-genai Client.

    Priority:
      1. GOOGLE_CLOUD_PROJECT set  →  Vertex AI endpoint (ADC / Workload Identity).
         Vertex AI models such as gemini-3.x-*-preview are only served here.
      2. GOOGLE_API_KEY only       →  Google AI API endpoint.
         Suitable for stable public models; has geographic restrictions.
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

    if settings.google_cloud_project:
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location or "global",
        )

    if settings.google_api_key:
        return genai.Client(api_key=settings.google_api_key)

    raise ExtractionError(
        "vertex_gemini",
        "No Gemini credentials found. Set GOOGLE_CLOUD_PROJECT (Vertex AI / ADC) "
        "or GOOGLE_API_KEY (Google AI API) in your .env.",
    )


class VertexGeminiExtractor(BaseExtractor):
    """Sends the document as an inline image/PNG to Gemini and parses the JSON response."""

    provider_name = "vertex_gemini"

    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> EIRExtraction:
        """Extract from a single image (or single-page PDF fallback)."""
        if mime_type == "application/pdf":
            pages = _pdf_pages_to_png(file_bytes)
            img_bytes = pages[0]
        else:
            img_bytes = file_bytes
        return await self._extract_image(img_bytes, filename)

    async def extract_pages(
        self, file_bytes: bytes, filename: str, mime_type: str
    ) -> list[EIRExtraction]:
        """Extract each PDF page as a separate EIRExtraction."""
        results: list[EIRExtraction] = []
        async for _page, _total, extraction in self.extract_pages_stream(
            file_bytes, filename, mime_type
        ):
            results.append(extraction)
        return results

    async def extract_pages_stream(
        self, file_bytes: bytes, filename: str, mime_type: str
    ):
        """Yield (page_num, total, EIRExtraction) as each page finishes — true streaming."""
        from collections.abc import AsyncGenerator  # noqa: F401 (type hint only)

        if mime_type != "application/pdf":
            result = await self._extract_image(file_bytes, filename)
            yield 1, 1, result
            return

        page_images = _pdf_pages_to_png(file_bytes)
        total = len(page_images)
        log = logger.bind(provider=self.provider_name, filename=filename)
        log.info("PDF split into pages for streaming extraction", pages=total)

        for i, img_bytes in enumerate(page_images):
            page_label = f"{filename} [page {i + 1}]"
            log.info("Extracting page", page=i + 1, total=total)
            extraction = await self._extract_image(img_bytes, page_label)
            yield i + 1, total, extraction

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _extract_image(self, img_bytes: bytes, label: str) -> EIRExtraction:
        """Send a single PNG image to Gemini and return the parsed extraction."""
        from google.genai import types

        settings = get_settings()
        log = logger.bind(provider=self.provider_name, label=label)
        log.info("Sending image to Gemini")

        client = _build_client()
        image_part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")

        try:
            response = await client.aio.models.generate_content(
                model=settings.vertex_model,
                contents=[image_part, _EXTRACTION_PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
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
        log.info("Page extraction complete", confidence=extraction.extraction_confidence)
        return extraction


def _pdf_pages_to_png(pdf_bytes: bytes) -> list[bytes]:
    """
    Render every page of a PDF to a PNG at _PDF_DPI resolution.

    Falls back to a single-page approach using pypdf if PyMuPDF is unavailable,
    or returns the raw PDF bytes wrapped in a list as a last resort.
    """
    try:
        import fitz  # PyMuPDF

        # Suppress MuPDF's stderr noise for benign structural metadata warnings
        # (e.g. "No common ancestor in structure tree") that don't affect rendering.
        fitz.TOOLS.mupdf_display_errors(False)
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages: list[bytes] = []
            mat = fitz.Matrix(_PDF_DPI / 72, _PDF_DPI / 72)
            for page in doc:
                pix = page.get_pixmap(matrix=mat)
                pages.append(pix.tobytes("png"))
        finally:
            fitz.TOOLS.mupdf_display_errors(True)
        if pages:
            return pages
    except Exception as exc:
        logger.warning("PyMuPDF rendering failed, falling back to pypdf", error=str(exc))

    # Fallback: extract each page as a single-page PDF and let Gemini parse them
    try:
        import io
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            writer = PdfWriter()
            writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            pages.append(buf.getvalue())
        if pages:
            return pages
    except Exception as exc:
        logger.warning("pypdf page extraction failed, sending raw PDF", error=str(exc))

    return [pdf_bytes]


def _parse_json_response(raw_text: str, provider: str) -> dict:
    """Strip markdown fences and parse JSON from the model response.

    Gemini occasionally wraps the object in an array ([{...}]); unwrap it
    so downstream code always receives a plain dict.
    """
    text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(provider, f"Failed to parse JSON response: {exc}", cause=exc) from exc

    if isinstance(parsed, list):
        if parsed and isinstance(parsed[0], dict):
            return parsed[0]
        raise ExtractionError(provider, f"Unexpected JSON array with no dict element: {parsed!r}")

    if not isinstance(parsed, dict):
        raise ExtractionError(provider, f"Expected a JSON object, got {type(parsed).__name__}: {parsed!r}")

    return parsed


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

    in_out_raw = _nullable_str(data.get("in_out_direction"))
    in_out = in_out_raw.upper() if in_out_raw and in_out_raw.upper() in {"IN", "OUT"} else in_out_raw

    return EIRExtraction(
        # Container
        container_number=_nullable_str(data.get("container_number")),
        container_size=optional_enum(ContainerSize, data.get("container_size")),
        container_type=optional_enum(ContainerType, data.get("container_type")),
        seal_number=_nullable_str(data.get("seal_number")),
        # Gate / EIR
        eir_number=_nullable_str(data.get("eir_number")),
        in_out_direction=in_out,
        designation=_nullable_str(data.get("designation")),
        # Shipping
        shipping_line=_nullable_str(data.get("shipping_line")),
        vessel_name=_nullable_str(data.get("vessel_name")),
        voyage_number=_nullable_str(data.get("voyage_number")),
        booking_number=_nullable_str(data.get("booking_number")),
        # Weight
        gross_weight=_parse_weight(data.get("gross_weight")),
        # Dates
        receipt_date=parse_date(data.get("receipt_date")),
        discharge_date=parse_date(data.get("discharge_date")),
        do_validity_date=parse_date(data.get("do_validity_date")),
        # Documents
        do_number=_nullable_str(data.get("do_number")),
        bill_of_entry_number=_nullable_str(data.get("bill_of_entry_number")),
        # Parties
        consignee=_nullable_str(data.get("consignee")),
        agent=_nullable_str(data.get("agent")),
        haulier=_nullable_str(data.get("haulier")),
        vehicle_number=_nullable_str(data.get("vehicle_number")),
        # Misc
        remarks=_nullable_str(data.get("remarks")),
        user_name=_nullable_str(data.get("user_name")),
        extraction_confidence=confidence,
        language_hints=langs,
    )
