# Remote access: Tailscale + production deployment

This runbook is documentation only. It does **not** change firewall rules,
Tailscale state, or install services on this host — those are privileged
actions that require explicit approval.

## Topology

```
phone / laptop (tailnet)
        |  HTTPS on the tailnet (100.x / MagicDNS)
        v
[Tailscale Serve  ->  uvicorn 127.0.0.1:8000]     (simplest, private only)
   or
[nginx :443 TLS  ->  uvicorn 127.0.0.1:8000]      (LAN + tailnet, custom DNS)
```

uvicorn binds loopback only (project rule 9). The backend now also serves the
built Yew app from the same origin (`/files`, `/share/{token}`, etc.), so one
reverse-proxy target is enough — no separate frontend port in production.

## Option A — Tailscale Serve (recommended for CGNAT / no public IP)

1. Install and join the tailnet (`tailscale up`); approve the device in the
   Tailscale admin console.
2. Build the frontend: `cd frontend-rs && trunk build --release`.
3. Start the backend: `cd backend && .venv/bin/uvicorn app.main:app
   --host 127.0.0.1 --port 8000` (or the hardened systemd unit in
   `deployment/mycloud-backend.service.example`).
4. Review and run `deployment/tailscale-serve.sh.example`
   (`tailscale serve --bg --https=443 / http://127.0.0.1:8000`).
5. Open the MagicDNS URL from `tailscale serve status` on a phone using mobile
   data. CGNAT is fine: traffic stays on the tailnet, no inbound port forward.

To revoke a device: remove it from the Tailscale admin console **and** revoke
its MyCloud device in the Devices page. These are independent trust layers.

## Option B — nginx on LAN/tailnet with TLS

1. Copy `deployment/nginx-mycloud.conf.example` to
   `/etc/nginx/sites-available/mycloud`, set `server_name`, certificate paths,
   and the absolute path to `frontend-rs/dist`.
2. Bind nginx to the Tailscale interface (or LAN IP) on 443. Keep uvicorn on
   127.0.0.1:8000. Never expose SSH, MariaDB, or admin ports.
3. HSTS/CSP/X-Content-Type-Options are included in the example. Adjust CSP if
   you add new asset origins.
4. Reload nginx only after `nginx -t` passes.
5. Firewall (with approval): default-deny incoming; allow 443 only from the
   tailnet/LAN.

## Production checklist

- `MYCLOUD_ENVIRONMENT=production` (disables API docs, tightens health checks).
- Set a strong `MYCLOUD_SECRET_KEY`; rotate it only with a maintenance window
  (sessions invalidate on rotation).
- Set `MYCLOUD_CORS_ORIGINS` to the exact HTTPS origin(s) you actually use.
- Verify `/api/health` reports no errors; confirm disk guardrails are active.
- Create a backup job in Settings, run it once, and store a copy off-host.
- Exercise a restore from the snapshot (`BACKUP_AND_RESTORE.md`).
- Confirm a share link works from a device outside the LAN (if sharing is
  enabled) and that revoked/expired links return 410.

## Verification commands

```bash
curl -fsS https://<host>/api/health | python3 -m json.tool
curl -fsS -o /dev/null -w '%{http_code}\n' https://<host>/files   # 200 = SPA served
cd backend && .venv/bin/python -m pytest                          # 110 passing
```
