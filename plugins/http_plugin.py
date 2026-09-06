class HttpPlugin:

    async def run(self, input_data, resolver):

        try:
            # chiamata HTTP simulata
            response = await self._request(input_data["url"])

            return {
                "ok": True,
                "data": response,
                "error": None
            }

        except TimeoutError:
            return self._error("HTTP_TIMEOUT", "Request timeout")

        except Exception as e:
            return self._error("HTTP_ERROR", str(e))