import mimetypes
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.config import ExtractionProvider, Settings, get_settings
from app.core.logging import new_request_id
from app.schemas.extraction import ExtractionResponse
from app.services.extractors.base import ExtractionError, get_extractor

router = APIRouter()
logger = structlog.get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/tiff",
    "application/pdf",
}


@router.post(
    "/extract",
    response_model=ExtractionResponse,
    tags=["extraction"],
    summary="Extract EIR fields from an uploaded document",
)
async def extract_document(
    file: Annotated[UploadFile, File(description="PDF or image of the EIR document")],
    provider_override: Annotated[
        str | None,
        Form(description="Override the default extraction provider for this request"),
    ] = None,
    settings: Settings = Depends(get_settings),
) -> ExtractionResponse:
    request_id = new_request_id()
    log = logger.bind(request_id=request_id, filename=file.filename)

    # Validate file type
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{mime}'. Allowed: {sorted(ALLOWED_MIME_TYPES)}",
        )

    # Validate file size
    contents = await file.read()
    max_bytes = settings.extraction_max_file_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.extraction_max_file_size_mb} MB limit.",
        )

    # Resolve provider
    provider_key = provider_override or settings.extraction_provider.value
    try:
        ExtractionProvider(provider_key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider '{provider_key}'. Valid: vertex, azure, paddle",
        )

    extractor = get_extractor(provider_key)
    log = log.bind(provider=extractor.provider_name)
    log.info("Extraction request received", size_bytes=len(contents))

    try:
        extraction = await extractor.extract(contents, file.filename or "upload", mime)
    except ExtractionError as exc:
        log.error("Extraction failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    warnings: list[str] = []
    if extraction.container_number is None:
        warnings.append("Container number could not be extracted.")

    return ExtractionResponse(
        request_id=request_id,
        filename=file.filename or "upload",
        extraction=extraction,
        warnings=warnings,
        provider_used=extractor.provider_name,
    )
