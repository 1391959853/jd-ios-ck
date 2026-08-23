# 🚀 Shadowrocket 配置

Shadowrocket 专用的京东 Cookie 捕获脚本

---

## ⚡ 快速部署

### Step 1. 添加模块

在 Shadowrocket 中导入：

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/shadowrocket/jd.sgmodule
```

### Step 2. 信任证书

设置 → 通用 → 证书信任设置 → 信任

### Step 3. 开启 MitM

域名：`api.m.jd.com`, `sh.jd.com`

---

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `jdcookie.js` | 核心脚本 |
| `jd.sgmodule` | Shadowrocket 模块 |

---

## 🔧 配置修改

编辑 `jdcookie.js` 修改 API 地址：

```javascript
const API_URL = "http://你的服务器：9090/jd/raw_ck";
```

---

**返回**: [主目录](../README.md)
