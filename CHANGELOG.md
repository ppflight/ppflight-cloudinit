# Changelog

## 2.0.1 - 2026-08-29

- Install Vim, curl and `net-tools` (`ifconfig`) through Cloud-Init by default.
- Use `vim-enhanced` on AlmaLinux and CentOS Stream guests.

## 2.0.0 - 2026-08-27

- Add the public one-command Proxmox template builder.
- Add explicit download/cache, snippet and final VM disk storage selection.
- Add exact filename-bound SHA-256/SHA-512 verification for official images.
- Use Ubuntu released images and document CentOS Stream CPU baselines.
- Add project ownership tags and conservative replacement protection.
- Add Cloud-Init SSH, QEMU Guest Agent, BBR, NTP, disk growth and console configuration.
- Add host-side bandwidth/IOPS limits and post-build verification.
- Add configuration example, CI, security policy and MIT license.
