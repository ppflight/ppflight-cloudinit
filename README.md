# PPFlight Proxmox Cloud-Init 模板安装

在 Proxmox VE 8/9 节点以 root 运行：

```bash
curl -fsSL https://raw.githubusercontent.com/ppflight/ppflight-cloudinit/main/install.sh | bash
```

无需 Git 或手动下载文件。启动脚本自动下载并校验完整安装程序，然后按菜单依次选择：

1. **模板**：输入 VMID；多个用空格或逗号分隔，`ALL` 全选。
2. **镜像下载位置**：选择保存云镜像和 Cloud-Init snippets 的存储。
3. **模板安装位置**：选择存放模板系统盘的存储。
4. **业务网桥与 VLAN**：查看网桥的上联、宿主地址和允许 VLAN，选择客户 VPS 使用的网络。

回车默认：模板 `ALL`、存储第 `1` 项、开始安装 `Yes`。网桥只有唯一无宿主地址且有上联的在线候选时提供回车推荐，多个候选必须明确选择。选完显示配置，按回车开始下载、校验和制作模板；输入 `n` 取消。无需命令参数，输入错误会重新提示，结束输入会取消安装。

完整操作示例、升级和常见问题见 [交互安装指南](docs/INTERACTIVE-INSTALL.md)，版本变化见 [CHANGELOG](CHANGELOG.md)。

确认开始制作后，自动关闭本机 PVE 的 APT 后台更新/无人值守升级及自动重启，并屏蔽相关定时器和服务。手动更新、PVE 日常维护和证书续期保留；已在执行的包管理操作不会被强行终止。此设置持久保存，即使后续模板制作失败也会保留。详情与恢复方式见安装指南。

| VMID | 模板 |
|---|---|
| 9000 | Ubuntu 22.04 |
| 9001 | Ubuntu 24.04 |
| 9002 | AlmaLinux 8 |
| 9003 | Debian 13 |
| 9004 | Debian 12 |
| 9005 | CentOS Stream 9 |
| 9006 | CentOS Stream 10 |
| 9007 | AlmaLinux 9 |
| 9008 | Rocky Linux 9 |
| 9009 | Ubuntu 26.04 LTS |

菜单显示已启用、在线且支持对应用途的 PVE 存储及剩余空间。镜像位置须支持 `iso,snippets`，安装目标须支持 `images`。没有合格存储时停止，请先在 PVE 配置相应内容类型。网桥不再固定选择 `vmbr0`：带宿主地址或默认路由的网桥会提示管理网络风险，选用时需输入 `USE` 确认；离线网桥不能选。VLAN-aware 网桥支持选择允许范围内的 VLAN，输入 `0` 使用无标签网络。

**PPFlight 当前双网桥示例**：`vmbr0` 是管理网，`vmbr1 → bond0` 是客户业务网，网桥仅允许 VLAN2100 时菜单推荐 `vmbr1` 和 `2100`；新模板 net0 将包含 `bridge=vmbr1,tag=2100,firewall=1`。用途推荐依据本机配置，仍须核对实际接线；脚本不修改宿主机网络、不启用全局 PVE 防火墙。

镜像固定到官方日期版地址，并同时验证目录 SHA-256 和官方 checksum，避免 `latest` 更新导致安装中断。

新模板的克隆系统默认关闭自动升级：PVE `ciupgrade=0`，Cloud-Init 不做全系统升级或自动重启，APT unattended-upgrades 和 DNF/YUM 自动更新任务被屏蔽。Cloud-init、QGA、SSH、CA 证书、curl、Chrony、磁盘扩容、IP/DNS/路由诊断和基本编辑工具在制作阶段提前安装；首次启动不再依赖软件源安装这些软件。手动安装和更新仍可用。此策略只作用于使用新模板和新 Cloud-Init 配置的克隆，不修改 PVE 宿主机或已有克隆。

此入口只制作模板，不备份模板、不创建 VPS 备份任务，也不执行已有备份恢复。脚本不分区或格式化宿主物理盘；选择的本项目旧模板会重新制作，普通 VM、容器及其他项目模板保持保护。VPS 的备份存储需在后续 PVE/WHMCS 备份任务中指定，不会通过克隆模板自动继承。

底层构建逻辑保留官方镜像校验、Cloud-Init 配置和安装结果检查。`tools/build-template-engine.sh` 是内部构建入口，供交互菜单和 Agent 共用。Agent 集成见 [接口文档](docs/AGENT-BOOTSTRAP.md) 和 [内置清单](docs/AGENT-VENDORING.md)。

## 重新制作与更新策略

再次运行同一命令并选择 `ALL`，会重新制作原有七个模板，并补上 9007–9009。选定旧模板必须名称和 `ppflight-cloudinit` 标签均匹配、处于停止状态、无锁、没有关联克隆或其他 VM 磁盘引用。目前自动替换仅支持**本地 ZFS 模板存储**（如 PPFlight 的 `vpspool`）；其他存储上的旧模板会停止并保留，不猜测依赖关系。新模板仍支持符合原条件的存储。

构建流程为：检查所有 VMID 和克隆依赖 → 下载并验证官方镜像 → 在独立 qcow2 中扩容、安装发行版当前更新及基础软件 → 清理机器身份和 SSH 主机密钥 → 用临时 overlay 隔离启动，确认 QGA 和 Cloud-init 完成 → 再次检查旧模板 → 替换并回读验证。所有选定镜像都准备成功后才开始替换；下载、更新或依赖检查失败时，旧模板尚未被删除。开始替换后若 PVE 导入失败，会报告失败，不声称批次原子回滚；修复后可重新运行。

制作阶段保留官方镜像的软件源、发行版默认签名验证与官方镜像网络，不加入第三方源或切换国内镜像。更新包括当前发行版仓库提供的安全和维护更新，不跨发行版大版本。CentOS Stream 是滚动维护发行线，不能把其更新描述成“仅安全补丁”。交付后关闭自动升级和自动重启，管理员/客户仍可手动更新。固定源镜像 SHA-256 与更新后镜像 SHA-256 分开记录；更新后的包版本和时间保存在镜像 `/var/lib/ppflight-template/` 及宿主构建报告中。隔离启动报告另存为 `ppflight-template-VMID-boot.json`，不等于客户公网连通性与防冒用验收。

首次运行会按需安装 Debian 官方 `guestfs-tools`、`guestfish`（使用 `--no-remove`，不允许为满足依赖删除 PVE 包）。这些是制作时使用的离线工具，不是常驻 Agent，也不用额外给客户业务 VLAN 分配临时地址；它们使用宿主网络下载更新。预留独立镜像制作空间，默认磁盘 16 GiB；根分区布局不能安全识别时停止。旧 VPS 不会随模板重做而重装或升级。

离线镜像安装工具的行为依据 [virt-customize 官方文档](https://libguestfs.org/virt-customize.1.html)；磁盘扩容依据 [virt-resize 官方文档](https://libguestfs.org/virt-resize.1.html)。

RHEL 系镜像若默认限制 QGA RPC，安装器仅补齐官网必需的 `guest-exec`、`guest-exec-status`、`guest-set-user-password` 和 `guest-network-get-interfaces`，保留其他限制。隔离启动会检查实际开放的能力，而不只检查 QGA 服务是否启动。

Ubuntu 官方镜像自带的 Snap 有独立后台刷新机制，因此默认同时屏蔽 snapd 服务/套接字和修复定时器；APT 手动更新正常可用。如客户主动要使用 Snap，可先 `systemctl unmask snapd.service snapd.socket snapd.seeded.service`、`systemctl start snapd.socket`，再按 [Snap 官方更新管理说明](https://snapcraft.io/docs/how-to-guides/manage-snaps/manage-updates/)执行 `snap refresh --hold=forever`，随后按需手动刷新。

更新 RHEL 系内核前会固定镜像自身的根文件系统 UUID 和启动参数，并构建通用 initramfs，防止离线环境的内核参数被带入客户系统。隔离启动使用与正式模板一致的 VirtIO SCSI 系统盘，并检查根文件系统扩容结果。

Debian/Ubuntu 镜像扩容后会重新安装 BIOS GRUB，并在内核启动阶段使用 `eth0`，避免新版本 Cloud-init 对已启用网卡重命名失败。RHEL 系在离线镜像内使用系统自带的 `setfiles` 和当前 SELinux 策略完整重标记；隔离启动还要求 SELinux 保持 Enforcing，不通过关闭防护来兼容更新。

**RHEL 系 QGA 权限边界**：官网需要通过 QGA 执行 root 级网络和时区配置，因此为 `qemu-guest-agent.service` 单独设置 `SELinuxContext=system_u:system_r:unconfined_service_t:s0`。这意味着 QGA 及其管理命令不再受默认 QGA SELinux 域限制；虚拟机全局仍是 Enforcing，其他服务保持发行版策略，QGA RPC 清单仍保留文件接口等默认限制。PVE 管理权限必须作为 root 管理权限保护。
