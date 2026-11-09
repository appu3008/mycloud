#!/usr/bin/env bash
# Read-only inspection of the spare partition (NEVER writes to it).
# Mounts READ-ONLY (noexec,nosuid,nodev), prints what is there in detail,
# then unmounts. No format, no delete, no modification.
#
# Run with:  sudo bash scripts/inspect_partition_readonly.sh
set -euo pipefail

PARTITION="/dev/nvme0n1p7"
MOUNTPOINT="/mnt/inspect-p7-readonly"
EXPECTED_UUID="267bb988-6945-4a39-a823-f984c38a8698"

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

echo "=== Partition identity ==="
blkid "$PARTITION" || true

actual_uuid="$(blkid -s UUID -o value "$PARTITION")"
[ "$actual_uuid" = "$EXPECTED_UUID" ] || {
  echo "ABORT: UUID mismatch ($actual_uuid)"; exit 1; }

echo
echo "=== Read-only mount at $MOUNTPOINT ==="
mkdir -p "$MOUNTPOINT"
mount -o ro,noexec,nosuid,nodev "$PARTITION" "$MOUNTPOINT"
trap 'umount "$MOUNTPOINT" || true' EXIT

echo
echo "=== What OS/installer made this filesystem ==="
cat "$MOUNTPOINT/etc/os-release" 2>/dev/null | head -4 || echo "(no os-release)"
echo
echo "=== Disk usage of the whole partition ==="
df -h "$MOUNTPOINT" | tail -1

echo
echo "=== Top-level sizes (biggest 15) ==="
du -x -h --max-depth=1 "$MOUNTPOINT" 2>/dev/null | sort -rh | head -16

echo
echo "=== User home directories on the old install ==="
ls -A "$MOUNTPOINT/home" 2>/dev/null || echo "(no /home)"

echo
echo "=== Real files in old homes (non-trivial size list, max 40) ==="
find "$MOUNTPOINT/home" -type f -size +1M -printf '%s %p\n' 2>/dev/null \
  | sort -rn | head -40 | awk '{printf "%8.1f MB  %s\n", $1/1048576, $2}'

echo
echo "=== Any users' Documents/Downloads/Videos/Pictures ==="
find "$MOUNTPOINT/home" -maxdepth 3 \( -type d \( -iname Documents -o -iname Downloads \
  -o -iname Pictures -o -iname Videos -o -iname Desktop \) \) -print 2>/dev/null

echo
echo "=== Windows remnant summary ==="
ls -A "$MOUNTPOINT/windows" 2>/dev/null | head -10 || true

echo
echo "=== fstab of the old install (tells us what this partition was) ==="
grep -vE '^\s*(#|$)' "$MOUNTPOINT/etc/fstab" 2>/dev/null | head -8 || echo "(no fstab)"

echo
echo "Unmounting (read-only). Nothing was modified."
