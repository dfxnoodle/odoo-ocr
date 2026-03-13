"""
PaddleOCR-VL local extraction adapter — subprocess bridge edition.

Why a subprocess?
-----------------
PaddlePaddle wheels are only available for Python 3.9–3.13.
This application targets Python 3.14+, so PaddleOCR-VL cannot be installed
into the same virtual environment.  The solution is a thin bridge:

  main app (Python 3.14)
      └─ spawns subprocess ──▶ paddle_vl_worker.py (Python 3.13 venv)
                                   └─ imports PaddleOCRVL, runs inference on GPU/CPU
                                   └─ writes {"ok": true, "markdown": "...", "json_result": ...} to stdout

Setup (one-time, on the server)
--------------------------------
1. Create a dedicated venv using the highest supported Python (3.13 recommended):

       python3.13 -m venv /opt/paddle-venv

2. Install PaddlePaddle matching your hardware:

   NVIDIA Blackwell GPU (RTX 5060/5070/5080/5090 — sm_120, requires CUDA driver ≥ 580 / CUDA 12.9+):
       /opt/paddle-venv/bin/pip install paddlepaddle-gpu==3.2.1 \
           -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
       /opt/paddle-venv/bin/pip install 'paddleocr[doc-parser]'
       /opt/paddle-venv/bin/pip install 'numpy<2.0'   # PaddlePaddle 3.x requires numpy 1.x

   NVIDIA Ampere/Ada GPU (RTX 30xx/40xx — CUDA 12.3):
       /opt/paddle-venv/bin/pip install paddlepaddle-gpu==3.0.0 \
           -i https://www.paddlepaddle.org.cn/packages/stable/cu123/
       /opt/paddle-venv/bin/pip install 'paddleocr[doc-parser]'

   CPU only:
       /opt/paddle-venv/bin/pip install paddlepaddle 'paddleocr[doc-parser]'

3. Configure .env:

       PADDLE_VL_PYTHON=/opt/paddle-venv/bin/python
       PADDLE_VL_DEVICE=gpu          # or "gpu:1" for a specific card, "cpu"
       EXTRACTION_PROVIDER=paddle_vl

Notes
-----
- Model weights (~1 GB) are downloaded automatically on first use by PaddleOCR
  to ~/.paddleocr/ (or $PADDLE_HOME / $HF_HOME, per PaddleOCR 3.x config).
- The first subprocess call may take 30–90 s while the model loads.
- Subsequent calls reuse the OS disk cache so model weight loading is fast.
- PDFs are rasterised page-by-page before being passed to the worker; PyMuPDF
  is preferred with a pypdf fallback.
- The worker first attempts VQA mode (predict with a JSON extraction query).
  If the installed PaddleOCR version does not support VQA, it falls back to
  plain OCR markdown + regex field extraction.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import tempfile
from datetime import datetime as _dt

import structlog

from app.schemas.extraction import (
    ContainerSize,
    EIRExtraction,
    WeightEntry,
    WeightUnit,
)
from app.services.extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)

_PDF_DPI = 200  # PaddleOCR-VL is robust at moderate resolution

# Absolute path to the worker script (co-located with this file)
_WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "paddle_vl_worker.py")


# ── Extractor ─────────────────────────────────────────────────────────────────

class PaddleVLExtractor(BaseExtractor):
    """
    Runs PaddleOCR-VL through a subprocess using a Python 3.12/3.13 interpreter.

    Extraction strategy (in priority order):
      1. VQA mode — worker passes a JSON extraction prompt to PaddleOCRVL.predict()
         and returns a structured dict directly.  This gives Gemini-quality results.
      2. Regex fallback — if the installed PaddleOCR version doesn't support VQA,
         the worker returns OCR markdown and this module applies improved regex
         heuristics to find EIR fields.
    """

    provider_name = "paddle_vl"

    def _python_path(self) -> str:
        from app.core.config import get_settings
        return get_settings().paddle_vl_python

    def _device(self) -> str:
        from app.core.config import get_settings
        return get_settings().paddle_vl_device

    def _check_interpreter(self) -> None:
        """Raise ExtractionError with clear instructions if interpreter is missing."""
        py = self._python_path()
        bare_names = {"python3", "python3.13", "python3.12", "python3.11", "python3.10", "python3.9"}
        if not os.path.isfile(py) and py not in bare_names:
            raise ExtractionError(
                self.provider_name,
                f"PADDLE_VL_PYTHON={py!r} does not exist. "
                "Create a Python 3.13 venv and install PaddleOCR.\n"
                "Blackwell GPU (RTX 5060/5070/5080/5090):\n"
                "  python3.13 -m venv /opt/paddle-venv\n"
                "  /opt/paddle-venv/bin/pip install paddlepaddle-gpu==3.2.1 "
                "-i https://www.paddlepaddle.org.cn/packages/stable/cu129/\n"
                "  /opt/paddle-venv/bin/pip install 'paddleocr[doc-parser]'\n"
                "Then set PADDLE_VL_PYTHON=/opt/paddle-venv/bin/python in your .env",
            )

    # ── Public interface ───────────────────────────────────────────────────────

    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> EIRExtraction:
        if mime_type == "application/pdf":
            pages = _pdf_pages_to_png(file_bytes)
            img_bytes = pages[0]
        else:
            img_bytes = file_bytes
        return await self._extract_image(img_bytes, filename)

    async def extract_pages(
        self, file_bytes: bytes, filename: str, mime_type: str
    ) -> list[EIRExtraction]:
        results: list[EIRExtraction] = []
        async for _page, _total, extraction in self.extract_pages_stream(
            file_bytes, filename, mime_type
        ):
            results.append(extraction)
        return results

    async def extract_pages_stream(
        self, file_bytes: bytes, filename: str, mime_type: str
    ):
        if mime_type != "application/pdf":
            result = await self._extract_image(file_bytes, filename)
            yield 1, 1, result
            return

        page_images = _pdf_pages_to_png(file_bytes)
        total = len(page_images)
        log = logger.bind(provider=self.provider_name, filename=filename)
        log.info("PDF split for PaddleOCR-VL extraction", pages=total)

        for i, img_bytes in enumerate(page_images):
            page_label = f"{filename} [page {i + 1}]"
            log.info("Extracting page via PaddleOCR-VL", page=i + 1, total=total)
            extraction = await self._extract_image(img_bytes, page_label)
            yield i + 1, total, extraction

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _extract_image(self, img_bytes: bytes, label: str) -> EIRExtraction:
        self._check_interpreter()
        log = logger.bind(provider=self.provider_name, label=label, device=self._device())
        log.info("Spawning PaddleOCR-VL worker subprocess")

        suffix = _guess_suffix(img_bytes)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        try:
            markdown_text, json_result = await _run_worker(
                self._python_path(), tmp_path, label, self._device()
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if json_result is not None:
            log.info(
                "PaddleOCR-VL VQA extraction complete (structured JSON)",
                confidence=json_result.get("extraction_confidence"),
                container=json_result.get("container_number"),
            )
            extraction = _map_json_to_eir(json_result)
            extraction.provider_raw = {
                "mode": "vqa",
                "json_result": json_result,
                "markdown_preview": markdown_text[:500] if markdown_text else "",
            }
        else:
            log.debug("PaddleOCR-VL markdown received (OCR fallback)", length=len(markdown_text))
            extraction = _parse_eir_from_markdown(markdown_text)
            extraction.provider_raw = {
                "mode": "ocr_regex",
                "markdown_preview": markdown_text[:3000],
                "markdown_length": len(markdown_text),
            }
            log.info(
                "PaddleOCR-VL regex extraction complete",
                confidence=extraction.extraction_confidence,
                container=extraction.container_number,
            )

        return extraction


# ── Subprocess runner ─────────────────────────────────────────────────────────

async def _run_worker(
    python_path: str, image_path: str, label: str, device: str = "gpu"
) -> tuple[str, dict | None]:
    """
    Spawn the worker script and return (markdown_text, json_result).

    json_result is a dict if the worker succeeded in VQA mode, else None.
    """
    from app.core.config import get_settings
    mem_fraction = get_settings().paddle_vl_gpu_mem_fraction
    env = {**os.environ,
           "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
           "FLAGS_fraction_of_gpu_memory_to_use": str(mem_fraction),
           "FLAGS_initial_gpu_memory_in_mb": "0",
           "FLAGS_auto_growth_chunk_size_in_mb": "16",
           "FLAGS_eager_delete_tensor_gb": "0.0",
           "NO_COLOR": "1",
           "PYTHONUNBUFFERED": "1"}

    proc = await asyncio.create_subprocess_exec(
        python_path,
        _WORKER_SCRIPT,
        image_path,
        device,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()

    stdout_text = stdout_bytes.decode(errors="replace").strip()
    stderr_text = stderr_bytes.decode(errors="replace").strip()

    if stderr_text:
        logger.debug(
            "paddle_vl worker stderr",
            label=label,
            returncode=proc.returncode,
            stderr=stderr_text,
        )

    payload: dict | None = None
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        pass

    if proc.returncode != 0:
        if payload is not None and not payload.get("ok"):
            raise ExtractionError("paddle_vl", payload.get("error", "Unknown worker error"))
        detail = stderr_text or stdout_text or f"exit code {proc.returncode}"
        raise ExtractionError(
            "paddle_vl",
            f"Worker crashed for {label!r} (exit {proc.returncode}):\n{detail}",
        )

    if payload is None:
        raise ExtractionError(
            "paddle_vl",
            f"Worker returned non-JSON output: {stdout_text[:300]}",
        )

    if not payload.get("ok"):
        raise ExtractionError("paddle_vl", payload.get("error", "Unknown worker error"))

    markdown = payload.get("markdown", "")
    json_result = payload.get("json_result")  # None when worker used OCR fallback
    return markdown, json_result


# ── JSON → EIRExtraction (VQA path, mirrors vertex_gemini._map_to_schema) ─────

def _nullable_str(val) -> str | None:
    if val is None or (isinstance(val, str) and val.strip().lower() in {"null", "none", ""}):
        return None
    return str(val).strip() or None


def _map_json_to_eir(data: dict) -> EIRExtraction:
    """Map the structured JSON dict returned by VQA mode to EIRExtraction."""

    def optional_enum(enum_cls, val):
        if val is None:
            return None
        try:
            return enum_cls(str(val).upper())
        except ValueError:
            return None

    def parse_datetime(val) -> _dt | None:
        if not val or str(val).strip().lower() in {"null", "none", ""}:
            return None
        raw = str(val).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return _dt.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    def parse_weight(d) -> WeightEntry | None:
        if not d or not isinstance(d, dict):
            return None
        value = d.get("value")
        unit_raw = d.get("unit")
        unit = None
        if unit_raw and str(unit_raw).strip().lower() not in {"null", "none", ""}:
            try:
                unit = WeightUnit(str(unit_raw).upper())
            except ValueError:
                unit = WeightUnit.kg
        if value is None and unit is None:
            return None
        try:
            return WeightEntry(value=float(value) if value is not None else None, unit=unit)
        except (ValueError, TypeError):
            return None

    confidence_raw = data.get("extraction_confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else None
        if confidence is not None:
            confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = None

    langs = data.get("language_hints")
    if not isinstance(langs, list):
        langs = [langs] if langs else None

    return EIRExtraction(
        container_number=_nullable_str(data.get("container_number")),
        seal_number=_nullable_str(data.get("seal_number")),
        container_size=optional_enum(ContainerSize, data.get("container_size")),
        vehicle_number=_nullable_str(data.get("vehicle_number")),
        haulier=_nullable_str(data.get("haulier")),
        receipt_date=parse_datetime(data.get("receipt_date")),
        gross_weight=parse_weight(data.get("gross_weight")),
        extraction_confidence=confidence,
        language_hints=langs,
    )


# ── PDF → PNG (mirrors vertex_gemini.py strategy) ─────────────────────────────

def _pdf_pages_to_png(pdf_bytes: bytes) -> list[bytes]:
    try:
        import fitz  # PyMuPDF

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
        logger.warning("PyMuPDF rendering failed, trying pypdf", error=str(exc))

    try:
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
        logger.warning("pypdf page extraction failed, sending raw bytes", error=str(exc))

    return [pdf_bytes]


# ── Magic-byte suffix detection ───────────────────────────────────────────────

def _guess_suffix(data: bytes) -> str:
    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


# ── EIR field extraction from markdown text (OCR fallback) ───────────────────

def _preprocess_markdown(text: str) -> str:
    """
    Convert PaddleOCR markdown to a format friendly for regex field extraction.

    Key insight: PaddleOCR often encodes EIR fields as markdown table rows
    like `| SEAL NO | FX43274(B) |`.  Stripping `|` destroys this structure.
    Instead, we convert table rows to "LABEL : VALUE" lines, then collapse
    excess whitespace while preserving newlines so patterns can anchor on them.
    """
    lines = text.splitlines()
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "|" in stripped:
            # Extract cells from markdown table row, skip separator rows (----)
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            cells = [c for c in cells if not re.match(r"^[-:]+$", c)]
            if cells:
                result.append(" : ".join(cells))
                continue
        result.append(re.sub(r"[#*_`]+", " ", stripped))

    joined = "\n".join(result)
    # Collapse runs of spaces/tabs but preserve newlines
    joined = re.sub(r"[ \t]{2,}", " ", joined)
    return joined


def _parse_eir_from_markdown(text: str) -> EIRExtraction:
    """
    Extract EIR fields from the OCR markdown produced by PaddleOCR-VL.

    This is the fallback path used when PaddleOCR-VL does not support VQA mode.
    We preserve table structure during preprocessing and use wider regex patterns.
    """
    cleaned = _preprocess_markdown(text)

    def find(patterns: list[str]) -> str | None:
        for pat in patterns:
            # Try on preprocessed (table-aware) text first
            m = re.search(pat, cleaned, re.IGNORECASE | re.MULTILINE)
            if m:
                val = m.group(1).strip(" \t\r\n:-|")
                if val and val.lower() not in {"null", "none", "n/a", "-"}:
                    return val
            # Also try on original text as a safety net
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                val = m.group(1).strip(" \t\r\n:-|")
                if val and val.lower() not in {"null", "none", "n/a", "-"}:
                    return val
        return None

    # ── Container number ──────────────────────────────────────────────────────
    container_number = find([
        r"CONTAINER\s*NO[.:]?\s*:?\s*([A-Z]{4}\d{7})\b",
        r"\b([A-Z]{4}\d{7})\b",
    ])

    # ── Seal number ───────────────────────────────────────────────────────────
    seal_number = find([
        r"SEAL\s*NO[.:]?\s*:?\s*([A-Z0-9\-/()]+)",
        r"SEAL\s*NUMBER[:\s]+:?\s*([A-Z0-9\-/()]+)",
    ])

    # ── Container size ────────────────────────────────────────────────────────
    _size_raw = find([
        r"SIZE\s*/\s*TYPE[:\s]+:?\s*(\S+)",
        r"SIZE\s*[:\s]+:?\s*(\d{2}(?:HC)?)",
        r"\b(40HC|45HC|40\s*HC|45\s*HC)\b",
        r"\b(20|40|45)\s*(?:GP|DC|HC|OT|FR|RF)?\b",
    ])
    container_size: ContainerSize | None = None
    if _size_raw:
        _s = re.sub(r"\s+", "", _size_raw.upper())
        try:
            container_size = ContainerSize(_s)
        except ValueError:
            _num = re.match(r"(\d{2})(HC)?", _s)
            if _num:
                _key = _num.group(1) + ("HC" if _num.group(2) else "")
                try:
                    container_size = ContainerSize(_key)
                except ValueError:
                    pass

    # ── Vehicle / truck number ────────────────────────────────────────────────
    vehicle_number = find([
        r"VEHICLE\s*NO[.:]?\s*:?\s*([A-Z0-9\-\s]{3,20})",
        r"TRUCK\s*(?:PLATE|NO)[.:]?\s*:?\s*([A-Z0-9\-\s]{3,20})",
        r"PLATE\s*NO[.:]?\s*:?\s*([A-Z0-9\-\s]{3,20})",
    ])
    if vehicle_number:
        vehicle_number = vehicle_number.strip()

    # ── Haulier / trucking company ────────────────────────────────────────────
    haulier = find([
        r"HAULIER\s*:?\s*([^\n|,]{3,60})",
        r"HAULER\s*:?\s*([^\n|,]{3,60})",
        r"TRANSPORT(?:ER)?\s*:?\s*([^\n|,]{3,60})",
        r"TRUCKER\s*:?\s*([^\n|,]{3,60})",
    ])
    if haulier:
        haulier = haulier.strip()

    # ── Receipt / issue date ──────────────────────────────────────────────────
    receipt_date: _dt | None = None
    _date_raw = find([
        r"DATE\s*OF\s*ISSUE\s*:?\s*([0-9/\-.\s:]+)",
        r"ISSUE\s*DATE\s*:?\s*([0-9/\-.\s:]+)",
        r"DATE\s*:?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
    ])
    if _date_raw:
        _date_raw = _date_raw.strip()
        for fmt in (
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                receipt_date = _dt.strptime(_date_raw, fmt)
                break
            except ValueError:
                continue

    # ── Gross weight ──────────────────────────────────────────────────────────
    gross_weight: WeightEntry | None = None
    _wt_raw = find([
        r"(?:GROSS\s+)?WEIGHT\s*:?\s*([\d,.]+)\s*/?\s*VGM",
        r"(?:GROSS\s+)?WEIGHT\s*:?\s*([\d,.]+)\s*(KG|MT|LBS|TONS?)",
        r"VGM\s*:?\s*([\d,.]+)\s*(KG|MT|LBS)?",
        r"\b([\d,.]{4,})\s*(KG|MT)\b",
    ])
    _wt_unit_raw = find([
        r"(?:GROSS\s+)?WEIGHT[\s\S]{0,40}?(KG|MT|LBS)",
    ])
    if _wt_raw:
        try:
            _value = float(re.sub(r"[,\s]", "", _wt_raw))
            _unit: WeightUnit | None = None
            if _wt_unit_raw:
                try:
                    _unit = WeightUnit(_wt_unit_raw.upper())
                except ValueError:
                    _unit = WeightUnit.kg
            else:
                _unit = WeightUnit.kg
            gross_weight = WeightEntry(value=_value, unit=_unit)
        except (ValueError, AttributeError):
            pass

    found = sum(
        x is not None
        for x in [container_number, seal_number, vehicle_number, haulier, receipt_date]
    )
    confidence = round(min(0.5 + found * 0.09, 0.85), 2)

    return EIRExtraction(
        container_number=container_number,
        seal_number=seal_number,
        container_size=container_size,
        vehicle_number=vehicle_number,
        haulier=haulier,
        receipt_date=receipt_date,
        gross_weight=gross_weight,
        extraction_confidence=confidence,
        language_hints=_detect_languages(text),
    )


def _detect_languages(text: str) -> list[str]:
    langs: list[str] = ["en"]
    if re.search(r"[\u0600-\u06FF]", text):
        langs.append("ar")
    if re.search(r"[\u4E00-\u9FFF]", text):
        langs.append("zh")
    return langs
