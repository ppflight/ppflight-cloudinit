# 交互安装指南

## 准备

在 Proxmox VE 8/9 宿主机的交互终端中以 root 运行。需要能访问发行版镜像站，并已配置 `vmbr0` 网桥和下列存储：

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

依次完成三步，随后显示配置并提示开始安装（回车默认 Yes，输入 n 取消）：

1. 回车默认 `ALL` 安装全部模板，或输入 `9000,9001` / `9000 9001` 选择模板。重复 VMID 自动去重。
2. 输入镜像下载存储的菜单序号（回车默认第 1 项）。
3. 输入模板安装位置存储的菜单序号（回车默认第 1 项）。

示例选择过程（序号取决于本机实际存储列表）：

```text
模板：9000,9001
选择镜像下载位置（iso、snippets）
选择序号：1
选择模板安装位置（images）
选择序号：2
制作配置：模板=9000,9001，镜像=local，安装位置=raid-zfs
```

脚本校验官方镜像后创建模板，再验证制作结果。此流程不备份模板、不从旧备份执行 `qmrestore`。VPS 备份目标在后续 PVE/WHMCS 备份任务中配置，不随模板克隆继承。

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

已有 VMID 不会被覆盖，请只选择尚未制作的模板。

## 常见情况

- **upstream checksum differs from catalog**：旧入口使用会变化的 `latest` 镜像，已切换到与固定校验值一致的官方日期版。重新运行在线命令即可获取修复；不要跳过 SHA 校验。现有正确镜像缓存会继续校验后复用。

- **发现 PVE 存储失败 / Unknown option: output-format**：旧版本误向 `pvesm` 传入 JSON 输出参数，已改为节点 `pvesh` API。重新执行在线命令获取修复版；新版也会显示具体失败原因。

- **没有合格存储**：在 PVE 中检查存储是否启用、对当前节点可用，以及是否允许表格中的内容类型。镜像存储必须同时支持 `iso` 和 `snippets`。
- **已有 VMID**：脚本停止，不覆盖已有 VM 或模板。重新运行时只选择尚未创建的 VMID。
- **输入错误**：重新显示输入提示；在菜单阶段按 Ctrl+C 或结束输入可退出。
- **提示需要交互终端**：在 PVE Shell/SSH 终端运行上面的一键命令；启动脚本会打开终端读取菜单，不要通过管道传入菜单答案。

## 自动化集成

新模板默认关闭克隆系统自动升级与自动重启，并屏蔽 APT unattended-upgrades、DNF/YUM 自动更新任务；必要软件的首次安装仍保留。此设置不追溯修改已有克隆。PVE/WHMCS 后续覆盖 `ciupgrade` 或 Cloud-Init 配置时，应继续保持 `ciupgrade=0` 和 `package_upgrade=false`。

面向人的入口使用上面的在线命令，不再接收旧命令参数。Agent 自动化使用 [Python helper](AGENT-BOOTSTRAP.md)，由 helper 调用内部构建引擎。镜像校验、VMID 保护和构建验证继续由公共引擎执行。
