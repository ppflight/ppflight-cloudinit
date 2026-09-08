# v3 bootstrap安全审计

本审计覆盖仓库现有README、builder、Cloud-Init profile、storage参数、QoS、manifest、CI和旧兼容入口。目标是让PPFlight Agent在PVE本机完成模板准备，而不获得或依赖官网保存的PVE Token。

## 已处理

| 发现 | 风险 | v3处理 |
|---|---|---|
| 模板目录硬编码在大段shell数组 | 官网、Agent和builder容易漂移 | 唯一真源改为严格JSON catalog；builder通过验证后的本地helper读取 |
| 上游`latest/release` URL会变 | 同一模板名称可能静默换镜像 | 使用与catalog对应的官方日期版URL；固定SHA-256、文件最小字节数及官方checksum entry，校验不符仍失败 |
| 旧脚本可自动`pvesm set`追加snippets | 无计划修改集群级storage配置 | 删除自动修改；discovery只返回typed reason和`automatic=false`的安全argv建议，执行前强制`iso+snippets` |
| storage只有下载/模板两种角色 | 无法明确选择和验证备份落点 | 增加显式image/template/backup三角色及content/active/enabled/space检查 |
| 单Raw builder可脱离其目录数据运行 | 执行文件与目录/摘要版本不一致 | v3 builder必须与catalog/helper同bundle；发布manifest固定每个runtime文件摘要 |
| shell环境变量可改变builder行为 | Agent未传`--replace`仍可能被环境旁路 | helper清理全部builder配置、`BASH_ENV`及runtime注入变量，使用固定PATH和argv |
| PVE API Token可能进入网站或日志 | 凭据泄露与跨节点高权限 | helper只调用本机PVE CLI；无需官网Token；最终JSON与本机stderr分离 |
| 目标VMID检查仅靠执行中的shell | Agent无法在确认前显示冲突 | plan先查集群资源并返回`VMID_CONFLICT`；builder在`qm create`前再次检查 |
| plan和execute之间catalog可变化 | 用户确认内容与执行内容不同 | execute强制回传UUID、revision和catalog SHA-256；builder再次验证同一摘要 |
| 字符串命令拼接 | shell注入 | helper只构造argv数组，storage/bridge/item/UPID均严格校验，不接受URL或catalog路径 |
| curl默认读取root的`.curlrc`或回退IPv6 | 本机配置可悄悄增加URL/上传等行为；不符合IPv4-only产品边界 | 每个下载都把`--disable`放在首参数，强制`--ipv4`，并把初始及重定向协议限制为HTTPS |
| content声明与实际文件路径能力不一致 | discovery显示可用、执行中才失败 | discovery和plan分别探测`iso`及`snippets`的`pvesm path`，返回typed reason |

## 有意保留的直接builder风险

`tools/build-template-engine.sh`仍为老用户保留`--config`和`--replace`：

- `--config`使用Bash `source`，配置文件就是可执行代码，只能加载root管理员自己审阅的文件。
- `--replace`不是事务切换；删除旧模板后若导入失败不会自动恢复。
- root密码SSH默认值适合VPS自动交付，但每个实例必须使用独立随机密码；不需要密码登录时设置`ALLOW_ROOT_PASSWORD_SSH=0`。

这些选项不属于Agent contract。helper不接受它们、清理同名环境变量，并把任何已占用VMID视为不可执行冲突。

仓库还保留测试节点历史、host key和基于Paramiko的远程运维工具，供既有人工流程追溯；它们包含节点绑定信息，也接受本地密码环境变量，不属于Agent runtime或vendor清单。Agent安装包必须只复制`agent-vendor-manifest.v1.json`明确列出的bundle文件，不得携带这些历史文件。

## 运行期剩余限制

- 构建锁只覆盖本节点；同一PVE集群不要在多个节点同时执行相同VMID catalog。
- 首次创建不是分布式事务。某个后续模板或备份失败时，已成功的新模板会保留并在per-item result中报告；helper不会用自动删除扩大故障。
- 备份成功不等于恢复演练完成。生产前仍需从backup storage测试恢复。
- 日期版镜像被上游删除或替换时仍会安全失败；升级镜像需要发布新`catalogRevision`和Agent bundle，不得只改摘要绕过review。
- Debian官方入口会选择HTTPS镜像节点；manifest把初始主机和upstream redirect policy分开声明，重定向内容仍必须通过两层固定摘要，不能把`networkHosts`误用为完整静态防火墙allowlist。
- Cloud-Init首次启动仍依赖客户网络和发行版软件源安装guest工具。
