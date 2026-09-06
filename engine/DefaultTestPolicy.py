class DefaultTestPolicy:

    def __init__(self, evaluator, builder):
        self.evaluator = evaluator
        self.builder = builder

    async def handle(self, test, plugin_result):
        if not plugin_result.ok:
            return self.builder.from_error(test, plugin_result)

        evaluation = self.evaluator.evaluate(plugin_result.data,test.get("assertions", {}))

        return self.builder.from_success(test,plugin_result,evaluation)