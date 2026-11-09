# Environment report — 2026-11-09 (measured on this host)

| Item | Value |
|---|---|
| OS | Kali GNU/Linux Rolling 2026.3 (kali-rolling) |
| Kernel | 7.2.15+kali-amd64 · x86_64 |
| CPU | 13th Gen Intel Core i5-1335U · 12 logic CPUs · VT-x present |
| RAM | 16 GB (15,657 MiB total; ~11 GiB available) · **no swap** |
| Disk | NVMe 476.9 GB: `/` ext4 263.5 GB (59 GB used, **187 GB free**, 25%); second **unmounted** ext4 `nvme0n1p7` 194.9 GB (untouched); EFI 260 MB |
| Python | 3.14.8 · pip 26.2.2 · PEP 668 externally-managed (venv required) |
| Preinstalled pkgs | fastapi 0.143.3, SQLAlchemy 2.0.52, pydantic 2.13.5, alembic 1.18.4, uvicorn 0.53.0, httpx 0.28.1 |
| Missing pkgs | argon2-cffi, python-multipart, pydantic-settings, pytest, pytest-asyncio |
| Node/npm | v22.18.0 / 10.9.3 · bun present |
| Git | 2.53.0, identity configured |
| Docker | **not installed** |
| Tailscale | 1.104.5 (installed) |
| systemd | 262 · ufw + nft available |
| Listening ports | MariaDB 127.0.0.1:3306 · SSH **0.0.0.0:22** (publicly bound — flagged) · 2 localhost app ports |
| Sensors | 7 hwmon entries → CPU temperature obtainable |
| SQLite | 3.53.4 (FTS5 usable) |
| Existing repo | none — fresh build; home dir contents left untouched |

## Predictions (to re-measure after dependency installs)
- Backend idle RSS: 80–150 MB. Thumbnail worker bounded ≤ 256 MB.
- venv install size: ~120–180 MB. Frontend node_modules: ~250–350 MB.
- Disk guardrails in settings: hard stop above 85% disk use; 30 GB reserve floor.

## Flagged items requiring user approval (planned, not executed)
1. Install backend Python deps into project venv (network).
2. Scaffold frontend with npm (network).
3. Any ufw/nftables change, SSH bind change, or Tailscale change (privileged).
4. Whether the unmounted 194.9 GB partition should host `storage/` (mount point
   under `/mnt` or FHS convention — needs sudo + fstab entry decision).
