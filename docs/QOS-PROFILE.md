# 默认磁盘QoS设计

QoS写入Proxmox模板及克隆VM的真实数据磁盘配置，由宿主机QEMU强制执行；不写入Cloud-Init，也不依赖来宾内的QEMU Guest Agent。

## 建议默认档位

| 项目 | 值 | 含义 |
|---|---:|---|
| 持续读取 | 200 MB/s | 单块虚拟盘长期读取上限 |
| 持续写入 | 150 MB/s | 单块虚拟盘长期写入上限 |
| Burst读取 | 350 MB/s | 短时读取峰值 |
| Burst写入 | 300 MB/s | 短时写入峰值 |
| 带宽Burst窗口 | 不设置 | 使用PVE/QEMU默认窗口（通常1秒） |
| 持续读IOPS | 5000 | 随机读取请求限制 |
| 持续写IOPS | 3500 | 随机写入请求限制 |
| Burst读IOPS | 8000 | 短时随机读峰值 |
| Burst写IOPS | 6000 | 短时随机写峰值 |
| IOPS Burst窗口 | 读写均30秒 | 随机I/O突发窗口 |

本档位已写入`build-cloud-templates.sh`，也可以由WHMCS在克隆后按产品档位覆盖。

## 重要限制

- 这是每块虚拟磁盘的限制，不是整台VM共享总额。
- 普通套餐最好只提供一块可扩容的`scsi0`。
- 若新增`scsi1/scsi2`，WHMCS必须重新分配整台VM额度，或明确商品按盘计费。
- Cloud-Init光驱不参与限速。
- PVE 8.4没有暴露`iops_size`，生产配置暂不使用；需以生产机实际schema为准。
- 当前默认配置不设置`bps_rd_max_length`和`bps_wr_max_length`。

## 生产机必须重新确认

```text
qm help set --verbose
```

检查目标磁盘总线支持的全部`mbps`、`iops`、`max`和`max_length`字段。不能直接根据网络文章或QEMU原生参数猜测Proxmox字段。
