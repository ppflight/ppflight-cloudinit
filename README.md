# PPFlight Proxmox Cloud-Init 模板安装

在 Proxmox VE 8/9 节点以 root 运行：

```bash
curl -fsSL https://raw.githubusercontent.com/ppflight/ppflight-cloudinit/main/install.sh | bash
```

无需 Git 或手动下载文件。启动脚本自动下载并校验完整安装程序，然后按菜单依次选择：

1. **模板**：输入 VMID；多个用空格或逗号分隔，`ALL` 全选。
2. **镜像下载位置**：选择保存云镜像和 Cloud-Init snippets 的存储。
3. **模板安装位置**：选择存放模板系统盘的存储。

回车默认：模板 `ALL`、存储第 `1` 项、开始安装 `Yes`。选完显示配置，按回车开始下载、校验和制作模板；输入 `n` 取消。无需命令参数，输入错误会重新提示，结束输入会取消安装。

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

菜单显示已启用、在线且支持对应用途的 PVE 存储及剩余空间。镜像位置须支持 `iso,snippets`，安装目标须支持 `images`。没有合格存储时停止，请先在 PVE 配置相应内容类型。默认网桥为 `vmbr0`。

镜像固定到官方日期版地址，并同时验证目录 SHA-256 和官方 checksum，避免 `latest` 更新导致安装中断。

新模板的克隆系统默认关闭自动升级：PVE `ciupgrade=0`，Cloud-Init 不做全系统升级或自动重启，APT unattended-upgrades 和 DNF/YUM 自动更新任务被屏蔽。首次启动仍安装 QEMU Agent 等必要软件，可能刷新软件源索引；手动安装和更新仍可用。此策略只作用于使用新模板和新 Cloud-Init 配置的克隆，不修改 PVE 宿主机或已有克隆。

此入口只制作模板，不备份模板、不创建 VPS 备份任务，也不执行已有备份恢复。脚本不分区、不格式化磁盘，也不覆盖已有 VMID。VPS 的备份存储需在后续 PVE/WHMCS 备份任务中指定，不会通过克隆模板自动继承。

底层构建逻辑保留官方镜像校验、Cloud-Init 配置和安装结果检查。`tools/build-template-engine.sh` 是内部构建入口，供交互菜单和 Agent 共用。Agent 集成见 [接口文档](docs/AGENT-BOOTSTRAP.md) 和 [内置清单](docs/AGENT-VENDORING.md)。
