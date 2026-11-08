# Changelog

## 3.3.1 - 2026-11-08

- 核对现有发行版分支的最新官方已发布云镜像，更新 Ubuntu 22.04/24.04/26.04、Debian 12/13、AlmaLinux 8/9 的固定源与校验值；UEFI/Legacy 共用对应来源。
- CentOS Stream 9/10 保持本次已更新的 20261103.0；Rocky 9 官方 latest 的 SHA256 与现有 9.8 日期镜像一致，经核对保留。
- 清单修订为 2026-11-08.2，所有源镜像虚拟容量均不超过 10GiB；Debian 下载实算 SHA256 并验证官方 SHA512。
- 包含 3.3.0 的预装 TCP 调优和正常/768MB 无 vendor-data 双场景验证。保留每个分支内的补丁更新、全部通过才替换模板及客户 VM 保护。

## 3.3.0 - 2026-11-08

- CentOS Stream 9/10 改为官方 20261103.0 固定镜像及对应 SHA256；原 20260826 校验地址已不可用，系统大版本与 VMID 不变。
- 预装独立的首次初始化 TCP 调优：实际客体内存、固定 300Mbps/200ms 参考，不依赖官网参数或外部下载。
- 原生 BBR/FQ 与有内存上限的 TCP 自动缓冲；不清空已有配置、不创建 Swap、不替换内核，不写废弃 sysctl。
- 在镜像内安装 cloud-init per-instance hook，兼容官网仅配置 network snippet 的场景；现有客户 VPS 不变。
- 所有系统保留版本选项，继续安装各自官方当前更新；每个镜像增加 768MB、无 vendor-data 的真实隔离启动测试。
- 增加内存边界、配置保留、幂等与首次启动实值核验。

## 3.1.2 — 2026-09-21

- 修复新 PVE 节点配置返回空对象、没有 digest 时无法保存客户备份目标的问题。首次初始化使用 PVE 原生节点配置锁，锁内再次检查为空并校验配置；已存在配置仍要求 digest，不覆盖并发修改。
- 备份菜单说明 zfspool 不能直接保存 vzdump 文件，需要 Directory 或 PBS/NFS 备份存储。

## 3.1.1 — 2026-09-21

- 增加客户 VPS 备份目标菜单及“仅设置备份位置”入口，无需重做模板。
- 将目标保存为 PVE 节点备注标记，保留其他备注、使用 digest 并发保护并验证读回结果。
- 官网资源同步可匹配目标；官网手动选择优先，客户备份权限与份数继续由官网控制。
- 不创建定时任务、不备份模板、不修改已有客户 VPS 的备份绑定。

## 3.1.0 — 2026-09-21

- 新增 AlmaLinux 9（9007）、Rocky Linux 9（9008）、Ubuntu 26.04 LTS（9009）的官方日期镜像、固定摘要和上游校验。
- 交互入口重做选中的旧模板，新增缺失模板；保护普通 VM/容器、其他节点及非本项目模板，替换仅支持能验证关联克隆的本地 ZFS，执行前再次检查配置摘要和依赖。
- 在独立 qcow2 中先安装官方当前更新和基础软件，清理机器身份、SSH 主机密钥，验证成功后才开始替换；记录原始与准备后摘要、软件版本和更新时间。
- 检查并补齐 RHEL 系 QGA 默认策略中官网需要的 RPC，保留其余限制；隔离启动要求 QGA 能力和 Cloud-init 完成。
- 客户首启不再下载必需软件；仍禁用后台自动升级与自动重启，保留手动更新及官方源。按需安装离线 guestfs 工具，不新增常驻 Agent。
- 修复 Rocky 内核升级继承离线环境启动参数的问题；RHEL 系使用客体根 UUID、通用 initramfs，并通过 VirtIO SCSI 隔离启动验收。Ubuntu 同时关闭 Snap 后台刷新路径。
- 修复 Ubuntu 26.04 扩容后的 BIOS 引导及网卡重命名问题；RHEL 系离线重标记 SELinux，启动验收要求 Enforcing。
- 为 RHEL 系 QGA 单独设置 root 管理 SELinux 上下文，兼容官网网络/时区命令；全局保持 Enforcing，明确记录 QGA 的权限例外。
- 补充依赖/冲突、失败保留、镜像准备和目录回归测试，以及重新制作说明。

## 2026-09-20 — 业务网桥与 VLAN 选择

- 在线 Bash 安装菜单发现 Linux 网桥，显示上联、地址、在线状态和 VLAN 范围；唯一业务候选提供推荐，管理网需要额外确认，离线网桥拒绝使用。
- 支持选择 VLAN2100 等允许标签并写入模板 net0；无标签、非法范围、配置漂移均有明确处理。构建前重新验证网络，不修改 PVE 宿主网络或全局防火墙。
- 示例配置、README、交互指南和运行文件摘要同步；添加模拟网桥／VLAN交互及边界测试。Agent v1 保持原请求接口并隔离继承的 VLAN 环境配置。

## 2026-09-09

- 一键制作入口在确认后关闭 PVE 宿主机 APT 后台更新、无人值守升级及其自动重启，持久屏蔽相关服务/定时器并验证状态。
- 保留手动更新和 `pve-daily-update` 日常维护、证书续期；不强行停止正在运行的包管理操作。
- 新增宿主机更新策略测试与恢复说明。Agent 内部入口不自动修改宿主机策略。

## 2026-09-08 — 交互安装入口

- 纠正备份用途：在线入口只制作模板，删除模板备份位置菜单并强制关闭模板备份。VPS 的备份存储由后续 PVE/WHMCS 备份任务指定，不作为模板属性继承。

- 七个镜像源固定为与 catalog 校验值匹配的官方日期版，修复 AlmaLinux、Debian、CentOS 的 `latest` 更新造成的校验中断；保持原始镜像 SHA 不变。
- 克隆系统关闭 Cloud-Init 升级及自动重启，禁用 APT unattended-upgrades 和 DNF/YUM 自动更新任务；保留必要软件安装与手动更新。

- 菜单支持回车默认值：模板 `ALL`、存储第 `1` 项，显示配置后的安装确认默认 `Yes`；输入 `n` 可取消。

- 修复 PVE 8.4 上 `pvesm status/list --output-format json` 不受支持的问题：存储状态和备份清单改用 `pvesh` 节点 JSON API，存储发现失败时展示具体错误。

- 新增 `install.sh` 在线入口，支持 `curl | bash` 自动下载、校验并启动菜单，无需 Git；菜单从终端读取输入，退出时清理临时程序文件。

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

## 3.2.0 — 2026-09-21

- 9000–9009 改为 UEFI；新增 9010 Ubuntu 24.04 Legacy、9011 Debian 12 Legacy。
- 明确目录固件类型、EFI 分区及引导检查、独立 EFI 变量盘与实际启动验证。
- EFI 盘随所选系统盘存储，4m、Secure Boot 关闭；保留克隆依赖和旧模板保护。
