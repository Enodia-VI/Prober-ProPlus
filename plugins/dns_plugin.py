import dns.query
import dns.asyncquery
import dns.message
import dns.rdatatype
import dns.exception
import dns.resolver
from api.dictionaries import PluginOutput, BasePlugin, PluginError, DnsInput

"""
    Definizione del plugin principale per i test DNS
"""
class DnsPlugin(BasePlugin):

    async def run(self, input_data: dict, resolver: str) -> PluginOutput:
        try:
            parsed = DnsInput(**input_data)
            query = self._build_query(parsed.qname,parsed.qtype)

            data = await self._query_dns(resolver, query)

            return PluginOutput(ok=True,data=data,error=None)

        # Gestion degli errori ed eventuale output

        except dns.exception.Timeout:
            return self._error("DNS_TIMEOUT", "Timeout contacting DNS server")

        except dns.resolver.NXDOMAIN:
            return self._error("DNS_NXDOMAIN", "Domain does not exist")

        except dns.resolver.NoNameservers:
            return self._error("DNS_NO_NAMESERVERS", "No nameservers available")

        except OSError as e:
            # Aggiungo il messaggio originale dell'OSError per un debug più facile
            return self._error("DNS_NETWORK_ERROR", f"Network unreachable: {e}")

        except Exception as e:
            return self._error("DNS_UNKNOWN_ERROR", str(e))



    @staticmethod
    def _error(code: str, message: str) -> PluginOutput:
        typed_error = PluginError(code=code,message=message)

        return PluginOutput(ok=False,data=None,error=typed_error)

    @staticmethod
    def _build_query(domain, qtype):
        rdtype = dns.rdatatype.from_text(qtype)
        return dns.message.make_query(domain, rdtype)

    @staticmethod
    async def _query_dns(where, query):

        answer = await dns.asyncquery.udp(query,where,timeout=10)

        return [str(rdata) for rrset in answer.answer for rdata in rrset]