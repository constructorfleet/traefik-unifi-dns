# Decisions

## UniFi DNS controller ownership

`unifi-dns-traefik` reconciles only literal Traefik `Host()` labels on opted-in
Swarm services and only inside its explicit local-zone allowlist. Its state
volume records each key it created or updated. Removal is permitted only for a
key in that state, so manually managed UniFi records and external DNS zones are
out of scope. Conflicting targets leave an existing owned record unchanged.
