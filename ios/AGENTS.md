# ios/ — iOS 端抓包脚本架构说明

> 本文件是 `ios/` 目录下所有脚本与配置文件的结构化摘要。Agent 读此文件即可理解全貌，无需通读源码。

## 元信息
- 语言：JavaScript（iOS 代理工具脚本引擎）
- 运行环境：Quantumult X / Surge / Loon（三选一）
- 用途：拦截京东 App 请求 → 提取 Cookie 字段 → 配对 → 提交到服务端 API
- 服务端：`http://<你的服务器>:9090/jd/raw_ck`（配套 `api/` 目录的 Flask 服务）

## 文件清单

| 文件 | 类型 | 主要作用 |
|---|---|---|
| `JDcookie.js` | JS 脚本 | 抓包、提取字段、队列配对、提交 API |
| `JDcookie2qx.conf` | QX 重写 | QX 导入入口，引用 `JDcookie.js` |
| `JDcookie2api.sgmodule` | Surge 模块 | Surge 导入入口，引用 `JDcookie.js` |
| `JDcookie2loon.conf` | Loon 规则 | Loon 导入入口，引用 `JDcookie.js` |
| `README.md` | 文档 | 部署步骤、配置修改、故障排查 |
| `京东京豆显示美化+优化.scriptable` | Scriptable | 桌面小组件，显示京豆余额与变动 |

---

## 一、JDcookie.js（核心）

### 功能
拦截京东 App 的两类请求：
1. **`sh.jd.com`** → 提取 `wskey` + `pin_hash`
2. **`api.m.jd.com` 的 `wareBusiness` / `serverConfig` / `basicConfig`** → 提取 `pt_pin` + `pt_key`

然后按 `pin_hash ↔ pt_pin` 映射配对，组合完整 Cookie 后 POST 到服务端 API。

### 配置（脚本第 5 行）
```javascript
const API_URL = "http://你的服务器:9090/jd/raw_ck";
```
**用户必须修改此项**，指向自己部署的服务端（对应 `api/` 目录的 Flask 服务）。

### 触发条件
| 路径 | Host | 条件 |
|---|---|---|
| A（wskey） | `sh.jd.com` | Cookie 含 `wskey=` |
| B（pt_key） | `api.m.jd.com/client.action?functionId=(wareBusiness\|serverConfig\|basicConfig)` | Cookie 含 `pt_pin=` 和 `pt_key=` |
| 其他 | — | 跳过，`$done({})` |

### 从 Cookie 提取的 4 个字段
```javascript
pt_pin    = decodeURIComponent(...)   // 解码态
pt_key    = ...                        // 原始
wskey     = ...                        // 原始
pin_hash  = ...                        // 原始
```

### 本地状态（`$prefs`）

| Key | 内容 | 说明 |
|---|---|---|
| `JD_PinMap` | `{ pin_hash: { pt_pin, verified } }` | 哈希 ↔ 账号映射 |
| `JD_Wskey_Queue` | `[{ wskey, pin_hash, timestamp }]` | wskey 队列（10 秒过期） |
| `JD_PtKey_Queue` | `[{ pt_pin, pt_key, timestamp }]` | pt_key 队列（10 秒过期） |
| `JD_Processed_Records` | `{ key: { timestamp, requestTime } }` | 去重记录（10 秒窗口，最多 20 条） |

### 核心流程

```
请求拦截
    │
    ▼
提取 pt_pin / pt_key / wskey / pin_hash
    │
    ├─ sh.jd.com + wskey → 入 JD_Wskey_Queue
    └─ api.m.jd.com + pin+key → 入 JD_PtKey_Queue
    │
    ▼
tryMatch()  队首配对
    │
    ├─ pin_hash + pt_pin 匹配（verified 优先）
    ├─ 时间差 ≤ 10s
    └─ 配对成功
    │
    ▼
combineAndSubmit()  组合 Cookie
    │
    ▼
POST API_URL
    body: { pt_key, pt_pin(encodeURIComponent), wskey, cookie, pin_hash }
    │
    ▼
响应处理
    ├─ data.startsWith("校验失败，京东账号: ")
    │   → removeBindingIfUnverified(failedPin, pin_hash)
    │   → 撤销本地未验证绑定
    │
    ├─ 其他响应
    │   → markMappingVerified(pin_hash)
    │   → data.includes("ok") ? 成功通知 : 失败通知
```

### 响应契约（客户端依赖，服务端必须遵守）
| 场景 | Body 格式 | 客户端行为 |
|---|---|---|
| 成功 | `ok\n账号：...\n时间：...\nIP：...` | `includes("ok")` → 成功通知 |
| 失败 | `校验失败，京东账号: <pt_pin>` | `startsWith` → 撤销本地未验证绑定 |
| HTTP 码 | 恒为 **200**（跨平台兼容） | 非 2xx 在 Surge/Loon/QX 回调不一致 |

### 超时与重试
- `timeout: 30000`（30 秒）
- 网络失败重试 1 次，间隔 2 秒

### 通知
```javascript
$notify("京东Cookie获取成功", `账号: ${pt_pin}`, "已成功获取并提交Cookie和wskey");
$notify("API提交成功", `账号: ${pt_pin}`, data);
$notify("API提交失败", `账号: ${pt_pin}`, data);
```

### 关键不变量
1. **`pin_hash` 不提交给服务端** —— 仅本地映射用
2. **`pt_pin` 提交前 `encodeURIComponent`** —— 服务端会 `unquote` 还原
3. **10 秒配对窗口** —— 队列时间差超过 10 秒不配对
4. **已 `verified` 的绑定不删除** —— 即使服务端返回"校验失败"
5. **同一 `(pt_pin, pt_key, wskey)` 组合 10 秒内不重复提交**

---

## 二、平台导入配置

### JDcookie2qx.conf（Quantumult X）

**导入方式**：QX → 重写 → 添加远程重写，URL 指向该文件。

**内容结构**：
```ini
[rewrite_local]
^https?:\/\/sh\.jd\.com\/ url script-request-header https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js
^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig) url script-request-header https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js

[mitm]
hostname = api.m.jd.com, sh.jd.com
```

### JDcookie2api.sgmodule（Surge）

**导入方式**：Surge → 模块 → 安装新模块，URL 指向该文件。

**内容结构**：
```ini
[Script]
JD Cookie = type=http-request,pattern=^https?:\/\/sh\.jd\.com\/,requires-body=0,script-path=https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js
JD Cookie 2 = type=http-request,pattern=^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig),requires-body=0,script-path=https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js

[MITM]
hostname = api.m.jd.com, sh.jd.com
```

### JDcookie2loon.conf（Loon）

**导入方式**：Loon → 配置 → 远程脚本，URL 指向该文件。

**内容结构**：
```ini
[Remote Script]
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js, tag=京东Cookie, enabled=true

[Rewrite]
^https?:\/\/sh\.jd\.com\/ url script-request-header 京东Cookie
^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig) url script-request-header 京东Cookie

[MITM]
hostname = api.m.jd.com, sh.jd.com
```

### 三平台共用的 MitM 域名
```
api.m.jd.com, sh.jd.com
```
**必须开启证书信任**（iOS 设置 → 通用 → 关于本机 → 证书信任设置）。

---

## 三、京东京豆显示美化+优化.scriptable

### 功能
iOS 桌面 Scriptable 小组件，显示京东账号的京豆余额与近期变动。

### 运行环境
Scriptable（iOS App Store 免费）

### 使用方式
1. 安装 Scriptable
2. 新建脚本，粘贴 `.scriptable` 文件内容
3. 回到桌面，添加 Scriptable 小组件，选择该脚本

### 依赖
- 京东账号 Cookie（需先通过 `JDcookie.js` 流程获取并存入青龙）
- 可能通过青龙 OpenAPI 读取 `JD_COOKIE` 环境变量

---

## 四、README.md（部署说明）

### QX 部署步骤

| Step | 内容 |
|---|---|
| 1 | 添加重写：`https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2qx.conf` |
| 2 | 添加脚本：`https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js` |
| 3 | MitM 配置：`api.m.jd.com, sh.jd.com` |
| 4 | 信任证书：设置 → 通用 → 证书信任设置 |

### Surge / Loon 部署
分别导入 `.sgmodule` / `.conf` 文件即可。

### 配置修改
**必须编辑 `JDcookie.js` 第 5 行**，把 `API_URL` 改为自己的服务端地址。

### 故障排查
| 问题 | 解决 |
|---|---|
| 配对失败 | 清空 `$prefs.valueForKey("JD_PinMap")` |
| API 失败 | 检查服务端（`api/` 的 Flask）是否运行 |
| 无响应 | 确认证书已信任 |

---

## 五、与其他目录关系

| 目录 | 关系 |
|---|---|
| `api/` | **本目录脚本提交的目标服务端**，Flask 接收 `POST /jd/raw_ck` |
| `ql/` | 青龙面板脚本，**不直接依赖本目录**；但 `wskey-update.py` 同样处理京东 Cookie |
| `psyduck/` | 部署 FRP 穿透 + SOCKS5，**不直接依赖本目录** |

**完整链路**：
```
iOS 京东 App
    │  (sh.jd.com / api.m.jd.com)
    ▼
Quantumult X / Surge / Loon
    │  拦截 → JDcookie.js 提取字段
    ▼
POST http://<server>:9090/jd/raw_ck
    │
    ▼
api/ 的 Flask 服务
    │  genToken + appjmp → 换 pt_key → 写青龙
    ▼
青龙面板 JD_COOKIE / JD_WSCK
```

---

## 六、常见故障

| 现象 | 排查 |
|---|---|
| 脚本不执行 | MitM 未开 / 证书未信任 / 重写规则未启用 |
| `配对失败` | 队列时间差 > 10s；清空 `JD_PinMap` 重试 |
| `API 失败` | 服务端未启动；`API_URL` 配置错误；服务器防火墙 |
| 反复 `校验失败` | 本地绑定已 `verified`，需清空 `JD_PinMap` 重新配对 |
| 通知一直不出现 | 检查 `$notify` 是否被系统静音；QX/Surge 通知权限 |
| Scriptable 小组件空白 | 检查脚本是否通过青龙 OpenAPI 读到 `JD_COOKIE` |
| 三平台行为不一致 | 非 2xx 响应在 Surge/Loon/QX 的回调路径不同；服务端应恒返回 200 |