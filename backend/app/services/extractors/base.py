"""
Abstract base class and factory for extraction providers.

Add a new provider by:
  1. Subclassing BaseExtractor
  2. Registering it in PROVIDER_REGISTRY
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.extraction import EIRExtraction


class BaseExtractor(ABC):
    """Common interface all extraction adapters must implement."""

    @abstractmethod
    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> "EIRExtraction":
        """
        Extract from a single file (image or single-page PDF).

        Implementations are responsible for their own I/O and error handling.
        Any unrecoverable error should raise ExtractionError.
        """

    async def extract_pages(
        self, file_bytes: bytes, filename: str, mime_type: str
    ) -> "list[EIRExtraction]":
        """
        Extract every page of a document as a separate EIRExtraction.

        Default: delegates to extract() once (covers non-PDF and providers that
        handle multi-page natively). Subclasses should override when they can
        split a multi-page PDF into per-page extractions.
        """
        return [await self.extract(file_bytes, filename, mime_type)]

    async def extract_pages_stream(
        self, file_bytes: bytes, filename: str, mime_type: str
    ) -> "AsyncGenerator[tuple[int, int, EIRExtraction], None]":
        """
        Async generator that yields (page_number_1based, total_pages, EIRExtraction)
        as each page finishes extraction.

        Default: calls extract_pages() in one shot then yields results sequentially.
        Subclasses override this to emit results as soon as each page is ready.
        """
        results = await self.extract_pages(file_bytes, filename, mime_type)
        total = len(results)
        for i, result in enumerate(results):
            yield i + 1, total, result

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier used in response metadata."""


class ExtractionError(Exception):
    """Raised when an extraction provider fails unrecoverably."""

    def __init__(self, provider: str, message: str, cause: Exception | None = None) -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")
        self.__cause__ = cause


def get_extractor(provider: str) -> BaseExtractor:
    """
    Factory that returns the appropriate extractor instance for a provider key.
    Import is deferred to avoid loading heavyweight SDKs unless the provider is active.
    """
    from app.core.config import ExtractionProvider

    match provider:
        case ExtractionProvider.vertex:
            from app.services.extractors.vertex_gemini import VertexGeminiExtractor
            return VertexGeminiExtractor()
        case ExtractionProvider.azure:
            from app.services.extractors.azure_docintel import AzureDocIntelExtractor
            return AzureDocIntelExtractor()
        case ExtractionProvider.paddle:
            from app.services.extractors.paddle_cpu import PaddleCpuExtractor
            return PaddleCpuExtractor()
        case ExtractionProvider.paddle_vl:
            from app.services.extractors.paddle_vl import PaddleVLExtractor
            return PaddleVLExtractor()
        case _:
            raise ValueError(f"Unknown extraction provider: {provider!r}")
