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

本项目包含三个核心部分：

| 组件 | 用途 | 快速入口 |
|:----:|------|:--------:|
| 📱 **iOS 端** | 通过 Qx/Surge 捕获京东 Cookie | [查看部署说明（含 Qx 配置） →](./ios/README.md) |
| 🐉 **青龙端** | 定时转换 wskey 为 pt_key | [查看青龙脚本说明 →](./ql/README.md) |
| 🔧 **服务端** | Flask API 接收并同步 Cookie | [查看 API 部署说明 →](./api/README.md) |

---

## 📁 项目结构

```
jd-ios-ck/
├── ios/                   # iOS 端脚本和模块（⭐ 含 Qx 配置）
│   ├── JDcookie.js              # iOS 代理工具脚本
│   ├── JDcookie2api.sgmodule    # Surge 模块
│   ├── JDcookie2qx.conf         # Quantumult X 重写配置
│   └── README.md                # iOS 端详细说明
├── ql/                    # 青龙面板脚本
│   ├── wskey-update.py          # wskey 转换脚本
│   ├── psyduck-ipv6.py          # IPv6 支持脚本
│   └── README.md                # 青龙脚本说明
├── api/                   # 服务端 API（可选）
│   ├── app.py                   # Flask API 服务器
│   ├── Dockerfile               # Docker 部署
│   └── README.md                # API 部署说明
├── README.md              # 本文件（项目总览）
└── .gitignore
```

---

## 🎯 核心功能

- ✅ **自动捕获** - iOS 打开京东 App 时自动获取 Cookie
- ✅ **智能配对** - 基于时间窗口和 pin_hash 映射自动配对
- ✅ **青龙同步** - 自动提交到青龙面板环境变量
- ✅ **代理池** - 动态从 FRPS 获取 SOCKS5 代理
- ✅ **智能通知** - Bark 推送，仅失败时通知

---

## ⚡ 3 分钟快速部署

### 方式 1: Quantumult X（推荐）⭐

> 💡 **提示**: Quantumult X 用户请优先使用此方式

#### Step 1. 添加重写

打开 Quantumult X → 配置 → 重写 → 添加远程重写：

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2qx.conf
```

#### Step 2. 添加脚本

配置 → 脚本库 → 添加远程脚本：

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js
```

#### Step 3. 配置 MitM

设置 → 通用 → MitM → 启用 → 域名：
```
api.m.jd.com
sh.jd.com
```

#### Step 4. 信任证书

设置 → 通用 → 关于本机 → 证书信任设置 → 信任证书

#### Step 5. 测试

打开京东 App → 查看 Quantumult X 日志输出

---

### 方式 2: Surge

#### 安装模块

在 Surge 中打开：
```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2api.sgmodule
```

然后信任证书 → 开启 MitM → 打开京东 App

---

### 方式 3: 青龙面板配置

#### Step 1. 添加脚本

青龙面板 → 脚本管理 → 新建脚本 → 复制 `wskey-update.py`

#### Step 2. 配置环境变量

| 变量名 | 必填 | 说明 |
|--------|:----:|------|
| `FRPS_API_URL` | ✅ | FRPS 代理接口地址 |
| `FRPS_API_AUTH` | ✅ | FRPS 认证（username:password） |
| `XIEQU_UID` | ✅ | 携趣 UID |
| `XIEQU_UKEY` | ✅ | 携趣 UKey |
| `BARK_SERVER` | ❌ | Bark 服务器地址 |

#### Step 3. 设置定时任务

推荐每 **4~6 小时** 运行一次：
```crontab
0 */4 * * *
```

---

## 📖 详细文档

| 文档 | 说明 |
|------|------|
| [📱 iOS 端部署指南](./ios/README.md) | **Quantumult X**/Surge/Loon 配置详解 |
| [🐉 青龙脚本说明](./ql/README.md) | `wskey-update.py` 配置与定时任务 |
| [🔧 服务端 API 部署](./api/README.md) | Flask API 服务器部署（可选） |
| [❓ 常见问题](./ios/README.md#故障排查) | 故障排查与解决方案 |

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
| 青龙面板 | https://github.com/whyour/qinglong |

---

## 📜 许可证

MIT License

---

<p align="center">
  <em>⭐ 如果本项目对您有帮助，欢迎 Star 支持！</em>
</p>

**最后更新**: 2026 年 8 月 14 日
