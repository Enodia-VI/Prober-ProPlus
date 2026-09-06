
# Tipi descrittivi per lo stato dei test job.

from typing import Any, Literal, Optional, TypedDict

JobStatus = Literal["queued","running","completed","failed",]


class TestJobRecord(TypedDict, total=False):
    job_id: str
    status: JobStatus
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    requested_by: str
    target_count: int
    suites: list[str]
    send_email: bool

    # Presenti solo dopo un completamento con successo
    report: dict[str, Any]
    report_path: str
    text_report_path: str
    html_report_path: str

    # Presente solo in caso di fallimento del job
    error: str