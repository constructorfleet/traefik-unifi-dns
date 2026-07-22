"""Dashboard HTML rendering for the UniFi DNS Traefik controller."""

from html import escape
from pathlib import Path
from string import Template

DASHBOARD_TEMPLATE = Template((Path(__file__).parent / "templates" / "dashboard.html").read_text())


def render_dashboard(ownership, conflicts, last_error, ignored=(), claims=(), dry_run=False):
    rows = "".join(
        f"<tr><td>{escape(host)}</td><td>{escape(target)}</td></tr>"
        for host, target in sorted(ownership.items())
    )
    if not rows:
        rows = '<tr><td colspan="2">No controller-owned records</td></tr>'

    ignored_rows = "".join(
        "<tr>"
        f"<td>{escape(item.service)}</td>"
        f"<td>{escape(item.label)}</td>"
        f"<td>{escape(item.host)}</td>"
        f"<td>{escape(item.reason)}</td>"
        "</tr>"
        for item in ignored
    )
    if not ignored_rows:
        ignored_rows = '<tr><td colspan="4">No ignored labels</td></tr>'

    claim_rows = "".join(
        "<tr>"
        f"<td>{escape(claim.host)}</td>"
        f"<td>{escape(claim.target)}</td>"
        f"<td>{escape(claim.service)}</td>"
        f"<td>{escape(claim.kind)}</td>"
        f"<td>{escape(claim.label)}</td>"
        "</tr>"
        for claim in claims
    )
    if not claim_rows:
        claim_rows = '<tr><td colspan="5">No active source claims</td></tr>'

    conflict_text = ", ".join(escape(host) for host in sorted(conflicts)) or "None"
    error_text = escape(last_error) if last_error else "None"

    return DASHBOARD_TEMPLATE.substitute(
        conflicts=conflict_text,
        dry_run="enabled" if dry_run else "disabled",
        error=error_text,
        ignored_rows=ignored_rows,
        claim_rows=claim_rows,
        rows=rows,
    )
