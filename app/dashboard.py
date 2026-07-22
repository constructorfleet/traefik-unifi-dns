"""Dashboard rendering and state serialization."""

from pathlib import Path

DASHBOARD_TEMPLATE = (Path(__file__).parent / "templates" / "dashboard.html").read_text()


def dashboard_state(controller) -> dict[str, object]:
    return {
        "dry_run": controller.dry_run,
        "last_error": controller.last_error,
        "last_reconcile": controller.last_reconcile,
        "counts": {
            "owned": len(controller.ownership),
            "conflicts": len(controller.conflicts),
            "ignored": len(controller.ignored),
            "claims": len(controller.claims),
        },
        "owned_records": [
            {"hostname": host, "target": target}
            for host, target in sorted(controller.ownership.items())
        ],
        "conflicts": sorted(controller.conflicts),
        "ignored": [
            {
                "service": item.service,
                "label": item.label,
                "hostname": item.host,
                "reason": item.reason,
            }
            for item in controller.ignored
        ],
        "claims": [
            {
                "hostname": claim.host,
                "target": claim.target,
                "service": claim.service,
                "type": claim.kind,
                "label": claim.label,
            }
            for claim in controller.claims
        ],
    }


def render_dashboard():
    return DASHBOARD_TEMPLATE
