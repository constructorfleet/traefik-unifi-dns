"""Dashboard rendering and state serialization."""

from pathlib import Path

DASHBOARD_TEMPLATE = (Path(__file__).parent / "templates" / "dashboard.html").read_text()


def dashboard_state(controller) -> dict[str, object]:
    claims_by_host = {claim.host: claim for claim in controller.claims}
    skipped_claims_by_host = {claim.host: claim for claim in controller.plan.skipped_claims}
    manual_metadata = controller.manual_metadata
    target_domains = controller.target_domains()
    unifi_target_records = [
        _unifi_target_record(
            record,
            claims_by_host,
            skipped_claims_by_host,
            manual_metadata,
            controller.plan.desired,
        )
        for record in controller.unifi_records
        if _is_cname(record) and record.get("value") in target_domains
    ]
    return {
        "dry_run": controller.dry_run,
        "default_target": controller.default_target,
        "cname_localdomain": controller.localdomain,
        "always_show_delete": controller.always_show_delete,
        "last_error": controller.last_error,
        "last_reconcile": controller.last_reconcile,
        "counts": {
            "owned": len(controller.ownership),
            "conflicts": len(controller.conflicts),
            "ignored": len(controller.ignored),
            "claims": len(controller.claims),
            "unifi_target_records": len(unifi_target_records),
            "stale_unifi_target_records": sum(
                1 for record in unifi_target_records if record["status"] == "stale"
            ),
        },
        "owned_records": [
            {
                "hostname": host,
                "target": target,
                "service": _metadata_value(manual_metadata, host, "service")
                or (claims_by_host[host].service if host in claims_by_host else ""),
                "stack": _metadata_value(manual_metadata, host, "stack")
                or (claims_by_host[host].stack if host in claims_by_host else ""),
            }
            for host, target in sorted(controller.ownership.items())
        ],
        "conflicts": sorted(controller.conflicts),
        "ignored": [
            {
                "service": item.service,
                "stack": item.stack,
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
                "stack": claim.stack,
                "type": claim.kind,
                "label": claim.label,
            }
            for claim in controller.claims
        ],
        "unifi_target_records": unifi_target_records,
    }


def render_dashboard():
    return DASHBOARD_TEMPLATE


def _is_cname(record: dict[str, object]) -> bool:
    record_type = record.get("record_type", record.get("type", "cname"))
    return str(record_type).lower() == "cname"


def _unifi_target_record(
    record,
    claims_by_host,
    skipped_claims_by_host,
    manual_metadata,
    desired,
):
    hostname = record.get("key", "")
    claim = claims_by_host.get(hostname) or skipped_claims_by_host.get(hostname)
    manual = manual_metadata.get(hostname, {})
    has_manual_metadata = bool(manual.get("stack") or manual.get("service"))
    status = "manual" if has_manual_metadata else ("current" if hostname in desired else "stale")
    return {
        "hostname": hostname,
        "target": record.get("value", ""),
        "status": status,
        "stack": manual.get("stack", "") or (claim.stack if claim else ""),
        "service": manual.get("service", "") or (claim.service if claim else ""),
    }


def _metadata_value(metadata, host, key) -> str:
    return metadata.get(host, {}).get(key, "")
