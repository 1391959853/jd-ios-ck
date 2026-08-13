# 📱 jd-ios-ck

> **iOS 京东 Cookie 自动化解决方案** - 基于 iOS 代理工具的京东 Cookie 捕获与青龙面板自动转换系统

<p align="center">
  <img src="https://img.shields.io/badge/platform-iOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/panel-QingLong-green" alt="QingLong">
  <img src="https://img.shields.io/badge/language-Python-orange" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-red" alt="License">
</p>

---

## 🚀 快速开始

本项目包含两个核心部分：

| 组件 | 用途 | 快速入口 |
|:----:|------|:--------:|
| 📱 **iOS 端** | 通过 Surge/Quantumult X 捕获京东 Cookie | [查看 iOS 部署说明 →](./JD/README.md) |
| 🐉 **青龙端** | 定时转换 wskey 为 pt_key | [查看青龙脚本说明 →](./JD/README.md#青龙脚本) |
| 🔧 **服务端** | Flask API 接收并同步 Cookie 到青龙 | [查看 API 部署说明 →](./api/README.md) |

---

## 📁 目录结构

```
jd-ios-ck/
├── JD/                  # iOS 脚本和青龙脚本
│   ├── JDcookie.js              # iOS 代理工具脚本
│   ├── JDcookie2api.sgmodule    # Surge 模块
│   ├── wskey-update.py          # 青龙面板 Python 脚本
│   └── README.md                # iOS 端详细说明
├── api/                 # 服务端 API（可选）
│   ├── app.py                   # Flask API 服务器
│   ├── Dockerfile               # Docker 部署
│   └── README.md                # API 部署说明
└── README.md            # 本文件（项目总览）
```

---

## 🎯 核心功能

- ✅ **自动捕获** - iOS 打开京东 App 时自动获取 Cookie
- ✅ **智能配对** - 基于时间窗口和 pin_hash 映射自动配对 wskey 和 pt_key
- ✅ **青龙同步** - 自动提交到青龙面板环境变量
- ✅ **代理池** - 动态从 FRPS 获取 SOCKS5 代理
- ✅ **智能通知** - Bark 推送，仅失败时通知

---

## 📖 详细文档

| 文档 | 说明 |
|------|------|
| [📱 iOS 端部署指南](./JD/README.md) | Surge/Quantumult X 配置、JS 脚本说明 |
| [🐉 青龙脚本说明](./JD/README.md#青龙脚本) | wskey-update.py 配置与定时任务 |
| [🔧 服务端 API 部署](./api/README.md) | Flask API 服务器部署（可选） |
| [❓ 常见问题](./JD/README.md#故障排查) | 故障排查与解决方案 |

---

## ⚡ 3 分钟快速部署

#### Step 1: iOS 端配置

1. 在 Surge 中安装模块：
   ```
   https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/JD/JDcookie2api.sgmodule
   ```
2. 开启 MitM 并信任证书
3. 打开京东 App → 自动捕获 Cookie

#### Step 2: 青龙面板配置

1. 添加脚本：`wskey-update.py`
2. 配置环境变量：`FRPS_API_URL`、`XIEQU_UID`、`XIEQU_UKEY`
3. 设置定时任务：`0 */4 * * *`（每 4 小时）

#### Step 3: 服务端部署（可选）

如需自建 API：
```bash
cd api && docker-compose up -d
```

> **详细说明请查看各模块文档**

---

## ⚠️ 注意事项

1. **冷却时间** - 同一账号 4 小时内不重复转换
2. **wskey 有效期** - 约 30~90 天，过期需重新捕获
3. **代理使用** - 建议使用代理池避免京东风控
4. **隐私保护** - 不要泄露 FRPS 认证和携趣 UKey

---

## 🔗 相关链接

| 项目 | 地址 |
|------|------|
| GitHub 仓库 | https://github.com/1391959853/jd-ios-ck |
| 原项目（可达鸭） | https://github.com/qitoqito/psyduck |
|青龙面板 | https://github.com/whyour/qinglong |

---

## 📜 许可证

MIT License

---

<p align="center">
  <em>⭐ 如果本项目对您有帮助，欢迎 Star 支持！</em>
</p>

**最后更新**: 2026 年 8 月 14 日
