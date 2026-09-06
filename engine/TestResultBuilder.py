class TestResultBuilder:

    @staticmethod
    def from_error(
        test,
        plugin_result,
    ):
        return {
            "test_id": test.get("id"),
            "test_type": test.get("type"),
            "status": "ERROR",
            "critical": bool(
                test.get("critical", False)
            ),
            "summary": (
                "Il test non ha potuto completare "
                "l'ispezione di rete."
            ),
            "details": {
                "error_code": (
                    plugin_result.error.code
                    if plugin_result.error
                    else "UNKNOWN"
                ),
                "error_message": (
                    plugin_result.error.message
                    if plugin_result.error
                    else "Unknown Error"
                ),
                "expected_assertions": test.get(
                    "assertions",
                    {},
                ),
            },
        }

    @staticmethod
    def from_success(test,plugin_result,evaluation,):
        passed = bool(evaluation.get("passed"))
        return {
            "test_id": test.get("id"),
            "test_type": test.get("type"),
            "status": (
                "PASS"
                if passed
                else "FAIL"
            ),
            "critical": bool(
                test.get("critical", False)
            ),
            "summary": (
                "OK"
                if passed
                else "Assertion non soddisfatte."
            ),
            "details": {
                "observed_data": plugin_result.data,
                "expected_assertions": test.get(
                    "assertions",
                    {},
                ),
                "evaluation_report": evaluation.get(
                    "groups",
                    {},
                ),
            },
        }