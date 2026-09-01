# Quantumult X 规则同步仓库

欢迎使用本规则仓库！本项目致力于收集和整理高质量的 Quantumult X 规则，帮助用户获得更好的网络体验。

> 🤝 **欢迎贡献！** 如果您有好的规则建议或发现现有规则有问题，欢迎通过 [Issue](https://github.com/1391959853/jd-ios-ck/issues) 或 [Pull Request](https://github.com/1391959853/jd-ios-ck/pulls) 参与贡献！

---

## 📖 项目说明

本仓库通过 GitHub Actions **自动同步** 自上游仓库 [zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX)，每天定时更新以下三个目录的规则文件：

| 目录 | 用途 |
|------|------|
| `qx/rewrite/` | 重写规则（Rewrite），用于 URL 重写、请求修改等 |
| `qx/rules/` | 分流规则（Rules），用于域名/IP 分流判断 |
| `qx/snippet/` | 代码片段（Snippet），可被其他文件引用复用 |

### ✅ 规则质量声明

> 本人已对规则进行**大量测试**，尤其是针对 **番茄小说（FanQieNovel）** 的规则已验证有效。您可放心使用，如遇问题欢迎反馈！

---


## 📑 分支说明

本仓库包含两个分支，用途和核心文件如下：

| 分支 | 用途 | 核心文件 |
|------|------|----------|
| `main` | Quantumult X 去广告规则自动同步 | `qx.conf` |
| `X` | 京东 Cookie 自动化脚本 | `JDcookie.js` / `wskey-update.py` |

> 💡 **提示**：
> - `main` 分支为当前分支，用于自动同步上游 QX 规则，并生成 `/qx/` 目录下的规则文件。
> - `X` 分支为京东 Cookie 维护脚本，如需使用请切换到该分支查看。

---
## 📁 目录结构
```
qx/
├── rewrite/          # 重写规则目录
│   ├── FanFiction.txt
│   ├── JD.txt
│   └── ...
├── rules/            # 分流规则目录
│   ├── FanFiction.list
│   ├── JD.list
│   └── ...
└── snippet/          # 代码片段目录
    ├── common.snippet
    └── ...
```

---

## 🚀 使用方法

### 方式一：本地导入

1. 进入 Quantumult X → 配置文件 → 编辑配置
2. 复制对应规则文件内容，粘贴到您的配置中
3. 保存并重启 Quantumult X

### 方式二：远程引用

在 Quantumult X 配置文件中添加远程规则引用：

```plaintext
[rewrite_remote]
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/qx/rewrite/JD.txt, tag=JD 重写, update-interval=86400, opt-parser=false, enabled=true

[ruleset]
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/qx/rules/JD.list, tag=JD 分流, update-interval=86400, enabled=true
```

> 💡 将 `JD` 替换为您需要的规则文件名即可。

### 方式三：Snippet 引用

通过 `include` 指令引用 `.snippet` 文件：

```plaintext
[snippet]
include = https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/qx/snippet/common.snippet
```

---

## 🤝 如何贡献

### 提交 Issue

如果您发现规则问题或有新规则建议：

1. 访问 [Issues](https://github.com/1391959853/jd-ios-ck/issues)
2. 点击 "New Issue"
3. 说明问题详情，并提供：
   - 相关截图（如有）
   - 抓包信息（如有）
   - 复现步骤

### 提交 Pull Request

1. **Fork** 本仓库
2. 在本地进行修改（建议新建分支）
3. 提交 PR 并说明修改内容

#### 📝 命名规范

- 文件名使用 `PascalCase`（如 `FanFiction.txt`）
- 规则 tag 使用清晰的英文或拼音（如 `FanFiction`）

#### 📄 文件注释要求

在规则文件开头添加注释，说明规则用途和来源：

```plaintext
# ==========================================
# 规则名称：番茄小说
# 功能说明：去广告、解锁部分功能
# 来源：zqzess/rule_for_quantumultX
# 最后更新：2024-01-15
# ==========================================
```

### 规则审核标准

提交的规则需满足以下条件：

- ✅ 经过实际测试，功能正常
- ✅ 不误伤其他正常请求
- ✅ 优先使用域名规则（优于 IP 规则）
- ✅ 合并冗余规则，保持简洁
- ✅ 不违反各服务条款

---

## 📄 许可证

本仓库规则文件遵循上游仓库 [zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX) 的许可证。

---

## 🙏 致谢

- 原始规则作者：[zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX)

---

> ⭐ 如果本仓库对您有帮助，欢迎 **Star** 支持！


## 📊 同步状态

- **最后同步时间**：2026-09-01 08:50:55
- **重写规则**（去重后）：215 条
- **分流规则**（去重后）：95768 条
- **规则片段**（snippet）：5 个
- **规则文件总数**：28 个