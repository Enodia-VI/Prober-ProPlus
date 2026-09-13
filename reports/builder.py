import json
from datetime import datetime
from typing import Any, Optional

from api.dictionaries import TestRunRequest

REPORT_VERSION = "1.0"

def _format_value(value: Any) -> str:
    """Formatta un valore per la visualizzazione testuale."""
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )
    return str(value)


def _html_escape(value: Any) -> str:
    import html
    return html.escape(_format_value(value), quote=True)


def _find_test_result(
    report: dict[str, Any],
    hostname: str,
    suite_name: str,
    test_id: str,
) -> Optional[dict[str, Any]]:
    for target in report.get("targets", []):
        if target.get("hostname") != hostname:
            continue

        suite = target.get("suites", {}).get(
            suite_name,
            {},
        )

        for test_result in suite.get("tests", []):
            if test_result.get("test_id") == test_id:
                return test_result

    return None


def determine_target_status(
    target: dict[str, Any],
) -> str:
    """
    Summary di un obbiettivo(Nodo).
    """

    statuses = [
        suite.get("status")
        for suite in target.get(
            "suites",
            {},
        ).values()
    ]

    if any(
        status == "ERROR"
        for status in statuses
    ):
        return "ERROR"

    if any(
        status == "FAIL"
        for status in statuses
    ):
        return "FAIL"

    if any(
        status == "PASS"
        for status in statuses
    ):
        return "PASS"

    return "SKIPPED"


def build_test_summary(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Costruisce il riepilogo globale del test job.
    """

    summary: dict[str, Any] = {
        "targets": len(results),
        "tests": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "critical_failures": 0,
        "critical_errors": 0,
    }

    for target in results:

        for suite in target.get(
            "suites",
            {},
        ).values():

            for test_result in suite.get(
                "tests",
                [],
            ):

                summary["tests"] += 1

                status = test_result.get(
                    "status"
                )

                critical = bool(
                    test_result.get(
                        "critical",
                        False,
                    )
                )

                if status == "PASS":

                    summary["passed"] += 1

                elif status == "FAIL":

                    summary["failed"] += 1

                    if critical:
                        summary[
                            "critical_failures"
                        ] += 1

                elif status == "ERROR":

                    summary["errors"] += 1

                    if critical:
                        summary[
                            "critical_errors"
                        ] += 1

                elif status == "SKIPPED":

                    summary["skipped"] += 1

    summary["critical_issues"] = (
        summary["critical_failures"]
        + summary["critical_errors"]
    )

    # Critical failure/error ha priorità assoluta.
    if summary["critical_issues"] > 0:

        summary["overall_status"] = "FAIL"

    elif summary["failed"] > 0:

        summary["overall_status"] = "FAIL"

    elif summary["errors"] > 0:

        summary["overall_status"] = "ERROR"

    else:

        summary["overall_status"] = "PASS"

    return summary


def build_suite_summary(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:

    suite_summary: dict[
        str,
        dict[str, Any],
    ] = {}

    for target in results:

        for suite_name, suite in target.get(
            "suites",
            {},
        ).items():

            current = suite_summary.setdefault(
                suite_name,
                {
                    "status": "SKIPPED",
                    "targets": 0,
                    "tests": 0,
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                },
            )

            current["targets"] += 1

            tests = suite.get(
                "tests",
                [],
            )

            current["tests"] += len(
                tests
            )

            for test_result in tests:

                status = test_result.get(
                    "status"
                )

                if status == "PASS":
                    current["passed"] += 1

                elif status == "FAIL":
                    current["failed"] += 1

                elif status == "ERROR":
                    current["errors"] += 1

                elif status == "SKIPPED":
                    current["skipped"] += 1

            suite_status = suite.get(
                "status"
            )

            # Priorità:
            # ERROR > FAIL > PASS > SKIPPED

            if suite_status == "ERROR":

                current["status"] = "ERROR"

            elif (
                suite_status == "FAIL"
                and current["status"] != "ERROR"
            ):

                current["status"] = "FAIL"

            elif (
                suite_status == "PASS"
                and current["status"] == "SKIPPED"
            ):

                current["status"] = "PASS"

    return suite_summary


def build_failure_index(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Costruisce un output dei test FAIL/ERROR.
    """

    failures: list[dict[str, Any]] = []

    for target in results:

        for suite_name, suite in target.get(
            "suites",
            {},
        ).items():

            for test_result in suite.get(
                "tests",
                [],
            ):

                status = test_result.get(
                    "status"
                )

                if status not in {
                    "FAIL",
                    "ERROR",
                }:
                    continue

                failures.append(
                    {
                        "hostname": target.get(
                            "hostname"
                        ),
                        "node_id": target.get(
                            "node_id"
                        ),
                        "suite": suite_name,
                        "test_id": test_result.get(
                            "test_id"
                        ),
                        "test_type": test_result.get(
                            "test_type"
                        ),
                        "status": status,
                        "critical": bool(
                            test_result.get(
                                "critical",
                                False,
                            )
                        ),
                        "resolver": test_result.get(
                            "resolver"
                        ),
                        "duration_ms": test_result.get(
                            "duration_ms"
                        ),
                        "summary": test_result.get(
                            "summary"
                        ),
                    }
                )

    return failures


#  ============ Costruzione JSON canonico ===================

def build_report(
    job_id: str,
    request: TestRunRequest,
    results: list[dict[str, Any]],
    created_at: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    """
    Costruisce il report JSON del test job.
    """

    summary = build_test_summary(
        results
    )

    suite_summary = build_suite_summary(
        results
    )

    failures = build_failure_index(
        results
    )

    completed_targets = 0
    failed_targets = 0
    error_targets = 0

    ipv4_available = 0
    ipv6_available = 0

    report_targets: list[
        dict[str, Any]
    ] = []

    for original_target in results:

        target_status = determine_target_status(
            original_target
        )

        if target_status in {
            "PASS",
            "FAIL",
            "ERROR",
        }:
            completed_targets += 1

        if target_status == "FAIL":
            failed_targets += 1

        elif target_status == "ERROR":
            error_targets += 1

        if original_target.get("ipv4"):
            ipv4_available += 1

        if original_target.get("ipv6"):
            ipv6_available += 1

        # Copia superficiale del risultato già prodotto dal motore.
        # Non creiamo una seconda struttura di test.
        target_report = dict(
            original_target
        )

        target_report["overall_status"] = (
            target_status
        )

        target_report["network"] = {
            "ipv4": target_report.pop(
                "ipv4",
                None,
            ),
            "ipv6": target_report.pop(
                "ipv6",
                None,
            ),
        }

        target_report["location"] = {
            "continent": target_report.pop(
                "continent",
                None,
            ),
            "country": target_report.pop(
                "country",
                None,
            ),
            "city": target_report.pop(
                "city",
                None,
            ),
            "site": target_report.pop(
                "site",
                None,
            ),
        }

        target_report["infrastructure"] = {
            "cluster_id": target_report.pop(
                "cluster_id",
                None,
            ),
            "cluster_name": target_report.pop(
                "cluster_name",
                None,
            ),
            "carrier": target_report.pop(
                "carrier",
                None,
            ),
            "device_type": target_report.pop(
                "device_type",
                None,
            ),
            "active": target_report.pop(
                "active",
                None,
            ),
        }

        report_targets.append(
            target_report
        )

    started_dt = datetime.fromisoformat(
        started_at
    )

    completed_dt = datetime.fromisoformat(
        completed_at
    )

    duration_ms = round(
        (
            completed_dt
            - started_dt
        ).total_seconds()
        * 1000,
        2,
    )

    return {
        "report_version": REPORT_VERSION,

        "job": {
            "job_id": job_id,
            "status": "completed",
            "overall_status": summary[
                "overall_status"
            ],
            "requested_by": request.requested_by,
            "created_at": created_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
        },

        "request": {
            "suites": list(
                request.suites
            ),
            "target_count": len(
                request.targets
            ),
            "send_email": request.send_email,
        },

        "summary": {
            "targets": {
                "total": len(results),
                "completed": completed_targets,
                "failed": failed_targets,
                "errors": error_targets,
            },

            "network": {
                "ipv4_available": ipv4_available,
                "ipv6_available": ipv6_available,
            },

            "tests": {
                "total": summary["tests"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "errors": summary["errors"],
                "skipped": summary["skipped"],
            },

            "critical": {
                "failures": summary[
                    "critical_failures"
                ],
                "errors": summary[
                    "critical_errors"
                ],
                "issues": summary[
                    "critical_issues"
                ],
            },
        },

        "suite_summary": suite_summary,

        "targets": report_targets,

        "failures": failures,
    }



# ============ Report TXT

def build_text_report(
    report: dict[str, Any],
) -> str:
    """Costruisce il report TXT per il terminale."""
    job = report.get("job", {})
    request = report.get("request", {})
    summary = report.get("summary", {})
    suite_summary = report.get("suite_summary", {})
    targets = report.get("targets", [])
    failures = report.get("failures", [])

    lines: list[str] = []

    lines.extend(
        [
            "=" * 78,
            "DNS ENTERPRISE TEST REPORT",
            "=" * 78,
            f"Report version : {_format_value(report.get('report_version'))}",
            f"Job ID         : {_format_value(job.get('job_id'))}",
            f"Status         : {_format_value(job.get('status'))}",
            f"Overall status : {_format_value(job.get('overall_status'))}",
            f"Requested by   : {_format_value(job.get('requested_by'))}",
            f"Created at     : {_format_value(job.get('created_at'))}",
            f"Started at     : {_format_value(job.get('started_at'))}",
            f"Completed at   : {_format_value(job.get('completed_at'))}",
            f"Duration (ms)  : {_format_value(job.get('duration_ms'))}",
            "",
            "-" * 78,
            "REQUEST",
            "-" * 78,
            f"Suites         : {', '.join(str(x) for x in request.get('suites', []))}",
            f"Target count   : {_format_value(request.get('target_count'))}",
            f"Send email     : {_format_value(request.get('send_email'))}",
            "",
            "-" * 78,
            "SUMMARY",
            "-" * 78,
        ]
    )

    targets_summary = summary.get("targets", {})
    network_summary = summary.get("network", {})
    tests_summary = summary.get("tests", {})
    critical_summary = summary.get("critical", {})

    lines.extend(
        [
            f"Targets        : total={_format_value(targets_summary.get('total'))} "
            f"completed={_format_value(targets_summary.get('completed'))} "
            f"failed={_format_value(targets_summary.get('failed'))} "
            f"errors={_format_value(targets_summary.get('errors'))}",
            f"Network        : ipv4={_format_value(network_summary.get('ipv4_available'))} "
            f"ipv6={_format_value(network_summary.get('ipv6_available'))}",
            f"Tests          : total={_format_value(tests_summary.get('total'))} "
            f"pass={_format_value(tests_summary.get('passed'))} "
            f"fail={_format_value(tests_summary.get('failed'))} "
            f"error={_format_value(tests_summary.get('errors'))} "
            f"skipped={_format_value(tests_summary.get('skipped'))}",
            f"Critical       : failures={_format_value(critical_summary.get('failures'))} "
            f"errors={_format_value(critical_summary.get('errors'))} "
            f"issues={_format_value(critical_summary.get('issues'))}",
            "",
            "-" * 78,
            "SUITE SUMMARY",
            "-" * 78,
        ]
    )

    for suite_name, suite in suite_summary.items():
        lines.append(
            f"{suite_name}: "
            f"status={_format_value(suite.get('status'))} "
            f"targets={_format_value(suite.get('targets'))} "
            f"tests={_format_value(suite.get('tests'))} "
            f"pass={_format_value(suite.get('passed'))} "
            f"fail={_format_value(suite.get('failed'))} "
            f"error={_format_value(suite.get('errors'))} "
            f"skipped={_format_value(suite.get('skipped'))}"
        )

    lines.extend(
        [
            "",
            "-" * 78,
            "TARGETS",
            "-" * 78,
        ]
    )

    for target in targets:
        network = target.get("network", {})
        location = target.get("location", {})
        infrastructure = target.get("infrastructure", {})

        lines.extend(
            [
                f"Target: {_format_value(target.get('hostname'))}",
                f"  Node ID       : {_format_value(target.get('node_id'))}",
                f"  Status        : {_format_value(target.get('overall_status'))}",
                f"  IPv4          : {_format_value(network.get('ipv4'))}",
                f"  IPv6          : {_format_value(network.get('ipv6'))}",
                f"  Location      : {_format_value(location.get('continent'))} / "
                f"{_format_value(location.get('country'))} / "
                f"{_format_value(location.get('city'))} / "
                f"{_format_value(location.get('site'))}",
                f"  Infrastructure: cluster={_format_value(infrastructure.get('cluster_id'))} "
                f"({ _format_value(infrastructure.get('cluster_name')) }) "
                f"carrier={_format_value(infrastructure.get('carrier'))} "
                f"type={_format_value(infrastructure.get('device_type'))} "
                f"active={_format_value(infrastructure.get('active'))}",
            ]
        )

        for suite_name, suite in target.get("suites", {}).items():
            lines.append(
                f"  Suite {suite_name}: "
                f"status={_format_value(suite.get('status'))}"
            )

            if suite.get("reason"):
                lines.append(
                    f"    Reason: {_format_value(suite.get('reason'))}"
                )

            for test_result in suite.get("tests", []):
                details = test_result.get("details", {}) or {}
                lines.extend(
                    [
                        f"    - {_format_value(test_result.get('test_id'))} "
                        f"[{_format_value(test_result.get('status'))}] "
                        f"type={_format_value(test_result.get('test_type'))} "
                        f"critical={_format_value(test_result.get('critical'))}",
                        f"      Summary : {_format_value(test_result.get('summary'))}",
                        f"      Resolver: {_format_value(test_result.get('resolver'))}",
                        f"      Duration: {_format_value(test_result.get('duration_ms'))} ms",
                    ]
                )

                if test_result.get("status") in {"FAIL", "ERROR"}:
                    if details.get("error_code") is not None:
                        lines.append(
                            f"      Error code   : {_format_value(details.get('error_code'))}"
                        )
                    if details.get("error_message") is not None:
                        lines.append(
                            f"      Error message: {_format_value(details.get('error_message'))}"
                        )
                    if details.get("expected_assertions") is not None:
                        lines.append(
                            "      Expected      : "
                            + _format_value(details.get("expected_assertions"))
                        )
                    if details.get("observed_data") is not None:
                        lines.append(
                            "      Observed      : "
                            + _format_value(details.get("observed_data"))
                        )
                    if details.get("evaluation_report") is not None:
                        lines.append(
                            "      Evaluation    : "
                            + _format_value(details.get("evaluation_report"))
                        )

        lines.append("")

    lines.extend(
        [
            "-" * 78,
            "FAILURES / ERRORS",
            "-" * 78,
        ]
    )

    if not failures:
        lines.append("No failures or errors.")
    else:
        for index, failure in enumerate(failures, start=1):
            hostname = failure.get("hostname")
            suite_name = failure.get("suite")
            test_id = failure.get("test_id")

            lines.extend(
                [
                    f"[{index}] {_format_value(hostname)} / "
                    f"{_format_value(suite_name)} / "
                    f"{_format_value(test_id)}",
                    f"    Status   : {_format_value(failure.get('status'))}",
                    f"    Type     : {_format_value(failure.get('test_type'))}",
                    f"    Critical : {_format_value(failure.get('critical'))}",
                    f"    Resolver : {_format_value(failure.get('resolver'))}",
                    f"    Duration : {_format_value(failure.get('duration_ms'))} ms",
                    f"    Summary  : {_format_value(failure.get('summary'))}",
                ]
            )

            details = _find_test_result(
                report,
                hostname=str(hostname),
                suite_name=str(suite_name),
                test_id=str(test_id),
            )
            if details:
                test_details = details.get("details", {}) or {}
                if test_details.get("expected_assertions") is not None:
                    lines.append(
                        "    Expected : "
                        + _format_value(test_details.get("expected_assertions"))
                    )
                if test_details.get("observed_data") is not None:
                    lines.append(
                        "    Observed : "
                        + _format_value(test_details.get("observed_data"))
                    )
                if test_details.get("error_code") is not None:
                    lines.append(
                        "    Error code: "
                        + _format_value(test_details.get("error_code"))
                    )
                if test_details.get("error_message") is not None:
                    lines.append(
                        "    Error message: "
                        + _format_value(test_details.get("error_message"))
                    )

                if failure.get("status") == "FAIL":
                    lines.append(
                        "    Interpretation: assertion del test non soddisfatte."
                    )
                    lines.append(
                        "    Recommended action: verificare resolver, "
                        "connettività DNS e dati osservati."
                    )
                elif failure.get("status") == "ERROR":
                    lines.append(
                        "    Interpretation: il test non è stato completato "
                        "correttamente dal motore."
                    )
                    lines.append(
                        "    Recommended action: verificare error code/message "
                        "e connettività del resolver."
                    )

            lines.append("")

    lines.extend(
        [
            "=" * 78,
            "END OF REPORT",
            "=" * 78,
            "",
        ]
    )

    return "\n".join(lines)



# ===== Report HTML

def build_html_report(report: dict[str, Any]) -> str:
    job = report.get('job', {})
    request = report.get('request', {})
    summary = report.get('summary', {})
    suite_summary = report.get('suite_summary', {})
    targets = report.get('targets', [])
    failures = report.get('failures', [])
    overall = str(job.get('overall_status', 'UNKNOWN'))
    status_class = {'PASS': 'status-pass', 'FAIL': 'status-fail', 'ERROR': 'status-error'}.get(overall, 'status-unknown')

    def metric(label: str, value: Any) -> str:
        return f'<div class="metric"><div class="metric-label">{_html_escape(label)}</div><div class="metric-value">{_html_escape(value)}</div></div>'

    parts = [
        '<!DOCTYPE html>', '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>DNS Test Report - {_html_escape(job.get("job_id"))}</title>', '<style>',
        ':root{font-family:Arial,Helvetica,sans-serif}body{margin:0;background:#f4f6f8;color:#20262d}.container{max-width:1400px;margin:0 auto;padding:24px}.header,.section{background:#fff;border:1px solid #d9dee3;border-radius:10px;padding:20px;margin-bottom:18px}.header h1{margin:0 0 10px;font-size:26px}.meta{color:#5f6b76;font-size:14px}.status{display:inline-block;margin-top:14px;padding:7px 12px;border-radius:999px;font-weight:700;font-size:13px}.status-pass{background:#e7f6ec;color:#1d6b35}.status-fail{background:#fdeaea;color:#a32121}.status-error{background:#fff3df;color:#8a5300}.status-unknown{background:#eceff2;color:#4d5965}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}.metric{border:1px solid #e1e5e9;border-radius:8px;padding:12px;background:#fafbfc}.metric-label{color:#66717c;font-size:12px}.metric-value{font-size:20px;font-weight:700}.target{border:1px solid #e0e4e8;border-radius:9px;padding:16px;margin-bottom:14px}.target h3{margin:0 0 8px}.target-meta{color:#626d78;font-size:13px;margin-bottom:12px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #e4e7ea;padding:8px;text-align:left;vertical-align:top}th{background:#f7f8fa}.suite{margin-top:14px}.suite-title{font-weight:700;margin-bottom:8px}.details{margin-top:8px;padding:10px 12px;background:#fafbfc;border-left:3px solid #c8d0d8;font-size:12px}.failure{border:1px solid #e4bcbc;border-radius:9px;padding:14px;margin-bottom:12px;background:#fffafa}.failure.error{border-color:#e7cf9e;background:#fffaf0}.footer{color:#707a84;text-align:center;font-size:12px;padding:10px 0 20px}@media(max-width:800px){.container{padding:12px}table{display:block;overflow-x:auto}}',
        '</style></head><body><div class="container">',
        '<div class="header"><h1>DNS Enterprise Test Report</h1><div class="meta">',
        f'Job ID: <code>{_html_escape(job.get("job_id"))}</code><br>Requested by: {_html_escape(job.get("requested_by"))}<br>Created: {_html_escape(job.get("created_at"))}<br>Duration: {_html_escape(job.get("duration_ms"))} ms</div>',
        f'<div class="status {status_class}">{_html_escape(overall)}</div></div>',
        # FIX: virgoletta di chiusura mancante su class="metrics" (rompeva il parsing dell'attributo).
        '<div class="section"><h2>Summary</h2><div class="metrics">',
        metric('Targets', summary.get('targets', {}).get('total')), metric('Completed', summary.get('targets', {}).get('completed')),
        metric('Target failures', summary.get('targets', {}).get('failed')), metric('Target errors', summary.get('targets', {}).get('errors')),
        metric('Tests', summary.get('tests', {}).get('total')), metric('Passed', summary.get('tests', {}).get('passed')), metric('Failed', summary.get('tests', {}).get('failed')), metric('Errors', summary.get('tests', {}).get('errors')), metric('Skipped', summary.get('tests', {}).get('skipped')), metric('Critical issues', summary.get('critical', {}).get('issues')),
        '</div></div>', '<div class="section"><h2>Request</h2><table>',
        f'<tr><th>Suites</th><td>{_html_escape(", ".join(map(str, request.get("suites", []))))}</td></tr>',
        f'<tr><th>Target count</th><td>{_html_escape(request.get("target_count"))}</td></tr>',
        f'<tr><th>Send email</th><td>{_html_escape(request.get("send_email"))}</td></tr></table></div>',
        '<div class="section"><h2>Suite Summary</h2><table><tr><th>Suite</th><th>Status</th><th>Targets</th><th>Tests</th><th>Pass</th><th>Fail</th><th>Error</th><th>Skipped</th></tr>'
    ]
    for name, s in suite_summary.items():
        parts.append(f'<tr><td>{_html_escape(name)}</td><td>{_html_escape(s.get("status"))}</td><td>{_html_escape(s.get("targets"))}</td><td>{_html_escape(s.get("tests"))}</td><td>{_html_escape(s.get("passed"))}</td><td>{_html_escape(s.get("failed"))}</td><td>{_html_escape(s.get("errors"))}</td><td>{_html_escape(s.get("skipped"))}</td></tr>')
    parts += ['</table></div>', '<div class="section"><h2>Targets</h2>']
    for t in targets:
        n = t.get('network', {}); loc = t.get('location', {}); inf = t.get('infrastructure', {})
        parts += [f'<div class="target"><h3>{_html_escape(t.get("hostname"))} [{_html_escape(t.get("overall_status"))}]</h3><div class="target-meta">Node ID: {_html_escape(t.get("node_id"))} | IPv4: {_html_escape(n.get("ipv4"))} | IPv6: {_html_escape(n.get("ipv6"))}<br>Location: {_html_escape(loc.get("continent"))} / {_html_escape(loc.get("country"))} / {_html_escape(loc.get("city"))} / {_html_escape(loc.get("site"))}<br>Cluster: {_html_escape(inf.get("cluster_id"))} ({_html_escape(inf.get("cluster_name"))}) | Carrier: {_html_escape(inf.get("carrier"))} | Type: {_html_escape(inf.get("device_type"))} | Active: {_html_escape(inf.get("active"))}</div>']
        for sname, s in t.get('suites', {}).items():
            parts += [f'<div class="suite"><div class="suite-title">{_html_escape(sname)} — {_html_escape(s.get("status"))}</div><table><tr><th>Test</th><th>Status</th><th>Type</th><th>Critical</th><th>Resolver</th><th>Duration</th><th>Summary</th></tr>']
            for tr in s.get('tests', []):
                parts.append(f'<tr><td><code>{_html_escape(tr.get("test_id"))}</code></td><td>{_html_escape(tr.get("status"))}</td><td>{_html_escape(tr.get("test_type"))}</td><td>{_html_escape(tr.get("critical"))}</td><td><code>{_html_escape(tr.get("resolver"))}</code></td><td>{_html_escape(tr.get("duration_ms"))} ms</td><td>{_html_escape(tr.get("summary"))}</td></tr>')
                if tr.get('status') in {'FAIL', 'ERROR'}:
                    d = tr.get('details', {}) or {}; bits = []
                    for k, l in [('expected_assertions', 'Expected'), ('observed_data', 'Observed'), ('evaluation_report', 'Evaluation'), ('error_code', 'Error code'), ('error_message', 'Error message')]:
                        if d.get(k) is not None:
                            bits.append(f'<div><strong>{l}:</strong> {_html_escape(d.get(k))}</div>')
                    if bits:
                        parts.append('<tr><td colspan="7"><div class="details">' + ''.join(bits) + '</div></td></tr>')
            parts.append('</table>')
            if s.get('reason'):
                parts.append(f'<div class="details"><strong>Reason:</strong> {_html_escape(s.get("reason"))}</div>')
            parts.append('</div>')
        parts.append('</div>')
    parts += ['</div><div class="section"><h2>Failures / Errors</h2>']
    if not failures:
        parts.append('<p>No failures or errors.</p>')
    else:
        for f in failures:
            cls = 'failure error' if f.get('status') == 'ERROR' else 'failure'
            parts += [f'<div class="{cls}"><strong>{_html_escape(f.get("hostname"))} / {_html_escape(f.get("suite"))} / <code>{_html_escape(f.get("test_id"))}</code></strong><div class="details">Status: {_html_escape(f.get("status"))}<br>Type: {_html_escape(f.get("test_type"))}<br>Critical: {_html_escape(f.get("critical"))}<br>Resolver: {_html_escape(f.get("resolver"))}<br>Duration: {_html_escape(f.get("duration_ms"))} ms<br>Summary: {_html_escape(f.get("summary"))}</div></div>']
    parts += ['</div><div class="footer">Generated from the canonical DNS test report.</div></div></body></html>']
    return '\n'.join(parts)