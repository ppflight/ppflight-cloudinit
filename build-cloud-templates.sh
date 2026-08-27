#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_VERSION="2.0.0"

# All settings can be overridden as environment variables or in CONFIG_FILE.
# The final VM disk storage is intentionally required. A host with both an SSD
# and a RAID pool cannot be mapped safely from device names alone.
IMAGE_STORAGE="${IMAGE_STORAGE:-}"
FILE_STORAGE="${FILE_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"
CACHE_DIR="${CACHE_DIR:-}"
DISK_SIZE="${DISK_SIZE:-16G}"
MEMORY_MB="${MEMORY_MB:-2048}"
CORES="${CORES:-2}"
CPU_TYPE="${CPU_TYPE:-host}"
BALLOON="${BALLOON:-0}"
FIREWALL="${FIREWALL:-1}"
DISK_SSD="${DISK_SSD:-1}"
DNS_SERVERS="${DNS_SERVERS-1.1.1.1 8.8.8.8}"
TIMEZONE="${TIMEZONE:-UTC}"
ALLOW_ROOT_PASSWORD_SSH="${ALLOW_ROOT_PASSWORD_SSH:-1}"
ENABLE_QOS="${ENABLE_QOS:-1}"
REPLACE_EXISTING="${REPLACE_EXISTING:-0}"
FORCE_REPLACE_UNMANAGED="${FORCE_REPLACE_UNMANAGED:-0}"
CLEANUP_FAILED_VM="${CLEANUP_FAILED_VM:-1}"
ONLY_TEMPLATES="${ONLY_TEMPLATES:-all}"

QOS_MBPS_RD="${QOS_MBPS_RD:-200}"
QOS_MBPS_WR="${QOS_MBPS_WR:-150}"
QOS_MBPS_RD_MAX="${QOS_MBPS_RD_MAX:-350}"
QOS_MBPS_WR_MAX="${QOS_MBPS_WR_MAX:-300}"
QOS_IOPS_RD="${QOS_IOPS_RD:-5000}"
QOS_IOPS_WR="${QOS_IOPS_WR:-3500}"
QOS_IOPS_RD_MAX="${QOS_IOPS_RD_MAX:-8000}"
QOS_IOPS_WR_MAX="${QOS_IOPS_WR_MAX:-6000}"
QOS_IOPS_RD_MAX_LENGTH="${QOS_IOPS_RD_MAX_LENGTH:-30}"
QOS_IOPS_WR_MAX_LENGTH="${QOS_IOPS_WR_MAX_LENGTH:-30}"

CURRENT_VMID=""
CURRENT_NAME=""
DEBIAN_SNIPPET=""
RHEL_SNIPPET=""
CREATED_VMIDS=()
SELECTED_ROWS=()

readonly TEMPLATE_ROWS=(
  "9000|ubuntu-2204|ubuntu-22.04-server-cloudimg-amd64.img|https://cloud-images.ubuntu.com/releases/jammy/release/ubuntu-22.04-server-cloudimg-amd64.img|https://cloud-images.ubuntu.com/releases/jammy/release/SHA256SUMS|sha256|debian|192.0.2.1|Ubuntu 22.04 LTS official released cloud image"
  "9001|ubuntu-2404|ubuntu-24.04-server-cloudimg-amd64.img|https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img|https://cloud-images.ubuntu.com/releases/noble/release/SHA256SUMS|sha256|debian|192.0.2.2|Ubuntu 24.04 LTS official released cloud image"
  "9002|almalinux-8|AlmaLinux-8-GenericCloud-latest.x86_64.qcow2|https://repo.almalinux.org/almalinux/8/cloud/x86_64/images/AlmaLinux-8-GenericCloud-latest.x86_64.qcow2|https://repo.almalinux.org/almalinux/8/cloud/x86_64/images/CHECKSUM|sha256|rhel|192.0.2.3|AlmaLinux 8 official GenericCloud image"
  "9003|debian-13|debian-13-generic-amd64.qcow2|https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2|https://cloud.debian.org/images/cloud/trixie/latest/SHA512SUMS|sha512|debian|192.0.2.4|Debian 13 official GenericCloud image"
  "9004|debian-12|debian-12-generic-amd64.qcow2|https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2|https://cloud.debian.org/images/cloud/bookworm/latest/SHA512SUMS|sha512|debian|192.0.2.5|Debian 12 official GenericCloud image"
  "9005|centos-stream-9|CentOS-Stream-GenericCloud-9-latest.x86_64.qcow2|https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-9-latest.x86_64.qcow2|https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-9-latest.x86_64.qcow2.SHA256SUM|sha256|rhel|192.0.2.6|CentOS Stream 9 official GenericCloud image; requires x86-64-v2"
  "9006|centos-stream-10|CentOS-Stream-GenericCloud-10-latest.x86_64.qcow2|https://cloud.centos.org/centos/10-stream/x86_64/images/CentOS-Stream-GenericCloud-10-latest.x86_64.qcow2|https://cloud.centos.org/centos/10-stream/x86_64/images/CentOS-Stream-GenericCloud-10-latest.x86_64.qcow2.SHA256SUM|sha256|rhel|192.0.2.7|CentOS Stream 10 official GenericCloud image; requires x86-64-v3"
)

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Build seven Proxmox Cloud-Init templates from official cloud images.

Usage:
  sudo bash build-cloud-templates.sh [options]

Options:
  --config FILE       Source configuration overrides from FILE.
  --image-storage ID  PVE storage for final template disks.
  --file-storage ID   Directory storage for cache and snippets.
  --cache-dir PATH    Override the cloud-image download cache path.
  --bridge NAME       PVE bridge used by template net0.
  --replace           Replace existing project-managed templates.
  --force-replace-unmanaged
                      With --replace, also replace an untagged template whose
                      VMID and name both match the selected definition.
  --only LIST         Comma-separated VMIDs or names (default: all).
  --no-qos            Do not add disk bandwidth/IOPS limits.
  --help              Show this help.

Examples:
  sudo bash build-cloud-templates.sh --image-storage local-zfs
  sudo bash build-cloud-templates.sh --image-storage raid-zfs --file-storage local
  sudo bash build-cloud-templates.sh --image-storage raid-zfs --replace
  sudo IMAGE_STORAGE=nvme-zfs bash build-cloud-templates.sh --only 9000,9001
EOF
}

parse_args() {
  while (($#)); do
    case "$1" in
      --config)
        (($# >= 2)) || die "--config requires a file"
        CONFIG_FILE="$2"
        shift 2
        ;;
      --replace)
        REPLACE_EXISTING=1
        shift
        ;;
      --force-replace-unmanaged)
        FORCE_REPLACE_UNMANAGED=1
        shift
        ;;
      --image-storage)
        (($# >= 2)) || die "--image-storage requires a PVE storage ID"
        IMAGE_STORAGE="$2"
        shift 2
        ;;
      --file-storage)
        (($# >= 2)) || die "--file-storage requires a PVE storage ID"
        FILE_STORAGE="$2"
        shift 2
        ;;
      --cache-dir)
        (($# >= 2)) || die "--cache-dir requires an absolute path"
        CACHE_DIR="$2"
        shift 2
        ;;
      --bridge)
        (($# >= 2)) || die "--bridge requires a bridge name"
        BRIDGE="$2"
        shift 2
        ;;
      --only)
        (($# >= 2)) || die "--only requires a list"
        ONLY_TEMPLATES="$2"
        shift 2
        ;;
      --no-qos)
        ENABLE_QOS=0
        shift
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *) die "unknown option: $1" ;;
    esac
  done
}

find_config_arg() {
  local args=("$@") index
  for ((index=0; index<${#args[@]}; index++)); do
    if [[ "${args[$index]}" == "--config" ]]; then
      ((index + 1 < ${#args[@]})) || die "--config requires a file"
      CONFIG_FILE="${args[$((index + 1))]}"
      return
    fi
  done
}

load_config() {
  if [[ -n "${CONFIG_FILE:-}" ]]; then
    [[ -r "$CONFIG_FILE" ]] || die "cannot read config: $CONFIG_FILE"
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
  fi
}

on_exit() {
  local rc=$?
  trap - EXIT
  if [[ -n "$CURRENT_VMID" && "$CLEANUP_FAILED_VM" == "1" ]]; then
    if qm status "$CURRENT_VMID" >/dev/null 2>&1 &&
       qm config "$CURRENT_VMID" | grep -qx "name: $CURRENT_NAME" &&
       qm config "$CURRENT_VMID" | grep -Eq '^tags: .*ppflight-cloudinit-build([;,]|$)'; then
      log "Cleaning incomplete project VMID $CURRENT_VMID"
      qm destroy "$CURRENT_VMID" --purge 1 --destroy-unreferenced-disks 1 || true
    fi
  fi
  if ((rc != 0)); then
    printf 'Build failed with exit code %s.\n' "$rc" >&2
  fi
  exit "$rc"
}
trap on_exit EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

validate_integer() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "$name must be a non-negative integer"
}

storage_is_active() {
  pvesm status 2>/dev/null | awk -v id="$1" 'NR > 1 && $1 == id && $3 == "active" { found=1 } END { exit !found }'
}

storage_value() {
  local storage="$1" key="$2"
  pvesh get "/storage/$storage" --output-format json | perl -MJSON::PP -e '
    my $key = shift @ARGV;
    local $/;
    my $data = JSON::PP::decode_json(<STDIN>);
    exit 0 if !exists $data->{$key} || !defined $data->{$key};
    my $value = $data->{$key};
    if (ref($value) eq "ARRAY") {
      print join(",", @{$value});
    } elsif (!ref($value)) {
      print $value;
    }
  ' "$key"
}

storage_content() {
  storage_value "$1" content
}

storage_content_dir() {
  local storage="$1" content_type="$2" fallback="$3" overrides entry value
  local entries=()
  overrides="$(storage_value "$storage" content-dirs)"
  IFS=',' read -r -a entries <<< "$overrides"
  for entry in "${entries[@]}"; do
    if [[ "${entry%%=*}" == "$content_type" && "$entry" == *=* ]]; then
      value="${entry#*=}"
      [[ -n "$value" && "$value" != /* && "/$value/" != *"/../"* ]] ||
        die "unsafe content-dirs value for $storage/$content_type: $value"
      printf '%s\n' "$value"
      return
    fi
  done
  printf '%s\n' "$fallback"
}

ensure_storage_content() {
  local storage="$1" required="$2" current
  current="$(storage_content "$storage")"
  [[ ",$current," == *",$required,"* ]] && return 0
  log "Adding content type '$required' to PVE storage '$storage' while preserving: ${current:-none}"
  if [[ -n "$current" ]]; then
    pvesm set "$storage" --content "$current,$required"
  else
    pvesm set "$storage" --content "$required"
  fi
}

resolve_file_storage_path() {
  local path
  path="$(storage_value "$FILE_STORAGE" path)"
  [[ -n "$path" && "$path" == /* ]] || die "$FILE_STORAGE must be a directory storage with an absolute path"
  printf '%s\n' "$path"
}

storage_descriptor() {
  local storage="$1" type path pool vgname thinpool
  type="$(storage_value "$storage" type)"
  path="$(storage_value "$storage" path)"
  pool="$(storage_value "$storage" pool)"
  vgname="$(storage_value "$storage" vgname)"
  thinpool="$(storage_value "$storage" thinpool)"

  case "$type" in
    dir|nfs|cifs)
      printf 'type=%s path=%s' "$type" "${path:-unknown}"
      ;;
    zfspool)
      printf 'type=zfspool pool=%s' "${pool:-unknown}"
      ;;
    lvmthin)
      printf 'type=lvmthin vg=%s thinpool=%s' "${vgname:-unknown}" "${thinpool:-unknown}"
      ;;
    rbd)
      printf 'type=rbd pool=%s' "${pool:-unknown}"
      ;;
    *)
      printf 'type=%s' "${type:-unknown}"
      ;;
  esac
}

show_storage_layout() {
  local file_storage_path="$1" snippet_relative="$2" mount_info free_space
  mount_info="$(findmnt -T "$CACHE_DIR" -n -o SOURCE,FSTYPE,TARGET 2>/dev/null || true)"
  free_space="$(df -hP "$CACHE_DIR" | awk 'NR == 2 {print $4 " available on " $6}')"

  log "Resolved download cache: $CACHE_DIR"
  log "Download filesystem: ${mount_info:-unable to resolve}; ${free_space:-free space unknown}"
  log "Cloud-Init snippets: storage=$FILE_STORAGE path=$file_storage_path/$snippet_relative"
  log "Final OS and Cloud-Init disks: $IMAGE_STORAGE ($(storage_descriptor "$IMAGE_STORAGE"))"
}

select_templates() {
  local row vmid name token matched
  if [[ "$ONLY_TEMPLATES" == "all" || -z "$ONLY_TEMPLATES" ]]; then
    SELECTED_ROWS=("${TEMPLATE_ROWS[@]}")
    return
  fi

  IFS=',' read -r -a requested <<< "$ONLY_TEMPLATES"
  for token in "${requested[@]}"; do
    matched=0
    for row in "${TEMPLATE_ROWS[@]}"; do
      IFS='|' read -r vmid name _ <<< "$row"
      if [[ "$token" == "$vmid" || "$token" == "$name" ]]; then
        SELECTED_ROWS+=("$row")
        matched=1
        break
      fi
    done
    ((matched == 1)) || die "unknown template in --only: $token"
  done
}

preflight() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || die "run this script as root on a Proxmox VE node"
  for cmd in qm pvesm pvesh pveversion qemu-img curl sha256sum sha512sum awk grep sed ip findmnt df flock perl; do
    require_command "$cmd"
  done
  perl -MJSON::PP -e 'exit 0' >/dev/null 2>&1 || die "required Perl module not found: JSON::PP"
  [[ -d /etc/pve ]] || die "/etc/pve not found; this does not look like a Proxmox VE node"
  [[ -n "$IMAGE_STORAGE" ]] || die "final disk storage is required; use --image-storage <PVE-storage-ID>"
  storage_is_active "$IMAGE_STORAGE" || die "image storage is not active: $IMAGE_STORAGE"
  storage_is_active "$FILE_STORAGE" || die "file storage is not active: $FILE_STORAGE"
  [[ ",$(storage_content "$IMAGE_STORAGE")," == *",images,"* ]] || die "$IMAGE_STORAGE does not allow VM images"
  ip link show "$BRIDGE" >/dev/null 2>&1 || die "bridge not found: $BRIDGE"

  for pair in MEMORY_MB:"$MEMORY_MB" CORES:"$CORES" BALLOON:"$BALLOON" FIREWALL:"$FIREWALL" DISK_SSD:"$DISK_SSD"; do
    validate_integer "${pair%%:*}" "${pair#*:}"
  done
  [[ "$DISK_SIZE" =~ ^[0-9]+[KMGT]$ ]] || die "DISK_SIZE must look like 16G"
  [[ -z "$CACHE_DIR" || "$CACHE_DIR" == /* ]] || die "CACHE_DIR must be an absolute path"
  [[ "$ALLOW_ROOT_PASSWORD_SSH" == "0" || "$ALLOW_ROOT_PASSWORD_SSH" == "1" ]] || die "ALLOW_ROOT_PASSWORD_SSH must be 0 or 1"
  [[ "$DISK_SSD" == "0" || "$DISK_SSD" == "1" ]] || die "DISK_SSD must be 0 or 1"
  [[ "$ENABLE_QOS" == "0" || "$ENABLE_QOS" == "1" ]] || die "ENABLE_QOS must be 0 or 1"
  [[ "$REPLACE_EXISTING" == "0" || "$REPLACE_EXISTING" == "1" ]] || die "REPLACE_EXISTING must be 0 or 1"
  [[ "$FORCE_REPLACE_UNMANAGED" == "0" || "$FORCE_REPLACE_UNMANAGED" == "1" ]] || die "FORCE_REPLACE_UNMANAGED must be 0 or 1"
  [[ "$CLEANUP_FAILED_VM" == "0" || "$CLEANUP_FAILED_VM" == "1" ]] || die "CLEANUP_FAILED_VM must be 0 or 1"
  [[ "$FORCE_REPLACE_UNMANAGED" == "0" || "$REPLACE_EXISTING" == "1" ]] || die "--force-replace-unmanaged also requires --replace"

  if [[ "$ENABLE_QOS" == "1" ]]; then
    local help field
    help="$(qm help set --verbose 2>&1)"
    for field in mbps_rd mbps_wr mbps_rd_max mbps_wr_max iops_rd iops_wr iops_rd_max iops_wr_max iops_rd_max_length iops_wr_max_length; do
      grep -q "$field" <<< "$help" || die "this PVE version does not expose disk field: $field (use --no-qos or upgrade PVE)"
    done
    for pair in \
      QOS_MBPS_RD:"$QOS_MBPS_RD" QOS_MBPS_WR:"$QOS_MBPS_WR" \
      QOS_MBPS_RD_MAX:"$QOS_MBPS_RD_MAX" QOS_MBPS_WR_MAX:"$QOS_MBPS_WR_MAX" \
      QOS_IOPS_RD:"$QOS_IOPS_RD" QOS_IOPS_WR:"$QOS_IOPS_WR" \
      QOS_IOPS_RD_MAX:"$QOS_IOPS_RD_MAX" QOS_IOPS_WR_MAX:"$QOS_IOPS_WR_MAX" \
      QOS_IOPS_RD_MAX_LENGTH:"$QOS_IOPS_RD_MAX_LENGTH" QOS_IOPS_WR_MAX_LENGTH:"$QOS_IOPS_WR_MAX_LENGTH"; do
      validate_integer "${pair%%:*}" "${pair#*:}"
    done
    ((QOS_MBPS_RD_MAX >= QOS_MBPS_RD)) || die "read burst must be >= sustained read"
    ((QOS_MBPS_WR_MAX >= QOS_MBPS_WR)) || die "write burst must be >= sustained write"
    ((QOS_IOPS_RD_MAX >= QOS_IOPS_RD)) || die "read IOPS burst must be >= sustained read IOPS"
    ((QOS_IOPS_WR_MAX >= QOS_IOPS_WR)) || die "write IOPS burst must be >= sustained write IOPS"
  fi

  log "PVE: $(pveversion)"
  log "Selected final disk storage: $IMAGE_STORAGE; file storage: $FILE_STORAGE; bridge: $BRIDGE"
}

write_snippets() {
  local file_path snippet_relative snippet_dir permit_root password_auth
  local debian_tmp rhel_tmp debian_hash rhel_hash
  ensure_storage_content "$FILE_STORAGE" snippets
  file_path="$(resolve_file_storage_path)"
  snippet_relative="$(storage_content_dir "$FILE_STORAGE" snippets snippets)"
  snippet_dir="$file_path/$snippet_relative"
  install -d -m 0755 "$snippet_dir"

  if [[ "$ALLOW_ROOT_PASSWORD_SSH" == "1" ]]; then
    permit_root=yes
    password_auth=yes
  else
    permit_root=prohibit-password
    password_auth=no
  fi

  debian_tmp="$snippet_dir/.ppflight-debian-$$.tmp"
  rhel_tmp="$snippet_dir/.ppflight-rhel-$$.tmp"
  rm -f -- "$debian_tmp" "$rhel_tmp"

  cat > "$debian_tmp" <<YAML
#cloud-config
disable_root: false
ssh_pwauth: $([[ "$ALLOW_ROOT_PASSWORD_SSH" == "1" ]] && echo true || echo false)
ssh_deletekeys: true
ssh_genkeytypes: [rsa, ecdsa, ed25519]
timezone: $TIMEZONE
ntp:
  enabled: true
growpart:
  mode: auto
  devices: ['/']
  ignore_growroot_disabled: false
resize_rootfs: true
package_update: true
packages:
  - qemu-guest-agent
write_files:
  - path: /etc/ssh/sshd_config.d/00-ppflight-cloud.conf
    owner: root:root
    permissions: '0644'
    content: |
      PermitRootLogin $permit_root
      PasswordAuthentication $password_auth
      KbdInteractiveAuthentication no
      PermitEmptyPasswords no
  - path: /etc/modules-load.d/tcp-bbr.conf
    owner: root:root
    permissions: '0644'
    content: |
      tcp_bbr
  - path: /etc/sysctl.d/99-ppflight-cloud.conf
    owner: root:root
    permissions: '0644'
    content: |
      net.core.default_qdisc=fq
      net.ipv4.tcp_congestion_control=bbr
      kernel.dmesg_restrict=1
runcmd:
  - [modprobe, tcp_bbr]
  - [sysctl, --system]
  - [systemctl, enable, --now, ssh]
  - [systemctl, restart, ssh]
  - [systemctl, enable, --now, qemu-guest-agent]
  - [systemctl, enable, serial-getty@ttyS0.service]
YAML

  debian_hash="$(sha256sum "$debian_tmp" | awk '{print $1}')"
  DEBIAN_SNIPPET="ppflight-debian-$debian_hash.yaml"
  if [[ -e "$snippet_dir/$DEBIAN_SNIPPET" ]]; then
    rm -f -- "$debian_tmp"
  else
    mv "$debian_tmp" "$snippet_dir/$DEBIAN_SNIPPET"
  fi
  chmod 0644 "$snippet_dir/$DEBIAN_SNIPPET"

  cat > "$rhel_tmp" <<YAML
#cloud-config
disable_root: false
ssh_pwauth: $([[ "$ALLOW_ROOT_PASSWORD_SSH" == "1" ]] && echo true || echo false)
ssh_deletekeys: true
ssh_genkeytypes: [rsa, ecdsa, ed25519]
timezone: $TIMEZONE
ntp:
  enabled: true
growpart:
  mode: auto
  devices: ['/']
  ignore_growroot_disabled: false
resize_rootfs: true
package_update: true
packages:
  - qemu-guest-agent
  - chrony
write_files:
  - path: /etc/ssh/sshd_config.d/00-ppflight-cloud.conf
    owner: root:root
    permissions: '0644'
    content: |
      PermitRootLogin $permit_root
      PasswordAuthentication $password_auth
      KbdInteractiveAuthentication no
      PermitEmptyPasswords no
  - path: /etc/modules-load.d/tcp-bbr.conf
    owner: root:root
    permissions: '0644'
    content: |
      tcp_bbr
  - path: /etc/sysctl.d/99-ppflight-cloud.conf
    owner: root:root
    permissions: '0644'
    content: |
      net.core.default_qdisc=fq
      net.ipv4.tcp_congestion_control=bbr
      kernel.dmesg_restrict=1
runcmd:
  - [modprobe, tcp_bbr]
  - [sysctl, --system]
  - [systemctl, enable, --now, sshd]
  - [systemctl, restart, sshd]
  - [systemctl, enable, --now, chronyd]
  - [systemctl, enable, --now, qemu-guest-agent]
  - [systemctl, enable, serial-getty@ttyS0.service]
YAML

  rhel_hash="$(sha256sum "$rhel_tmp" | awk '{print $1}')"
  RHEL_SNIPPET="ppflight-rhel-$rhel_hash.yaml"
  if [[ -e "$snippet_dir/$RHEL_SNIPPET" ]]; then
    rm -f -- "$rhel_tmp"
  else
    mv "$rhel_tmp" "$snippet_dir/$RHEL_SNIPPET"
  fi
  chmod 0644 "$snippet_dir/$RHEL_SNIPPET"
  log "Immutable Cloud-Init profiles: $DEBIAN_SNIPPET; $RHEL_SNIPPET"
}

verify_download() {
  local file="$1" checksum_file="$2" algorithm="$3" actual expected filename expected_length
  filename="$(basename "$file")"
  case "$algorithm" in
    sha256)
      actual="$(sha256sum "$file" | awk '{print tolower($1)}')"
      expected_length=64
      ;;
    sha512)
      actual="$(sha512sum "$file" | awk '{print tolower($1)}')"
      expected_length=128
      ;;
    *) die "unsupported checksum algorithm: $algorithm" ;;
  esac

  # Accept both GNU format (HASH [ *]FILENAME) and BSD format
  # (SHA256 (FILENAME) = HASH), but only for this exact basename.
  expected="$(awk -v wanted="$filename" '
    {
      hash = ""
      name = ""
      if ($1 ~ /^[[:xdigit:]]+$/ && NF >= 2) {
        hash = $1
        name = $2
        sub(/^\*/, "", name)
      } else if (($1 == "SHA256" || $1 == "SHA512") && $2 == "(" wanted ")" && $3 == "=" && NF >= 4) {
        hash = $4
        name = wanted
      }
      if (name == wanted) {
        print tolower(hash)
        exit
      }
    }
  ' "$checksum_file")"

  [[ ${#expected} -eq $expected_length && "$expected" =~ ^[0-9a-f]+$ ]] || return 1
  [[ "$actual" == "$expected" ]] || return 1
  printf '%s\n' "$actual"
}

download_image() {
  local image="$1" url="$2" checksum_url="$3" algorithm="$4"
  local target="$CACHE_DIR/$image" checksum_file="$CACHE_DIR/$image.$algorithm.sums" actual attempt

  for attempt in 1 2; do
    curl --fail --location --show-error --silent --retry 5 --retry-delay 3 --retry-all-errors \
      --output "$checksum_file.tmp" "$checksum_url"
    mv "$checksum_file.tmp" "$checksum_file"

    if [[ ! -s "$target" ]]; then
      log "Downloading $image"
      curl --fail --location --show-error --silent --retry 8 --retry-delay 5 --retry-all-errors \
        --continue-at - --output "$target.part" "$url"
      mv "$target.part" "$target"
    else
      log "Using cached $image (checksum will still be verified)"
    fi

    if actual="$(verify_download "$target" "$checksum_file" "$algorithm")"; then
      IMAGE_HASHES["$image"]="$algorithm:$actual"
      log "$algorithm verified: $image"
      qemu-img info "$target" >/dev/null
      return 0
    fi

    log "Checksum mismatch for $image on attempt $attempt/2; refreshing image and checksum"
    rm -f -- "$target" "$target.part"
  done
  die "checksum verification failed for $image"
}

check_existing_vmids() {
  local row vmid name config existing_name
  for row in "${SELECTED_ROWS[@]}"; do
    IFS='|' read -r vmid name _ <<< "$row"
    if qm status "$vmid" >/dev/null 2>&1; then
      config="$(qm config "$vmid")"
      grep -qx 'template: 1' <<< "$config" || die "VMID $vmid exists and is not a template"
      [[ "$REPLACE_EXISTING" == "1" ]] || die "template $vmid already exists; rerun with --replace"
      if ! grep -Eq '^tags: .*ppflight-cloudinit([;,]|$)' <<< "$config"; then
        existing_name="$(awk '$1 == "name:" {print $2; exit}' <<< "$config")"
        [[ "$FORCE_REPLACE_UNMANAGED" == "1" && "$existing_name" == "$name" ]] ||
          die "template $vmid is not tagged ppflight-cloudinit; refusing to replace it"
      fi
    fi
  done
}

destroy_existing_template() {
  local vmid="$1" expected_name="$2" config existing_name
  if qm status "$vmid" >/dev/null 2>&1; then
    [[ "$REPLACE_EXISTING" == "1" ]] || die "template $vmid appeared during the build; refusing to replace it without --replace"
    config="$(qm config "$vmid")"
    grep -qx 'template: 1' <<< "$config" || die "VMID $vmid changed and is no longer a template"
    existing_name="$(awk '$1 == "name:" {print $2; exit}' <<< "$config")"
    if ! grep -Eq '^tags: .*ppflight-cloudinit([;,]|$)' <<< "$config"; then
      [[ "$FORCE_REPLACE_UNMANAGED" == "1" && "$existing_name" == "$expected_name" ]] ||
        die "template $vmid is unmanaged or changed; refusing to destroy it"
    fi
    log "Replacing existing template $vmid"
    qm destroy "$vmid" --purge 1 --destroy-unreferenced-disks 1
  fi
}

disk_qos_suffix() {
  if [[ "$ENABLE_QOS" == "1" ]]; then
    printf ',mbps_rd=%s,mbps_wr=%s,mbps_rd_max=%s,mbps_wr_max=%s,iops_rd=%s,iops_wr=%s,iops_rd_max=%s,iops_wr_max=%s,iops_rd_max_length=%s,iops_wr_max_length=%s' \
      "$QOS_MBPS_RD" "$QOS_MBPS_WR" "$QOS_MBPS_RD_MAX" "$QOS_MBPS_WR_MAX" \
      "$QOS_IOPS_RD" "$QOS_IOPS_WR" "$QOS_IOPS_RD_MAX" "$QOS_IOPS_WR_MAX" \
      "$QOS_IOPS_RD_MAX_LENGTH" "$QOS_IOPS_WR_MAX_LENGTH"
  fi
}

create_template() {
  local row="$1" vmid name image _url _checksum_url _algorithm family placeholder_ip description
  local imported_volume snippet qos description_full
  IFS='|' read -r vmid name image _url _checksum_url _algorithm family placeholder_ip description <<< "$row"
  snippet="$DEBIAN_SNIPPET"
  [[ "$family" == "rhel" ]] && snippet="$RHEL_SNIPPET"
  [[ -n "$snippet" ]] || die "Cloud-Init profile was not generated for $family"
  qos="$(disk_qos_suffix)"
  description_full="$description; built by ppflight-cloudinit v$SCRIPT_VERSION on $(date -u '+%F')"

  destroy_existing_template "$vmid" "$name"
  log "Creating $vmid ($name)"
  qm create "$vmid" \
    --name "$name" \
    --description "$description_full" \
    --ostype l26 \
    --memory "$MEMORY_MB" \
    --balloon "$BALLOON" \
    --cores "$CORES" \
    --cpu "$CPU_TYPE" \
    --net0 "virtio,bridge=$BRIDGE,firewall=$FIREWALL" \
    --scsihw virtio-scsi-single \
    --serial0 socket \
    --vga std \
    --agent enabled=1,fstrim_cloned_disks=1 \
    --tags ppflight-cloudinit-build \
    --onboot 0
  CURRENT_VMID="$vmid"
  CURRENT_NAME="$name"

  qm disk import "$vmid" "$CACHE_DIR/$image" "$IMAGE_STORAGE"
  imported_volume="$(qm config "$vmid" | awk -F': ' '/^unused[0-9]+:/ {print $2; exit}')"
  [[ -n "$imported_volume" ]] || die "imported disk not found for VMID $vmid"

  qm set "$vmid" --scsi0 "$imported_volume,discard=on,ssd=$DISK_SSD,iothread=1$qos"
  qm set "$vmid" --ide2 "$IMAGE_STORAGE:cloudinit"
  qm set "$vmid" --boot order=scsi0
  qm set "$vmid" --citype nocloud
  qm set "$vmid" --ciuser root
  qm set "$vmid" --ciupgrade 0
  qm set "$vmid" --cicustom "vendor=$FILE_STORAGE:snippets/$snippet"
  qm set "$vmid" --ipconfig0 "ip=$placeholder_ip/32"
  [[ -z "$DNS_SERVERS" ]] || qm set "$vmid" --nameserver "$DNS_SERVERS"
  qm resize "$vmid" scsi0 "$DISK_SIZE"
  qm cloudinit update "$vmid"
  qm template "$vmid"
  qm set "$vmid" --tags ppflight-cloudinit
  CREATED_VMIDS+=("$vmid")
  CURRENT_VMID=""
  CURRENT_NAME=""
}

verify_template() {
  local row="$1" vmid name _image _url _checksum _algorithm family config disk cloudinit_disk field expected_snippet
  IFS='|' read -r vmid name _image _url _checksum _algorithm family _ <<< "$row"
  expected_snippet="$DEBIAN_SNIPPET"
  [[ "$family" == "rhel" ]] && expected_snippet="$RHEL_SNIPPET"
  config="$(qm config "$vmid")"
  grep -qx 'template: 1' <<< "$config" || die "$vmid is not a template"
  grep -qx "name: $name" <<< "$config" || die "$vmid has unexpected name"
  grep -Eq '^tags: .*ppflight-cloudinit([;,]|$)' <<< "$config" || die "$vmid is missing the project tag"
  grep -q '^agent: enabled=1' <<< "$config" || die "$vmid does not have QEMU Agent enabled"
  grep -q '^serial0: socket' <<< "$config" || die "$vmid does not have serial0"
  grep -q '^vga: std' <<< "$config" || die "$vmid does not have VGA"
  grep -Fqx "cicustom: vendor=$FILE_STORAGE:snippets/$expected_snippet" <<< "$config" || die "$vmid has an unexpected Cloud-Init profile"
  disk="$(sed -n 's/^scsi0: //p' <<< "$config")"
  cloudinit_disk="$(sed -n 's/^ide2: //p' <<< "$config")"
  [[ "$disk" == "$IMAGE_STORAGE:"* ]] || die "$vmid system disk is not on $IMAGE_STORAGE"
  [[ "$cloudinit_disk" == "$IMAGE_STORAGE:"* ]] || die "$vmid Cloud-Init disk is not on $IMAGE_STORAGE"
  [[ "$disk" == *"discard=on"* && "$disk" == *"iothread=1"* && "$disk" == *"ssd=$DISK_SSD"* ]] || die "$vmid disk tuning is incomplete"
  if [[ "$ENABLE_QOS" == "1" ]]; then
    for field in \
      "mbps_rd=$QOS_MBPS_RD" "mbps_wr=$QOS_MBPS_WR" \
      "mbps_rd_max=$QOS_MBPS_RD_MAX" "mbps_wr_max=$QOS_MBPS_WR_MAX" \
      "iops_rd=$QOS_IOPS_RD" "iops_wr=$QOS_IOPS_WR" \
      "iops_rd_max=$QOS_IOPS_RD_MAX" "iops_wr_max=$QOS_IOPS_WR_MAX" \
      "iops_rd_max_length=$QOS_IOPS_RD_MAX_LENGTH" "iops_wr_max_length=$QOS_IOPS_WR_MAX_LENGTH"; do
      [[ ",$disk," == *",$field,"* ]] || die "$vmid is missing $field"
    done
  fi
  qm cloudinit dump "$vmid" network >/dev/null
}

write_manifest() {
  local manifest="$CACHE_DIR/ppflight-template-build-manifest.txt" row vmid name image
  {
    printf 'script_version=%s\n' "$SCRIPT_VERSION"
    printf 'built_at_utc=%s\n' "$(date -u '+%FT%TZ')"
    printf 'pve_version=%s\n' "$(pveversion)"
    printf 'image_storage=%s\nfile_storage=%s\nbridge=%s\n' "$IMAGE_STORAGE" "$FILE_STORAGE" "$BRIDGE"
    printf 'debian_snippet=%s\nrhel_snippet=%s\n' "$DEBIAN_SNIPPET" "$RHEL_SNIPPET"
    printf 'disk_size=%s\ndisk_ssd=%s\nmemory_mb=%s\ncores=%s\ncpu_type=%s\nqos_enabled=%s\n' "$DISK_SIZE" "$DISK_SSD" "$MEMORY_MB" "$CORES" "$CPU_TYPE" "$ENABLE_QOS"
    for row in "${SELECTED_ROWS[@]}"; do
      IFS='|' read -r vmid name image _ <<< "$row"
      printf 'template=%s|%s|%s|%s\n' "$vmid" "$name" "$image" "${IMAGE_HASHES[$image]}"
    done
  } > "$manifest"
  chmod 0644 "$manifest"
  log "Manifest: $manifest"
}

main() {
  find_config_arg "$@"
  load_config
  parse_args "$@"
  select_templates
  preflight
  exec 9>/run/lock/ppflight-cloudinit.lock
  flock -n 9 || die "another ppflight-cloudinit build is already running"

  local file_storage_path snippet_relative row vmid name image url checksum_url algorithm _family _ip _description
  file_storage_path="$(resolve_file_storage_path)"
  snippet_relative="$(storage_content_dir "$FILE_STORAGE" snippets snippets)"
  if [[ -z "$CACHE_DIR" ]]; then
    CACHE_DIR="$file_storage_path/.ppflight-cloudinit/cache"
  fi
  install -d -m 0755 "$CACHE_DIR"
  show_storage_layout "$file_storage_path" "$snippet_relative"

  check_existing_vmids

  declare -gA IMAGE_HASHES=()
  log "Downloading and verifying all selected images before changing VMIDs"
  for row in "${SELECTED_ROWS[@]}"; do
    IFS='|' read -r vmid name image url checksum_url algorithm _family _ip _description <<< "$row"
    download_image "$image" "$url" "$checksum_url" "$algorithm"
  done

  write_snippets

  for row in "${SELECTED_ROWS[@]}"; do
    create_template "$row"
  done

  for row in "${SELECTED_ROWS[@]}"; do
    verify_template "$row"
  done
  write_manifest

  log "Completed templates: ${CREATED_VMIDS[*]}"
  qm list
}

main "$@"
