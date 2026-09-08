# Changelog

## 2026-09-08 — 交互安装入口

- 直接运行 `bash build-cloud-templates.sh`，按菜单依次选择模板、镜像下载位置、模板安装／恢复目标和备份保存位置。
- 模板支持 `ALL` 全选和多个 VMID；无效输入重新提示，输入结束则取消。
- 存储菜单按启用状态、在线状态和内容类型过滤，并显示剩余空间。
- 选完自动下载、校验、创建模板和备份；已有 VMID 保持拒绝覆盖。
- 删除自动选盘入口，将内部构建引擎移至 `tools/build-template-engine.sh`，供菜单和 Agent 共用。
- 补充交互安装文档、菜单测试和运行文件摘要清单。

迁移说明：原来的 `build-cloud-templates.sh --config/--only/...` 参数入口改为交互菜单。Agent 继续使用 Python helper；不需要把自动化调用改成模拟终端输入。

## 3.0.0 - 2026-08-30

- Add the strict, versioned website/Agent template catalog with pinned source
  SHA-256 values and official upstream checksums.
- Add local PVE storage discovery and plan-first JSON bootstrap helper.
- Add explicit image/template/backup storage roles and optional template
  backups.
- Reject catalog drift and occupied VMIDs in the Agent execution path.
- Probe ISO/snippets paths during storage discovery and disable curl user
  configuration while restricting downloads and redirects to HTTPS.
- Return non-executing, argv-based content remediation for otherwise suitable
  file storages that are missing `iso` or `snippets`.
- Add JSON Schemas, unit tests and an Agent vendoring contract.

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
