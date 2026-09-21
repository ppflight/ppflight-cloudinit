# 交互安装指南

## 准备

在 Proxmox VE 8/9 宿主机的交互终端中以 root 运行。需要能访问发行版镜像站，并已配置在线的客户业务 Linux 网桥和下列存储：

| 菜单 | 存储用途 | PVE 内容类型 |
|---|---|---|
| 镜像下载位置 | 云镜像缓存及 Cloud-Init snippets | `iso` 和 `snippets`，且能解析文件路径 |
| 模板安装位置 | 模板系统盘、Cloud-Init 盘 | `images` |

脚本使用已配置的 PVE 存储 ID，不会分区或格式化物理盘。镜像和模板可选择同一支持相应用途的存储。请预留足够的下载和系统盘空间；菜单中的剩余空间不是容量保证。

## 安装

一条命令下载并启动，无需 Git：

```bash
curl -fsSL https://raw.githubusercontent.com/ppflight/ppflight-cloudinit/main/install.sh | bash
```

依次完成以下选择，随后显示配置并提示开始安装（回车默认 Yes，输入 n 取消）：

1. 回车默认 `ALL` 安装全部模板，或输入 `9000,9001` / `9000 9001` 选择模板。重复 VMID 自动去重。
2. 输入镜像下载存储的菜单序号（回车默认第 1 项）。
3. 输入模板安装位置存储的菜单序号（回车默认第 1 项）。
4. 查看业务网桥列表，选择序号。唯一无宿主地址／默认路由、有上联的在线候选提供回车推荐；多个候选必须明确选择。带宿主地址或默认路由的网桥提示风险，需额外输入 `USE` 才能选用。
5. 对 VLAN-aware 网桥选择允许范围内的 VLAN，输入 `0` 不打标签；只有一个允许 VLAN 时默认该 VLAN。普通网桥使用无标签网络。

这里只选择模板虚拟网卡所接网桥，不修改 PVE 物理网卡、bond、网桥或防火墙总开关。宿主地址可能用于其他用途，推荐不代表已验证实际接线。构建前会重新读取网桥状态及 VLAN 范围，配置变更后失效则停止。

示例选择过程（序号取决于本机实际存储列表）：

```text
模板：9000,9001
选择镜像下载位置（iso、snippets）
选择序号：1
选择模板安装位置（images）
选择序号：2
选择客户 VPS 业务网桥
  1) vmbr0  管理网络风险：10.128.93.33/24 / nic0
  2) vmbr1  业务候选：bond0 / VLAN2100
网桥序号：2
客户 VLAN [2100]：
制作配置：模板=9000,9001，镜像=local，安装位置=vpspool，网桥=vmbr1，VLAN=2100
```

脚本校验官方镜像后，在独立镜像安装当前发行版官方更新和基础软件；所有镜像准备完成后才替换/创建模板，再验证制作结果。此流程不备份模板、不从旧备份执行 `qmrestore`。VPS 备份目标在后续 PVE/WHMCS 备份任务中配置，不随模板克隆继承。

启动程序从 GitHub 下载完整版本快照并核对运行文件摘要。菜单从当前终端读取输入，因此 `curl | bash` 不影响选择操作。程序退出后清理临时安装文件；镜像缓存和模板保留在所选 PVE 存储。

## PVE 宿主机自动更新

确认开始制作后，脚本会先对当前 PVE 宿主机应用以下持久设置：

- 写入 `/etc/apt/apt.conf.d/99zz-ppflight-host-no-auto-upgrades`，禁用 APT 周期更新、无人值守升级及无人值守自动重启。
- 停止并屏蔽 `apt-daily.timer`、`apt-daily-upgrade.timer`。
- 屏蔽 `apt-daily.service`、`apt-daily-upgrade.service`、`unattended-upgrades.service` 的后续启动，并检查屏蔽状态。

正在执行的包管理操作会继续完成，避免打断 dpkg。取消制作确认不会修改宿主机；确认后即使模板制作失败，该设置也会保留。集群内其他节点不会被修改。

手动通过 PVE 界面或 APT 更新仍然可用。`pve-daily-update` 保留，因为它还负责日常维护和 ACME 证书续期；因此仍可能看到 PVE 刷新可用更新列表。[PVE 官方文档](https://pve.proxmox.com/pve-docs/pve-admin-guide.html#sysadmin_certs_acme)说明了证书自动续期与此服务的关系。自行编写的 cron/第三方升级脚本不在本功能管理范围内。

若以后要恢复 APT 定时更新，可在宿主机执行：

```bash
rm -f /etc/apt/apt.conf.d/99zz-ppflight-host-no-auto-upgrades
systemctl unmask apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service unattended-upgrades.service
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
```

恢复后的自动升级行为取决于原来的 APT/unattended-upgrades 配置。再次使用一键制作入口会重新应用关闭策略。

## 再次运行在线入口

再次执行同一条命令即可获取当前版本：

```bash
curl -fsSL https://raw.githubusercontent.com/ppflight/ppflight-cloudinit/main/install.sh | bash
```

选中的已有项目模板会重新制作；新 VMID 则新增模板。替换前检查名称、标签、状态、锁、ZFS 关联克隆和其他 VM 的磁盘引用；发现依赖即停止。仅自动替换本地 ZFS 上的受管模板，普通 VM／容器／其他存储上的旧模板均保留。

## 常见情况

- **upstream checksum differs from catalog**：旧入口使用会变化的 `latest` 镜像，已切换到与固定校验值一致的官方日期版。重新运行在线命令即可获取修复；不要跳过 SHA 校验。现有正确镜像缓存会继续校验后复用。

- **发现 PVE 存储失败 / Unknown option: output-format**：旧版本误向 `pvesm` 传入 JSON 输出参数，已改为节点 `pvesh` API。重新执行在线命令获取修复版；新版也会显示具体失败原因。

- **没有合格存储**：在 PVE 中检查存储是否启用、对当前节点可用，以及是否允许表格中的内容类型。镜像存储必须同时支持 `iso` 和 `snippets`。
- **已有 VMID**：仅重做本项目、无依赖的本地 ZFS 模板；其他占用一律停止。不要删除客户克隆来绕过此检查。
- **输入错误**：重新显示输入提示；在菜单阶段按 Ctrl+C 或结束输入可退出。
- **提示需要交互终端**：在 PVE Shell/SSH 终端运行上面的一键命令；启动脚本会打开终端读取菜单，不要通过管道传入菜单答案。

## 自动化集成

新模板默认关闭克隆系统自动升级与自动重启，并屏蔽 APT unattended-upgrades、DNF/YUM 自动更新任务；必要软件在独立镜像制作时预装，首次启动不再下载。此设置不追溯修改已有克隆。PVE/WHMCS 后续覆盖 `ciupgrade` 或 Cloud-Init 配置时，应继续保持 `ciupgrade=0` 和 `package_upgrade=false`。

面向人的入口使用上面的在线命令，不再接收旧命令参数。Agent 自动化使用 [Python helper](AGENT-BOOTSTRAP.md)，由 helper 调用内部构建引擎。镜像校验、VMID 保护和构建验证继续由公共引擎执行。

## 模板网络配置

当前 PPFlight 两台 PVE 建议选择 `vmbr1`、VLAN `2100`，模板网卡为 `virtio,bridge=vmbr1,firewall=1,tag=2100`。官网正式绑定的网桥和 VLAN 应与此一致；后续开通仍以官网网络附件配置为准。`vmbr0` 留给管理访问。

直接使用内部构建引擎时，可设置 `BRIDGE`、`VLAN_TAG`，或使用 `--bridge vmbr1 --vlan-id 2100`；`--vlan-id 0` 为无标签。内部引擎未指定网桥时保留历史 `vmbr0` 默认值以兼容已有调用，但也会检查网桥在线状态。Agent v1 接口不新增 VLAN 字段，并清理继承的 `VLAN_TAG` 环境变量，避免改变既有 Agent 请求含义。

制作流程、预装软件、软件源、ZFS 替换边界及离线工具说明见 [README](../README.md#重新制作与更新策略)。首次制作比只导入官方云镜像更慢，因为实际安装了更新和软件；后续客户开通无需等待这些下载。
