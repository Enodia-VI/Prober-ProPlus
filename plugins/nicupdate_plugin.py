import httpx
from api.dictionaries import PluginOutput, PluginError, NicUpdateInput

class NicUpdatePlugin:

    async def run(self, input_data: dict, resolver=None) -> PluginOutput:
        try:
            parsed = NicUpdateInput(**input_data)
        except Exception as e:
            return self._error("NIC_INVALID_INPUT", str(e))

        target_url = f"https://{parsed.hostname}/{parsed.url}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    target_url,
                    auth=(parsed.username, parsed.password)
                )

            body = response.text.strip()

            return PluginOutput(ok=True, data=[body], error=None)

        except httpx.TimeoutException:
            return self._error("NIC_TIMEOUT", "Timeout contacting nic-update endpoint")
        except httpx.ConnectError as e:
            return self._error("NIC_NETWORK_ERROR", f"Network unreachable: {e}")
        except Exception as e:
            return self._error("NIC_UNKNOWN_ERROR", str(e))

    @staticmethod
    def _error(code: str, message: str) -> PluginOutput:
        return PluginOutput(ok=False, data=None, error=PluginError(code=code, message=message))