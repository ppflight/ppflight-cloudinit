#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=build-cloud-templates.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../build-cloud-templates.sh"
host_test_dir="$(mktemp -d)"
trap 'rm -rf -- "$host_test_dir"' EXIT
install() {
  [[ "$1" == -m && "$2" == 0644 ]]
  [[ "$4" == /etc/apt/apt.conf.d/99zz-ppflight-host-no-auto-upgrades ]]
  cp "$3" "$host_test_dir/policy"
}
systemctl() {
  printf '%s\n' "$*" >> "$host_test_dir/commands"
  if [[ "$1" == is-enabled ]]; then printf 'masked\n'; return 1; fi
}
disable_pve_auto_updates
grep -qx 'APT::Periodic::Unattended-Upgrade "0";' "$host_test_dir/policy"
grep -qx 'Unattended-Upgrade::Automatic-Reboot "false";' "$host_test_dir/policy"
grep -qx 'mask --now apt-daily.timer apt-daily-upgrade.timer' "$host_test_dir/commands"
grep -qx 'mask apt-daily.service apt-daily-upgrade.service unattended-upgrades.service' "$host_test_dir/commands"
! grep -q 'pve-daily-update' "$host_test_dir/commands"
! grep -q '^stop ' "$host_test_dir/commands"
! grep -q -- '--now.*\.service' "$host_test_dir/commands"
systemctl() { if [[ "$1" == is-enabled ]]; then printf 'enabled\n'; fi; }
if (disable_pve_auto_updates); then
  printf 'Failed to detect an unmasked update unit\n' >&2
  exit 1
fi
printf 'PVE host update policy tests passed.\n'
