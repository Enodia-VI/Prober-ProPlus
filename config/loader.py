"""
Caricamento della configurazione dei test da config.yml.
"""

import logging
import os
import re
from functools import lru_cache
from typing import Any

import yaml

logger = logging.getLogger("config.loader")

# espressione per trovare e catturare i riferimenti alle variabili d'ambiente ${NOME_VARIABILE}
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")

# TODO: RIMUOVERE O SOSTITUIRE
def _substitute_env_vars(
    value: Any,
) -> Any:
    """
    Sostituisce ricorsivamente i placeholder ${VAR_NAME}
    con le corrispondenti variabili d'ambiente.
    """

    if isinstance(value, str):
        def _replace(match: re.Match[str],) -> str:

            var_name = match.group(1)
            env_value = os.environ.get(var_name)

            if env_value is None:
                raise RuntimeError(f"Variabile d'ambiente richiesta ma non impostata: {var_name}")
            return env_value
        return _ENV_VAR_PATTERN.sub(_replace,value,)

    if isinstance(value, dict):
        return {
            key: _substitute_env_vars(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [ _substitute_env_vars(item) for item in value]
    return value


def _load_test_configuration(path: str = "config.yml",) -> dict[str, Any]:
    """
    Carica e normalizza la configurazione dei test.
    """

    try:
        with open(path, encoding="utf-8",) as file:
            config = yaml.safe_load(file)
        config = _substitute_env_vars(config)

        logger.info("Configurazione dei test YAML caricata correttamente.")
        return config or {}
    except Exception as exc:

        logger.critical("Impossibile caricare %s: %s",path,exc,)
        return {}


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """
    Ritorna la configurazione dei test, caricandola al primo
    utilizzo e riutilizzando poi lo stesso risultato (singleton
    per processo, come il precedente CONFIG globale).
    """
    return _load_test_configuration()
