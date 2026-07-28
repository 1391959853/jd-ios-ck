# Quantumult X 规则自动同步仓库

🎉 **欢迎加入共创！**

如果你有更好的规则（包括去广告、分流、重写等），或者发现现有规则有遗漏/错误，**非常欢迎提交 Pull Request 或 Issue**。让我们一起维护这个仓库，让它成为更可靠、更全面的 QX 规则参考。

---

## 📑 分支说明

| 分支 | 用途 | 核心文件 |
|:----:|------|:--------:|
| `main` | Quantumult X 去广告规则 | `qx.conf` |
| `X` | 京东 Cookie 自动化脚本 | `JDcookie.js` / `wskey-update.py` |

---
## 📦 项目说明

本仓库通过 GitHub Actions 每日自动同步自 **[zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX)** 的 `QuantumultX` 目录下的三个核心文件夹（`rewrite/`、`rules/`、`snippet/`）。

> **关于规则质量**：该源仓库的规则已由本人经过**大量时间实际测试**，尤其针对 **番茄小说（FanQieNovel）** 的去广告、请求拦截及重写规则，已反复验证其有效性与稳定性。因此选择此源作为基础，并持续跟进更新。

同步后，本仓库会自动生成 `/qx/README.md` 文件，清晰列出每个规则文件对应的 App 和规则条数，方便快速查找使用。

---

## 📂 目录结构
/qx/
├── rewrite/ # 重写规则（.qxrewrite）
├── rules/ # 分流/筛选规则（.list）
├── snippet/ # QX 规则配置片段（.snippet）
└── README.md # 规则文件详细说明

---

## 📊 同步状态

- **最后同步时间**：2026-07-28 11:34:22
- **重写规则**（去重后）：215 条
- **分流规则**（去重后）：95768 条
- **规则片段**（snippet）：5 个
- **规则文件总数**：28 个
## 🔧 使用方法

1. 将 `/qx/rewrite/` 下的 `.qxrewrite` 文件内容复制到 QX 的 `[rewrite_local]` 段落。
2. 将 `/qx/rules/` 下的 `.list` 文件内容复制到 QX 的 `[filter_local]` 段落。
3. 将 `/qx/snippet/` 下的 `.snippet` 文件作为规则片段引用（或按需使用）。

> 具体每个文件对应的 App，请查看 `/qx/README.md`。

---

## 🙏 致谢

本仓库规则来源于 [zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX)，感谢原作者的无私分享与持续维护。
