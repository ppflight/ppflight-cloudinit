# PPFlight Agent vendoring

全新 PVE 的运行路径不得在命令执行时 `git clone`、`git pull` 或从官网获取可执行脚本。Agent 安装包应把下列文件作为同一个只读版本单元内置：

仓库根目录的`agent-vendor-manifest.v1.json`给出可直接用于Agent构建/安装校验的固定文件摘要和依赖；其schema为`contracts/agent-vendor-manifest.schema.json`。

推荐安装为 root 拥有且普通用户不可写的固定目录；以下是完整安装清单：

```text
/usr/local/lib/ppflight-agent/template-bootstrap/
├── agent-vendor-manifest.v1.json
├── build-cloud-templates.sh
├── catalog/
│   ├── template-catalog.v1.json
│   └── template-catalog.schema.json
├── contracts/
│   ├── agent-vendor-manifest.schema.json
│   ├── template-bootstrap-request.schema.json
│   ├── template-bootstrap-result.schema.json
│   └── template-storage-discovery.schema.json
└── tools/
    ├── build-template-engine.sh
    └── ppflight-template-bootstrap.py
```

目录使用 `root:root`/`0755`，文件使用 `root:root`/`0644` 即可；builder 由固定 `/usr/bin/bash` 读取，不需要可写或 setuid 权限。Agent 应先在同文件系统临时目录验证完整 bundle，再原子切换版本目录。

运行入口必须是 vendored `tools/ppflight-template-bootstrap.py`；推荐固定调用形式：

```text
/usr/bin/python3 -I /usr/local/lib/ppflight-agent/template-bootstrap/tools/ppflight-template-bootstrap.py <subcommand> ...
```

`-I` 让 Python 启动时忽略用户级模块路径。Agent 不应直接拼接或执行 `build-cloud-templates.sh` 参数。

发布 Agent 包时应把以下值记录进自身构建 manifest，并在安装时验证文件 SHA-256：

- cloudinit bundle version（当前 builder `3.0.0`）。
- catalog `catalogRevision`。
- catalog 文件 SHA-256（helper 的 `catalogSha256`）。
- 上述每个 runtime 文件的 SHA-256。

catalog 文件摘要会随 JSON 的任何字节变化而变化。Agent 不应重排、格式化或重新序列化 vendored catalog。

`agent-vendor-manifest.v1.json` 本身由 Agent 安装包的签名/摘要保护，因此不会递归记录自身摘要；installer 必须验证它列出的每个文件，拒绝缺失文件、摘要不符、额外可写覆盖层或版本混装。manifest 中 `requiredAtRuntime=false` 仅表示 helper 不读取该 schema，不表示安装包可以省略它。

## PVE 运行依赖

PVE 8/9 默认通常已提供大部分依赖；Agent 安装/健康检查仍应显式确认：

```text
python3 >= 3.9
bash >= 5
qm, pvesm, pvesh, pveversion, pvecm, vzdump
qemu-img, curl
sha256sum, sha512sum, stat, awk, grep, sed, ip, findmnt, df, dirname, flock
perl + JSON::PP
```

manifest 的 `networkHosts` 是 catalog 内置 `urlKey` 的初始 HTTPS 主机。Debian 的官方 `cloud.debian.org` 入口会选择 HTTPS 镜像节点，因此它不是完整的静态防火墙allowlist；`networkRedirectPolicy`明确记录只允许HTTPS重定向、host下载强制IPv4，且最终字节仍必须同时满足catalog SHA-256和固定官方checksum entry。调用方不能提供或覆盖URL。helper不需要PPFlight网站凭据或PVE API Token。

安装包不得把仓库中的历史远程运维脚本、host key、测试节点状态或 Git 元数据一并复制到该目录。运行时不需要 Git、Paramiko，也不需要访问 GitHub。

## 升级规则

Agent 升级应原子替换整个 bundle，不能只更新 catalog 或单独更新 builder。已有 plan 若发现 `catalogRevision` 或 `catalogSha256` 变化，必须废弃并重新展示确认。
