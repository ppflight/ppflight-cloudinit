#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=tools/build-template-engine.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../tools/build-template-engine.sh"
profile_test_dir="$(mktemp -d)"
trap 'rm -rf -- "$profile_test_dir"' EXIT
resolve_storage_content_dir() { printf '%s\n' "$profile_test_dir"; }
ALLOW_ROOT_PASSWORD_SSH=1
TIMEZONE=UTC
write_snippets
for family in debian rhel; do
  profile="$profile_test_dir/$DEBIAN_SNIPPET"
  reference="$SCRIPT_DIR/cloud-init/ubuntu-root-password-bbr.yaml"
  if [[ "$family" == rhel ]]; then
    profile="$profile_test_dir/$RHEL_SNIPPET"
    reference="$SCRIPT_DIR/cloud-init/rhel-root-password-bbr.yaml"
  fi
  diff -u <(sed '/^# Reference copy/d' "$reference") "$profile"
  grep -qx 'package_update: false' "$profile"
  grep -qx 'package_upgrade: false' "$profile"
  grep -qx 'package_reboot_if_required: false' "$profile"
  grep -q 'systemctl, mask,' "$profile"
done
grep -q 'APT::Periodic::Unattended-Upgrade "0"' "$profile_test_dir/$DEBIAN_SNIPPET"
grep -q 'apply_updates = no' "$profile_test_dir/$RHEL_SNIPPET"
grep -q 'dnf-automatic-install.service' "$profile_test_dir/$RHEL_SNIPPET"
printf 'Cloud profile tests passed.\n'
