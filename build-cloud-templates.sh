#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=tools/build-template-engine.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/tools/build-template-engine.sh"

choose_templates() {
  local row vmid name answer token found
  local -a requested=() chosen=()
  printf '\n选择模板（ALL 全选；多个 VMID 用逗号或空格分隔）\n'
  for row in "${TEMPLATE_ROWS[@]}"; do
    IFS='|' read -r vmid name _ <<< "$row"
    printf '  %s  %s\n' "$vmid" "$name"
  done
  while true; do
    read -r -p '模板：' answer || die '输入已结束，安装取消'
    answer="${answer//,/ }"
    read -r -a requested <<< "$answer"
    if [[ ${#requested[@]} == 1 && "${requested[0]^^}" == ALL ]]; then
      ONLY_TEMPLATES=all
      return
    fi
    chosen=()
    for token in "${requested[@]}"; do
      found=0
      for row in "${TEMPLATE_ROWS[@]}"; do
        if [[ "${row%%|*}" == "$token" ]]; then found=1; break; fi
      done
      if [[ "$found" == 0 ]]; then
        printf '无效模板：%s，请重新选择。\n' "$token"
        chosen=()
        break
      fi
      if [[ " ${chosen[*]} " != *" $token "* ]]; then chosen+=("$token"); fi
    done
    if ((${#chosen[@]})); then
      ONLY_TEMPLATES="$(IFS=,; printf '%s' "${chosen[*]}")"
      return
    fi
    printf '请输入模板 VMID 或 ALL。\n'
  done
}

choose_storage() {
  local role="$1" title="$2" variable="$3" rows id type free answer index
  local -a ids=()
  rows="$(python3 -c '
import json, sys
data = json.load(sys.stdin)
if data.get("state") != "succeeded":
    sys.exit("存储发现失败")
for s in data["storages"]:
    if s["enabled"] and s["active"] and s["roleEligibility"][sys.argv[1]]["allowed"]:
        free = ("%.1f GiB" % (int(s["availableBytes"]) / 1024**3)
                if s["availableBytesKnown"] else "未知")
        print("|".join((s["storageId"], s["type"], free)))
' "$role" <<< "$STORAGE_DISCOVERY")" || die '读取存储列表失败'
  [[ -n "$rows" ]] || die "$title：没有启用且在线的合格存储，请先在 PVE 配置对应内容类型"
  printf '\n%s\n' "$title"
  while IFS='|' read -r id type free; do
    ids+=("$id")
    printf '  %s) %s  [%s]  可用：%s\n' "${#ids[@]}" "$id" "$type" "$free"
  done <<< "$rows"
  while true; do
    read -r -p '选择序号：' answer || die '输入已结束，安装取消'
    for index in "${!ids[@]}"; do
      if [[ "$answer" == "$((index + 1))" ]]; then
        printf -v "$variable" '%s' "${ids[$index]}"
        return
      fi
    done
    printf '无效序号，请重新选择。\n'
  done
}

interactive_main() {
  (($# == 0)) || die '直接运行 bash build-cloud-templates.sh，按菜单选择即可，无需参数'
  [[ ${EUID:-$(id -u)} -eq 0 && -d /etc/pve ]] || die '请在 Proxmox VE 节点以 root 运行'
  [[ -t 0 ]] || die '请在交互终端运行 bash build-cloud-templates.sh'
  require_command python3
  require_command pvesh
  require_command pvesm
  load_template_catalog
  choose_templates
  STORAGE_DISCOVERY="$(python3 "$CATALOG_HELPER" discover)" || die '发现 PVE 存储失败'
  choose_storage image '选择镜像下载位置（iso、snippets）' FILE_STORAGE
  choose_storage template '选择模板安装／恢复目标（images）' IMAGE_STORAGE
  choose_storage backup '选择备份文件保存位置（backup）' BACKUP_STORAGE
  printf '\n开始安装：模板=%s，镜像=%s，安装／恢复=%s，备份=%s\n' \
    "$ONLY_TEMPLATES" "$FILE_STORAGE" "$IMAGE_STORAGE" "$BACKUP_STORAGE"
  unset CONFIG_FILE
  CACHE_DIR=''
  REPLACE_EXISTING=0
  FORCE_REPLACE_UNMANAGED=0
  main
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  interactive_main "$@"
fi
