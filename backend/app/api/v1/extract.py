import asyncio
import json
import mimetypes
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.config import ExtractionProvider, Settings, get_settings
from app.core.logging import new_request_id
from app.schemas.extraction import ExtractionBatchResponse, ExtractionResponse
from app.services.extractors.base import ExtractionError, get_extractor

router = APIRouter()
logger = structlog.get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/tiff",
    "application/pdf",
}


def _sse(event_type: str, payload: dict) -> str:
    """Format a single Server-Sent Event line."""
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


@router.post(
    "/extract",
    tags=["extraction"],
    summary="Extract EIR fields from an uploaded document — streams SSE progress events",
    response_class=StreamingResponse,
)
async def extract_document(
    file: Annotated[UploadFile, File(description="PDF or image of the EIR document")],
    provider_override: Annotated[
        str | None,
        Form(description="Override the default extraction provider for this request"),
    ] = None,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    request_id = new_request_id()
    log = logger.bind(request_id=request_id, filename=file.filename)

    # ── Validate before streaming ───────────────────────────────────────────
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{mime}'. Allowed: {sorted(ALLOWED_MIME_TYPES)}",
        )

    contents = await file.read()
    max_bytes = settings.extraction_max_file_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.extraction_max_file_size_mb} MB limit.",
        )

    provider_key = provider_override or settings.extraction_provider.value
    try:
        ExtractionProvider(provider_key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider '{provider_key}'. Valid: vertex, azure, paddle, paddle_vl",
        )

    extractor = get_extractor(provider_key)
    filename = file.filename or "upload"
    log = log.bind(provider=extractor.provider_name)
    log.info("Extraction request received (SSE)", size_bytes=len(contents))

    # ── SSE generator ───────────────────────────────────────────────────────
    async def event_stream():
        extraction_responses: list[ExtractionResponse] = []

        # Wire up retry notifications if the extractor supports them.
        retry_queue: asyncio.Queue[dict] = asyncio.Queue()
        if hasattr(extractor, "retry_notification_queue"):
            extractor.retry_notification_queue = retry_queue

        gen = extractor.extract_pages_stream(contents, filename, mime)
        try:
            while True:
                # Kick off the next page as a background task so we can emit
                # retry SSE events *while* it is blocked inside back-off sleeps.
                page_task: asyncio.Task = asyncio.create_task(gen.__anext__())  # type: ignore[arg-type]

                while not page_task.done():
                    await asyncio.sleep(0.2)
                    while not retry_queue.empty():
                        info = retry_queue.get_nowait()
                        yield _sse("page_retrying", {
                            "label": info.get("label", ""),
                            "attempt": info.get("attempt", 1),
                        })

                # Final drain after the page task finished
                while not retry_queue.empty():
                    info = retry_queue.get_nowait()
                    yield _sse("page_retrying", {
                        "label": info.get("label", ""),
                        "attempt": info.get("attempt", 1),
                    })

                try:
                    page_num, total_pages, extraction = page_task.result()
                except StopAsyncIteration:
                    break
                except ExtractionError as exc:
                    log.error("Extraction failed mid-stream", error=str(exc))
                    yield _sse("error", {"detail": str(exc)})
                    return

                warnings: list[str] = []
                if extraction.container_number is None:
                    warnings.append("Container number could not be extracted.")

                resp = ExtractionResponse(
                    request_id=request_id,
                    filename=filename,
                    extraction=extraction,
                    warnings=warnings,
                    provider_used=extractor.provider_name,
                    page_number=page_num,
                    total_pages=total_pages,
                )
                extraction_responses.append(resp)

                yield _sse("page_done", {
                    "page": page_num,
                    "total": total_pages,
                    "container_number": extraction.container_number,
                })

        finally:
            if hasattr(extractor, "retry_notification_queue"):
                extractor.retry_notification_queue = None

        # Emit the complete batch as the final event
        batch = ExtractionBatchResponse(
            request_id=request_id,
            filename=filename,
            provider_used=extractor.provider_name,
            total_pages=len(extraction_responses),
            extractions=extraction_responses,
        )
        log.info("SSE stream complete", total_pages=len(extraction_responses))
        yield _sse("result", {"data": batch.model_dump(mode="json")})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
