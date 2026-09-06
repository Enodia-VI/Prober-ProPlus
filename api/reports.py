"""
Endpoint per il recupero dei report generati dai test job.
"""

# TODO: Aumentare descrizione componente

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

from core.security import validate_internal_token
from reports.storage import (
    is_valid_job_id,
    report_exists,
    report_file_path,
)

router = APIRouter(
    prefix="/api/internal/test-runs",
    tags=["reports"],
)


def _require_valid_job_id(job_id: str) -> None:
    if not is_valid_job_id(job_id):
        raise HTTPException(
            status_code=400,
            detail="job_id non valido: deve essere un UUID.",
        )


def _require_report_path(
    job_id: str,
    report_format: str,
    label: str,
) -> str:
    if not report_exists(job_id, report_format):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Report {label} non trovato per il job '{job_id}'. "
                "Il job potrebbe non esistere, essere ancora in "
                "esecuzione, oppure essere terminato prima di "
                "produrre un report."
            ),
        )

    return report_file_path(job_id, report_format)


@router.get("/{job_id}/report.json")
async def get_report_json(
    job_id: str,
    x_internal_token: Optional[str] = Header(None),
):
    """Restituisce il report JSON canonico del job."""

    validate_internal_token(x_internal_token)
    _require_valid_job_id(job_id)

    path = _require_report_path(job_id, "json", "JSON")

    return FileResponse( path, media_type="application/json")


@router.get("/{job_id}/report.txt")
async def download_report_txt(
    job_id: str,
    x_internal_token: Optional[str] = Header(None),
):
    """Scarica il report TXT del job come allegato."""

    validate_internal_token(x_internal_token)
    _require_valid_job_id(job_id)

    path = _require_report_path(job_id, "txt", "TXT")

    return FileResponse(
        path,
        media_type="text/plain",
        # 'filename' forza Content-Disposition: attachment -> download.
        filename=f"report-{job_id}.txt",
    )


@router.get("/{job_id}/report.html")
async def view_report_html(
    job_id: str,
    x_internal_token: Optional[str] = Header(None),
):
    """Restituisce il report HTML del job per la visualizzazione."""

    validate_internal_token(x_internal_token)
    _require_valid_job_id(job_id)

    path = _require_report_path(job_id, "html", "HTML")

    # Nessun 'filename' -> il browser lo visualizza inline invece di scaricarlo.
    return FileResponse( path, media_type="text/html", )