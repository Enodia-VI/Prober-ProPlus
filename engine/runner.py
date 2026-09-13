import asyncio
import logging
import time

from api.dictionaries import PluginError, PluginOutput
from core.logging import log_context

logger = logging.getLogger("engine.runner")


class Runner:

    def __init__(self, registry, policy, max_concurrent_tests: int = 10):
        self.registry = registry
        self.policy = policy
        # Limita i test simultanei per non saturare la macchina o i DNS target
        self.semaphore = asyncio.Semaphore(max_concurrent_tests)

    async def run_suite(self, suite_tests: list, resolver: str, suite_name: str = "unknown"):
        with log_context(suite=suite_name):
            logger.info(
                "Avvio esecuzione suite.",
                extra={"test_count": len(suite_tests)},
            )

            # Funzione worker interna che rispetta il semaforo
            async def worker(test):
                async with self.semaphore:
                    return await self.run_test(test, resolver)

            # Creazione dei task concorrenti
            tasks = [worker(test) for test in suite_tests]

            # return_exceptions=True: run_test() già intercetta e converte
            # in ERROR qualunque eccezione del plugin/valutazione (vedi il
            # suo try/except), ma un bug prima di quel punto (es. test
            # malformato senza "type") uscirebbe comunque da worker()
            # senza passare di lì. Senza return_exceptions, un solo test
            # rotto in questo modo farebbe fallire asyncio.gather e perdere
            # i risultati di TUTTI gli altri test della suite.
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            results = []
            for test, raw_result in zip(suite_tests, raw_results):
                if isinstance(raw_result, BaseException):
                    with log_context(test_id=test.get("id")):
                        logger.error(
                            "Test interrotto da un errore non gestito nel worker.",
                            exc_info=raw_result,
                        )
                    results.append(
                        self._build_test_crash_result(test, resolver, raw_result)
                    )
                else:
                    results.append(raw_result)

            logger.info("Suite completata.")
            return results

    @staticmethod
    def _build_test_crash_result(test, resolver, exc: BaseException) -> dict:
        """
        Risultato sintetico per un test il cui worker è esploso PRIMA di
        entrare nel try/except di run_test() (es. test malformato). Stessa
        forma che run_test() produce già per le eccezioni che intercetta
        lui stesso, per coerenza nel report finale.
        """
        return {
            "test_id": test.get("id"),
            "test_type": test.get("type"),
            "status": "ERROR",
            "critical": bool(test.get("critical", False)),
            "resolver": resolver,
            "duration_ms": 0,
            "summary": "Il test è stato interrotto da un errore non gestito nel worker.",
            "details": {
                "error_code": "UNEXPECTED_WORKER_EXCEPTION",
                "error_message": str(exc),
                "expected_assertions": test.get("assertions", {}),
            },
        }

    async def run_test(
            self,
            test,
            resolver,
    ):
        with log_context(test_id=test.get("id")):

            plugin_type = test["type"]

            if (
                    plugin_type not in self.registry
                    or not self.registry[plugin_type]
            ):
                logger.error(
                    "Plugin di tipo '%s' assente nel Registry.",
                    plugin_type,
                )

                # NOTA: prima questo caso costruiva a mano un dizionario di
                # errore, duplicando (in modo incompleto: mancava
                # expected_assertions) il formato prodotto da
                # TestResultBuilder per gli altri errori. Un plugin mancante
                # è concettualmente identico a un plugin che risponde
                # ok=False, quindi lo facciamo passare dallo stesso
                # policy.handle() per ottenere una struttura consistente.
                missing_plugin_result = PluginOutput(
                    ok=False,
                    data=None,
                    error=PluginError(
                        code="PLUGIN_NOT_CONFIGURED",
                        message=(
                            f"Il plugin per {plugin_type} "
                            "non è censito nel sistema."
                        ),
                    ),
                )

                evaluated_result = await self.policy.handle(
                    test,
                    missing_plugin_result,
                )

                evaluated_result["duration_ms"] = 0
                evaluated_result["resolver"] = resolver
                evaluated_result["critical"] = bool(
                    test.get("critical", False)
                )

                logger.info(
                    "Test completato.",
                    extra={
                        "status": evaluated_result["status"],
                        "duration_ms": evaluated_result["duration_ms"],
                    },
                )

                return evaluated_result

            plugin = self.registry[plugin_type]

            logger.debug(
                "Esecuzione test tramite plugin %s",
                plugin_type,
            )

            started = time.perf_counter()

            try:

                result = await plugin.run(
                    test["input"],
                    resolver,
                )

                duration_ms = round(
                    (time.perf_counter() - started) * 1000,
                    2,
                )

                evaluated_result = await self.policy.handle(
                    test,
                    result,
                )

                evaluated_result["duration_ms"] = duration_ms
                evaluated_result["resolver"] = resolver
                evaluated_result["critical"] = bool(
                    test.get("critical", False)
                )

                logger.info(
                    "Test completato.",
                    extra={
                        "status": evaluated_result["status"],
                        "duration_ms": evaluated_result["duration_ms"],
                    },
                )

                return evaluated_result

            except Exception as exc:

                duration_ms = round(
                    (time.perf_counter() - started) * 1000,
                    2,
                )

                logger.exception("Errore critico non gestito durante il test.")

                evaluated_result = {
                    "test_id": test.get("id"),
                    "test_type": plugin_type,
                    "status": "ERROR",
                    "critical": bool(test.get("critical", False)),
                    "resolver": resolver,
                    "duration_ms": duration_ms,
                    "summary": "Errore non gestito durante il test.",
                    "details": {
                        "error_code": "UNEXPECTED_RUNNER_EXCEPTION",
                        "error_message": str(exc),
                        "expected_assertions": test.get(
                            "assertions",
                            {},
                        ),
                    },
                }

                logger.info(
                    "Test completato.",
                    extra={
                        "status": evaluated_result["status"],
                        "duration_ms": evaluated_result["duration_ms"],
                    },
                )

                return evaluated_result