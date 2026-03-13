"""
Abstract base class and factory for extraction providers.

Add a new provider by:
  1. Subclassing BaseExtractor
  2. Registering it in PROVIDER_REGISTRY
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.extraction import EIRExtraction


class BaseExtractor(ABC):
    """Common interface all extraction adapters must implement."""

    @abstractmethod
    async def extract(self, file_bytes: bytes, filename: str, mime_type: str) -> "EIRExtraction":
        """
        Accepts raw file bytes and returns a validated EIRExtraction.

        Implementations are responsible for their own I/O and error handling.
        Any unrecoverable error should raise ExtractionError.
        """

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
        case _:
            raise ValueError(f"Unknown extraction provider: {provider!r}")
