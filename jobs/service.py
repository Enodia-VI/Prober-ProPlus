"""
Gestione dei test job: stato in memoria, esecuzione in background,
esecuzione dei singoli target.

Lo stato dei job (TEST_RUNS) resta in memoria: se il processo viene
riavviato si perde, ma i report già scritti su disco restano
leggibili da api/reports.py. Vedi punto 8 della roadmap.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional, TypedDict
from uuid import uuid4

from api.dictionaries import TestRunRequest, TestTarget
from config.settings import get_config, get_settings
from core.logging import log_context
from engine.DefaultTestPolicy import DefaultTestPolicy
from engine.TestResultBuilder import TestResultBuilder
from engine.evaluator import Evaluator
from engine.registry import registry
from engine.runner import Runner
from reports.builder import build_report
from reports.storage import (
    save_html_report,
    save_json_report,
    save_text_report,
)

logger = logging.getLogger("jobs.service")


# =============================================================================
# Stato di un job: solo tipi descrittivi (TypedDict, niente validazione
# runtime). Un vero modello Pydantic è previsto al passo 5.
# =============================================================================

JobStatus = Literal["queued", "running", "completed", "failed"]


class TestJobRecord(TypedDict, total=False):
    job_id: str
    status: JobStatus
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    requested_by: str
    target_count: int
    suites: list[str]
    send_email: bool

    # Presenti solo dopo un completamento (anche parziale, se il
    # salvataggio di un formato di report fallisce)
    report: dict[str, Any]
    report_path: Optional[str]
    text_report_path: Optional[str]
    html_report_path: Optional[str]

    # Presente solo se il salvataggio di almeno un formato è fallito
    report_errors: dict[str, str]

    # Presente solo in caso di fallimento del job
    error: str


# =============================================================================
# Test engine configuration
# =============================================================================

TEST_RUN_MAX_CONCURRENT_TARGETS = get_settings().test_run_max_concurrent_targets

policy = DefaultTestPolicy(
    evaluator=Evaluator(),
    builder=TestResultBuilder(),
)


# =============================================================================
# Job state (in-memory)
# =============================================================================

TEST_RUNS: dict[str, TestJobRecord] = {}

TEST_RUN_TASKS: dict[
    str,
    asyncio.Task[Any],
] = {}


def get_job(job_id: str) -> Optional[TestJobRecord]:
    return TEST_RUNS.get(job_id)


def update_test_run_status(
    job_id: str,
    status: JobStatus,
    **fields: Any,
) -> None:
    """
    Aggiorna lo stato e i metadati di un test job.
    """

    job = TEST_RUNS.get(
        job_id
    )

    if job is None:

        logger.error(
            "Impossibile aggiornare il job %s: "
            "job non trovato.",
            job_id,
        )

        return

    job["status"] = status
    job.update(fields)


# =============================================================================
# Test suite preparation
# =============================================================================

def build_suite_runners(
    suite_names: list[str],
) -> tuple[
    dict[str, list],
    dict[str, Runner],
]:
    """
    Prepara test e Runner per tutte le suite richieste.
    """

    config = get_config()

    suite_tests: dict[str, list] = {}
    suite_runners: dict[str, Runner] = {}

    for suite_name in suite_names:

        suite_config = (
            config
            .get("dns", {})
            .get(suite_name)
        )

        if not suite_config:

            raise RuntimeError(
                f"Suite '{suite_name}' "
                "non configurata."
            )

        tests = suite_config.get(
            "tests",
            [],
        )

        if not tests:

            raise RuntimeError(
                f"Suite '{suite_name}' "
                "non contiene test."
            )

        concurrency = (
            suite_config
            .get("execution", {})
            .get("concurrency", 10)
        )

        suite_tests[suite_name] = tests

        suite_runners[suite_name] = Runner(
            registry=registry,
            policy=policy,
            max_concurrent_tests=concurrency,
        )

    return (
        suite_tests,
        suite_runners,
    )


# =============================================================================
# Target execution
# =============================================================================

async def run_test_target(
    target: TestTarget,
    suite_tests: dict[str, list],
    suite_runners: dict[str, Runner],
    target_semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """
    Esegue tutte le suite richieste su un singolo target.
    """

    with log_context(target=target.hostname):
        async with target_semaphore:

            target_result: dict[str, Any] = {
                "hostname": target.hostname,
                "node_id": target.node_id,
                "ipv4": (
                    str(target.ipv4)
                    if target.ipv4
                    else None
                ),
                "ipv6": (
                    str(target.ipv6)
                    if target.ipv6
                    else None
                ),
                "continent": target.continent,
                "country": target.country,
                "city": target.city,
                "site": target.site,
                "cluster_id": target.cluster_id,
                "cluster_name": target.cluster_name,
                "carrier": target.carrier,
                "device_type": target.device_type,
                "active": target.active,
                "suites": {},
            }

            for suite_name in suite_tests:

                suite_result: dict[str, Any] = {
                    "status": "SKIPPED",
                    "tests": [],
                }

                if (
                    suite_name == "from_ipv4"
                    and target.ipv4 is None
                ):

                    suite_result["reason"] = (
                        "TARGET_HAS_NO_IPV4"
                    )

                    target_result["suites"][
                        suite_name
                    ] = suite_result

                    continue

                if (
                    suite_name == "from_ipv6"
                    and target.ipv6 is None
                ):

                    suite_result["reason"] = (
                        "TARGET_HAS_NO_IPV6"
                    )

                    target_result["suites"][
                        suite_name
                    ] = suite_result

                    continue

                if suite_name == "from_ipv4":

                    resolver = str(
                        target.ipv4
                    )

                elif suite_name == "from_ipv6":

                    resolver = str(
                        target.ipv6
                    )

                else:

                    raise RuntimeError(
                        f"Unsupported suite: {suite_name}"
                    )

                results = await suite_runners[
                    suite_name
                ].run_suite(
                    suite_tests[suite_name],
                    resolver,
                    suite_name,
                )

                statuses = [
                    result.get("status")
                    for result in results
                ]

                if any(
                    status == "ERROR"
                    for status in statuses
                ):

                    suite_status = "ERROR"

                elif any(
                    status == "FAIL"
                    for status in statuses
                ):

                    suite_status = "FAIL"

                elif results:

                    suite_status = "PASS"

                else:

                    suite_status = "SKIPPED"

                target_result["suites"][
                    suite_name
                ] = {
                    "status": suite_status,
                    "tests": results,
                }

            return target_result


# =============================================================================
# Isolamento dei fallimenti: un target o un formato di report rotto
# non deve far perdere il resto del job.
# =============================================================================

def _build_target_crash_result(
    target: TestTarget,
    suite_names: list[str],
    exc: BaseException,
) -> dict[str, Any]:
    """target_result sintetico quando l'esecuzione di un target esplode del tutto (critical=True: va sempre in FAIL)."""

    synthetic_test = {
        "test_id": "_target_execution",
        "test_type": "internal",
        "status": "ERROR",
        "critical": True,
        "resolver": None,
        "duration_ms": 0,
        "summary": "Esecuzione del target interrotta da un errore non gestito.",
        "details": {
            "error_code": "TARGET_EXECUTION_FAILED",
            "error_message": str(exc),
        },
    }

    return {
        "hostname": target.hostname,
        "node_id": target.node_id,
        "ipv4": str(target.ipv4) if target.ipv4 else None,
        "ipv6": str(target.ipv6) if target.ipv6 else None,
        "continent": target.continent,
        "country": target.country,
        "city": target.city,
        "site": target.site,
        "cluster_id": target.cluster_id,
        "cluster_name": target.cluster_name,
        "carrier": target.carrier,
        "device_type": target.device_type,
        "active": target.active,
        "suites": {
            suite_name: {"status": "ERROR", "tests": [synthetic_test]}
            for suite_name in suite_names
        },
    }


def _persist_reports(
    job_id: str,
    report: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Salva i 3 formati indipendentemente: uno che fallisce non blocca gli altri né il job."""

    savers = {
        "json": save_json_report,
        "txt": save_text_report,
        "html": save_html_report,
    }

    paths: dict[str, str] = {}
    errors: dict[str, str] = {}

    for report_format, save in savers.items():
        try:
            paths[report_format] = save(job_id=job_id, report=report)
        except Exception as exc:
            logger.exception(
                "Salvataggio del report fallito.",
                extra={"report_format": report_format},
            )
            errors[report_format] = str(exc)

    return paths, errors


# =============================================================================
# Background test execution
# =============================================================================

async def execute_test_run(
    job_id: str,
    request: TestRunRequest,
) -> None:
    """
    Esegue un test job in background.
    """

    with log_context(job_id=job_id):
        try:

            update_test_run_status(
                job_id,
                "running",
                started_at=(
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            )

            logger.info("Avvio esecuzione job.")

            (
                suite_tests,
                suite_runners,
            ) = build_suite_runners(
                list(request.suites)
            )

            target_semaphore = asyncio.Semaphore(
                TEST_RUN_MAX_CONCURRENT_TARGETS
            )

            targets = list(request.targets)

            tasks = [
                run_test_target(
                    target=target,
                    suite_tests=suite_tests,
                    suite_runners=suite_runners,
                    target_semaphore=target_semaphore,
                )
                for target in targets
            ]

            # return_exceptions=True: un target la cui esecuzione esplode
            # con un'eccezione non gestita non deve far perdere i
            # risultati (già pronti) degli altri target, né far fallire
            # l'intero job — viene invece rappresentato come un target
            # con esito ERROR nel report finale.
            raw_results = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            results: list[dict[str, Any]] = []

            for target, raw_result in zip(targets, raw_results):

                if isinstance(raw_result, BaseException):

                    with log_context(target=target.hostname):
                        logger.error(
                            "Esecuzione del target interrotta da un "
                            "errore non gestito.",
                            exc_info=raw_result,
                        )

                    results.append(
                        _build_target_crash_result(
                            target,
                            list(suite_tests.keys()),
                            raw_result,
                        )
                    )

                else:
                    results.append(raw_result)

            completed_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            job = TEST_RUNS.get(
                job_id
            )

            if job is None:
                raise RuntimeError(
                    f"Test job '{job_id}' non trovato "
                    "durante la finalizzazione."
                )

            report = build_report(
                job_id=job_id,
                request=request,
                results=results,
                created_at=job["created_at"],
                started_at=job["started_at"],
                completed_at=completed_at,
            )

            report_paths, report_errors = _persist_reports(
                job_id, report
            )

            update_fields: dict[str, Any] = {
                "completed_at": completed_at,
                "report": report,
                "report_path": report_paths.get("json"),
                "text_report_path": report_paths.get("txt"),
                "html_report_path": report_paths.get("html"),
            }

            if report_errors:
                update_fields["report_errors"] = report_errors
                logger.warning(
                    "Uno o più formati di report non sono stati "
                    "salvati su disco.",
                    extra={"formati_falliti": ",".join(report_errors)},
                )

            update_test_run_status(
                job_id,
                "completed",
                **update_fields,
            )

            logger.info("Job completato.")

        except Exception as exc:

            completed_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            update_test_run_status(
                job_id,
                "failed",
                completed_at=completed_at,
                error=str(exc),
            )

            logger.exception("Job terminato con errore.")


# =============================================================================
# Job creation
# =============================================================================

def create_test_run(request: TestRunRequest) -> str:
    """
    Crea un nuovo test job (stato 'queued') e ne avvia l'esecuzione
    in background. Ritorna il job_id.
    """

    job_id = str(uuid4())

    created_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    TEST_RUNS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": created_at,
        "started_at": None,
        "completed_at": None,
        "requested_by": request.requested_by,
        "target_count": len(request.targets),
        "suites": list(request.suites),
        "send_email": request.send_email,
    }

    with log_context(job_id=job_id):
        logger.info(
            "Creato nuovo test job: richiedente=%s, target=%d, suites=%s",
            request.requested_by,
            len(request.targets),
            request.suites,
        )

    task = asyncio.create_task(
        execute_test_run(
            job_id,
            request,
        )
    )

    TEST_RUN_TASKS[job_id] = task

    def cleanup_task(
        completed_task: asyncio.Task[Any],
    ) -> None:

        TEST_RUN_TASKS.pop(
            job_id,
            None,
        )

    task.add_done_callback(
        cleanup_task
    )

    return job_id