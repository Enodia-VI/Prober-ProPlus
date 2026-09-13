"""
API interne per la creazione e il monitoraggio dei test job.

Router "sottile": la logica di creazione/esecuzione dei job vive in
jobs/service.py, qui c'è solo validazione della richiesta HTTP,
autenticazione e forma della risposta.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from api.dictionaries import TestRunAccepted, TestRunRequest
from config.settings import get_config
from core.security import validate_internal_token
from jobs.service import create_test_run, get_job

logger = logging.getLogger("api.internal")

router = APIRouter(tags=["internal"])


def _build_report_urls(job_id: str) -> dict[str, str]:
    """
    URL di comodo per recuperare i tre formati di report di un job,
    così i chiamanti non devono ricostruirseli a mano.
    """

    base = f"/api/internal/test-runs/{job_id}"

    return {
        "json": f"{base}/report.json",
        "txt": f"{base}/report.txt",
        "html": f"{base}/report.html",
    }


@router.post(
    "/api/internal/test-runs",
    response_model=TestRunAccepted,
    status_code=202,
)
async def create_test_run_endpoint(
    request: TestRunRequest,
    x_internal_token: Optional[str] = Header(None),
):

    validate_internal_token(
        x_internal_token
    )

    if not get_config():

        raise HTTPException(
            status_code=500,
            detail=(
                "Configurazione dei test assente."
            ),
        )

    job_id = create_test_run(request)

    return TestRunAccepted(
        job_id=job_id,
        status="queued",
    )


@router.get(
    "/api/internal/test-runs/{job_id}"
)
async def get_test_run_endpoint(
    job_id: str,
    x_internal_token: Optional[str] = Header(None),
):

    validate_internal_token(
        x_internal_token
    )

    job = get_job(job_id)

    if job is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Test job '{job_id}' "
                "non trovato."
            ),
        )

    response = dict(job)

    if job.get("status") == "completed":
        response["report_urls"] = _build_report_urls(job_id)

    return response