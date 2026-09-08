#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=install.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../install.sh"
fixture_dir="$(mktemp -d)"
trap 'rm -rf -- "$fixture_dir"' EXIT
mkdir -p "$fixture_dir/source/ppflight-cloudinit-main" "$fixture_dir/output"
python3 - "$fixture_dir/source/ppflight-cloudinit-main" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
script = b'#!/bin/bash\necho menu\n'
(root / 'build-cloud-templates.sh').write_bytes(script)
(root / 'agent-vendor-manifest.v1.json').write_text(json.dumps({
    'files': [{'path': 'build-cloud-templates.sh', 'sha256': hashlib.sha256(script).hexdigest()}]
}))
PY
tar -czf "$fixture_dir/fixture.tar.gz" -C "$fixture_dir/source" ppflight-cloudinit-main
curl() {
  while (($#)); do
    if [[ "$1" == --output ]]; then cp "$fixture_dir/fixture.tar.gz" "$2"; return; fi
    shift
  done
  return 1
}
ppflight_download_bundle "$fixture_dir/output"
[[ -f "$fixture_dir/output/ppflight-cloudinit-main/build-cloud-templates.sh" ]]
printf 'corrupted\n' >> "$fixture_dir/source/ppflight-cloudinit-main/build-cloud-templates.sh"
tar -czf "$fixture_dir/fixture.tar.gz" -C "$fixture_dir/source" ppflight-cloudinit-main
if ppflight_download_bundle "$fixture_dir/output"; then
  printf 'Corrupt bundle was accepted.\n' >&2
  exit 1
fi
curl() { return 22; }
if ppflight_download_bundle "$fixture_dir/output"; then
  printf 'Download failure was ignored.\n' >&2
  exit 1
fi
printf 'Installer tests passed.\n'
