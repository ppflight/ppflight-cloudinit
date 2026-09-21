#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../tools/build-template-engine.sh"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
# Exercise real orchestration without calling PVE, network, or host package tools.
find_config_arg() { :; }; load_config() { :; }; parse_args() { :; }
load_template_catalog() { :; }; select_templates() { SELECTED_ROWS=('9000|ubuntu|one|||||||||||' '9001|debian|two|||||||||||'); }
preflight() { :; }; flock() { :; }; show_storage_layout() { :; }
resolve_storage_content_dir() { printf '%s' "$work"; }
check_existing_vmids() { printf 'checked\n' >> "$work/order"; }
prepare_host_for_build() { :; }
download_image() { printf 'download-%s\n' "$1" >> "$work/order"; }
write_snippets() { printf 'profiles\n' >> "$work/order"; }
prepare_images() { printf 'prepared\n' >> "$work/order"; [[ "${fail_prepare:-0}" == 0 ]] || exit 72; }
create_template() { printf 'create-%s\n' "${1%%|*}" >> "$work/order"; }
verify_template() { printf 'verified\n' >> "$work/order"; }
backup_templates() { :; }; write_manifest() { :; }; qm() { :; }
CACHE_DIR="$work"
# Redirect the fixed lock path used by main so test environments need no root.
# Function definitions are ours; only the exact known lock literal is rewritten.
eval "$(declare -f main | sed "s@/run/lock/ppflight-cloudinit.lock@$work/lock@g")"
(main)
[[ "$(cat "$work/order")" == $'checked\ndownload-one\ndownload-two\nprofiles\nprepared\ncreate-9000\ncreate-9001\nverified\nverified' ]]
: > "$work/order"
if (fail_prepare=1; main); then echo 'Preparation failure unexpectedly succeeded' >&2; exit 1; fi
if grep -q '^create-' "$work/order"; then echo 'Old templates were touched before preparation completed' >&2; exit 1; fi
printf 'Rebuild ordering and failure preservation passed.\n'
