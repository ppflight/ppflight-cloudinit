#!/usr/bin/env bash
# Runs INSIDE the offline libguestfs appliance chroot, never on the PVE host.
set -Eeuo pipefail
[[ -f /etc/ppflight-offline-build ]] || { echo 'Offline build marker missing' >&2; exit 1; }
root_uuid="$(cat /etc/ppflight-offline-build)"
firmware="$(cat /etc/ppflight-build-firmware)"
[[ "$firmware" == ovmf || "$firmware" == seabios ]] || exit 1
[[ "$root_uuid" =~ ^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$ ]] || { echo 'Invalid guest root UUID' >&2; exit 1; }
install -d -m 0755 /var/lib/ppflight-template
# shellcheck disable=SC1091
source /etc/os-release
case "$ID" in
  ubuntu|debian)
    export DEBIAN_FRONTEND=noninteractive
    apt_opts=(-o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 -o Dpkg::Options::=--force-confold)
    # Keep the official image's source configuration and signature verification.
    apt-get "${apt_opts[@]}" update --error-on=any
    apt-get "${apt_opts[@]}" -y dist-upgrade
    apt-get "${apt_opts[@]}" -y --no-install-recommends install cloud-init qemu-guest-agent openssh-server ca-certificates curl chrony cloud-guest-utils iproute2 iputils-ping dnsutils traceroute net-tools vim-tiny sudo
    # Resizing cloud images can relocate the BIOS boot partition. Reinstall GRUB
    # only onto the disk containing the guest UUID, never the appliance root.
    root_device="$(blkid -U "$root_uuid")"
    disk_name="$(lsblk -n -o PKNAME "$root_device")"
    [[ "$disk_name" =~ ^[sv]d[a-z]+$ ]] || { echo 'Cannot identify guest boot disk' >&2; exit 1; }
    if [[ "$firmware" == ovmf ]]; then
      mountpoint -q /boot/efi || { echo "EFI system partition is not mounted" >&2; exit 1; }
      apt-get "${apt_opts[@]}" -y --no-install-recommends install grub-efi-amd64-bin
      grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable --no-nvram --force
      test -s /boot/efi/EFI/BOOT/BOOTX64.EFI
    else
      grub-install --target=i386-pc "/dev/$disk_name"
    fi
    # Proxmox NoCloud v1 addresses the first NIC as eth0. Select that name at
    # boot, before Ubuntu networkd can bring up a predictable name and prevent
    # cloud-init from renaming the active device.
    install -d /etc/default/grub.d
    # Expanded by update-grub when sourcing the file.
    # shellcheck disable=SC2016
    printf '%s\n' 'GRUB_CMDLINE_LINUX="${GRUB_CMDLINE_LINUX} net.ifnames=0"' > /etc/default/grub.d/99-ppflight-network.cfg
    update-grub
    grep -q "$root_uuid" /boot/grub/grub.cfg
    if grep -Eq 'guestfs_network=|udevtimeout=6000' /boot/grub/grub.cfg; then
      echo 'Appliance arguments leaked into GRUB configuration' >&2
      exit 1
    fi
    dpkg-query -W -f='${Package}\t${Version}\n' > /var/lib/ppflight-template/packages.tsv
    install -d /etc/apt/apt.conf.d
    cat > /etc/apt/apt.conf.d/99zz-ppflight-no-auto-upgrades <<'EOF'
APT::Periodic::Enable "0";
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Download-Upgradeable-Packages "0";
APT::Periodic::Unattended-Upgrade "0";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
    automatic_units=(apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service unattended-upgrades.service)
    # Official Ubuntu cloud images include snapd; stop its independent refresh path.
    if command -v snap >/dev/null; then
      automatic_units+=(snapd.service snapd.socket snapd.seeded.service snapd.snap-repair.timer snapd.snap-repair.service)
    fi
    ssh_unit=ssh.service
    time_unit=chrony.service
    apt-get clean
    ;;
  almalinux|rocky|centos)
    # kernel-install must never inherit the libguestfs appliance /proc/cmdline.
    guest_cmdline="root=UUID=$root_uuid ro console=tty0 console=ttyS0,115200n8 net.ifnames=0"
    install -d /etc/kernel /etc/dracut.conf.d
    printf '%s\n' "$guest_cmdline" > /etc/kernel/cmdline
    printf 'hostonly="no"\n' > /etc/dracut.conf.d/99-ppflight-generic.conf
    dnf_opts=(--setopt=ip_resolve=4 --setopt=timeout=60 --setopt=retries=3 --setopt='*.skip_if_unavailable=False')
    dnf "${dnf_opts[@]}" -y --refresh upgrade
    dnf "${dnf_opts[@]}" -y install cloud-init qemu-guest-agent openssh-server ca-certificates chrony cloud-utils-growpart iproute iputils bind-utils traceroute net-tools vim-minimal sudo policycoreutils
    command -v curl >/dev/null || dnf "${dnf_opts[@]}" -y install curl
    rpm -qa --qf '%{NAME}\t%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort > /var/lib/ppflight-template/packages.tsv
    install -d /etc/dnf
    cat > /etc/dnf/automatic.conf <<'EOF'
[commands]
download_updates = no
apply_updates = no
reboot = never
EOF
    automatic_units=(dnf-automatic.timer dnf-automatic.service dnf-automatic-download.timer dnf-automatic-download.service dnf-automatic-install.timer dnf-automatic-install.service dnf-automatic-notifyonly.timer dnf-automatic-notifyonly.service yum-cron.service)
    ssh_unit=sshd.service
    time_unit=chronyd.service
    # Keep initramfs independent of the appliance's detected hardware and root.
    dracut --regenerate-all --force --no-hostonly
    for entry in /boot/loader/entries/*.conf; do
      [[ -f "$entry" ]] || continue
      sed -i "s|^options .*|options $guest_cmdline|" "$entry"
      grep -q "^options root=UUID=$root_uuid " "$entry"
      if grep -Eq 'guestfs_network=|udevtimeout=6000|cgroup_disable=memory|selinux=0' "$entry"; then
        echo 'Appliance kernel arguments leaked into guest boot entry' >&2
        exit 1
      fi
    done
    # PPFlight uses QGA to execute root administration (network/timezone).
    # Confine the exception to this trusted management service, not the VM.
    install -d /etc/systemd/system/qemu-guest-agent.service.d
    cat > /etc/systemd/system/qemu-guest-agent.service.d/10-ppflight-management.conf <<'EOF'
[Service]
SELinuxContext=system_u:system_r:unconfined_service_t:s0
EOF
    # Permit only the declared QGA executable as this service entrypoint.
    cat > /var/lib/ppflight-template/qga-management.cil <<'EOF'
(allow unconfined_service_t virt_qemu_ga_exec_t (file (entrypoint)))
EOF
    semodule -n -i /var/lib/ppflight-template/qga-management.cil
    dnf clean all
    ;;
  *) echo "Unsupported guest distribution: $ID" >&2; exit 1 ;;
esac
python3 /var/tmp/ppflight-configure-qga.py
install -d -m 0755 /etc/ssh/sshd_config.d
if ! grep -Eq '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config.d/\*\.conf' /etc/ssh/sshd_config; then
  sed -i '1i Include /etc/ssh/sshd_config.d/*.conf' /etc/ssh/sshd_config
fi
# --root avoids talking to the appliance's init system.
systemctl --root=/ mask "${automatic_units[@]}"
systemctl --root=/ enable "$ssh_unit" "$time_unit"
# QGA is activated by its virtio device (often a static unit).
[[ -f /usr/lib/systemd/system/qemu-guest-agent.service || -f /lib/systemd/system/qemu-guest-agent.service ]]
for program in cloud-init qemu-ga sshd curl chronyd growpart ip ping; do command -v "$program" >/dev/null; done
for unit in "${automatic_units[@]}"; do
  [[ "$(readlink "/etc/systemd/system/$unit")" == /dev/null ]]
done
# Do not ship shared SSH host keys, instance state, machine identity or seed files.
cloud-init clean --logs --seed
rm -f /etc/ssh/ssh_host_* /var/lib/dbus/machine-id /var/lib/systemd/random-seed
truncate -s 0 /etc/machine-id
passwd -l root
rm -f /root/.ssh/authorized_keys
# Record what was actually installed, separately from the original source checksum.
printf 'updated_at_utc=%s\nos=%s\nversion=%s\nupdates=official-repositories\nautomatic_upgrades=disabled\nautomatic_reboot=disabled\n' "$(date -u '+%FT%TZ')" "$ID" "$VERSION_ID" > /var/lib/ppflight-template/build-info
rm -f /etc/ppflight-offline-build /etc/ppflight-build-firmware
# Debian's appliance may not ship the SELinux relabel feature. Use the guest's
# own current policy and setfiles, and fail rather than defer to a reboot.
if [[ "$ID" == almalinux || "$ID" == rocky || "$ID" == centos ]]; then
  rm -f /.autorelabel
  setfiles -F -e /proc -e /sys -e /dev -e /run /etc/selinux/targeted/contexts/files/file_contexts /
  matchpathcon -V /usr/lib64/ld-linux-x86-64.so.2 /usr/sbin/sshd /usr/bin/qemu-ga
fi
