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

If two services claim the same hostname with different targets, the hostname is treated as a
conflict and no UniFi record is changed for that host.

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `UNIFI_URL` | yes | none | Base URL for the UniFi Network application. |
| `ALLOWED_ZONES` | yes | none | Comma-separated DNS zones the controller may manage. |
| `DOCKER_HOST` | no | `unix:///var/run/docker.sock` | Docker endpoint. Use `http://docker-socket-proxy:2375` for a socket proxy. |
| `UNIFI_API_KEY_FILE` | no | `/run/secrets/unifi_api_key` | File containing the UniFi API key. |
| `STATE_PATH` | no | `/state/ownership.json` | Persistent ownership-state file. |
| `DEFAULT_TARGET` | no | `docker-swarm` | CNAME target label fallback. |
| `CNAME_LOCALDOMAIN` | no | `local` | Suffix appended to target names. |
| `DRY_RUN` | no | `false` | Plan records and report state without mutating UniFi DNS or ownership state. |
| `RECONCILE_INTERVAL_SECONDS` | no | `300` | Maximum time between full reconciles while watching events. |
| `PORT` | no | `8080` | HTTP UI and health endpoint port. |
| `LOG_LEVEL` | no | `INFO` | Python logging level. |

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

- `/`: status dashboard with owned records, conflicts, and last error.
- `/healthz`: process health.
- `/readyz`: readiness after the first successful reconcile.
- `/metrics`: Prometheus-compatible gauges.

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
