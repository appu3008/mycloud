# MyCloud — Deployment

## Development (current phase)
```bash
cd /home/appu/mycloud
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
# frontend (Phase 4)
```
Loopback binding only (project rule 9). CORS limited to the Vite dev origin.

## Production topology (target)
```
[Client] --HTTPS(Tailscale 100.x or LAN)--> nginx/caddy :443 --> uvicorn 127.0.0.1:8000
```
Components:
1. **uvicorn** via systemd unit (`app` venv, hardened: NoNewPrivileges, ProtectSystem=full,
   PrivateTmp).
2. **Reverse proxy** (nginx or Caddy) terminating TLS; serves only
   `/api/*` + frontend static build. Sets HSTS, CSP, `X-Content-Type-Options`.
3. **Tailscale (installed)**: private transport; each device joins the tailnet
   (device auth in the admin UI of tailscale, no MyCloud API key involved).
   Options: serve solely on the tailnet interface (recommended), or MagicDNS name +
   Let's Encrypt via TS cert command once the access model is verified.
4. **Docker Compose (optional; Docker not installed on this host — install first if
   desired, see dependency plan).** The compose file ships but is inert until Docker
   exists; compose is never required.

## NAT / CGNAT explanation (section 21)
- Home Wi-Fi + mobile data phone: phone cannot dial a private LAN address; it needs
  either (a) the tailnet (works across CGNAT — Tailscale punches through/DERPs),
  or (b) port forwarding + public IP + DNS + TLS, which is explicitly NOT assumed.
- CGNAT: carrier-side NAT means no inbound port forwarding at all — tailnet approach
  is the primary design; public exposure is out of scope until the security model is
  verified (section 12: sharing disabled publicly until then).
- Never expose SSH (currently bound 0.0.0.0), MariaDB (already loopback-only), or
  admin ports to the internet.

## Firewall guidance (to apply WITH user approval)
- ufw default deny incoming; allow 22 from LAN/tailnet only; proxy ports
  (443, tailnet interface); keep MariaDB off 0.0.0.0.

## systemd (files under `deployment/`)
- `mycloud-backend.service` (example unit, hardened flags, after=network.target)
- Install path: `/etc/systemd/system/` (privileged action — ask first).

## Concrete runbook (phase 17)
- `docs/REMOTE_ACCESS.md`: Tailscale Serve and nginx options, CGNAT notes,
  production checklist, verification commands.
- `deployment/nginx-mycloud.conf.example`: TLS, HSTS/CSP, SPA static files and
  `/api` proxy to the loopback backend.
- `deployment/tailscale-serve.sh.example`: private tailnet-only exposure that
  points at `127.0.0.1:8000` (the backend serves both API and SPA).
- Backend SPA fallback is covered by `tests/test_static_spa.py`: unknown API
  paths stay JSON 404 and 405 semantics are preserved.

No network state, firewall, or systemd units were changed on this host; all
deployment files are examples for review.
