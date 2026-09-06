import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from api.dictionaries import TestRunRequest, TestTarget
from config.loader import get_config
from engine.DefaultTestPolicy import DefaultTestPolicy
from engine.TestResultBuilder import TestResultBuilder
from engine.evaluator import Evaluator
from engine.registry import registry
from engine.runner import Runner
from jobs.models import JobStatus, TestJobRecord
from reports.builder import build_report
from reports.storage import (
    save_html_report,
    save_json_report,
    save_text_report,
)

"""
Gestione dei test job: stato in memoria, esecuzione in background,
esecuzione dei singoli target.
"""

logger = logging.getLogger("jobs.service")


# =========== Test engine configuration
TEST_RUN_MAX_CONCURRENT_TARGETS = int(os.getenv("TEST_RUN_MAX_CONCURRENT_TARGETS","10",))

policy = DefaultTestPolicy(evaluator=Evaluator(),builder=TestResultBuilder(),)

# ============== Job state
TEST_RUNS: dict[str, TestJobRecord] = {}

TEST_RUN_TASKS: dict[str,asyncio.Task[Any],] = {}


def get_job(job_id: str) -> Optional[TestJobRecord]:
    return TEST_RUNS.get(job_id)


def update_test_run_status(job_id: str,status: JobStatus,**fields: Any,) -> None:
    """
    Aggiorna lo stato e i metadati di un test job.
    """
    job = TEST_RUNS.get(job_id)

    if job is None:
        logger.error("Impossibile aggiornare il job %s: job non trovato.",job_id,)
        return

    job["status"] = status
    job.update(fields)


#  ================= Test suite preparation ==========================

def build_suite_runners(suite_names: list[str],) -> tuple[dict[str, list],dict[str, Runner],]:

    config = get_config()

    suite_tests: dict[str, list] = {}
    suite_runners: dict[str, Runner] = {}

    for suite_name in suite_names:
        suite_config = (config.get("dns", {}).get(suite_name))
        if not suite_config:
            raise RuntimeError(f"Suite '{suite_name}' non configurata.")

        tests = suite_config.get("tests",[],)

        if not tests:

            raise RuntimeError(f"Suite '{suite_name}' non contiene test.")

        concurrency = (suite_config.get("execution", {}).get("concurrency", 10))

        suite_tests[suite_name] = tests

        suite_runners[suite_name] = Runner(
            registry=registry,
            policy=policy,
            max_concurrent_tests=concurrency,
        )

    return suite_tests,suite_runners,


# Esecuzione task su singolo target

async def run_test_target(
    target: TestTarget,
    suite_tests: dict[str, list],
    suite_runners: dict[str, Runner],
    target_semaphore: asyncio.Semaphore,
) -> dict[str, Any]:

    async with target_semaphore:

        target_result: dict[str, Any] = {
            "hostname": target.hostname,
            "node_id": target.node_id,
            "ipv4": (str(target.ipv4) if target.ipv4 else None),
            "ipv6": (str(target.ipv6) if target.ipv6 else None),
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

            suite_result: dict[str, Any] = {"status": "SKIPPED","tests": [],}

            if suite_name == "from_ipv4" and target.ipv4 is None:
                suite_result["reason"] = "TARGET_HAS_NO_IPV4"
                target_result["suites"][suite_name] = suite_result
                continue

            if suite_name == "from_ipv6" and target.ipv6 is None:
                suite_result["reason"] = "TARGET_HAS_NO_IPV6"
                target_result["suites"][suite_name] = suite_result
                continue

            if suite_name == "from_ipv4":
                resolver = str(target.ipv4)

            elif suite_name == "from_ipv6":
                resolver = str(target.ipv6)

            else:
                raise RuntimeError(f"Unsupported suite: {suite_name}")

            results = await suite_runners[suite_name].run_suite(
                suite_tests[suite_name],
                resolver,
                suite_name,
            )

            statuses = [result.get("status") for result in results]

            if any(status == "ERROR" for status in statuses):
                suite_status = "ERROR"
            elif any(status == "FAIL" for status in statuses):
                suite_status = "FAIL"
            elif results:
                suite_status = "PASS"
            else:
                suite_status = "SKIPPED"

            target_result["suites"][suite_name] = {
                "status": suite_status,
                "tests": results,
            }

        return target_result


# =================== Esecuzione in background

async def execute_test_run(job_id: str, request: TestRunRequest,) -> None:

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

        logger.info(
            "Avvio esecuzione job %s.",
            job_id,
        )

        (suite_tests,suite_runners,) = build_suite_runners(list(request.suites))

        target_semaphore = asyncio.Semaphore(TEST_RUN_MAX_CONCURRENT_TARGETS)

        tasks = [
            run_test_target(
                target=target,
                suite_tests=suite_tests,
                suite_runners=suite_runners,
                target_semaphore=target_semaphore,
            )
            for target in request.targets
        ]

        results = await asyncio.gather(*tasks)

        completed_at = (datetime.now(timezone.utc).isoformat())

        job = TEST_RUNS.get(job_id)

        if job is None:
            raise RuntimeError(f"Test job '{job_id}' non trovato durante la finalizzazione.")

        report = build_report(
            job_id=job_id,
            request=request,
            results=results,
            created_at=job["created_at"],
            started_at=job["started_at"],
            completed_at=completed_at,
        )

        report_path = save_json_report(
            job_id=job_id,
            report=report,
        )

        text_report_path = save_text_report(
            job_id=job_id,
            report=report,
        )

        html_report_path = save_html_report(
            job_id=job_id,
            report=report,
        )

        update_test_run_status(
            job_id,
            "completed",
            completed_at=completed_at,
            report=report,
            report_path=report_path,
            text_report_path=text_report_path,
            html_report_path=html_report_path,
        )

        logger.info("Job %s completato.",job_id,)

    except Exception as exc:

        completed_at = (datetime.now(timezone.utc).isoformat())

        update_test_run_status(
            job_id,
            "failed",
            completed_at=completed_at,
            error=str(exc),
        )

        logger.exception("Job %s terminato con errore.",job_id,)



#  ============ Job creation

"""
Crea un nuovo test job (stato 'queued') e ne avvia l'esecuzione
in background. Ritorna il job_id.
"""
def create_test_run(request: TestRunRequest) -> str:

    job_id = str(uuid4())

    created_at = (datetime.now(timezone.utc).isoformat())

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

    logger.info(
        "Creato test job %s da %s: "
        "%d target, suites=%s",
        job_id,
        request.requested_by,
        len(request.targets),
        request.suites,
    )

    task = asyncio.create_task(execute_test_run(job_id,request,))

    TEST_RUN_TASKS[job_id] = task

    def cleanup_task(completed_task: asyncio.Task[Any],) -> None:
        TEST_RUN_TASKS.pop(job_id,None,)

    task.add_done_callback(cleanup_task)
    return job_id