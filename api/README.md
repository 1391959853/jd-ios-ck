# JD Cookie API

## 功能
接收客户端提交的 `pt_key` / `pt_pin` / `wskey` / `pin_hash`，按
`pt_pin + pin_hash` 命中缓存则跳过 JD 转换，否则走 `genToken + appjmp`
换 `pt_key`。两条路都会写青龙（`JD_COOKIE` + `JD_WSCK`）。

## 接口
### `GET /health`
返回：`{"status":"ok","qinglong_connected":true}`

### `POST /jd/raw_ck`
请求体（JSON）：
```json
{
  "pt_key":   "app_openAAJ...",
  "pt_pin":   "jd_xxx",
  "wskey":    "AAJ...",
  "pin_hash": "1987555117",
  "cookie":   "pt_key=...;pt_pin=...;"      // 可选，服务端不用
}
```

**成功响应**（HTTP 200，纯文本）：
```
ok
账号：jd_xxx
时间：2026-09-15 20:28:27
IP：1.2.3.4
```

**失败响应**（HTTP 200，纯文本）：
```
校验失败，京东账号: jd_xxx
```

客户端判据：`body.includes("ok")` / `body.startsWith("校验失败，京东账号: ")`

## 部署
```bash
mkdir -p data
docker-compose up -d --build
docker-compose logs -f
```

## 配置
配置**硬编码**在 `app.py` 顶部，不使用环境变量。

## 网络
- 容器使用 `network_mode: host`
- 青龙：`http://127.0.0.1:5700`
- FRPS：`http://127.0.0.1:7500/api/proxy/tcp`
- 监听：`0.0.0.0:9090`

## 缓存
- 文件：`./data/success_cache.json`
- 格式：`{ "pt_pin": "pin_hash" }`
- 命中条件：`pt_pin` 存在且 `pin_hash` 相同
- 无过期时间，同 key 覆盖

架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)