#!/usr/bin/env bash
# Mount the spare ext4 partition as MyCloud's file storage.
# Defensive: refuses to proceed if the partition already contains files.
#
# Run with sudo (requires password):
#   sudo bash scripts/mount_storage_partition.sh
#
# This script: verifies the partition, mounts it, checks it is empty (or
# already contains the expected MyCloud layout), creates storage subdirs,
# prints the fstab line to persist across reboots. It NEVER formats or
# repartitions anything.
set -euo pipefail

PARTITION="/dev/nvme0n1p7"
MOUNTPOINT="/mnt/mycloud-storage"
EXPECTED_UUID="267bb988-6945-4a39-a823-f984c38a8698"  # verified 2026-11-09

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

actual_uuid="$(blkid -s UUID -o value "$PARTITION")"
[ "$actual_uuid" = "$EXPECTED_UUID" ] || {
  echo "ABORT: $PARTITION UUID mismatch ($actual_uuid). Check lsblk -f."; exit 1; }

if ! findmnt -n "$MOUNTPOINT" >/dev/null 2>&1; then
  mkdir -p "$MOUNTPOINT"
  # noexec/nosuid/nodev: nothing under storage is ever executed (SECURITY.md)
  mount -o noexec,nosuid,nodev "$PARTITION" "$MOUNTPOINT"
fi

# Ownership for the service user
chown appu:appu "$MOUNTPOINT"
chmod 750 "$MOUNTPOINT"

# Refuse if partition contains unexpected data (safe check: created by this
# script earlier is fine).
contents="$(ls -A "$MOUNTPOINT" 2>/dev/null || true)"
non_mycloud="$(echo "$contents" | grep -v -E '^(\.mycloud-storage|files|thumbnails|temporary)$' | grep -v '^$' || true)"
if [ -n "$non_mycloud" ]; then
  echo "ABORT: partition is NOT empty. Existing entries:"
  echo "$contents"
  echo "Review these files first; nothing was placed on the partition."
  exit 1
fi

install -d -o appu -g appu -m 750 \
  "$MOUNTPOINT/files" "$MOUNTPOINT/thumbnails" "$MOUNTPOINT/temporary"
touch "$MOUNTPOINT/.mycloud-storage"

echo
echo "Mounted at $MOUNTPOINT ($(df -h "$MOUNTPOINT" | tail -1 | awk '{print $2}') capacity)."
echo
echo "To persist across reboots, append this line to /etc/fstab:"
echo "UUID=$EXPECTED_UUID  /mnt/mycloud-storage  ext4  noexec,nosuid,nodev  0  2"
echo
echo "Then update MyCloud configuration (done for you below if .env exists):"
if [ -f /home/appu/mycloud/.env ]; then
  if grep -q "MYCLOUD_STORAGE_ROOT" /home/appu/mycloud/.env; then
    sed -i 's|^MYCLOUD_STORAGE_ROOT=.*|MYCLOUD_STORAGE_ROOT=/mnt/mycloud-storage|' \
      /home/appu/mycloud/.env
  else
    echo "MYCLOUD_STORAGE_ROOT=/mnt/mycloud-storage" >> /home/appu/mycloud/.env
  fi
  echo "  .env updated: MYCLOUD_STORAGE_ROOT=/mnt/mycloud-storage"
else
  echo "  Run manually:  echo 'MYCLOUD_STORAGE_ROOT=/mnt/mycloud-storage' >> /home/appu/mycloud/.env"
fi
echo
echo "Done. Restart the backend to pick up the new storage root."
