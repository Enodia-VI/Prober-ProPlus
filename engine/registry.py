from plugins.dns_plugin import DnsPlugin
from plugins.nicupdate_plugin import NicUpdatePlugin

registry = {
    "dns_query": DnsPlugin(),
    "nic_update": NicUpdatePlugin(),
    # "dot": "",
    # "doh": "",
}