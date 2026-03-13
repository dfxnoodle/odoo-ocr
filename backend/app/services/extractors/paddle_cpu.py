"""
CPU-optimized PaddleOCR extraction adapter (stub).

To activate:
  pip install paddlepaddle paddleocr
Set EXTRACTION_PROVIDER=paddle in your .env.
Expected latency: 2-5s per page on Azure D-series CPUs.
"""

from __future__ import annotations

import structlog

from app.schemas.extraction import EIRExtraction
from app.services.extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)


class PaddleCpuExtractor(BaseExtractor):
    provider_name = "paddle_cpu"

    def __init__(self) -> None:
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore[import]
            except ImportError as exc:
                raise ExtractionError(
                    self.provider_name,
                    "paddleocr is not installed. Run: pip install paddleocr paddlepaddle",
                    cause=exc,
                ) from exc
            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
        return self._ocr

    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> EIRExtraction:
        import asyncio
        import io

        from PIL import Image

        log = logger.bind(provider=self.provider_name, filename=filename)
        log.info("Starting PaddleOCR CPU extraction")

        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")

        loop = asyncio.get_event_loop()
        raw_result = await loop.run_in_executor(None, self._run_ocr, image)

        text_lines = [item[1][0] for block in raw_result for item in block if item[1]]
        full_text = "\n".join(text_lines)

        log.debug("PaddleOCR raw text", lines=len(text_lines))
        extraction = _parse_text_heuristics(full_text)
        extraction.provider_raw = {"text_lines": text_lines}
        return extraction

    def _run_ocr(self, image) -> list:
        import numpy as np

        ocr = self._get_ocr()
        return ocr.ocr(np.array(image), cls=True)


def _parse_text_heuristics(text: str) -> EIRExtraction:
    """
    Regex-based fallback parser for structured EIR text.
    Extend this with more patterns as needed.
    """
    import re

    def find(pattern: str, flags=0) -> str | None:
        m = re.search(pattern, text, flags | re.IGNORECASE)
        return m.group(1).strip() if m else None

    container_number = find(r"\b([A-Z]{4}\d{7})\b")
    seal_number = find(r"[Ss]eal\s*[Nn]o[.:]?\s*([A-Z0-9]+)")
    shipping_line = find(r"[Ss]hipping\s+[Ll]ine[:\s]+([^\n]+)")
    vessel_name = find(r"[Vv]essel[:\s]+([^\n]+)")

    return EIRExtraction(
        container_number=container_number,
        seal_number=seal_number,
        shipping_line=shipping_line,
        vessel_name=vessel_name,
        extraction_confidence=0.6,
    )
