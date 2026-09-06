# TODO: Descrizione componente

import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter

logger = logging.getLogger("api.dns_servers")

router = APIRouter(tags=["dns-servers"])

DNS_SERVERS_FILE = os.path.join( "data", "dns_servers.json", )

DNS_SERVERS_STATE: dict[str, Any] = { "updated_at": None, "servers": [], }


def load_dns_servers_state() -> None:
    """
    Ripristina la lista DNS precedentemente salvata su disco.
    """

    if not os.path.exists( DNS_SERVERS_FILE ):
        return

    try:
        with open( DNS_SERVERS_FILE, encoding="utf-8", ) as file:

            DNS_SERVERS_STATE.update( json.load(file) )

        logger.info(
            "Lista DNS server ripristinata da disco (%d nodi).",
            len( DNS_SERVERS_STATE["servers"] ),
        )

    except Exception as exc:

        logger.warning(
            "Impossibile leggere %s: %s",
            DNS_SERVERS_FILE,
            exc,
        )


@router.get( "/api/dns-servers" )
async def get_dns_servers(
    continent: Optional[str] = None,
    country: Optional[str] = None,
):

    servers = DNS_SERVERS_STATE[ "servers" ]

    if continent:
        servers = [ server for server in servers if (server.get("continent") or "" ).lower() == continent.lower() ]

    if country:
        servers = [ server for server in servers if ( server.get("country") or "" ).lower() == country.lower() ]

    return {
        "updated_at": ( DNS_SERVERS_STATE[ "updated_at" ] ),
        "servers": servers,
    }
