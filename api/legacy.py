"""
API legacy per l'esecuzione sincrona di una singola suite di test
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from api.dictionaries import RunSuiteRequest
from config.loader import get_config
from engine.registry import registry
from engine.runner import Runner
from jobs.service import policy

logger = logging.getLogger("api.legacy")

router = APIRouter(tags=["legacy"])


@router.post("/api/run-suite")
async def run_suite(request: RunSuiteRequest,):

    config = get_config()
    if not config:

        raise HTTPException(status_code=500,detail="Configurazione assente.",)
    tasks = []

    esegui_ipv4 = (
        request.suite == "from_ipv4"
        or (
            request.suite
            not in [
                "from_ipv4",
                "from_ipv6",
            ]
            and bool(
                request.dns4_server
            )
        )
    )

    esegui_ipv6 = (
        request.suite == "from_ipv6"
        or (
            request.suite
            not in [
                "from_ipv4",
                "from_ipv6",
            ]
            and bool(
                request.dns6_server
            )
        )
    )

    if esegui_ipv4 and not request.dns4_server:
        raise HTTPException(status_code=400,detail=(
                "È stata richiesta o rilevata "
                "l'esecuzione IPv4, ma "
                "dns4_server è assente."
            ),
        )

    if esegui_ipv6 and not request.dns6_server:

        raise HTTPException(
            status_code=400,
            detail=(
                "È stata richiesta o rilevata "
                "l'esecuzione IPv6, ma "
                "dns6_server è assente."
            ),
        )

    if esegui_ipv4:

        ipv4_config = (config.get("dns", {}).get("from_ipv4"))

        if ipv4_config:
            suite_tests = ipv4_config.get("tests",[],)
            concurrency = (ipv4_config.get("execution", {}).get("concurrency",10,))

            runner_v4 = Runner(registry=registry, policy=policy, max_concurrent_tests=concurrency,)

            tasks.append(
                runner_v4.run_suite(
                    suite_tests,
                    request.dns4_server,
                    "from_ipv4",
                )
            )

    if esegui_ipv6:

        ipv6_config = (config.get("dns", {}).get("from_ipv6"))

        if ipv6_config:
            suite_tests = ipv6_config.get("tests",[],)
            concurrency = (ipv6_config.get("execution", {}).get("concurrency",10,))

            runner_v6 = Runner(
                registry=registry,
                policy=policy,
                max_concurrent_tests=concurrency,
            )

            tasks.append(
                runner_v6.run_suite( suite_tests, request.dns6_server,"from_ipv6", )
            )

    if not tasks:

        raise HTTPException(
            status_code=404,
            detail="Nessuna suite di test configurata o eseguibile con i parametri passati.",
        )

    logger.info(
        "Avvio esecuzione simultanea multi-stack. Task attivi in parallelo: %d",
        len(tasks),
    )

    liste_risultati = await asyncio.gather(*tasks)

    flat_results = []

    for risultati_suite in liste_risultati:
        flat_results.extend(risultati_suite)

    return {
        "suite_richiesta": request.suite,
        "dns4_server_utilizzato": ( request.dns4_server if esegui_ipv4 else None),
        "dns6_server_utilizzato": ( request.dns6_server if esegui_ipv6 else None ),
        "results": flat_results,
    }
