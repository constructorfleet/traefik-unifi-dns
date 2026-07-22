---
name: unifi-dns-traefik
---

# UniFi DNS Traefik

`unifi-dns-traefik` is a small Dockerized controller for Docker Swarm. It watches Docker
service changes, reads opted-in Traefik router `Host(...)` rules, and reconciles those
hostnames into UniFi Network static DNS CNAME records.

It is designed for GitOps-managed Swarm deployments where services advertise DNS intent
through labels instead of hand-maintained DNS entries.

## Architecture

The service is split by responsibility:

- `app/controller.py`: UniFi reconciliation orchestration.
- `app/ports.py`: protocols for replaceable infrastructure adapters.
- `app/traefik.py`: Traefik label parsing and desired-record planning.
- `app/docker_client.py`: Docker Engine API adapter. Supports Unix sockets and HTTP socket proxies.
- `app/unifi_client.py`: UniFi Network static DNS API adapter.
- `app/state_store.py`: persisted ownership state so the controller only deletes records it owns.
- `app/runtime.py`: event/reconcile loop.
- `app/dashboard.py`: status UI template rendering.
- `app/templates/dashboard.html`: dashboard markup.
- `app/web.py`: health, readiness, metrics, and dashboard HTTP routes.
- `app/config.py`: environment parsing and validation.
- `app/main.py`: composition root.

The controller only mutates records it created or previously owned. Manual UniFi records are
left alone.

## Docker Labels

A service opts in with:

```yaml
deploy:
  labels:
    unifi-dns.enable: "true"
    unifi-dns.source: "app.home.example.com"
    unifi-dns.target: "docker-swarm"
    traefik.http.routers.app.rule: Host(`app.home.example.com`)
```

Sources can come from literal Traefik `Host(...)` values or from a comma/whitespace-separated
`unifi-dns.source` label. `HostRegexp`, wildcards, malformed rules, and hostnames outside
`ALLOWED_ZONES` are ignored. `ALLOWED_ZONES` is an allowlist for fully qualified hostnames; it
does not append zones to short source names.

Traefik labels alone are not enough. The controller only reads services with
`unifi-dns.enable: "true"` or `unifi-dns.enabled: "true"`, so `traefik.enable: "true"`
without the UniFi DNS opt-in is skipped.

Use `unifi-dns.source.<target>` when one service needs to claim hostnames for different CNAME
targets:

```yaml
deploy:
  labels:
    unifi-dns.enable: "true"
    unifi-dns.source.edge: "app.home.example.com"
    unifi-dns.source.media: "media.home.example.com"
```

If two services claim the same hostname with different targets, the hostname is treated as a
conflict and no UniFi record is changed for that host.

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `UNIFI_URL` | yes | none | Base URL for the UniFi Network application. |
| `UNIFI_VERIFY_SSL` | no | `true` | Verify the UniFi HTTPS certificate. Set to `false` for self-signed controller certificates, such as `https://192.168.1.1`. |
| `ALLOWED_ZONES` | yes | none | Comma-separated DNS zones the controller may manage. |
| `DOCKER_HOST` | no | `unix:///var/run/docker.sock` | Docker endpoint. Use `http://docker-socket-proxy:2375` or Docker-style `tcp://docker-socket-proxy:2375` for a socket proxy. |
| `UNIFI_API_KEY_FILE` | no | `/run/secrets/unifi_api_key` | File containing the UniFi API key. |
| `STATE_PATH` | no | `/state/ownership.json` | Persistent ownership-state file. |
| `DEFAULT_TARGET` | no | `docker-swarm` | CNAME target label fallback. |
| `CNAME_LOCALDOMAIN` | no | `local` | Suffix appended to target names. |
| `DRY_RUN` | no | `false` | Plan records and report state without mutating UniFi DNS or ownership state. |
| `REQUIRE_UNIFI_DNS_ENABLE` | no | `true` | Require `unifi-dns.enable: "true"` before reading a service. Set to `false` to process matching Traefik rules without the opt-in label. `DRY_RUN` still prevents mutations. |
| `ALWAYS_SHOW_DELETE` | no | `false` | Show the dashboard delete action for every target CNAME row instead of stale rows only. |
| `RECONCILE_INTERVAL_SECONDS` | no | `300` | Maximum time between full reconciles while watching events. |
| `PORT` | no | `8080` | HTTP UI and health endpoint port. |
| `LOG_LEVEL` | no | `INFO` | Python logging level. |

Every value-style environment variable also supports a Docker-style `_FILE` companion, such as
`UNIFI_URL_FILE`, `ALLOWED_ZONES_FILE`, or `DRY_RUN_FILE`. The file contents are read, trimmed,
and then validated as if the direct environment variable had been set. Setting both `NAME` and
`NAME_FILE` is rejected at startup. `UNIFI_API_KEY_FILE` remains the file path used to read the
UniFi API key itself.

In dry-run mode, create/update/delete candidates are logged with `"result": "dry_run"`. The
ownership state file is not updated, because dry-run records were not actually created and should
not become eligible for later deletion as controller-owned records.

Manual stack/service annotations from the dashboard are stored in the same state file as ownership
data and are restored after restarts.

## Deployment

For local development:

```bash
docker compose up --build
```

For Swarm/GitOps deployment, build and publish an image first, then deploy `stack.yml`:

```bash
export IMAGE=ghcr.io/your-org/unifi-dns-traefik:sha
docker stack deploy -c stack.yml unifi-dns-traefik
```

Create the UniFi API key secret before deploying:

```bash
printf '%s' "$UNIFI_API_KEY" | docker secret create unifi_dns_traefik_api_key -
```

## UI and Operations

The container exposes:

- `/`: reactive status dashboard with add-CNAME controls, a UniFi target-CNAME tab, owned records, source claims, ignored labels, conflicts, last error, and service/stack/URL filters.
- `/api/state`: current dashboard state as JSON.
- `/api/cname`: create a manual CNAME with a JSON `hostname` and optional target label.
- `/api/cname-metadata`: persist manual stack/service metadata for a target CNAME.
- `/events`: server-sent dashboard state events.
- `/healthz`: process health.
- `/readyz`: readiness after the first successful reconcile.
- `/metrics`: Prometheus-compatible gauges.

The Docker event stream is long-lived and may reconnect after an idle read timeout. This is logged
as `{"action":"docker_events","result":"reconnect"}` and the next loop performs a fresh reconcile.

## Development

Install dependencies:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Run quality gates:

```bash
ruff check .
ruff format --check .
PYTHONPATH=. python -m unittest discover -s tests -v
python -m py_compile app/*.py
docker compose -f docker-compose.yml config --no-interpolate
docker build -t unifi-dns-traefik:test .
```
