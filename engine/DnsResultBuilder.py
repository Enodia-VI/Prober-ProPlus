class DnsResultBuilder:

    @staticmethod
    def success(data):

        return {
            "ok": True,
            "data": data,
            "error": None,
            "message": None
        }

    @staticmethod
    def error(code, message):

        return {
            "ok": False,
            "data": [],
            "error": code,
            "message": message
        }