class Evaluator:

    @classmethod
    def evaluate(cls, observed, assertions):

        groups = {}
        overall_result = True

        if "all" in assertions:

            all_results = [
                cls.evaluate_assertion(observed, a)
                for a in assertions["all"]
            ]

            groups["all"] = {
                "passed": all(r["passed"] for r in all_results),
                "results": all_results
            }

            overall_result &= groups["all"]["passed"]

        if "any" in assertions:

            any_results = [cls.evaluate_assertion(observed, a) for a in assertions["any"]]

            groups["any"] = {
                "passed": any(r["passed"] for r in any_results),
                "results": any_results
            }

            overall_result &= groups["any"]["passed"]

        return {
            "passed": overall_result,
            "groups": groups
        }

    @staticmethod
    def evaluate_assertion(observed, assertion):

        op = assertion["op"]
        expected = assertion["value"]

        if op == "equals":
            passed = observed == [expected]

        elif op == "contains":
            passed = any(expected in str(x) for x in observed)

        elif op == "not_contains":
            passed = all(expected not in str(x) for x in observed)

        else:
            raise ValueError(f"Unsupported operator: {op}")

        return {
            "op": op,
            "expected": expected,
            "passed": passed
        }