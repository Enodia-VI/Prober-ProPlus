import os
from typing import Optional

from fastapi import HTTPException


def validate_internal_token(x_internal_token: Optional[str]) -> None:
    """
    Verifica il token utilizzato dalle chiamate interne.
    """
    expected_token = os.environ.get("INVENTORY_PUSH_TOKEN")
    if not expected_token or x_internal_token != expected_token:
        raise HTTPException(status_code=401,detail="Token interno mancante o non valido.",)