import structlog
from fastapi import APIRouter, HTTPException, status

from app.schemas.extraction import CommitRequest, OdooCommitResult
from app.services.odoo.client import (
    EIRToOdooMapper,
    OdooAuthError,
    OdooConnectionError,
    get_odoo_client,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post(
    "/odoo/commit",
    response_model=OdooCommitResult,
    tags=["odoo"],
    summary="Push validated EIR extraction into Odoo",
)
async def commit_to_odoo(body: CommitRequest) -> OdooCommitResult:
    log = logger.bind(request_id=body.request_id, model=body.odoo_model, dry_run=body.dry_run)
    log.info("Odoo commit requested")

    try:
        client = get_odoo_client()
        mapper = EIRToOdooMapper()
        values, warnings, unresolved = mapper.map(body.extraction, body.odoo_model, client)

        if body.dry_run:
            log.info("Dry run – skipping Odoo write", field_count=len(values))
            return OdooCommitResult(
                success=True,
                record_id=None,
                odoo_model=body.odoo_model,
                dry_run=True,
                warnings=warnings,
                unresolved_refs=unresolved,
            )

        # Idempotency check: avoid duplicate records keyed on container number
        if body.extraction.container_number:
            existing_id = client.check_duplicate(
                body.odoo_model,
                [("x_container_number", "=", body.extraction.container_number)],
            )
            if existing_id:
                warnings.append(
                    f"Record already exists in {body.odoo_model} with id={existing_id} "
                    f"for container {body.extraction.container_number}. Skipping create."
                )
                log.warning("Duplicate record detected", existing_id=existing_id)
                return OdooCommitResult(
                    success=True,
                    record_id=existing_id,
                    odoo_model=body.odoo_model,
                    dry_run=False,
                    warnings=warnings,
                    unresolved_refs=unresolved,
                )

        record_id = client.create(body.odoo_model, values)
        log.info("Odoo record created", record_id=record_id)

        return OdooCommitResult(
            success=True,
            record_id=record_id,
            odoo_model=body.odoo_model,
            dry_run=False,
            warnings=warnings,
            unresolved_refs=unresolved,
        )

    except OdooAuthError as exc:
        log.error("Odoo auth failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except OdooConnectionError as exc:
        log.error("Odoo connection error", error=str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("Unexpected error during Odoo commit")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {exc}",
        ) from exc
