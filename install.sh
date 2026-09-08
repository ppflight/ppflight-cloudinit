#!/usr/bin/env bash
set -Eeuo pipefail

ppflight_download_bundle() {
  local destination="$1"
  curl --disable --fail --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 20 --max-time 300 --retry 3 \
    https://codeload.github.com/ppflight/ppflight-cloudinit/tar.gz/refs/heads/main \
    --output "$destination/bundle.tar.gz" || return 1
  tar -xzf "$destination/bundle.tar.gz" -C "$destination" || return 1
  /usr/bin/python3 -I - "$destination/ppflight-cloudinit-main" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
manifest = json.loads((root / "agent-vendor-manifest.v1.json").read_text())
for entry in manifest["files"]:
    path = (root / entry["path"]).resolve()
    if root not in path.parents or not path.is_file():
        sys.exit("运行文件路径无效：" + entry["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        sys.exit("运行文件校验失败：" + entry["path"])
print("安装文件下载及校验完成。")
PY
}

ppflight_install_main() {
  [[ ${EUID:-$(id -u)} -eq 0 && -d /etc/pve ]] || {
    printf '请在 Proxmox VE 节点的 root 终端运行。\n' >&2
    return 1
  }
  # stdin carries the downloaded script; the menu must read the actual terminal.
  exec 3</dev/tty || { printf '请在交互终端运行此命令。\n' >&2; return 1; }
  local command
  for command in curl tar mktemp python3; do
    command -v "$command" >/dev/null || { printf '缺少命令：%s\n' "$command" >&2; return 1; }
  done
  PPFLIGHT_INSTALL_DIR="$(mktemp -d /tmp/ppflight-cloudinit.XXXXXXXX)"
  trap 'rm -rf -- "$PPFLIGHT_INSTALL_DIR"' EXIT
  printf '正在下载模板安装程序……\n'
  ppflight_download_bundle "$PPFLIGHT_INSTALL_DIR" || {
    printf '下载安装程序失败，尚未开始制作模板。\n' >&2
    return 1
  }
  bash "$PPFLIGHT_INSTALL_DIR/ppflight-cloudinit-main/build-cloud-templates.sh" <&3
}

if [[ -z "${BASH_SOURCE[0]:-}" || "${BASH_SOURCE[0]}" == "$0" ]]; then
  ppflight_install_main "$@"
fi
