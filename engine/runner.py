import asyncio
import logging

from api.dictionaries import PluginError, PluginOutput

logger = logging.getLogger("engine.runner")


class Runner:

    def __init__(self, registry, policy, max_concurrent_tests: int = 10):
        self.registry = registry
        self.policy = policy
        # Limita i test simultanei per non saturare la macchina o i DNS target
        self.semaphore = asyncio.Semaphore(max_concurrent_tests)

    async def run_suite(self, suite_tests: list, resolver: str, suite_name: str = "unknown"):
        logger.info(f"Avvio esecuzione suite [{suite_name}] contenente {len(suite_tests)} test.")

        # Funzione worker interna che rispetta il semaforo
        async def worker(test):
            async with self.semaphore:
                return await self.run_test(test, resolver)

        # Creazione dei task concorrenti
        tasks = [worker(test) for test in suite_tests]

        # Esecuzione parallela controllata
        results = await asyncio.gather(*tasks)

        logger.info(f"Suite [{suite_name}] completata con successo.")
        return results

    async def run_test(self,test,resolver,):
        import time

        plugin_type = test["type"]

        if plugin_type not in self.registry or not self.registry[plugin_type]:
            logger.error(
                "Test %s: plugin di tipo '%s' assente nel Registry.",
                test.get("id"),
                plugin_type,
            )

            missing_plugin_result = PluginOutput(
                ok=False,
                data=None,
                error=PluginError(code="PLUGIN_NOT_CONFIGURED",
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

            return evaluated_result

        plugin = self.registry[plugin_type]

        logger.debug(
            "Esecuzione test %s tramite plugin %s",
            test["id"],
            plugin_type,
        )

        started = time.perf_counter()

        try:

            result = await plugin.run(test["input"],resolver,)

            duration_ms = round((time.perf_counter() - started) * 1000,2,)

            evaluated_result = await self.policy.handle(test,result,)

            evaluated_result["duration_ms"] = duration_ms
            evaluated_result["resolver"] = resolver
            evaluated_result["critical"] = bool(test.get("critical", False))

            return evaluated_result

        except Exception as exc:

            duration_ms = round((time.perf_counter() - started) * 1000,2,)

            logger.exception(
                "Errore critico non gestito durante il test %s",
                test.get("id"),
            )

            return {
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
                    "expected_assertions": test.get("assertions",{},),
                },
            }