"""
Logging strutturato: contextvars per portare job_id/target/suite/test
in ogni riga di log anche con esecuzione concorrente (asyncio.gather
su più target/job in parallelo), più due formatter (testo grep-abile
e JSON).
"""

import contextvars
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

_job_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("job_id", default=None)
_target_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("target", default=None)
_suite_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("suite", default=None)
_test_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("test_id", default=None)

CONTEXT_FIELDS = ("job_id", "target", "suite", "test_id")


@contextmanager
def log_context(
    job_id: Optional[str] = None,
    target: Optional[str] = None,
    suite: Optional[str] = None,
    test_id: Optional[str] = None,
) -> Iterator[None]:
    """Imposta i campi di contesto per la durata del blocco 'with' (annidabile)."""
    tokens = []
    if job_id is not None:
        tokens.append((_job_id_var, _job_id_var.set(job_id)))
    if target is not None:
        tokens.append((_target_var, _target_var.set(target)))
    if suite is not None:
        tokens.append((_suite_var, _suite_var.set(suite)))
    if test_id is not None:
        tokens.append((_test_id_var, _test_id_var.set(test_id)))

    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def current_context() -> dict[str, Optional[str]]:
    """Snapshot dei campi di contesto correnti (utile nei test)."""
    return {
        "job_id": _job_id_var.get(),
        "target": _target_var.get(),
        "suite": _suite_var.get(),
        "test_id": _test_id_var.get(),
    }


class ContextFilter(logging.Filter):
    """Inietta i campi di contesto correnti in ogni LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = _job_id_var.get()
        record.target = _target_var.get()
        record.suite = _suite_var.get()
        record.test_id = _test_id_var.get()
        return True


# Attributi "di serie" di un LogRecord, per distinguerli dai campi
# extra passati con logger.info(msg, extra={...}).
_STANDARD_LOGRECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


def _extra_fields(record: logging.LogRecord) -> dict:
    return {
        key: value
        for key, value in vars(record).items()
        if key not in _STANDARD_LOGRECORD_ATTRS and key not in CONTEXT_FIELDS
    }


class TextFieldsFormatter(logging.Formatter):
    """Riga leggibile + campi key=value in coda (job_id=... target=... ...), grep-abile."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context_str = " ".join(f"{n}={getattr(record, n, None) or '-'}" for n in CONTEXT_FIELDS)
        parts = [base, context_str]

        extra = _extra_fields(record)
        if extra:
            parts.append(" ".join(f"{k}={v}" for k, v in extra.items()))

        return " | ".join(parts)


class JsonLinesFormatter(logging.Formatter):
    """Una riga = un oggetto JSON, stessi campi del TextFieldsFormatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for name in CONTEXT_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value

        payload.update(_extra_fields(record))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)