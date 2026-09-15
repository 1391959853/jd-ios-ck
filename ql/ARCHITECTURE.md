# ql/ 脚本 — 架构说明

> 本文件是 `ql/` 目录下两个脚本的结构化摘要。Agent 读此文件即可理解全貌，无需通读源码。

## 元信息
- 语言：Python 3.x（青龙面板内置解释器）
- 依赖：`wskey-update.py` 需 `PySocks`（自动安装）；`psyduck-ipv6.py` 仅标准库
- 部署：青龙面板「脚本管理」定时任务
- 入口：两脚本均 `if __name__ == '__main__': main()`

## 文件清单
| 文件 | 用途 | 主入口 |
|---|---|---|
| `wskey-update.py` | wskey → pt_key 转换，写青龙 env | `main()` |
| `psyduck-ipv6.py` | 探测 FRPS 穿透端口 IPv6，写代理配置 | `FrpsProxyUpdater.run()` |

---

## 一、wskey-update.py

### 配置（环境变量）
| 项 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `REMOTE_QL_URL` | ✅ | — | 远端青龙地址（同时是 FRPS 主机） |
| `REMOTE_QL_CLIENT_ID` | ✅ | — | 远端青龙 OpenAPI Client ID |
| `REMOTE_QL_CLIENT_SECRET` | ✅ | — | 远端青龙 OpenAPI Client Secret |
| `FRPS_API_PORT` | | `7500` | FRPS 面板端口 |
| `FRPS_API_AUTH` | | 空 | Basic 认证 `user:pass` |
| `FRPS_SOCKS5_NAME_PATTERN` | | `^psyduck\d{4}-socks5$` | SOCKS5 隧道匹配 |
| `REMOTE_SOCKS5_USER` | | `xiaoz` | SOCKS5 用户名 |
| `REMOTE_SOCKS5_PASS` | | `a1391959853` | SOCKS5 密码 |
| `XIEQU_UID` / `XIEQU_UKEY` | | 空 | 携趣白名单 |
| `BARK_SERVER` | | `https://api.day.app` | Bark 服务器 |
| `DEBUG_MODE` | | `False` | 请求日志全开 |

### 脚本内常量
| 项 | 值 | 说明 |
|---|---|---|
| `BARK_GROUP_MAP` | 硬编码 | Bark Token → 京东账号列表 |
| `MAX_ATTEMPTS` | `2` | 单次请求重试 |
| `RETRY_SLEEP` | `3` | 重试间隔（秒） |
| `REQUEST_TIMEOUT` | `10` | 单次 http 超时（秒） |
| `PROXY_TEST_TIMEOUT` | `5` | TCP 探测超时（秒） |

### 模块结构

**1. HTTP 层**（`http_request`）
- 统一走 `urllib.request` + PySocks
- `set_default_proxy` + patch `socket.socket`（`_SOCKS_LOCK` 串行化）
- `DEBUG_MODE` 开启时打印所有请求/响应

**2. 青龙操作**
- `get_remote_ql_token` — 远端 OpenAPI 换 token（缓存 600s 过期前）
- `fetch_remote_envs` — 拉远端 env
- `sync_remote_envs_to_local_silent` — 远端 → 本机补齐（静默）
- `subcookie` — 写本机 JD_COOKIE + enable

**3. 代理层**
- `fetch_proxies_from_frps` — 从 FRPS 拉 SOCKS5 隧道（300s 缓存）
- `test_proxy` — TCP 端口探活（2s 硬超时）
- `get_exit_ip` — 走代理查出口 IP
- `select_proxy_with_ip` — 挨个试到第一个 TCP 可达的

**4. 转换层**
- `get_sign` — JD 签名（`json.dumps` 默认参数、body 做 URL 编码）
- `getcookie_wskey` — genToken → appjmp → 校验 `app_open`
- `randomuserAgent` — 随机 iOS UA

**5. 通知层**
- `bark_send` — 按 token 推送
- `BARK_GROUP_MAP` 分组失败账号

### 执行流程
```
1. check_config_and_print()     配置检查，逐项 ✅/❌
2. check_and_add_xiequ_ip()     携趣白名单（如配置）
3. 读本机青龙 token（keyv.sqlite / auth.json）
4. sync_remote_envs_to_local_silent()   远端 → 本机补齐
5. 拉本机 JD_COOKIE / JD_WSCK
6. 清理 pin=**** 的无效记录
7. 逐个账号转换：
   ├─ 备注含"转换时间:"且距今 < 4h → 跳过
   ├─ select_proxy_with_ip() 选代理
   ├─ getcookie_wskey() 走完整转换
   ├─ 成功 → subcookie() 写回 + 更新备注
   └─ 失败 → 对比远端 wskey → 不一致则覆盖重试
      └─ 仍失败 → 禁用 env + 加 Bark 通知
8. 按 Bark 分组推送
9. 汇总：成功 X 跳过 Y 无代理 Z 失败 W 共 N 耗时 T
```

### 日志分级

**非 DEBUG**：配置检查 → `▓▓ 账号 ▓▓` + 结果行 → 汇总

**DEBUG**：额外打印所有 http 请求/响应、代理选择、genToken/appjmp 重试

### 写入格式（青龙 env）
| 字段 | 值 |
|---|---|
| `JD_COOKIE.value` | `pt_key=<new>;pt_pin=<encoded>;` |
| `JD_COOKIE.remarks` | `<原备注> - 转换时间:YYYY-MM-DD HH:MM:SS` |
| `JD_WSCK` | 不修改（仅失败时对比远端） |

### 关键不变量
1. **无可用代理拒绝服务**，绝不降级直连
2. **SOCKS5 账密必填**，否则代理不通
3. **失败才禁用 env**（无代理跳过不禁用）
4. **4h 节流**：备注含 `转换时间:` 且未满 4h 跳过
5. **远端对比重试**：本机失败且远端有不同 wskey 时，覆盖后重试一次

### 数据流
```
本机 JD_WSCK ──┐
               ├─► select_proxy ─► get_sign ─► genToken ─► appjmp
远端 env  ─────┘                                           │
                                                           ▼
                                               pt_key + pt_pin
                                                           │
                                                           ▼
                                            subcookie 写本机 JD_COOKIE
                                                           │
                                                           ▼
                                              失败 → Bark 通知
```

---

## 二、psyduck-ipv6.py

### 配置（环境变量）
| 项 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `REMOTE_QL_URL` | ✅ | — | 同时作为 FRPS 主机 |
| `FRPS_API_PORT` | | `7500` | FRPS 面板端口 |
| `FRPS_API_AUTH` | | 空 | Basic 认证 |
| `FRPS_HTTP_NAME_PATTERN` | | `^psyduck\d{4}$` | **无** `-socks5` 后缀 |

### 脚本内常量
| 项 | 值 | 说明 |
|---|---|---|
| `VERSION` | `20260915_v1` | 版本号 |
| `TOKEN_PORT_MAP` | 硬编码 | Bark Token → 端口列表 |
| `FAIL_THRESHOLD` | `2` | 连续失败通知阈值 |
| `FAIL_COUNT_FILE` | `/var/log/psyduck_frps_fail_count` | 失败计数 |
| `LOG_FILE` | `/var/log/psyduck-proxy-updater.log` | 日志 |
| `VERBOSE` | `False`（main 里） | DEBUG 开关 |

### 模块结构

**1. HTTP 层**（`http_get`）
- `urllib.request`，无代理
- `verify=False` 时跳过证书校验

**2. 节点解析**
- `_extract_port` — 兼容 v0.70+ 的 `spec.tcp.remotePort`
- `_extract_status` — 兼容 `status.phase` / `status` / `state`

**3. 核心类 `FrpsProxyUpdater`**
- `get_frps_ports` — 拉 FRPS 端口列表
- `get_ipv6_from_port` — 探 `/ipv6` 接口，重试 3 次
- `filter_public_ipv6` — 排除 fe80/fc/fd/2001:db8/2002 等
- `filter_ports_by_ipv6_segment` — 前三段去重
- `write_proxy_config` — 写 `proxy.ini`（端口打乱顺序）

**4. 通知**
- `notify_affected_tokens` — FRPS 连续失败时按 Token 通知
- 每个 Token 只发一条，含其负责的全部受影响端口

### 执行流程
```
1. 打印版本
2. get_frps_ports()
   ├─ 无端口 → frps配置: ❌ → 失败计数 +1
   │           达阈值 → Bark 通知 → 重置
   └─ 有端口 → frps配置: ✅
3. 逐端口 get_ipv6_from_port（重试 3 次）
4. filter_ports_by_ipv6_segment（前三段去重）
5. 写 proxy.ini（[jdRelay] 段）
6. 非 DEBUG 输出：[i/N] 端口 | 前三段 ✅/❌
```

### 日志分级

**非 DEBUG**：
```
psyduck-ipv6  版本: 20260915_v1
frps配置: ✅
[1/9] 3010 | 2409:8a55:d642  ✅
...
配置已更新，共 9 条代理
```

**DEBUG**：额外打印 FRPS 地址、探测过程、addresses 列表、去重原因、配置内容。

### 符号约定
| 符号 | 含义 |
|---|---|
| `✅` | 成功 |
| `❌ 获取ip失败` | 端口探测失败（无原因，DEBUG 下打） |
| `❌ 重复` | 前三段相同被去重 |
| `frps配置: ❌` | FRPS API 异常 / 无匹配端口 |

### 去重规则
**IPv6 前三段相同 → 同网段 → 只保留首个出现的端口。**

例：
- `2408:824c:9a20:xxx` 与 `2408:824c:9a24:xxx` → 前三段不同 → 都保留
- `2408:824c:9a20:aaa` 与 `2408:824c:9a20:bbb` → 前三段相同 → 后者被过滤

### 输出文件
| 文件 | 内容 |
|---|---|
| `qitoqito_psyduck/config/proxy.ini` | `[jdRelay]` 段，每行一个 URL |
| `/var/log/psyduck-proxy-updater.log` | 5MB × 3 备份 |
| `/var/log/psyduck_frps_fail_count` | 连续失败计数 |

### 关键不变量
1. **IPv6 前三段去重**，同网段只留一个端口
2. **端口顺序随机**，避免固定顺序造成负载不均
3. **配置无变化不写**（对比排序后的 URL 集合）
4. **FRPS 连续失败 2 次**才触发 Bark 通知

### 数据流
```
FRPS API ──► 端口列表 ──► 逐端口探 /ipv6 ──► 过滤公网 IPv6
                                                    │
                                                    ▼
                                            前三段去重
                                                    │
                                                    ▼
                                        写 proxy.ini（打乱顺序）
```

---

## 三、两者关系

| | wskey-update.py | psyduck-ipv6.py |
|---|---|---|
| **FRPS 隧道** | `^psyduck\d{4}-socks5$` | `^psyduck\d{4}$` |
| **访问方式** | SOCKS5 代理 | HTTP 直连 `/ipv6` |
| **输出** | 青龙 env | proxy.ini |
| **Bark 通知** | 账号转换失败 | FRPS 连续失败 |
| **依赖** | PySocks | 无 |
| **共享环境变量** | `REMOTE_QL_URL` / `FRPS_API_PORT` / `FRPS_API_AUTH` | 同 |

**两脚本独立运行，互不影响。**

---

## 四、常见故障

| 现象 | 排查 |
|---|---|
| `服务端: ❌` | `REMOTE_QL_URL` / `CLIENT_ID` / `SECRET` 是否正确 |
| `FRPS: ❌` | `FRPS_API_PORT` 是否开放；ufw 是否放行 |
| `无可用代理` | FRPS 无 `-socks5` 在线隧道；检查 frpc |
| 端口全部 `获取ip失败❌` | 探测主机 IPv6 不通 / 端口未监听 |
| 大量 `❌ 重复` | 多隧道指向同一设备网段（正常） |
| wskey 转换全失败 | SOCKS5 账密 / FRPS 端口段是否放行 |
| `配置文件为空` | 所有端口失败或被过滤 |