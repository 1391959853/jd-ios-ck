# 📱 jd-ios-ck

> iOS 京东 Cookie 自动化 - 自动捕获 + 青龙转换 + FRP 部署

<p align="center">
  <img src="https://img.shields.io/badge/platform-iOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/panel-QingLong-green" alt="QingLong">
  <img src="https://img.shields.io/badge/frp-psyduck-orange" alt="FRP">
</p>

---

## ⚡ 3 分钟部署

### iOS 端（Quantumult X）⭐

```ini
# 重写
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2qx.conf

# 脚本
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js

# MitM 域名
api.m.jd.com, sh.jd.com
```

### 青龙端

```bash
# 脚本
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ql/wskey-update.py

# 定时任务
0 */4 * * *
```

### FRP 部署（可选）🦆

```bash
# 首次部署
curl -fsSL https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/psyduck/frp-psyduck.sh | bash

# 强制重建
curl -fsSL .../frp-psyduck.sh | bash -s -- --debug
```

### 服务端 API（可选）

```bash
cd api && docker-compose up -d
```

---

## 📁 完整目录

| 模块 | 说明 | 文档 |
|:----:|------|:----:|
| 📱 **ios/** | iOS 端脚本（Qx/Surge/Loon） | [查看 →](./ios/README.md) |
| 🐉 **ql/** | 青龙转换脚本 | [查看 →](./ql/README.md) |
| 🔧 **api/** | 服务端 API | [查看 →](./api/README.md) |
| 🦆 **psyduck/** | FRP 一键部署 | [查看 →](./psyduck/README.md) |
| 🚀 **shadowrocket/** | Shadowrocket 配置 | [查看 →](./shadowrocket/README.md) |

---

## 🔗 快速链接

- [📱 iOS 部署](./ios/README.md) - Quantumult X / Surge / Loon
- [🐉 青龙脚本](./ql/README.md) - wskey 转换配置
- [🔧 服务端 API](./api/README.md) - Flask 部署
- [🦆 FRP 部署](./psyduck/README.md) - 可达鸭一键部署
- [❓ 故障排查](./ios/README.md#故障排查)

---

## ⚠️ 注意

- 冷却时间：**4 小时**
- wskey 有效期：**30~90 天**
- 使用代理池避免风控
- FRP 部署会保留 SSH 容器

---

**完整文档**: [查看各模块说明 ↑](#-完整目录)
