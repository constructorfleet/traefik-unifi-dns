"""Dashboard HTML rendering for the UniFi DNS Traefik controller."""

from html import escape
from pathlib import Path
from string import Template

DASHBOARD_TEMPLATE = Template((Path(__file__).parent / "templates" / "dashboard.html").read_text())


def render_dashboard(ownership, conflicts, last_error):
    rows = "".join(
        f"<tr><td>{escape(host)}</td><td>{escape(target)}</td></tr>"
        for host, target in sorted(ownership.items())
    )
    if not rows:
        rows = '<tr><td colspan="2">No controller-owned records</td></tr>'

    conflict_text = ", ".join(escape(host) for host in sorted(conflicts)) or "None"
    error_text = escape(last_error) if last_error else "None"

    return DASHBOARD_TEMPLATE.substitute(
        conflicts=conflict_text,
        error=error_text,
        rows=rows,
    )
