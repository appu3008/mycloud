# Hosting / app manager

The Hosting page (linked from Settings) turns this box into an all-in-one
server: MyCloud's API/SPA plus additional sites or app proxies on one nginx.

## Model

- **Static app**: files under `<data_dir>/hosting/<name>`, served by nginx
  `root`; the page can write small UTF-8 files (e.g. `index.html`) safely.
- **Proxy app**: forwards `domain/path` to `http://127.0.0.1:<port>`; run your
  own app process on that loopback port (systemd unit recommended).

Names, domains, paths and ports are validated; duplicate names, duplicate
routes and duplicate ports are rejected.

## Safeguards

- The API only **stages** config into `<data_dir>/hosting/staged/`.
  It never writes `/etc/nginx` and never reloads a service.
- `deployment/apply-hosting.sh.example` is the explicit sudo step: it installs
  the staged config, runs `nginx -t`, then reloads nginx.
- Static file writes reject absolute paths and `..` traversal.
- All hosting endpoints are admin-only and CSRF-protected.

## Typical flow

1. Settings -> Hosting -> add a static app (`site.local`).
2. Select it, write `index.html`.
3. Stage config; review the preview.
4. Run the apply script with sudo.
5. Add a hosts/MagicDNS entry for `site.local` and open it.
