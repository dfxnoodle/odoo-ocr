"""
GET /api/v1/providers

Returns the list of all extraction providers together with their availability
status.  The frontend uses this to render the provider selector and disable
options that are not usable in the current deployment.

Availability is checked lazily and cached for _CACHE_TTL seconds so that the
slow paddle_vl subprocess probe does not block every page load.
"""

from __future__ import annotations

import asyncio
import importlib.util
import time

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter()
logger = structlog.get_logger(__name__)

_CACHE_TTL = 60  # seconds before re-probing
_cache: list["ProviderStatus"] | None = None
_cache_ts: float = 0.0


# ── Schema ────────────────────────────────────────────────────────────────────

class ProviderStatus(BaseModel):
    id: str
    label: str
    description: str
    available: bool
    unavailable_reason: str | None = None


class ProvidersResponse(BaseModel):
    providers: list[ProviderStatus]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/providers", response_model=ProvidersResponse, tags=["extraction"])
async def list_providers() -> ProvidersResponse:
    """Return all providers with their current availability status."""
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache is None or now - _cache_ts > _CACHE_TTL:
        _cache = await _build_provider_list()
        _cache_ts = now
    return ProvidersResponse(providers=_cache)


# ── Availability checks ───────────────────────────────────────────────────────

async def _build_provider_list() -> list[ProviderStatus]:
    settings = get_settings()

    vertex_ok, vertex_reason = _check_vertex(settings)
    azure_ok, azure_reason = _check_azure(settings)
    paddle_ok, paddle_reason = _check_paddle()
    paddle_vl_ok, paddle_vl_reason = await _check_paddle_vl(settings)

    return [
        ProviderStatus(
            id="vertex",
            label="Gemini",
            description="Google Gemini via Vertex AI or Google AI API",
            available=vertex_ok,
            unavailable_reason=vertex_reason,
        ),
        ProviderStatus(
            id="azure",
            label="Azure Document Intelligence",
            description="Microsoft Azure Document Intelligence (cloud)",
            available=azure_ok,
            unavailable_reason=azure_reason,
        ),
        ProviderStatus(
            id="paddle_vl",
            label="PaddleOCR-VL",
            description="Local vision-language model — GPU accelerated, no cloud needed",
            available=paddle_vl_ok,
            unavailable_reason=paddle_vl_reason,
        ),
        ProviderStatus(
            id="paddle",
            label="PaddleOCR CPU",
            description="Local PaddleOCR 2.x — CPU only, basic text recognition",
            available=paddle_ok,
            unavailable_reason=paddle_reason,
        ),
    ]


def _check_vertex(settings) -> tuple[bool, str | None]:
    if (
        settings.google_api_key
        or settings.google_cloud_project
        or settings.google_cloud_projects
        or settings.google_ai_api_keys
    ):
        return True, None
    return (
        False,
        "Set GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_PROJECTS (Vertex AI) "
        "or GOOGLE_API_KEY / GOOGLE_AI_API_KEYS (Google AI API) in .env",
    )


def _check_azure(settings) -> tuple[bool, str | None]:
    placeholder_ep = "https://your-resource.cognitiveservices.azure.com/"
    placeholder_key = "your-azure-key"
    ep = settings.azure_docintel_endpoint
    key = settings.azure_docintel_key
    if ep and key and ep != placeholder_ep and key != placeholder_key:
        return True, None
    return False, "Set AZURE_DOCINTEL_ENDPOINT and AZURE_DOCINTEL_KEY in .env"


def _check_paddle() -> tuple[bool, str | None]:
    spec = importlib.util.find_spec("paddleocr")
    if spec is not None:
        return True, None
    return (
        False,
        "paddleocr is not installed in this Python environment "
        "(PaddlePaddle requires Python 3.9–3.13; consider paddle_vl instead)",
    )


async def _check_paddle_vl(settings) -> tuple[bool, str | None]:
    import os
    python = settings.paddle_vl_python

    # Resolve bare command names to their full path
    bare_names = {"python3", "python3.13", "python3.12", "python3.11", "python3.10", "python3.9"}
    if python not in bare_names and not os.path.isfile(python):
        return (
            False,
            f"PADDLE_VL_PYTHON={python!r} not found. "
            "Create the venv and set PADDLE_VL_PYTHON in .env.",
        )

    # Quick import probe — does not initialise the model
    try:
        proc = await asyncio.create_subprocess_exec(
            python,
            "-c",
            "import importlib.util; "
            "ok = importlib.util.find_spec('paddleocr') is not None; "
            "print('ok' if ok else 'missing')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0 and b"ok" in stdout:
            return True, None
        return (
            False,
            f"paddleocr is not installed in {python!r}. "
            "Run: pip install paddlepaddle-gpu==3.2.1 "
            "-i https://www.paddlepaddle.org.cn/packages/stable/cu129/ "
            "&& pip install 'paddleocr[doc-parser]'",
        )
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as exc:
        return False, f"Could not probe {python!r}: {exc}"
