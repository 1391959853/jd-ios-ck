# JD Cookie API 服务端 — 架构说明

> 本文件是 `app.py` 的结构化摘要。Agent 读此文件即可理解全貌，无需通读源码。

## 元信息
- 语言：Python 3.11 / Flask
- 依赖：`flask`、`PySocks`
- 部署：Docker + `network_mode: host`，监听 `0.0.0.0:9090`
- 入口：`POST /jd/raw_ck`，健康检查：`GET /health`

## 配置（硬编码于顶部）
| 项 | 值 |
|---|---|
| 青龙 | `http://127.0.0.1:5700` |
| FRPS | `http://127.0.0.1:7500/api/proxy/tcp` |
| FRPS 隧道名正则 | `^psyduck\d{4}-socks5$` |
| SOCKS5 账密 | `xiaoz` / `a1391959853` |
| 超时 | request=8s, test=3s |
| 重试 | 2 次，间隔 1s |
| 缓存文件 | `/app/data/success_cache.json` |

## 模块结构

### 1. 缓存层（`_CACHE_LOCK` 保护）
- 文件格式：`{ "pt_pin": "pin_hash" }`
- `cache_lookup(pt_pin, pin_hash) → bool`：文件[pt_pin] == pin_hash
- `cache_store(pt_pin, pin_hash)`：内容相同不写；空值不写；原子写（tmp + rename）
- 无过期时间，同 key 覆盖

### 2. 代理层（`_SOCK_LOCK` 保护 socket patch）
- `_urlopen_via_socks5(req, host, port, timeout, follow_redirect)`：
  patch `socket.socket = socks.socksocket`，SOCKS5 + 账密
- `fetch_proxies_from_frps() → [url]`：
  过滤 `status==online` + 名字正则 + `conf.remotePort` 存在
  单节点异常隔离（try/except 包住循环体）
- `test_proxy(url) → bool`：只测 `https://jd.com` 返回 200
- `get_next_available_proxy() → (url, host, port)`：
  打乱列表逐个测；无可用 → 返回 `(None, None, None)`

### 3. 青龙 API（`class QingLongAPI`）
- `_login()`：`GET /open/auth/token?client_id=&client_secret=` → Bearer token
- `_request(method, endpoint, params, json_body)`：统一带 Authorization
- `search_env_by_pin(pt_pin, name_prefix)`：按 pt_pin 匹配 env
- `add_env / update_env / enable_env`

### 4. 签名与转换
- `randomuserAgent()` → 随机 iOS UA（存线程本地 `_ua_local`）
- `sign_core(inarg)` → 魔改 MD5 核心
- `get_ep()` / `base64Encode()` / `randomeid()` → 参数构造
- `get_sign(functionId, body)`：
  - `all_arg` 用**原始** body 算签名
  - 拼 URL 时 `urllib.parse.quote(body, safe='')`（关键：urllib 必须手动编码）
- `getcookie_wskey(key)`：
  1. 拉代理（无 → `return "Error"`，**绝不直连**）
  2. `genToken` → 取 `tokenKey`
  3. `appjmp` → 302 `Set-Cookie` 取 `pt_key` / `pt_pin`
  4. 校验 `pt_key` 含 `app_open`
  5. 返回 `"pt_key=...;pt_pin=...;"` 或 `"Error"`

### 5. 路由 `POST /jd/raw_ck`
```
1. 解析 JSON → 4 字段：pt_key / pt_pin / wskey / pin_hash
2. 任一为空 → 返回 "校验失败，京东账号: {pt_pin}"
3. cache_lookup(pt_pin, pin_hash)?
   ├─ 命中：
   │    跳过 JD 转换
   │    用客户端 pt_key/wskey 写青龙（JD_COOKIE + JD_WSCK）
   │    返回成功
   └─ 未命中：
        getcookie_wskey → 校验返回的 pt_pin
        → 写青龙 → cache_store
        → 返回成功
```

## 响应契约（客户端依赖，不可改）
| 场景 | HTTP | Body |
|---|---|---|
| 成功 | **200** | `ok\n账号：...\n时间：...\nIP：...` |
| 失败 | **200** | `校验失败，京东账号: {pt_pin}` |
| 客户端判据 | — | `body.includes("ok")` / `body.startsWith("校验失败，京东账号: ")` |

## 关键不变量
1. **HTTP 状态码恒为 200**（客户端跨平台兼容）
2. **外网只走 SOCKS5**；青龙/FRPS 走 127.0.0.1 直连
3. **无可用代理拒绝服务**，绝不降级直连 JD
4. **命中缓存仍写青龙**（用客户端 pt_key）
5. **缓存文件只存 `pt_pin → pin_hash`**，不存 pt_key
6. **四字段必填**，任一为空即返回失败

## 数据流
```
客户端 POST {pt_key, pt_pin, wskey, pin_hash}
  → 四字段校验
  → cache_lookup
      ├─ 命中 → 写青龙 → ok
      └─ 未命中 → SOCKS5 → genToken → appjmp → pt_key
                → 写青龙 → cache_store → ok
```

## 客户端改动（对端契约）
`submitToAPI` body 新增 `pin_hash` 字段，其余不动。

## 常见故障点
| 现象 | 排查 |
|---|---|
| `所有 FRPS 代理均不可用` | FRPS 无在线隧道 / 账密错 / 端口错 |
| `获取 token 失败: URL can't contain control characters` | `get_sign` 里 body 未 quote |
| `校验失败` 但日志无"命中/未命中" | 四字段缺一（尤其 pin_hash） |
| 一直未命中 | 客户端 pin_hash 每次都变（检查 `markMappingVerified`） |
| `青龙登录异常` | 凭据错 / 青龙未启动 |