# Own-network auditing (Security Lab)

The Security Lab page (linked from Settings) inventories services on networks
**you own**. It is deliberately narrow:

- A scan requires an active **scope** (CIDR) with an owner, optional expiry,
  and written notes. Scopes can be revoked at any time.
- Only RFC1918 / loopback / link-local IPv4 targets are accepted. Public IPs
  are rejected with a 400 before any connection is attempted.
- The target must be inside the chosen scope (403 otherwise).
- Scans check TCP reachability on a small port list and record open ports,
  generic service names, and a severity hint. No credentials are tried, no
  exploit payloads are sent, no version/banner scraping is performed.
- Every scope change and scan is written to `/api/v1/admin/audit` with the
  actor, target and finding count.
- The hardening panel derives its checklist from real local config
  (production mode, secret key length, CORS, admin count, backup jobs, DB).

This is an inventory/defensive tool, not an attack platform. Do not use it on
networks you do not own or administer. The host has `nmap` installed, but the
implementation uses its own bounded socket scanner so behavior is predictable
and testable; no external packages are required.

The corresponding API lives under `/api/v1/security/*` and is admin-only.
