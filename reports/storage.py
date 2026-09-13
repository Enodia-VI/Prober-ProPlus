"""
Persistenza su filesystem dei report (JSON, TXT, HTML) e helper
per accedervi in modo sicuro dall'API.
"""

import json
import os
import uuid
from typing import Any, Optional

from reports.builder import build_html_report, build_text_report

REPORTS_BASE_DIR = os.getenv("REPORTS_BASE_DIR",os.path.join("data", "reports"),)
os.makedirs(REPORTS_BASE_DIR,exist_ok=True,)

_REPORT_FILENAMES = {
    "json": "report.json",
    "txt": "report.txt",
    "html": "report.html",
}

def is_valid_job_id(job_id: str) -> bool:
    """
    Verifica che job_id sia un UUID valido.
    """

    try:
        uuid.UUID(str(job_id))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def report_dir(job_id: str) -> str:
    return os.path.join(REPORTS_BASE_DIR,job_id,)


def report_file_path(job_id: str,report_format: str,) -> str:
    filename = _REPORT_FILENAMES.get(report_format)

    if filename is None:
        raise ValueError(f"Formato report sconosciuto: {report_format}")

    return os.path.join(report_dir(job_id),filename,)


def report_exists(job_id: str,report_format: str,) -> bool:
    return os.path.exists(report_file_path(job_id, report_format))



def _atomic_write(path: str, content: str) -> None:
    directory = os.path.dirname(path)

    os.makedirs(directory,exist_ok=True,)

    temp_path = os.path.join(directory,f".{os.path.basename(path)}.tmp",)

    with open(temp_path,"w",encoding="utf-8",) as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())

    os.replace(temp_path,path,)


def save_json_report(job_id: str,report: dict[str, Any],) -> str:
    """Salva il report JSON."""

    path = report_file_path(job_id, "json")

    content = json.dumps(report,ensure_ascii=False,indent=2,) + "\n"
    _atomic_write(path, content)

    return path


def save_text_report(job_id: str,report: dict[str, Any],) -> str:
    """Costruisce e salva il report TXT."""

    path = report_file_path(job_id, "txt")

    _atomic_write(path,build_text_report(report),)
    return path


def save_html_report(job_id: str,report: dict[str, Any],) -> str:
    """Costruisce e salva il report HTML."""

    path = report_file_path(job_id, "html")

    _atomic_write(path,build_html_report(report),)
    return path


def load_json_report(job_id: str,) -> Optional[dict[str, Any]]:
    """Carica il report JSON canonico dal filesystem, se esiste."""

    path = report_file_path(job_id, "json")

    if not os.path.exists(path):
        return None

    with open(path,encoding="utf-8",) as file:
        return json.load(file)