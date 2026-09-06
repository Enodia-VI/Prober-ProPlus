import socket
import ipaddress

def is_ip_address(nameserver):
    try:
        ipaddress.ip_address(nameserver)
        return True
    except ValueError:
        return False


def resolve_domain_name(nameserver):
    if is_ip_address(nameserver):
        return nameserver
    else:
        # first check if the 'flashstart.com' suffix is present. In case it's not, append it
        if not nameserver.endswith('.flashstart.com'):
            nameserver += '.flashstart.com'

        try:
            return socket.gethostbyname(nameserver)
        except socket.gaierror:
            # get_logger().error(f"Failed to resolve {nameserver}")
            return None
