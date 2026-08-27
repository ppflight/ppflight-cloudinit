# PPFlight Proxmox Cloud-Init Templates

在 Proxmox VE 节点上一键下载、校验并创建常用 Linux Cloud-Init 模板。

脚本只使用发行版官方云镜像，下载完成后验证官方 SHA-256/SHA-512 校验值，再导入指定的 Proxmox 存储。适用于 VPS 自动开通、WHMCS、实验室及批量克隆场景。

## 创建的模板

| VMID | 模板名称 | 上游镜像 |
|---:|---|---|
| 9000 | `ubuntu-2204` | Ubuntu 22.04 LTS Cloud Image |
| 9001 | `ubuntu-2404` | Ubuntu 24.04 LTS Cloud Image |
| 9002 | `almalinux-8` | AlmaLinux 8 GenericCloud |
| 9003 | `debian-13` | Debian 13 GenericCloud |
| 9004 | `debian-12` | Debian 12 GenericCloud |
| 9005 | `centos-stream-9` | CentOS Stream 9 GenericCloud |
| 9006 | `centos-stream-10` | CentOS Stream 10 GenericCloud |

> CentOS Stream 9要求x86-64-v2，CentOS Stream 10要求x86-64-v3。模板可以在旧CPU节点上创建，但克隆出的系统未必能够启动；虚拟化不能补出宿主机没有的指令集。

## 功能

- 官方镜像URL与官方校验文件。
- 所有镜像验证成功后才开始修改VMID。
- 默认拒绝覆盖已有VM或模板。
- 使用`--replace`时只替换带`ppflight-cloudinit`标签的项目模板，绝不删除同号普通VM。
- 支持任意活动的PVE镜像存储，如ZFS、LVM-thin、Ceph RBD或目录存储。
- Cloud-Init静态IPv4占位配置，方便WHMCS在克隆时覆盖。
- root密码或SSH Key下发。
- QEMU Guest Agent首次开机安装并启用。
- BBR、`fq`、NTP、时区、SSH Host Key重新生成。
- Cloud-Init vendor-data按内容哈希使用不可变文件名，局部重建不会改写旧模板的SSH策略。
- 首次开机自动扩展分区及根文件系统。
- VGA与串口控制台同时保留。
- VirtIO SCSI Single、IO Thread、Discard、SSD标志。
- 可选的QEMU宿主机磁盘带宽与IOPS限制。
- 构建完成后回读模板配置并生成manifest。

## 环境要求

- Proxmox VE 8.x或9.x。
- 在PVE宿主机上以root运行。
- 节点可以访问Ubuntu、Debian、AlmaLinux和CentOS官方镜像站。
- 至少一个允许`images`内容的活动存储。
- 一个目录类型存储，用于Cloud-Init snippets和镜像下载缓存。
- 默认网桥为`vmbr0`。

运行前查看存储ID：

```bash
pvesm status
pvesh get /storage --output-format json-pretty
```

## 最快使用

### 克隆仓库

```bash
git clone https://github.com/ppflight/ppflight-cloudinit.git
cd ppflight-cloudinit
sudo bash build-cloud-templates.sh \
  --image-storage local-zfs \
  --file-storage local
```

### 单文件一键运行

发布到GitHub后，可以直接运行Raw脚本：

```bash
curl -fsSL https://raw.githubusercontent.com/ppflight/ppflight-cloudinit/main/build-cloud-templates.sh \
  -o /root/build-cloud-templates.sh

sudo bash /root/build-cloud-templates.sh \
  --image-storage local-zfs \
  --file-storage local
```

建议先下载再执行，便于审阅脚本。不要直接运行来源不明的Shell脚本。

## SSD＋RAID主机如何选择存储

脚本将“上游镜像下载缓存”和“最终PVE模板磁盘”分开处理。两者不是同一个东西：qcow2/img先作为普通文件下载，随后由`qm disk import`转换并导入目标PVE存储。

```text
FILE_STORAGE / CACHE_DIR
    存放下载的qcow2/img、校验文件和Cloud-Init snippets

IMAGE_STORAGE
    存放最终模板的系统盘以及Cloud-Init盘
```

假设主机有：

```text
local       → 系统SSD上的目录存储
raid-zfs    → 多盘RAID/ZFS池，允许Disk image
```

希望下载缓存放SSD、最终模板放RAID：

```bash
sudo bash build-cloud-templates.sh \
  --file-storage local \
  --image-storage raid-zfs
```

结果是：

```text
官方镜像缓存：local所在SSD
Cloud-Init snippets：local所在SSD
9000–9006系统盘：raid-zfs
9000–9006 Cloud-Init盘：raid-zfs
```

脚本不会为`IMAGE_STORAGE`使用隐式默认值。没有明确传入`--image-storage`就会退出，因此在SSD＋RAID主机上不会悄悄把最终模板放到系统SSD。

运行前先核对PVE存储ID与真实后端：

```bash
pvesm status
pvesh get /storage/local --output-format json-pretty
pvesh get /storage/raid-zfs --output-format json-pretty

# 若local的path为/var/lib/vz，确认它实际位于哪块盘/哪个挂载点
findmnt -T /var/lib/vz

# raid-zfs为ZFS时，再确认池的物理盘组成
zpool status
```

执行时脚本会在下载前输出类似：

```text
Resolved download cache: /var/lib/vz/.ppflight-cloudinit/cache
Download filesystem: /dev/mapper/pve-root ext4 /
Final OS and Cloud-Init disks: raid-zfs (type=zfspool pool=tank/vmdata)
```

看到的路径或池名不符合预期，应立即停止，不要使用`--replace`继续。

如果希望下载缓存写到另一个已挂载目录：

```bash
sudo bash build-cloud-templates.sh \
  --file-storage local \
  --image-storage raid-zfs \
  --cache-dir /mnt/download-ssd/cloud-images-cache
```

脚本不按`/dev/sda`或`/dev/nvme0n1`猜测硬盘，只使用明确给出的PVE存储ID，并在修改VMID前检查：

- 存储是否存在并处于`active`。
- `IMAGE_STORAGE`是否允许`images`。
- `FILE_STORAGE`是否为具有绝对路径的目录存储。
- 网桥是否存在。

因此有多个SSD/RAID池时，必须明确指定`--image-storage`，不要依赖默认值。

如果是PVE集群，`FILE_STORAGE=local`中的snippet文件并不会自动复制到其他节点。需要迁移或跨节点克隆时，应把`FILE_STORAGE`改为所有目标节点都能访问、并允许`snippets`的共享目录存储。

构建锁只覆盖当前节点；同一集群不要在多个节点同时运行本脚本。

若`FILE_STORAGE`尚未允许`snippets`，脚本会通过`pvesm set`在保留该存储当前有效content列表的基础上追加它。PVE的存储配置是集群级配置，运行日志会明确显示这次变更。

## 已有模板

默认情况下，只要本次所选VMID任一已存在，脚本便会停止。确认需要替换已有模板时才加入`--replace`：

```bash
sudo bash build-cloud-templates.sh \
  --image-storage raid-zfs \
  --file-storage local \
  --replace
```

保护规则：

- 同号普通VM：始终停止，不删除。
- 带`ppflight-cloudinit`标签的同号模板：只有`--replace`才替换。
- 老版本或人工创建的无标签模板：还需同时加入`--force-replace-unmanaged`，且名称必须匹配。
- 存在依赖该模板的Linked Clone时，PVE通常会阻止删除，脚本随即失败。
- 镜像校验在删除旧模板之前完成。

`--replace`不是事务切换：旧模板删除后若后续导入失败，脚本不会自动恢复旧模板。生产环境替换前应确认有可恢复备份，并安排维护窗口；首次部署到空VMID不受此风险影响。

迁移旧版无标签模板的示例：

```bash
sudo bash build-cloud-templates.sh \
  --image-storage raid-zfs \
  --file-storage local \
  --replace \
  --force-replace-unmanaged
```

## 只创建部分模板

按VMID：

```bash
sudo bash build-cloud-templates.sh \
  --image-storage local-zfs \
  --file-storage local \
  --only 9000,9001,9004
```

按名称：

```bash
sudo bash build-cloud-templates.sh \
  --image-storage local-zfs \
  --file-storage local \
  --only ubuntu-2204,ubuntu-2404,debian-12
```

## 配置文件

```bash
cp config.example.env /root/ppflight-cloudinit.env
nano /root/ppflight-cloudinit.env

sudo bash build-cloud-templates.sh \
  --config /root/ppflight-cloudinit.env
```

常用配置：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `IMAGE_STORAGE` | 必填 | 最终模板系统盘与Cloud-Init盘的PVE存储ID |
| `FILE_STORAGE` | `local` | snippets及默认缓存所在目录存储 |
| `CACHE_DIR` | 自动 | 下载缓存绝对路径 |
| `BRIDGE` | `vmbr0` | 模板VirtIO网卡桥接 |
| `DISK_SIZE` | `16G` | 模板最小系统盘 |
| `MEMORY_MB` | `2048` | 默认内存 |
| `CORES` | `2` | 默认CPU核数 |
| `CPU_TYPE` | `host` | PVE CPU模型；异构集群需修改 |
| `BALLOON` | `0` | 默认关闭内存气球 |
| `FIREWALL` | `1` | 启用PVE网卡防火墙标志 |
| `DISK_SSD` | `1` | 向来宾报告非旋转盘；纯HDD RAID设为`0` |
| `TIMEZONE` | `UTC` | 来宾默认时区 |
| `DNS_SERVERS` | `1.1.1.1 8.8.8.8` | Cloud-Init兜底DNS，可留空禁用 |
| `ALLOW_ROOT_PASSWORD_SSH` | `1` | 是否允许root密码SSH |
| `ENABLE_QOS` | `1` | 是否写入模板磁盘QoS |
| `REPLACE_EXISTING` | `0` | 是否替换已有模板 |
| `FORCE_REPLACE_UNMANAGED` | `0` | 是否允许替换同名无项目标签的旧模板 |

命令行参数优先于配置文件。

## 默认磁盘QoS

QoS写入Proxmox模板的`scsi0`，由宿主机QEMU执行，不依赖客户系统或QEMU Guest Agent。

| 类型 | 持续值 | Burst上限 | Burst时间 |
|---|---:|---:|---:|
| 读取带宽 | 200 MB/s | 350 MB/s | 未显式设置，使用PVE/QEMU默认窗口（通常1秒） |
| 写入带宽 | 150 MB/s | 300 MB/s | 未显式设置，使用PVE/QEMU默认窗口（通常1秒） |
| 读取IOPS | 5000 | 8000 | 30秒 |
| 写入IOPS | 3500 | 6000 | 30秒 |

按当前设计没有设置`bps_rd_max_length`和`bps_wr_max_length`。如不需要QoS：

```bash
sudo bash build-cloud-templates.sh \
  --image-storage local-zfs \
  --file-storage local \
  --no-qos
```

多块虚拟磁盘的QoS分别计算。如果商品承诺的是整台VPS总额度，WHMCS必须在添加数据盘时重新分配额度。

## Cloud-Init行为

模板使用RFC 5737文档地址作为不可路由占位值：

```text
9000 → 192.0.2.1/32
...
9006 → 192.0.2.7/32
```

克隆VPS时必须通过PVE或WHMCS覆盖：

- IPv4/CIDR和网关。
- IPv6和网关（如使用）。
- DNS、hostname。
- root密码或SSH Key。
- CPU、内存和磁盘大小。

模板不会内置固定root密码。

## root密码SSH安全说明

本项目面向VPS自动交付，示例默认允许Cloud-Init设置root密码登录。每台VPS必须使用独立随机密码。

如果只允许SSH Key：

```bash
sudo ALLOW_ROOT_PASSWORD_SSH=0 bash build-cloud-templates.sh \
  --image-storage local-zfs \
  --file-storage local
```

该设置只影响来宾模板，不应改变PVE宿主机的SSH安全策略。

## 模板发布后的验证

脚本会静态检查：

- VMID为模板且名称正确。
- QEMU Guest Agent开关。
- VGA与串口设备。
- SCSI磁盘优化和全部启用的QoS字段。
- Cloud-Init网络数据可生成。

构建manifest默认位于：

```text
<FILE_STORAGE路径>/.ppflight-cloudinit/cache/ppflight-template-build-manifest.txt
```

静态检查不能替代开机测试。正式上线前至少克隆一台候选VPS，验证SSH、网络、QEMU Guest Agent、BBR、磁盘扩容和唯一SSH Host Keys。

## WHMCS集成

推荐顺序：

```text
克隆模板
→ 等待PVE任务完成
→ Full Clone时明确指定目标storage
→ 设置CPU/内存
→ 扩容scsi0
→ 下发Cloud-Init IP、网关、DNS、密码或SSH Key
→ 按套餐覆盖QoS（如需要）
→ GET回读VM配置
→ 验证成功后启动VM
```

如果WHMCS重写完整`scsi0`，必须保留卷名、磁盘大小、Discard、SSD、IO Thread以及需要的QoS字段。

模板自身位于`--image-storage`指定的存储，但客户VPS的Full Clone位置仍由PVE clone API的`storage`字段决定；WHMCS应明确下发同一个RAID存储ID并在克隆后回读`scsi0`。Linked Clone通常必须留在模板所在存储。

## 常见问题

### `IMAGE_STORAGE does not allow VM images`

检查`pvesh get /storage/<storage-id> --output-format json-pretty`，目标存储必须允许`images`。

### `FILE_STORAGE must be a directory storage`

snippets需要文件路径。选择`local`或另一个目录类型存储，不要直接使用仅提供zvol的`zfspool`作为`FILE_STORAGE`。

### CentOS Stream无法启动

CentOS Stream 9确认CPU支持x86-64-v2；CentOS Stream 10确认CPU支持x86-64-v3。旧AMD Phenom、部分老Xeon不满足要求，虚拟化不能增加宿主机没有的指令集。

### Cloud-Init首次启动较慢

QEMU Guest Agent需要在首次启动通过发行版软件源安装。如果公网IP、网关、DNS或软件源不可用，安装会失败或延迟。生产环境可以进一步制作离线预装版镜像。

## 文件说明

```text
build-cloud-templates.sh          GitHub推荐的一键构建脚本
config.example.env               配置示例
cloud-init/                      独立Cloud-Init参考文件
docs/                            QoS、WHMCS和生产运行文档
CHANGELOG.md                     版本记录
.github/workflows/               ShellCheck持续检查
```

## 许可证

[MIT](LICENSE)
