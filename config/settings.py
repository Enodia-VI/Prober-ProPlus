import logging
import os
import re
from functools import lru_cache
from typing import Any, Literal, Optional

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config")

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


class Settings(BaseSettings):
    """Variabili di processo, prima lette con os.getenv() sparsi in più moduli."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    inventory_push_token: Optional[str] = None
    reports_base_dir: str = "data/reports"
    test_run_max_concurrent_targets: int = 10
    config_path: str = "config.yml"
    log_level: str = "INFO"
    log_file: str = "logs/engine.log"
    log_format: Literal["text", "json"] = "text"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _substitute_env_vars(value: Any) -> Any:
    """Sostituisce ricorsivamente i placeholder ${VAR} con le variabili d'ambiente."""
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                raise RuntimeError(f"Variabile d'ambiente richiesta ma non impostata: {var_name}")
            return env_value
        return _ENV_VAR_PATTERN.sub(_replace, value)

    if isinstance(value, dict):
        return {key: _substitute_env_vars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


def _load_test_configuration(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as file:
            config = yaml.safe_load(file)
        config = _substitute_env_vars(config)
        logger.info("Configurazione dei test YAML caricata correttamente.")
        return config or {}
    except Exception as exc:
        logger.critical("Impossibile caricare %s: %s", path, exc)
        return {}


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    return _load_test_configuration(get_settings().config_path)