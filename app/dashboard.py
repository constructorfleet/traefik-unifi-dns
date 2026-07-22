"""Dashboard HTML rendering for the UniFi DNS Traefik controller."""
from html import escape
from string import Template


DASHBOARD_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>UniFi DNS Traefik</title>
  <style>
    body{font:16px system-ui;max-width:800px;margin:3rem auto;color:#172033}
    table{border-collapse:collapse;width:100%}
    td,th{padding:.6rem;border-bottom:1px solid #d9dee8;text-align:left}
    code{background:#f2f4f8;padding:.2rem}
  </style>
</head>
<body>
  <h1>UniFi DNS Traefik</h1>
  <p>Conflicts: <code>$conflicts</code></p>
  <p>Last error: <code>$error</code></p>
  <h2>Owned records</h2>
  <table>
    <tr><th>Hostname</th><th>CNAME target</th></tr>
    $rows
  </table>
</body>
</html>""")


def render_dashboard(ownership, conflicts, last_error):
    rows = ''.join(
        '<tr><td>{host}</td><td>{target}</td></tr>'.format(
            host=escape(host),
            target=escape(target),
        )
        for host, target in sorted(ownership.items())
    )
    if not rows:
        rows = '<tr><td colspan="2">No controller-owned records</td></tr>'

    conflict_text = ', '.join(escape(host) for host in sorted(conflicts)) or 'None'
    error_text = escape(last_error) if last_error else 'None'

    return DASHBOARD_TEMPLATE.substitute(
        conflicts=conflict_text,
        error=error_text,
        rows=rows,
    )
