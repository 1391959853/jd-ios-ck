# 📦 jd-ios-ck

> **iOS 代理工具及青龙面板的京东辅助脚本合集**

<p align="center">
  <img src="https://img.shields.io/badge/platform-iOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/panel-QingLong-green" alt="QingLong">
  <img src="https://img.shields.io/badge/language-Python-orange" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-red" alt="License">
</p>

基于 [**可达鸭**](https://github.com/qitoqito/psyduck) 仓库改造，提供 iOS 端京东 Cookie 自动化捕获及青龙面板定时转换工具。

---

## 📑 分支说明

| 分支 | 用途 | 核心文件 |
|:----:|------|:--------:|
| `main` | Quantumult X 去广告规则 | `qx.conf` |
| `X` | 京东 Cookie 自动化脚本 | `JDcookie.js` / `wskey-update.py` |

---

## 🚀 X 分支 — 京东 Cookie 自动化

### 📁 文件清单

| 文件 | 描述 |
|------|------|
| [`JDcookie.js`](https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/JD/JDcookie.js) | 拦截京东 App 的 `wskey` 和 `pt_key` 请求，配对后提交到 API |
| [`JDcookie2api.sgmodule`](https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/JD/JDcookie2api.sgmodule) | Surge 模块封装（含持久化映射表） |
| [`wskey-update.py`](https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/JD/wskey-update.py) | 青龙 Python 脚本，从 FRPS 拉取 SOCKS5 代理并转换 Cookie |

---

### ⚙️ 功能说明

#### 📱 iOS 端

```
┌─────────────────────────────────────────────────────────┐
│  自动捕获京东 App 请求                                    │
│  ├─> 10 秒时间窗口配对 pin_hash 与 pt_pin               │
│  ├─> 映射表持久化存储                                    │
│  └─> 提交到自定义 API（默认：http://1.sggg3326.top:9090/jd/raw_ck）│
└─────────────────────────────────────────────────────────┘
```

**支持代理工具：** Surge / Quantumult X / Loon

#### 🐉 青龙面板端

| 功能 | 说明 |
|------|------|
| 🔄 动态代理 | 从 FRPS 拉取 SOCKS5 代理 |
| 👥 多账号支持 | 批量转换多个京东账号 |
| 🔓 URL 解码 | 自动解码 URL 编码的 `pt_pin` |
| ⏱️ 冷却机制 | 内置 **4 小时** 冷却，避免频繁操作 |
| 📝 自动备注 | 替换为 `京东账号：{pt_pin} - 转换时间:xxxx` |
| ✔️ 携趣白名单 | 支持携趣代理白名单 |
| 📢 失败通知 | 失败禁用并发送 Bark 通知 |

---

### 📥 部署步骤

#### 方法一：iOS（Surge）

```
Step 1. 安装模块
  └─> https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/JD/JDcookie2api.sgmodule

Step 2. 信任证书

Step 3. 打开京东 App，自动捕获
```

#### 方法二：青龙面板

**Step 1.** 创建脚本任务

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/JD/wskey-update.py
```

**Step 2.** 设置定时任务（推荐 **4~6 小时**）

**Step 3.** 配置环境变量

| 变量名 | 必填 | 说明 |
|--------|:----:|------|
| `FRPS_API_URL` | ✅ | FRPS 接口地址 |
| `FRPS_API_AUTH` | ✅ | FRPS 认证信息 |
| `XIEQU_UID` | ✅ | 携趣 UID |
| `XIEQU_UKEY` | ✅ | 携趣 UKEY |
| `BARK_SERVER` | ❌ | Bark 通知服务器 |
| `DEBUG_MODE` | ❌ | 调试模式（true/false） |

---

### ⚠️ 注意事项

> 💡 **代理回退**：代理不可用时会自动回退直连，可能触发风控。

> 💡 **wskey 有效期**：`wskey` 有效期约 **30~90 天**，过期需重新获取。

> 💡 **备注覆盖**：转换成功后，**原备注将被完全替换**，请提前备份。

---

### 📜 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026.07.28 | 修复 URL 编码匹配，新增 4 小时冷却，替换备注格式 |
| 2026.06.23 | 优化青龙转换脚本，增加 SOCKS5 代理动态获取 |
| 2026.06.22 | 优化 JDcookie.js 配对逻辑，增强 pin_hash 映射 |
| 2026.03.17 | 首次公开 wskey-update.py |

---

## ⚠️ 免责声明

本项目仅供学习研究使用，请勿用于商业用途。**使用风险自负**。

---

## 🙏 致谢

| 项目/作者 | 链接 |
|----------|------|
| 可达鸭（原仓库） | [https://github.com/qitoqito/psyduck](https://github.com/qitoqito/psyduck) |
| ShellCrash | [https://github.com/juewuy/ShellCrash](https://github.com/juewuy/ShellCrash) |
| FRPS 社区 | — |

---

## 🔗 相关链接

| 分支 | 地址 |
|------|------|
| main 分支 | [https://github.com/1391959853/jd-ios-ck/tree/main](https://github.com/1391959853/jd-ios-ck/tree/main) |
| X 分支 | [https://github.com/1391959853/jd-ios-ck/tree/X](https://github.com/1391959853/jd-ios-ck/tree/X) |

---

<p align="center">
  <em>⭐ 如果本项目对您有帮助，欢迎 Star 支持！</em>
</p>
