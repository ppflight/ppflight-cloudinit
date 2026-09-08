# Agent 本地模板 Bootstrap 契约

`tools/ppflight-template-bootstrap.py` 是供 PPFlight Agent 调用的本地 helper。它只使用 PVE 节点本机的 `pvesh`、`pvesm`、`qm` 等命令，不读取官网 PVE Token，也不调用 PPFlight 私有接口。

## 安全边界

- 默认行为是 plan；只有显式加入 `--execute` 才修改 PVE。
- CLI 不接受 URL、catalog 路径、cache 路径、`--replace` 或任意 shell 片段。
- 镜像 URL 只能由内置 `urlKey` 映射解析；catalog 同时固定源文件 SHA-256 和发行版官方 checksum。
- catalog 解析拒绝重复 JSON key、未知字段、未知 `urlKey`、重复 `templateRef`/alias/VMID 以及不安全字符。
- 执行命令全部使用 argv 数组和 `shell=False`。
- helper 固定子进程PATH并清除`BASH_ENV`、语言runtime注入变量以及所有builder配置环境变量；外部环境不能偷偷启用`REPLACE_EXISTING`、`CONFIG_FILE`或自定义cache。
- helper 在集群资源中发现任一目标 VMID 已存在时返回 `VMID_CONFLICT`；它永远不覆盖或删除已有 VM/模板，也不会向底层 builder 传 `--replace`。
- `--execute` 必须带回已确认 plan 的 `requestId`、`operationId`、`catalogRevision` 和 catalog SHA-256；任一漂移都会在修改 PVE 前停止。
- 执行日志只写本机 stderr。Agent 不应把完整日志、UPID task log 或宿主机路径上传到官网。

直接使用 `tools/build-template-engine.sh --config` 会 `source` 本地配置文件，等同执行该文件中的 shell。Agent 集成绝不能使用 `--config`，只应调用本 helper。

## Storage 角色

`discover` 返回每个 storage 的 `active`、`enabled`、`shared`、`contentTypes`、十进制字符串 `availableBytes`、`availableBytesKnown`，并为三种角色给出 `allowed` 和 typed `reasons`。当 PVE 没有报告容量时，`availableBytes` 为字符串 `"0"` 且 `availableBytesKnown=false`，不能把它解释成存储已满。

| 参数 | 必须支持 | 用途 |
|---|---|---|
| `imageStorage` | `iso` 和 `snippets` | 官方镜像下载缓存及不可变 Cloud-Init snippet |
| `templateStorage` | `images` | 最终模板系统盘和 Cloud-Init 盘 |
| `backupStorage` | `backup` | 新建模板的 `vzdump` 备份 |

下载缓存默认落在 `imageStorage` 的 ISO 内容目录下 `ppflight-cloudinit-cache/`。helper 在 discovery 和执行前都会分别用 `pvesm path` 探测 `iso` 与 `snippets`；无法解析为安全本机路径时，image role 的 `allowed=false` 并返回 `IMAGE_STORAGE_ISO_PATH_UNSUPPORTED` 或 `IMAGE_STORAGE_SNIPPETS_PATH_UNSUPPORTED`。

`iso` 内容目录承载官方镜像、checksum和本地build manifest；`snippets` 内容目录承载模板通过`cicustom`引用的不可变Cloud-Init vendor-data。因此image role硬性要求二者。典型新装PVE的`local`若只缺`snippets`，discovery会给出机器可读、但绝不自动执行的建议：

```json
{
  "code": "ENABLE_STORAGE_CONTENT",
  "storageId": "local",
  "currentContent": "backup,iso,vztmpl",
  "requiredContent": "snippets",
  "proposedContent": "backup,iso,snippets,vztmpl",
  "command": {
    "program": "pvesm",
    "argv": ["pvesm", "set", "local", "--content", "backup,iso,snippets,vztmpl"]
  },
  "automatic": false
}
```

它只会出现在已启用、活动且类型明确支持文件内容的storage `remediations[]`中。若没有`roleEligibility.image.allowed=true`的候选，Agent必须停止、显示建议并要求管理员显式执行后重新运行；不得代执行、不得把空storage选择继续传入bootstrap。

不备份必须显式使用 `backupPolicy=disabled`；不能用空字符串或缺少选择来猜测。`backupPolicy=required` 时必须传 `--backup-storage`。

## CLI

所有成功和失败的最终响应都输出到 stdout，格式为 JSON。执行过程写 stderr。

### Catalog

```bash
python3 tools/ppflight-template-bootstrap.py catalog
```

无需 PVE 命令即可运行。返回已验证 catalog、`catalogRevision` 和 `catalogSha256`。

### Storage discovery

```bash
python3 tools/ppflight-template-bootstrap.py discover
```

### Plan（默认且无副作用）

```bash
python3 tools/ppflight-template-bootstrap.py bootstrap \
  --image-storage local \
  --template-storage raid-zfs \
  --backup-policy required \
  --backup-storage pbs-backup \
  --items all \
  --bridge vmbr0
```

明确不备份：

```bash
python3 tools/ppflight-template-bootstrap.py bootstrap \
  --image-storage local \
  --template-storage raid-zfs \
  --backup-policy disabled
```

`--items` 只接受 `all` 或 catalog 中的 `templateRef`、alias、VMID，以逗号分隔。响应中的 item 一律归一化成官网稳定 `templateRef`。

### Execute（确认后的本地 Agent 调用）

Agent 必须原样带回 plan 的四个确认字段，并使用相同 storage/items/bridge：

```bash
python3 tools/ppflight-template-bootstrap.py bootstrap \
  --image-storage local \
  --template-storage raid-zfs \
  --backup-policy required \
  --backup-storage pbs-backup \
  --items all \
  --bridge vmbr0 \
  --request-id 11111111-1111-4111-8111-111111111111 \
  --operation-id 22222222-2222-4222-8222-222222222222 \
  --expected-catalog-revision 2026-08-30.1 \
  --expected-catalog-sha256 <plan.catalog.catalogSha256> \
  --execute
```

Agent UI 应先展示 plan（storage、VMID、模板、固定摘要、备份策略和阻塞项），获得用户明确确认后才调用 execute。

## JSON contract

正式 schema：

- `catalog/template-catalog.schema.json`
- `contracts/template-bootstrap-request.schema.json`
- `contracts/template-bootstrap-result.schema.json`
- `contracts/template-storage-discovery.schema.json`

Request 的稳定字段：

```json
{
  "schemaVersion": "ppflight.template-bootstrap-request/v1",
  "requestId": "UUID",
  "operationId": "UUID",
  "catalogRevision": "2026-08-30.1",
  "imageStorage": "local",
  "templateStorage": "raid-zfs",
  "backupStorage": "pbs-backup",
  "backupPolicy": "required",
  "items": [
    {
      "templateRef": "ubuntu-2404",
      "version": "24.04",
      "sha256": "64 lowercase hex characters",
      "targetVmid": 9001
    }
  ]
}
```

`backupPolicy=disabled` 时 `backupStorage` 字段必须省略。

每个 plan/result item 始终包含：

```text
templateRef, version, sha256, targetVmid,
phase, state, errorCode,
sourceVolume, templateVolume, backupVolume, upid
```

未知或尚未产生的 volume/UPID 使用 JSON `null`，不是空字符串。所有 byte 数量在 plan/result/discovery 中均为十进制字符串。

官网 `/vps/proxmox-templates` 与本地 catalog 只能按以下五个字段匹配：

```text
templateRef + version + sha256 + architecture + guestType
```

VMID 是本地部署目标，不是官网业务主键。

## Exit code

| Code | 含义 |
|---:|---|
| `0` | discovery/catalog 成功、plan ready，或 execute 全部成功 |
| `1` | 已进入执行但 builder/模板/备份任务失败 |
| `2` | 参数、catalog、PVE preflight、storage 或 VMID 冲突导致拒绝 |

业务判断应优先使用 JSON `state`、item `errorCode` 和 `errors[]`，不要解析人类日志。

常用 typed error code：

| 范围 | Codes |
|---|---|
| 请求确认 | `UUID_INVALID`, `OPERATION_CONFIRMATION_REQUIRED`, `CATALOG_CONFIRMATION_REQUIRED`, `CATALOG_DRIFT` |
| 备份策略 | `BACKUP_POLICY_INVALID`, `BACKUP_STORAGE_REQUIRED`, `BACKUP_STORAGE_FORBIDDEN` |
| Storage | `STORAGE_NOT_FOUND`, `STORAGE_DISABLED`, `STORAGE_INACTIVE`, `IMAGE_STORAGE_CONTENT_UNSUPPORTED`, `TEMPLATE_STORAGE_CONTENT_UNSUPPORTED`, `BACKUP_STORAGE_CONTENT_UNSUPPORTED`, `*_STORAGE_INSUFFICIENT_SPACE` |
| 文件型 storage | `IMAGE_STORAGE_ISO_PATH_UNSUPPORTED`, `IMAGE_STORAGE_SNIPPETS_PATH_UNSUPPORTED` |
| PVE 目标 | `BRIDGE_NOT_FOUND`, `VMID_CONFLICT`, `ROOT_REQUIRED` |
| 执行 | `BUILDER_FAILED`, `TEMPLATE_VOLUME_NOT_FOUND`, `BACKUP_TASK_FAILED`, `BACKUP_TASK_TIMEOUT` |

`CATALOG_*` 和 `PVE_*` 还覆盖 catalog/schema、内置源以及本地 PVE CLI 响应异常；调用方必须把未知 code 当作失败，而不是放行。
