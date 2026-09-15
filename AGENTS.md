# jd-ios-ck — 项目总览

> 本文件是仓库的顶层架构摘要。各子目录另有独立的 `AGENTS.md`，深入细节请查阅对应文件。

## 元信息
- 语言：Python 3 / JavaScript / Bash
- 用途：京东 App 自动抓 Cookie → 服务端验证 → 写入青龙面板
- 部署链路：iOS 抓包 → Flask API → 青龙面板 → 定时任务
- 分支：`X`（主开发分支）

## 目录总览

```
jd-ios-ck/
├── ios/         iOS 端抓包脚本 + 三平台导入配置
├── api/         Flask 服务端（接收 Cookie，转换与写库）
├── ql/          青龙面板脚本（wskey 转换 + IPv6 探测）
└── psyduck/     FRP 穿透 + SOCKS5 代理一键部署
```

| 目录 | 语言 | 作用 | 依赖 |
|---|---|---|---|
| `ios/` | JavaScript | 拦截京东 App 请求，提取 Cookie 并提交 | Quantumult X / Surge / Loon |
| `api/` | Python (Flask) | 接收 iOS 提交，wskey→pt_key 转换，写青龙 | flask, PySocks |
| `ql/` | Python | 青龙内定时任务：wskey 批量转换、IPv6 探测 | PySocks（ql 内自动装） |
| `psyduck/` | Bash | 部署 FRP 隧道 + SOCKS5 代理容器 | Docker, root 权限 |

## 数据流

```
┌─────────────────────────────────────────────────────────┐
│  iOS 京东 App                                            │
│    │  (sh.jd.com / api.m.jd.com 请求)                    │
│    ▼                                                     │
│  Quantumult X / Surge / Loon                            │
│    │  ios/JDcookie.js 拦截 → 提取 4 字段                 │
│    ▼                                                     │
│  POST http://<server>:9090/jd/raw_ck                    │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  api/ — Flask 服务端                                     │
│    1. 四字段校验                                          │
│    2. 查 success_cache.json（pt_pin → pin_hash）         │
│       ├─ 命中 → 跳过转换，用客户端 pt_key 写青龙          │
│       └─ 未命中 → 走 genToken + appjmp 换 pt_key         │
│    3. 写青龙 JD_COOKIE / JD_WSCK                         │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  青龙面板                                                 │
│    JD_COOKIE / JD_WSCK                                   │
│    │                                                      │
│    ├─ ql/wskey-update.py — 定时批量转换                  │
│    └─ ql/psyduck-ipv6.py — 定时探测 FRPS 端口 IPv6       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  psyduck/ — 基础设施                                      │
│    frp-psyduck.sh 部署：                                  │
│      FRP 穿透容器 + SOCKS5 代理 + SSH                    │
│    提供 api/ 和 ql/ 使用的 SOCKS5 出口                    │
└─────────────────────────────────────────────────────────┘
```

## 目录详解

### ios/ — iOS 抓包端

**核心文件**：
- `JDcookie.js` — 拦截、提取、配对、提交
- `JDcookie2qx.conf` / `JDcookie2api.sgmodule` / `JDcookie2loon.conf` — 三平台导入入口
- `京东京豆显示美化+优化.scriptable` — Scriptable 桌面组件

**关键配置**：`JDcookie.js` 第 5 行 `API_URL`，须指向 `api/` 部署地址

**依赖**：iOS 代理工具（QX / Surge / Loon 之一）+ 证书信任

**详见**：`ios/AGENTS.md`

---

### api/ — 服务端

**核心文件**：`app.py`（Flask 服务）
- `POST /jd/raw_ck` — 接收四字段
- `GET /health` — 健康检查

**运行时**：Docker `network_mode: host`，监听 `0.0.0.0:9090`

**依赖**：`flask`、`PySocks`

**缓存**：`./data/success_cache.json`（`pt_pin → pin_hash`）

**关键配置**（硬编码于 `app.py` 顶部）：
- 青龙：`http://127.0.0.1:5700` + `QL_CLIENT_ID` / `QL_CLIENT_SECRET`
- FRPS：`http://127.0.0.1:7500/api/proxy/tcp`
- SOCKS5：`xiaoz` / `<密码>`

**详见**：`api/AGENTS.md`

---

### ql/ — 青龙脚本

**两个独立脚本**：

| 文件 | 用途 | 触发方式 |
|---|---|---|
| `wskey-update.py` | 批量 wskey → pt_key 转换，写回青龙 | 定时任务 |
| `psyduck-ipv6.py` | 探测 FRPS 端口 IPv6，写代理配置 | 定时任务 |

**共享环境变量**：`REMOTE_QL_URL` / `FRPS_API_PORT` / `FRPS_API_AUTH`

**关键区别**：
- `wskey-update.py` 匹配 `^psyduck\d{4}-socks5$`
- `psyduck-ipv6.py` 匹配 `^psyduck\d{4}$`

**详见**：`ql/AGENTS.md`

---

### psyduck/ — 基础设施部署

**核心文件**：`frp-psyduck.sh`（Bash，需 root）

**功能**：
- 装 Docker / Git / APT 镜像
- 构建 `psyduck` / `psyduck-socks5` / `psyduck-ssh` 镜像
- 建 macvlan 网络，起主容器 + SOCKS5 + SSH
- 每日 04:00 自动重启非 SSH 容器

**依赖**：Debian / Ubuntu + Docker

**详见**：`psyduck/AGENTS.md`

## 端到端配置步骤

新用户从零部署的**正确顺序**：

```
1. 部署 psyduck/frp-psyduck.sh
   → 提供 SOCKS5 出口给 api/ 和 ql/ 使用

2. 部署 api/app.py
   → Docker 起 Flask 服务，监听 9090
   → 修改 app.py 顶部配置（青龙 / FRPS / SOCKS5 凭据）

3. 配置 ios/
   → 导入 .conf/.sgmodule 到 iOS 代理工具
   → 修改 JDcookie.js 的 API_URL 指向 api/ 地址

4. 配置 ql/
   → 把 wskey-update.py / psyduck-ipv6.py 上传到青龙
   → 设置环境变量 REMOTE_QL_URL 等
   → 建定时任务
```

## 关键不变量（跨目录）

1. **HTTP 状态码恒为 200**（api/ 返回给 ios/）
2. **成功标识**：`body.includes("ok")`（ios/ 判断）
3. **失败标识**：`body.startsWith("校验失败，京东账号: ")`（ios/ 撤销本地绑定）
4. **四字段必填**：`pt_key` / `pt_pin` / `wskey` / `pin_hash`（api/ 校验）
5. **`pt_pin` 提交前 `encodeURIComponent`**（ios/），api/ 会 `unquote` 还原
6. **无可用代理拒绝服务**（api/ 和 ql/ 都遵守，绝不降级直连）
7. **缓存只存 `pt_pin → pin_hash`**（api/），不存 `pt_key`

## 常见故障（跨目录）

| 现象 | 排查方向 |
|---|---|
| iOS 抓不到包 | MitM 未开 / 证书未信任 |
| api/ 返回"校验失败" | SOCKS5 代理不通 / 防火墙未放行端口段 |
| ql/ 转换失败 | FRPS 无可用 SOCKS5 隧道 / 账密错 |
| psyduck 部署后容器起不来 | macvlan 网卡不支持 / IPv6 未配置 |
| 青龙写入后无 `JD_COOKIE` | api/ 的 `QL_CLIENT_ID/SECRET` 错误 |

## 各目录独立说明文件

| 目录 | 说明文件 |
|---|---|
| `ios/` | `ios/AGENTS.md` |
| `api/` | `api/AGENTS.md`（或 `ARCHITECTURE.md`） |
| `ql/` | `ql/AGENTS.md`（或 `ARCHITECTURE.md`） |
| `psyduck/` | `psyduck/AGENTS.md` |

**Agent 工具通常会自动读取当前目录及父目录的 `AGENTS.md`。** 在任一子目录下工作时，工具会先加载该子目录的说明，再回溯到根目录。

## 分支与提交

- 主开发分支：`X`
- 推送：`git push origin X`
- 各子目录的 AGENTS.md 与源码一同提交