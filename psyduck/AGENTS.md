# psyduck/ — 部署脚本架构说明

> 本文件是 `psyduck/frp-psyduck.sh` 的结构化摘要。Agent 读此文件即可理解全貌，无需通读源码。

## 元信息
- 语言：Bash（`set -euo pipefail`）
- 运行环境：Debian / Ubuntu，**必须 root**
- 用途：一键部署 FRP 穿透 + SOCKS5 代理 + SSH 容器（Docker + macvlan）
- 入口：`main "$@"`，支持 `--debug` / `--check`
- 部署标识：`/opt/psyduck/.deployed`（完成后 touch）

## 配置（脚本内硬编码）

### FRP 服务端
| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEFAULT_SERVER_ADDR` | `nezha.sggg3326.top` | FRPS 地址 |
| `DEFAULT_SERVER_PORT` | `7000` | FRPS 端口 |
| `DEFAULT_TOKEN` | `a1391959853-a1391959853` | FRP token |
| `FRP_VERSION` | `0.70.1` | frpc 版本 |
| `GOST_VERSION` | `3.2.6` | gost 版本 |

### SOCKS5 账密
| 变量 | 值 |
|---|---|
| `SOCKS5_USER` | `xiaoz` |
| `SOCKS5_PASS` | `a1391959853` |

### 其他
| 变量 | 值 | 说明 |
|---|---|---|
| `GITHUB_PROXY_PREFIX` | `https://ghproxy.q114.top/` | GitHub 加速前缀 |
| `IPV6_PREFIX_BASE` | `fdfa` | macvlan IPv6 前缀基 |
| `FASTEST_ALPINE_MIRROR` | `mirrors.aliyun.com` | Alpine 源（自动测速后更新） |
| `DEPLOY_FLAG` | `/opt/psyduck/.deployed` | 部署完成标识 |
| `CONFIG_FILE` | `/opt/psyduck/psyduck.conf` | 运行时配置 |
| `SCRIPT_PATH` | `/usr/local/bin/psyduck_maintenance.sh` | 维护脚本路径 |

### 主仓库来源
```
https://github.com/xoyoxoyo/relayApi.git
```
clone 到 `relayApi/`，构建 `psyduck` 主镜像（内置 frpc + 应用）。

## 模块结构

### 1. 工具函数
- `detect_arch` — 识别 x86_64 / aarch64 / armv7 / i386，设置 `BINARY_PATTERN`
- `get_physical_ifaces` — 过滤物理网卡（排除 lo/docker/br-/veth）
- `get_iface_info` — 返回 `ip|subnet|gateway`
- `check_iface_ipv6` — 检查是否有 `240e:* / 2408:* / 2409:* / 240a:*` 公网 IPv6

### 2. 环境准备（顺序执行）
| 函数 | 作用 |
|---|---|
| `check_and_set_mirrors` | APT 源改国内镜像（已国内则跳过） |
| `install_docker` | 未装则装，阿里云镜像；已装则确保 daemon 运行 |
| `check_docker_mirror` | 注入 3 个 registry-mirrors（nmqu / daocloud / nat.tf），失败自动回滚 |
| `install_git` | 装 git |
| `clone_and_build_main` | clone relayApi → 找二进制改名 psyduck → `docker build -t psyduck` |
| `test_alpine_mirrors` | 4 个源测速，写 `FASTEST_ALPINE_MIRROR` |

### 3. 镜像构建
| 函数 | 输出镜像 | 关键 |
|---|---|---|
| `build_socks5_image` | `psyduck-socks5` | alpine + frpc + gost；启动 `start.sh` 双进程守护 |
| `build_ssh_image` | `psyduck-ssh` | alpine + frpc；仅 entrypoint 跑 frpc |

**镜像标签**：`frp_version=<ver>` + `gost_version=<ver>`（用于版本检测，不匹配自动重建）

**SOCKS5 启动脚本**（`start.sh`）逻辑：
- 同时启动 gost（socks5 2233）和 frpc
- 各自独立监控，退出则指数退避重启（2s → 4s → ...）
- 连续 5 次异常退出 → 容器退出（避免死循环）
- 稳定运行 60s 后重置计数

### 4. 清理与漂移检测
| 函数 | 作用 |
|---|---|
| `clean_all_containers keep_ssh` | 删除所有 `psyduck*` 容器与网络；`keep_ssh=true` 时保留 SSH |
| `write_config_snapshot` | 把关键变量写进 conf 文件尾部 |
| `check_config_drift` | 对比脚本当前值与快照；不一致则清理全部容器 + 重写快照 |

### 5. 部署编排
| 函数 | 作用 |
|---|---|
| `select_deployment_mode` | 探网卡 → 分类（保留/失效/新增）→ 决定 single/multi |
| `configure_ports` | 每网卡分配主端口（rport），SOCKS5 = rport+1000 |
| `detect_and_save_config` | 写 `psyduck.conf`，含 `NETWORKS` 数组 |
| `create_macvlan_network` | 建 macvlan 网络，IPv4 + IPv6（前缀:5a35:6fce::/64） |
| `deploy_main_container` | 起 `psyduck<rport>` 主容器 |
| `deploy_socks5_container` | 起 `psyduck<rport>-socks5` |
| `deploy_ssh_container` | 起 `psyduck<rport>-ssh`（host 网络） |
| `generate_maintenance_script` | 生成 `/usr/local/bin/psyduck_maintenance.sh` |
| `setup_systemd_timer` | 每日 04:00 重启非 SSH 容器 |
| `verify_main_containers` | 检查主容器 `/ipv6` 接口通不通 |

## 命名与端口约定

### 容器名
| 类型 | 命名 | 网络 |
|---|---|---|
| 主容器 | `psyduck<rport>` | macvlan |
| SOCKS5 | `psyduck<rport>-socks5` | macvlan |
| SSH | `psyduck<rport>-ssh` | **host** |

### 端口映射
| 容器 | 本地端口 | 远程端口 | 说明 |
|---|---|---|---|
| 主容器 | 24678 | `<rport>` | 应用端口 |
| SOCKS5 | 2233 | `<rport + 1000>` | gost socks5 |
| SSH | 22 | `<rport + 2000>` | 本机 sshd |

### 网络
| 网卡序号 | 网络名 | IPv6 前缀 |
|---|---|---|
| 1 | `psyduck` | `fdfa` |
| 2 | `psyduck2` | `fdfa1` |
| 3 | `psyduck3` | `fdfa2` |
| ... | ... | ... |

**macvlan IPv6 subnet**：`<ipv6_prefix>:5a35:6fce::/64`

### frpc.ini 模板（三个容器共用结构）
```ini
[common]
server_addr = <DEFAULT_SERVER_ADDR>
server_port = <DEFAULT_SERVER_PORT>
token = <DEFAULT_TOKEN>
tls_enable = true

[psyduck<rport>(-socks5|-ssh)]
type = tcp
local_ip = 127.0.0.1
local_port = <本地端口>
remote_port = <远程端口>
```

## 配置漂移机制

**快照对比项**：`DEFAULT_SERVER_ADDR` / `DEFAULT_SERVER_PORT` / `DEFAULT_TOKEN` / `SOCKS5_USER` / `SOCKS5_PASS` / `FRP_VERSION` / `GOST_VERSION` / `GITHUB_PROXY_PREFIX`

**触发条件**：脚本内这些变量与 `psyduck.conf` 里的 `SNAPSHOT_*` 不一致

**动作**：清理所有 `psyduck*` 容器 + 网络 → 删除快照段 → 重写新快照

**目的**：保证修改脚本变量后，重新部署能真正生效（不会沿用旧容器）

## 命令行参数

| 参数 | 作用 |
|---|---|
| `--debug` | 部署前先清理**除 SSH 外**的所有容器与网络 |
| `--check` | 检查模式（**当前未实现**，仅打印提示退出） |
| 无 | 正常部署 |

## 部署流程（main 函数顺序）

```
1. 解析参数（--debug / --check）
2. --check 则退出
3. --debug 则 clean_all_containers(true)
4. check_and_set_mirrors        APT 源
5. install_docker               装 Docker
6. check_docker_mirror          Docker 加速
7. install_git                  装 Git
8. clone_and_build_main         拉仓库 + 构建主镜像
9. 判断 SOCKS5/SSH 镜像版本
   ├─ 都匹配 → 跳过测速
   └─ 有缺失 → test_alpine_mirrors 选最快源
10. build_socks5_image
11. build_ssh_image
12. check_config_drift          漂移检测
    └─ 不一致 → 清理容器 + 网络
13. select_deployment_mode      选网卡
14. configure_ports             配置端口
15. detect_and_save_config      写 psyduck.conf
16. source psyduck.conf
17. 遍历 NETWORKS
    ├─ create_macvlan_network
    ├─ deploy_main_container
    └─ deploy_socks5_container
18. 遍历 NETWORKS
    └─ deploy_ssh_container
19. 重启所有非 SSH 容器
20. generate_maintenance_script
21. setup_systemd_timer
22. verify_main_containers
23. touch /opt/psyduck/.deployed
```

## 输出文件与路径

| 路径 | 内容 |
|---|---|
| `/opt/psyduck/psyduck.conf` | 运行时配置（含快照） |
| `/opt/psyduck/.deployed` | 部署完成标识 |
| `/opt/psyduck/bin/frpc` | 本地 frpc 二进制（构建镜像用） |
| `/opt/psyduck/bin/gost` | 本地 gost 二进制 |
| `/opt/psyduck/socks5_<rport>/frpc.ini` | SOCKS5 容器挂载配置 |
| `/opt/psyduck/ssh_<rport>/frpc.ini` | SSH 容器挂载配置 |
| `/usr/local/bin/psyduck_maintenance.sh` | 每日维护脚本 |
| `/etc/systemd/system/psyduck-maintenance.{service,timer}` | systemd 定时器 |

## 关键不变量

1. **必须 root**：`[ "$EUID" -ne 0 ] && exit 1`
2. **`set -euo pipefail`**：任一步失败即退出（部分有 `|| true` 例外）
3. **端口推导固定**：SOCKS5 = rport+1000，SSH = rport+2000
4. **SSH 用 host 网络**，主容器和 SOCKS5 用 macvlan
5. **配置漂移即全清**：变量改了，旧容器必须删（避免版本混淆）
6. **镜像版本用 label 校验**：不匹配自动重建
7. **单网卡无交互**：只有一个可用网卡时直接 single，多个才提示选择
8. **窗口漂移保护**：`check_config_drift` 在 `select_deployment_mode` **之前**执行

## 数据流

```
用户执行 frp-psyduck.sh
    │
    ▼
环境准备（APT / Docker / Git / 主镜像）
    │
    ▼
构建 SOCKS5 + SSH 镜像
    │
    ▼
漂移检测 ──不一致──► 清理全部容器+网络
    │
    ▼
探测网卡 IPv6
    │
    ▼
决定部署模式（single / multi）
    │
    ▼
配置端口 → 保存 psyduck.conf
    │
    ▼
建 macvlan 网络
    │
    ▼
起容器（主 + SOCKS5 + SSH）
    │
    ▼
重启非 SSH 容器确保生效
    │
    ▼
生成维护脚本 + systemd 定时器
    │
    ▼
验证主容器 /ipv6 接口
    │
    ▼
touch .deployed
```

## 常见故障

| 现象 | 排查 |
|---|---|
| `请使用 root 权限` | 需要 `sudo` 或 root 用户 |
| `未找到物理网卡` | 无 `/sys/class/net/*/device`；VM 环境可能需调整 |
| `无可用 IPv6 网卡` | 网卡无 `240e/2408/2409/240a` 前缀 IPv6 |
| Docker 下载失败 | 检查 `get.docker.com` 可达性 |
| `docker build` 失败 | 检查 `xoyoxoyo/relayApi` 可达性；查看 `/tmp` 磁盘空间 |
| frpc / gost 下载失败 | GitHub 代理失效则回退直连，均失败则报错退出 |
| 容器重启循环 | 检查 frpc.ini 的 server_addr / token 是否正确 |
| 容器起来但没网 | macvlan 需父网卡支持混杂模式；检查 `docker network inspect` |
| `Socks5 镜像版本不匹配` | 修改 `FRP_VERSION` / `GOST_VERSION` 后自动重建，无需手动删 |
| 脚本变量修改不生效 | `check_config_drift` 应自动清理；若未生效，检查 `psyduck.conf` 里是否有 `SNAPSHOT_*` |
| `--check` 无输出 | 该模式**未实现**，预留 |
| 每日 04:00 重启失败 | `systemctl status psyduck-maintenance.service` |

## 依赖外部资源

| 资源 | 用途 |
|---|---|
| `https://get.docker.com` | Docker 安装脚本 |
| `https://github.com/xoyoxoyo/relayApi.git` | 主程序源码 |
| `https://github.com/fatedier/frp/releases/download/...` | frpc 二进制 |
| `https://github.com/go-gost/gost/releases/download/...` | gost 二进制 |
| `<FRPS 地址>:<端口>` | FRP 服务端（nezha.sggg3326.top:7000） |

**GitHub 下载失败时**：自动回退到直连；仍失败则报错退出。

## 与其他目录关系

| 目录 | 关系 |
|---|---|
| `api/` | 独立的 HTTP 服务（Cookie API），与此部署脚本无关 |
| `ql/` | 青龙面板脚本，运行时**依赖本脚本部署的 SOCKS5 代理**（端口由 `ql/wskey-update.py` 拉取） |

**链路**：
```
frp-psyduck.sh（本脚本）
   ↓ 部署
psyduck<rport>-socks5 容器 ← 提供 SOCKS5 出口
   ↓ 被使用
ql/wskey-update.py ← 拉 FRPS SOCKS5 端口列表 → 走代理转换 wskey
```